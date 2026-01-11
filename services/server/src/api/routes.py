"""
API route definitions for SLURM-based service orchestration.
"""

import asyncio
import logging
import os
import time
import threading
from fastapi import APIRouter, HTTPException, Body, Depends, Query, Request
from typing import List, Dict, Any, Optional, Tuple

from api.schemas import ServiceRequest, ServiceResponse, RecipeResponse
from service_orchestration.services.inference.vllm_models_config import (
    get_architecture_info,
    search_hf_models,
    get_model_info as get_hf_model_info,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Keep recent service metrics around so a single slow scrape (common when vLLM is
# saturated by a benchmark run) doesn't result in a visible gap in Grafana.
#
# Prometheus considers a target "down" if the scrape fails/timeout, which shows
# as a discontinuity in Grafana panels. Returning the last-good metrics for a
# short window avoids gaps while still allowing detection of prolonged issues.
#
# Increased to 60s to better handle high-load scenarios where vLLM HTTP server
# is blocked during inference and cannot respond to metrics scrapes.
_SERVICE_METRICS_CACHE_TTL_SECONDS = float(
    os.environ.get("SERVICE_METRICS_CACHE_TTL_SECONDS", "60")
)
_SERVICE_METRICS_CACHE: Dict[str, Tuple[float, str]] = {}
_SERVICE_METRICS_CACHE_LOCK = threading.Lock()

# Background batch metrics fetcher configuration
# This fetcher proactively refreshes metrics cache to reduce SSH tunnel contention
_BATCH_METRICS_REFRESH_INTERVAL_SECONDS = float(
    os.environ.get("BATCH_METRICS_REFRESH_INTERVAL_SECONDS", "10")
)
_BATCH_METRICS_ENABLED = os.environ.get("BATCH_METRICS_ENABLED", "true").lower() == "true"
_batch_metrics_task: Optional[asyncio.Task] = None

# HuggingFace model options cache - avoid hitting HF API rate limits
# Cache for 1 hour (3600 seconds) by default
_HF_MODELS_CACHE_TTL_SECONDS = float(
    os.environ.get("HF_MODELS_CACHE_TTL_SECONDS", "3600")
)
_HF_MODELS_CACHE: Optional[Tuple[float, List[Dict[str, str]]]] = None

# Service targets cache - prevents gaps in Grafana when orchestrator is slow
# Cache targets for 30s to handle temporary communication issues
_SERVICE_TARGETS_CACHE_TTL_SECONDS = float(
    os.environ.get("SERVICE_TARGETS_CACHE_TTL_SECONDS", "30")
)
_SERVICE_TARGETS_CACHE: Optional[Tuple[float, List[Dict[str, Any]]]] = None


def _clear_service_metrics_cache() -> None:
    """Test helper to reset cached metrics between test cases."""
    with _SERVICE_METRICS_CACHE_LOCK:
        _SERVICE_METRICS_CACHE.clear()


def _parse_prometheus_scrape_timeout_seconds(request: Request) -> Optional[float]:
    """Extract Prometheus scrape timeout budget from request headers."""
    header_value = request.headers.get("X-Prometheus-Scrape-Timeout-Seconds")
    if not header_value:
        return None
    try:
        return float(header_value)
    except (TypeError, ValueError):
        return None

# Global orchestrator proxy instance (set by main.py at startup)
_orchestrator_proxy_instance = None

def set_orchestrator_proxy(proxy):
    """Set the global orchestrator proxy instance."""
    global _orchestrator_proxy_instance
    _orchestrator_proxy_instance = proxy

def get_orchestrator_proxy():
    """Dependency function to get the orchestrator proxy instance."""
    if _orchestrator_proxy_instance is None:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator not running. Start it via POST /api/v1/orchestrator/start"
        )
    return _orchestrator_proxy_instance


async def _batch_metrics_fetcher():
    """Background task that proactively fetches metrics for all services.
    
    This reduces SSH tunnel contention by:
    1. Making a single batch request instead of N individual requests
    2. Populating the cache so Prometheus scrapes hit cache instead of tunnel
    3. Running on a fixed interval independent of Prometheus scrape timing
    """
    logger.info("Background batch metrics fetcher started")
    
    while True:
        try:
            await asyncio.sleep(_BATCH_METRICS_REFRESH_INTERVAL_SECONDS)
            
            orchestrator = _orchestrator_proxy_instance
            if orchestrator is None:
                continue
            
            # Get service IDs to fetch - try to get from targets cache first,
            # otherwise fetch service groups directly from orchestrator
            service_ids = []
            
            cached_targets = _SERVICE_TARGETS_CACHE
            if cached_targets and cached_targets[1]:
                for target in cached_targets[1]:
                    labels = target.get("labels", {})
                    service_id = labels.get("service_id")
                    if service_id and service_id not in service_ids:
                        service_ids.append(service_id)
            
            # If no targets cached, try to get service groups directly
            if not service_ids:
                try:
                    groups = await asyncio.get_event_loop().run_in_executor(
                        None, orchestrator.list_service_groups
                    )
                    for group in (groups or []):
                        group_id = group.get("id")
                        if group_id and group_id not in service_ids:
                            service_ids.append(group_id)
                except Exception as e:
                    logger.debug(f"Batch metrics fetcher: failed to list service groups: {e}")
            
            if not service_ids:
                continue
            
            logger.info(f"Batch metrics fetcher: fetching metrics for {len(service_ids)} services: {service_ids}")
            
            # Fetch metrics in batch via orchestrator
            try:
                batch_results = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: orchestrator.get_batch_metrics(service_ids, timeout=5)
                )
                
                # Update cache with results
                now = time.monotonic()
                cached_count = 0
                with _SERVICE_METRICS_CACHE_LOCK:
                    for service_id, result in batch_results.items():
                        if result.get("success") and result.get("metrics"):
                            _SERVICE_METRICS_CACHE[service_id] = (now, result["metrics"])
                            cached_count += 1
                
                logger.info(f"Batch metrics fetcher: cached {cached_count}/{len(service_ids)} services")
                
            except Exception as e:
                logger.warning(f"Batch metrics fetcher: failed to fetch batch metrics: {e}")
                
        except asyncio.CancelledError:
            logger.info("Batch metrics fetcher cancelled")
            break
        except Exception as e:
            logger.error(f"Batch metrics fetcher error: {e}")
            # Continue running even on error


def start_batch_metrics_fetcher():
    """Start the background batch metrics fetcher task."""
    global _batch_metrics_task
    
    if not _BATCH_METRICS_ENABLED:
        logger.info("Batch metrics fetcher disabled via BATCH_METRICS_ENABLED=false")
        return
    
    if _batch_metrics_task is not None:
        logger.warning("Batch metrics fetcher already running")
        return
    
    try:
        loop = asyncio.get_event_loop()
        _batch_metrics_task = loop.create_task(_batch_metrics_fetcher())
        logger.info(f"Started batch metrics fetcher (interval: {_BATCH_METRICS_REFRESH_INTERVAL_SECONDS}s)")
    except Exception as e:
        logger.error(f"Failed to start batch metrics fetcher: {e}")


def stop_batch_metrics_fetcher():
    """Stop the background batch metrics fetcher task."""
    global _batch_metrics_task
    
    if _batch_metrics_task is not None:
        _batch_metrics_task.cancel()
        _batch_metrics_task = None
        logger.info("Stopped batch metrics fetcher")


@router.post("/services", response_model=ServiceResponse, summary="Create and start a new service")
async def create_service(
    request: ServiceRequest = Body(...,
        examples={
            "simple": {
                "summary": "Create a basic vLLM service",
                "value": {"recipe_name": "inference/vllm-single-node", "config": {"nodes": 1, "cpus": 2, "memory": "8G", "time": "00:30:00"}}
            }
        }
    ),
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Create and start a new service.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, parameters, and examples, see the orchestrator API documentation at:
    **POST /api/services/start** on the orchestrator service.
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        
        # Redact sensitive info from logs
        log_config = (request.config or {}).copy()
        if "environment" in log_config:
            env = log_config["environment"].copy()
            for key in ["HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"]:
                if key in env:
                    env[key] = "[REDACTED]"
            log_config["environment"] = env
            
        logger.info(f"[DEBUG] create_service received: recipe_name={request.recipe_name}, config={log_config}")
        response = orchestrator.start_service(
            recipe_name=request.recipe_name,
            config=request.config or {}
        )
        
        # Check for error responses from orchestrator
        if isinstance(response, dict) and response.get("status") == "error":
            raise HTTPException(status_code=500, detail=response.get("message", "Unknown error"))
        
        # Unwrap service_data if present (orchestrator returns {status, job_id, service_data})
        if "service_data" in response:
            return response["service_data"]
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services", response_model=List[ServiceResponse])
async def list_services(orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** List all services managed by the orchestrator.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, filtering options, and response schemas, see the orchestrator API documentation at:
    **GET /api/services** on the orchestrator service.
    """
    services = orchestrator.list_services()
    return services


@router.get("/services/targets")
async def get_service_targets():
    """Get Prometheus scrape targets for all managed services.

    This endpoint returns a list of Prometheus scrape targets for running services.
    This allows to dynamically configure Prometheus to monitor all services managed by this server.
    
    NOTE: This endpoint does NOT use the standard orchestrator dependency to allow
    returning cached targets when the orchestrator is temporarily unavailable.

    **Returns:**
    - Content-Type: `application/json`
    - Body: JSON object compatible with Prometheus file-based service discovery format

    **Example Response:**
    ```json
    [
      {
        "targets": ["mel0343:8002"],
        "labels": {
          "job": "service-3642874",
          "service_id": "3642874",
          "recipe_name": "inference/vllm-single-node"
        }
      },
      ...
    ]
    ```
    """
    global _SERVICE_TARGETS_CACHE
    now = time.monotonic()
    
    # Check orchestrator availability manually (not via Depends) to allow cache fallback
    orchestrator = _orchestrator_proxy_instance
    if orchestrator is None:
        # Orchestrator not running - return cached targets if available
        if _SERVICE_TARGETS_CACHE and (now - _SERVICE_TARGETS_CACHE[0]) <= _SERVICE_TARGETS_CACHE_TTL_SECONDS:
            logger.warning("Orchestrator not running, using cached targets")
            return _SERVICE_TARGETS_CACHE[1]
        # No cache available - return empty list (Prometheus will retry)
        logger.warning("Orchestrator not running and no cached targets available")
        return []
    
    try:
        targets = []
        # Add service groups first so they are discoverable immediately.
        # Prometheus should scrape ONLY the group_id for replica deployments.
        try:
            groups = orchestrator.list_service_groups() or []
        except Exception as e:
            logger.warning(f"Failed to list service groups: {e}")
            groups = []

        for group in groups:
            if not isinstance(group, dict):
                continue
            group_id = group.get("id")
            if not group_id:
                continue

            # Use a placeholder target; Prometheus address is rewritten to server:8001.
            targets.append({
                "targets": [f"pending-{group_id}"],
                "labels": {
                    "job": f"service-{group_id}",
                    "service_id": group_id,
                    "recipe_name": group.get("recipe_name", "unknown"),
                    "group_id": group_id,
                    "node_job_id": group_id.split("-", 1)[1] if isinstance(group_id, str) and group_id.startswith("sg-") else group_id,
                },
            })

        services_response = orchestrator.list_services()
        logger.debug(f"list_services() returned: {type(services_response)} = {repr(services_response)}")
        
        # Handle both dict response {'services': [...]} and list response [...]
        if isinstance(services_response, dict):
            services_list = services_response.get('services', [])
        else:
            services_list = services_response
        
        for service in services_list:
            try:
                discovered_id = service["id"]

                # For replica-group deployments, do not expose individual replica targets.
                # Replica IDs are composite "<job_id>:<port>".
                if isinstance(discovered_id, str) and ":" in discovered_id:
                    continue
                
                # Get full service details to resolve endpoint
                service_details = orchestrator.get_service(discovered_id)
                if not service_details:
                    continue
                
                # Include services early so the dashboard shows them immediately.
                # We keep terminal states too so they remain visible for a while.
                status = (service_details.get("status") or "").lower()
                allowed_statuses = {
                    "submitted",
                    "pending",
                    "building",
                    "starting",
                    "running",
                    "completed",
                    "failed",
                    "cancelled",
                    "unknown",
                }
                if status not in allowed_statuses:
                    continue
                
                # Extract endpoint - it's in format "http://host:port"
                endpoint = service_details.get("endpoint")
                if not endpoint:
                    # If pending, we might not have an endpoint yet.
                    # Use a placeholder so Prometheus still discovers it.
                    if status in ["submitted", "pending", "building", "starting", "unknown"]:
                        target = f"pending-{discovered_id}"
                    else:
                        continue
                else:
                    # Strip protocol to get "host:port" format for Prometheus
                    target = endpoint.replace("http://", "").replace("https://", "")

                # Replica/service-group labeling:
                # - Prometheus needs the raw identifier for __metrics_path__ substitution.
                # - Grafana needs stable grouping across all nodes of a replica group.
                # We add:
                #   group_id: replica group's id (or fallback to node job id for single services)
                #   replica_id: the raw identifier used for scraping (e.g. "<job>:<port>"), unique across nodes
                #   node_job_id: the SLURM job id portion (useful for legends)
                replica_id = discovered_id
                node_job_id = discovered_id.split(":", 1)[0] if ":" in discovered_id else discovered_id
                group_id = service_details.get("group_id") or service_details.get("id")
                if not group_id or not isinstance(group_id, str) or not group_id.strip():
                    group_id = node_job_id
                
                targets.append({
                    "targets": [target],
                    "labels": {
                        "job": f"service-{discovered_id}",
                        "service_id": discovered_id,
                        "recipe_name": service["recipe_name"],
                        "group_id": group_id,
                        "replica_id": replica_id,
                        "node_job_id": node_job_id,
                    }
                })
            except Exception as e:
                # Log but don't fail - continue processing other services
                logger.warning(f"Error processing service {service.get('id', 'unknown')}: {e}")
                continue
        
        # Update cache with successful result
        _SERVICE_TARGETS_CACHE = (now, targets)
        return targets
            
    except HTTPException:
        # Fall back to cached targets if available
        if _SERVICE_TARGETS_CACHE and (now - _SERVICE_TARGETS_CACHE[0]) <= _SERVICE_TARGETS_CACHE_TTL_SECONDS:
            logger.warning("Using cached targets due to HTTPException")
            return _SERVICE_TARGETS_CACHE[1]
        raise
    except Exception as e:
        # Fall back to cached targets if available
        if _SERVICE_TARGETS_CACHE and (now - _SERVICE_TARGETS_CACHE[0]) <= _SERVICE_TARGETS_CACHE_TTL_SECONDS:
            logger.warning(f"Using cached targets due to exception: {e}")
            return _SERVICE_TARGETS_CACHE[1]
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/{service_id}", response_model=ServiceResponse)
async def get_service(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get detailed information about a specific service or service group.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, response formats, and service/group detection logic, see the orchestrator API documentation at:
    **GET /api/services/{service_id}** on the orchestrator service.
    """
    service = orchestrator.get_service(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.get("/service-groups")
async def list_service_groups(orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** List all service groups.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, response format, and filtering options, see the orchestrator API documentation at:
    **GET /api/service-groups** on the orchestrator service.
    """
    try:
        groups = orchestrator.list_service_groups()
        return groups
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service-groups/{group_id}")
async def get_service_group(group_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get detailed information about a service group and all its replicas.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, replica information, and health status details, see the orchestrator API documentation at:
    **GET /api/service-groups/{group_id}** on the orchestrator service.
    """
    try:
        group_info = orchestrator.get_service_group(group_id)
        if not group_info:
            raise HTTPException(status_code=404, detail=f"Service group '{group_id}' not found")
        return group_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/service-groups/{group_id}")
async def stop_service_group(group_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Stop all replicas in a service group.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, response format, and error handling, see the orchestrator API documentation at:
    **DELETE /api/service-groups/{group_id}** on the orchestrator service.
    """
    try:
        result = orchestrator.stop_service_group(group_id)
        
        # Handle not found gracefully - if already stopped, return success
        if not result.get("success"):
            error_msg = result.get("error", "Service group not found")
            # If the group doesn't exist, it's already stopped - this is idempotent
            if "not found" in error_msg.lower():
                return {
                    "success": True,
                    "message": f"Service group {group_id} already stopped or does not exist",
                    "group_id": group_id,
                    "replicas_stopped": 0
                }
            # For other errors, return 500
            raise HTTPException(status_code=500, detail=error_msg)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service-groups/{group_id}/status")
async def get_service_group_status(group_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get aggregated status of a service group.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, status values, and health metrics, see the orchestrator API documentation at:
    **GET /api/service-groups/{group_id}/status** on the orchestrator service.
    """
    try:
        status_info = orchestrator.get_service_group_status(group_id)
        if not status_info:
            raise HTTPException(status_code=404, detail=f"Service group '{group_id}' not found")
        return status_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/service-groups/{group_id}/status")
async def update_service_group_status(
    group_id: str,
    status_update: Dict[str, str] = Body(..., examples={
        "cancel": {
            "summary": "Cancel a service group",
            "value": {"status": "cancelled"}
        }
    }),
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Update the status of a service group (primarily for cancelling).
    
    This endpoint proxies to the orchestrator's service group management API.
    Similar to single service status updates, this allows graceful cancellation
    of all replicas in a group while preserving metadata for analysis.
    
    For detailed documentation, see the orchestrator API documentation at:
    **POST /api/service-groups/{group_id}/status** on the orchestrator service.
    """
    new_status = status_update.get("status")
    
    if not new_status:
        raise HTTPException(status_code=400, detail="Missing 'status' field in request body")
    
    # Currently only support cancelling service groups
    if new_status == "cancelled":
        result = orchestrator.update_service_group_status(group_id, new_status)
        if not result.get("success"):
            error_msg = result.get("error", "Service group not found")
            if "not found" in error_msg.lower():
                raise HTTPException(status_code=404, detail=error_msg)
            else:
                raise HTTPException(status_code=500, detail=error_msg)
        return result
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported status value: '{new_status}'. Currently only 'cancelled' is supported."
        )


@router.get("/services/{service_id}/metrics")
async def get_service_metrics(
    service_id: str,
    request: Request,
    orchestrator=Depends(get_orchestrator_proxy),
):
    """**[Proxy]** Get Prometheus-compatible metrics from any service.
    
    This endpoint proxies to the orchestrator's unified metrics API.
    When batch metrics fetcher is enabled, this endpoint primarily serves
    from cache (populated by the background fetcher) to reduce SSH tunnel contention.
    
    For detailed documentation, supported service types, metric formats, and Prometheus integration examples, see the orchestrator API documentation at:
    **GET /api/services/{service_id}/metrics** on the orchestrator service.
    """
    from fastapi.responses import PlainTextResponse

    now = time.monotonic()
    
    # Check cache first - if we have fresh data, return it immediately
    # This is the primary path when batch metrics fetcher is running
    with _SERVICE_METRICS_CACHE_LOCK:
        cached = _SERVICE_METRICS_CACHE.get(service_id)
    
    # If cache is fresh (less than half TTL), return immediately without hitting tunnel
    # This drastically reduces SSH tunnel contention during Prometheus scrapes
    cache_fresh_threshold = _SERVICE_METRICS_CACHE_TTL_SECONDS / 2
    if cached and (now - cached[0]) <= cache_fresh_threshold:
        return PlainTextResponse(
            content=cached[1],
            media_type="text/plain; version=0.0.4",
        )

    # Prefer using Prometheus' declared scrape timeout as our total budget.
    # This prevents the proxy from blocking longer than Prometheus is willing
    # to wait, which would otherwise create gaps in Grafana.
    scrape_budget_seconds = _parse_prometheus_scrape_timeout_seconds(request)
    proxy_timeout_seconds: Optional[int]
    if scrape_budget_seconds is None:
        proxy_timeout_seconds = None
    else:
        # Keep a small safety margin so we can still return a cached response.
        # Round down to ensure we stay within the declared budget.
        safe_budget = max(1.0, scrape_budget_seconds - 0.25)
        proxy_timeout_seconds = max(1, int(safe_budget))

    try:
        # Route to appropriate service-specific metrics endpoint
        if proxy_timeout_seconds is None:
            result = orchestrator.get_service_metrics(service_id)
        else:
            result = orchestrator.get_service_metrics(service_id, timeout=proxy_timeout_seconds)

        metrics_text: Optional[str] = None

        if isinstance(result, dict):
            if result.get("success"):
                metrics_text = result.get("metrics", "")
            else:
                # Orchestrator returned a structured failure
                error_msg = result.get("error", "Unknown error fetching metrics")
                raise HTTPException(status_code=500, detail=error_msg)
        elif isinstance(result, (str, bytes)):
            metrics_text = result.decode("utf-8", errors="replace") if isinstance(result, bytes) else result
        else:
            metrics_text = str(result)

        with _SERVICE_METRICS_CACHE_LOCK:
            _SERVICE_METRICS_CACHE[service_id] = (now, metrics_text)
        return PlainTextResponse(
            content=metrics_text,
            media_type="text/plain; version=0.0.4",
        )

    except HTTPException:
        # Fall back to cached metrics for a short window, otherwise bubble up.
        if cached and (now - cached[0]) <= _SERVICE_METRICS_CACHE_TTL_SECONDS:
            cached_text = cached[1]
            cached_text = (
                cached_text
                + f"\nservice_metrics_proxy_stale{{service_id=\"{service_id}\"}} 1\n"
            )
            return PlainTextResponse(
                content=cached_text,
                media_type="text/plain; version=0.0.4",
            )
        raise
    except Exception as e:
        if cached and (now - cached[0]) <= _SERVICE_METRICS_CACHE_TTL_SECONDS:
            cached_text = cached[1]
            cached_text = (
                cached_text
                + f"\nservice_metrics_proxy_stale{{service_id=\"{service_id}\"}} 1\n"
            )
            return PlainTextResponse(
                content=cached_text,
                media_type="text/plain; version=0.0.4",
            )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/services/{service_id}")
async def stop_service(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** DEPRECATED - Stop a service (use POST /services/{service_id}/status instead).
    
    This endpoint proxies to the orchestrator's service stop API.
    
    **DEPRECATION NOTICE:** Use POST /services/{service_id}/status with {"status": "cancelled"} instead.
    
    For detailed documentation and recommended alternatives, see the orchestrator API documentation at:
    **POST /api/services/stop/{service_id}** on the orchestrator service.
    """
    success = orchestrator.stop_service(service_id)
    if success:
        return {"message": f"Service {service_id} stopped successfully"}
    else:
        raise HTTPException(status_code=404, detail="Service not found or failed to stop")


@router.get("/services/{service_id}/logs")
async def get_service_logs(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get SLURM logs (stdout and stderr) from a service.
    
    This endpoint proxies to the orchestrator's service logs API.
    
    For detailed documentation, log format descriptions, and troubleshooting tips, see the orchestrator API documentation at:
    **GET /api/services/{service_id}/logs** on the orchestrator service.
    """
    return orchestrator.get_service_logs(service_id)


@router.get("/services/{service_id}/status")
async def get_service_status(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get the current detailed status of a service.
    
    This endpoint proxies to the orchestrator's service status API.
    
    For detailed documentation, status values, and initialization stages, see the orchestrator API documentation at:
    **GET /api/services/{service_id}/status** on the orchestrator service.
    """
    return orchestrator.get_service_status(service_id)


@router.post("/services/{service_id}/status")
async def update_service_status(
    service_id: str,
    status_update: Dict[str, str] = Body(..., examples={
        "cancel": {
            "summary": "Cancel a running service",
            "value": {"status": "cancelled"}
        }
    }),
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Update the status of a service (primarily for cancelling).
    
    This endpoint proxies to the orchestrator's service status update API.
    
    For detailed documentation, supported status values, state transitions, and examples, see the orchestrator API documentation at:
    **POST /api/services/{service_id}/status** (or equivalent) on the orchestrator service.
    """
    new_status = status_update.get("status")
    
    if not new_status:
        raise HTTPException(status_code=400, detail="Missing 'status' field in request body")
    
    # Currently only support cancelling services
    if new_status == "cancelled":
        # If the ID refers to a service group, cancel the whole group.
        try:
            group_info = orchestrator.get_service_group(service_id)
        except Exception:
            group_info = None

        if group_info:
            try:
                result = orchestrator.update_service_group_status(service_id, new_status)
                if not result or not result.get("success", True):
                    # Some orchestrators return {success: false, error: ...}
                    raise HTTPException(status_code=500, detail=result.get("error", "Failed to cancel service group"))
                return {
                    "message": f"Service group {service_id} status updated to {new_status}",
                    "service_id": service_id,
                    "status": new_status
                }
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=f"Service group not found or failed to cancel: {e}")

        # Otherwise, cancel a single service.
        try:
            orchestrator.stop_service(service_id)
            return {
                "message": f"Service {service_id} status updated to {new_status}",
                "service_id": service_id,
                "status": new_status
            }
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Service not found or failed to stop: {e}")
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported status value: '{new_status}'. Currently only 'cancelled' is supported."
        )


def get_orchestrator_proxy_optional():
    """Dependency function that returns the orchestrator proxy or None."""
    return _orchestrator_proxy_instance


@router.get("/recipes")
async def list_or_get_recipe(
    path: Optional[str] = None,
    name: Optional[str] = None,
    orchestrator = Depends(get_orchestrator_proxy_optional)
):
    """**[Proxy]** List all available recipes OR get a specific recipe.
    
    This endpoint proxies to the orchestrator's recipe management API.
    Returns empty list if orchestrator is not running.
    
    For detailed documentation, query parameters, recipe structure, and examples, see the orchestrator API documentation at:
    **GET /api/recipes** on the orchestrator service.
    """
    if orchestrator is None:
        # Return empty list when orchestrator is not running
        # This allows Grafana panels to show "No data" instead of error
        return []
    
    recipes = orchestrator.list_available_recipes()
    
    # If no search criteria provided, return all recipes
    if not path and not name:
        return recipes
    
    # Otherwise, find specific recipe by path or name
    recipe = None
    for r in recipes:
        if (path and r.get("path") == path) or (name and r.get("name") == name):
            recipe = r
            break
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.get("/vllm/services")
async def list_vllm_services(orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** List all running vLLM inference services with their endpoints.
    
    This endpoint proxies to the orchestrator's vLLM service discovery API.
    
    For detailed documentation, endpoint resolution, and service status meanings, see the orchestrator API documentation at:
    **GET /api/vllm** (or /api/data-plane/vllm) on the orchestrator service.
    """
    try:
        vllm_services = orchestrator.find_vllm_services()
        return {"vllm_services": vllm_services}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/available-models")
async def list_available_vllm_models():
    """Get information about models that can be used with vLLM.

    This endpoint provides information about vLLM's supported model architectures
    and how to find compatible models from HuggingFace Hub. Unlike a hardcoded model list,
    this returns architectural compatibility information since vLLM can load ANY model
    from HuggingFace Hub that uses a supported architecture.

    **Key Information:**
    - **Model Source**: All models are downloaded from HuggingFace Hub (https://huggingface.co/models)
    - **Compatibility**: Based on model architecture, not specific model names
    - **How to Use**: Provide any HuggingFace model ID in the `VLLM_MODEL` environment variable
    - **Format**: `organization/model-name` (e.g., `meta-llama/Llama-2-7b-chat-hf`)

    **Returns:**
    ```json
    {
      "model_source": "HuggingFace Hub",
      "supported_architectures": {
        "text-generation": ["LlamaForCausalLM", "MistralForCausalLM", ...],
        "vision-language": ["LlavaForConditionalGeneration", ...],
        "embedding": ["BertModel", ...]
      },
      "examples": {
        "GPT-2 (small, for testing)": "gpt2",
        "Llama 2 7B Chat": "meta-llama/Llama-2-7b-chat-hf",
        "Qwen 2.5 0.5B Instruct": "Qwen/Qwen2.5-0.5B-Instruct",
        ...
      },
      "how_to_find_models": [
        "Browse HuggingFace: https://huggingface.co/models?pipeline_tag=text-generation",
        "Check model card for architecture",
        ...
      ],
      "resource_guidelines": {
        "small_models": {
          "size_range": "< 1B parameters",
          "min_gpu_memory_gb": 4,
          ...
        },
        ...
      }
    }
    ```

    **How to Find Compatible Models:**
    1. Browse HuggingFace: https://huggingface.co/models?pipeline_tag=text-generation
    2. Check the model's architecture in its `config.json` file
    3. Verify the architecture is in vLLM's supported list (returned by this endpoint)
    4. Use the model ID when creating a vLLM service

    **Example Usage:**

    First, query this endpoint to see supported architectures and examples:
    ```bash
    curl http://localhost:8001/vllm/available-models
    ```

    Then create a service with any compatible model:
    ```json
    {
      "recipe_name": "inference/vllm-single-node",
      "config": {
        "environment": {
          "VLLM_MODEL": "Qwen/Qwen2.5-7B-Instruct"
        }
      }
    }
    ```

    **Resource Planning:**
    Use the `resource_guidelines` section to estimate GPU memory requirements based on model size.
    Larger models may require multiple GPUs using tensor parallelism.

    **Authentication:**
    Some models (e.g., Llama 2, Llama 3) require HuggingFace authentication.
    You'll need to set up HuggingFace credentials before deploying these models.
    """
    try:
        info = get_architecture_info()
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/model-options")
def get_vllm_model_options():
    """Get vLLM model options formatted for Grafana dropdown.
    
    Returns an array of label/value pairs suitable for use in Grafana Form Panel dropdowns.
    Each entry contains a human-readable label and the corresponding HuggingFace model ID.
    
    Results are cached for 1 hour (configurable via HF_MODELS_CACHE_TTL_SECONDS env var)
    to avoid hitting HuggingFace API rate limits.
    
    **Returns:**
    ```json
    [
      {"label": "GPT-2 (small, for testing)", "value": "gpt2"},
      {"label": "Llama 2 7B Chat", "value": "meta-llama/Llama-2-7b-chat-hf"},
      ...
    ]
    ```
    """
    global _HF_MODELS_CACHE
    
    try:
        # Check if we have a valid cached response
        now = time.time()
        if _HF_MODELS_CACHE is not None:
            cache_time, cached_options = _HF_MODELS_CACHE
            if now - cache_time < _HF_MODELS_CACHE_TTL_SECONDS:
                logger.debug(f"Returning cached HF models (age: {now - cache_time:.0f}s)")
                return cached_options
        
        options = []
        
        # Always include a small model for testing
        options.append({
            "label": "GPT-2 (Small, for testing)",
            "value": "gpt2"
        })
        
        # Fetch popular models from HuggingFace
        try:
            # Use a reasonable limit to keep response size manageable but useful
            hf_models = search_hf_models(limit=100, sort_by="downloads")
            
            for model in hf_models:
                # Skip gpt2 if it comes back in search to avoid duplicate
                if model["id"] == "gpt2":
                    continue
                    
                options.append({
                    "label": f"{model['id']} ({model.get('downloads', 0)} downloads)",
                    "value": model["id"]
                })
            
            logger.info(f"Fetched {len(options)} models from HuggingFace, caching for {_HF_MODELS_CACHE_TTL_SECONDS}s")
        except Exception as e:
            logger.warning(f"Failed to fetch dynamic models from HF: {e}")
            # Fallback to static examples if HF fetch fails
            info = get_architecture_info()
            examples = info.get("examples", {})
            # Filter out gpt2 since we added it manually
            for label, value in examples.items():
                if value != "gpt2":
                    options.append({"label": label, "value": value})
        
        # Cache the result
        _HF_MODELS_CACHE = (now, options)
        return options
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/search-models")
async def search_vllm_models(
    query: Optional[str] = Query(None, description="Search query (e.g., 'llama', 'mistral', 'qwen')"),
    architecture: Optional[str] = Query(None, description="Filter by architecture (e.g., 'LlamaForCausalLM')"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results (1-100)"),
    sort_by: str = Query("downloads", description="Sort by: downloads, likes, trending, created_at")
):
    """Search HuggingFace Hub for models compatible with vLLM.

    This endpoint queries the HuggingFace Hub API to find models that match your search criteria
    and checks their compatibility with vLLM's supported architectures.

    **Query Parameters:**
    - `query`: Search string (e.g., "llama", "mistral", "qwen", "instruct")
    - `architecture`: Filter by specific architecture class name
    - `limit`: Maximum results to return (1-100, default: 20)
    - `sort_by`: Sort order - "downloads", "likes", "trending", or "created_at"

    **Returns:**
    ```json
    {
      "models": [
        {
          "id": "meta-llama/Llama-2-7b-chat-hf",
          "downloads": 1500000,
          "likes": 5000,
          "architecture": "LlamaForCausalLM",
          "vllm_compatible": true,
          "created_at": "2023-07-18T...",
          "tags": ["llama", "text-generation", "conversational"]
        },
        ...
      ],
      "total": 20
    }
    ```

    **Example Searches:**

    Find popular Llama models:
    ```
    GET /vllm/search-models?query=llama&sort_by=downloads&limit=10
    ```

    Find Qwen instruction models:
    ```
    GET /vllm/search-models?query=qwen+instruct&limit=15
    ```

    Find all models with specific architecture:
    ```
    GET /vllm/search-models?architecture=MistralForCausalLM
    ```

    **Use Case:**
    Use this to discover new models before creating a vLLM service. The `vllm_compatible`
    field indicates whether the model uses an architecture supported by vLLM.
    """
    try:
        models = search_hf_models(
            query=query,
            architecture=architecture,
            limit=limit,
            sort_by=sort_by
        )
        return {
            "models": models,
            "total": len(models)
        }
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/model-info/{model_id:path}")
async def get_model_info(model_id: str):
    """Get detailed information about a specific model from HuggingFace Hub.

    This endpoint fetches comprehensive information about a model including its architecture,
    size, compatibility with vLLM, and download statistics.

    **Path Parameters:**
    - `model_id`: HuggingFace model ID (e.g., "meta-llama/Llama-2-7b-hf", "Qwen/Qwen2.5-3B-Instruct")

    **Returns:**
    ```json
    {
      "id": "Qwen/Qwen2.5-3B-Instruct",
      "architecture": "Qwen2ForCausalLM",
      "vllm_compatible": true,
      "task_type": "text-generation",
      "downloads": 250000,
      "likes": 1200,
      "tags": ["qwen2", "instruct", "chat"],
      "size_bytes": 6442450944,
      "size_gb": 6.0,
      "pipeline_tag": "text-generation",
      "library_name": "transformers"
    }
    ```

    **Fields:**
    - `vllm_compatible`: Whether this model can be loaded by vLLM
    - `task_type`: Type of task (text-generation, vision-language, embedding)
    - `size_gb`: Approximate model size in gigabytes
    - `architecture`: The model's architecture class

    **Example Usage:**

    Check if a model is compatible before deployment:
    ```bash
    curl http://localhost:8001/vllm/model-info/Qwen/Qwen2.5-7B-Instruct
    ```

    Then use the model ID to create a service:
    ```json
    {
      "recipe_name": "inference/vllm-single-node",
      "config": {
        "environment": {
          "VLLM_MODEL": "Qwen/Qwen2.5-7B-Instruct"
        }
      }
    }
    ```

    **Note:** Some models require HuggingFace authentication. Check the model page on
    HuggingFace Hub if you encounter access errors.
    """
    try:
        model_info = get_hf_model_info(model_id)
        return model_info
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )
    except Exception as e:
        # Could be 404 if model doesn't exist, or other HF API errors
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found or error accessing HuggingFace Hub: {str(e)}"
        )


@router.get("/vector-db/services")
async def list_vector_db_services(orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** List all running vector database services.
    
    This endpoint proxies to the orchestrator's vector database service discovery API.
    
    For detailed documentation, supported vector databases, and endpoint formats, see the orchestrator API documentation at:
    **GET /api/vector-db** (or /api/data-plane/vector-db) on the orchestrator service.
    """
    try:
        vector_db_services = orchestrator.find_vector_db_services()
        return {"vector_db_services": vector_db_services}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector-db/{service_id}/collections")
async def get_collections(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get list of collections from a vector database service.
    
    This endpoint proxies to the orchestrator's vector database collections API.
    
    For detailed documentation, supported operations, and response formats, see the orchestrator API documentation at:
    **GET /api/vector-db/{service_id}/collections** on the orchestrator service.
    """
    try:
        result = orchestrator.get_collections(service_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector-db/{service_id}/collections/{collection_name}")
async def get_collection_info(
    service_id: str,
    collection_name: str,
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Get detailed information about a specific collection.
    
    This endpoint proxies to the orchestrator's collection info API.
    
    For detailed documentation, collection metadata formats, and vector configuration details, see the orchestrator API documentation at:
    **GET /api/vector-db/{service_id}/collections/{collection_name}** on the orchestrator service.
    """
    try:
        result = orchestrator.get_collection_info(service_id, collection_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/vector-db/{service_id}/collections/{collection_name}")
async def create_collection(
    service_id: str,
    collection_name: str,
    request: Dict[str, Any] = Body(..., examples={
        "basic": {
            "summary": "Create a basic collection",
            "value": {"vector_size": 384, "distance": "Cosine"}
        },
        "euclidean": {
            "summary": "Create collection with Euclidean distance",
            "value": {"vector_size": 768, "distance": "Euclid"}
        }
    }),
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Create a new collection in the vector database.
    
    This endpoint proxies to the orchestrator's collection creation API.
    
    For detailed documentation, vector size configuration, distance metrics, and examples, see the orchestrator API documentation at:
    **PUT /api/vector-db/{service_id}/collections/{collection_name}** on the orchestrator service.
    """
    try:
        vector_size = request.get("vector_size")
        if not vector_size:
            raise HTTPException(status_code=400, detail="vector_size is required")
        
        distance = request.get("distance", "Cosine")
        result = orchestrator.create_collection(service_id, collection_name, vector_size, distance)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/vector-db/{service_id}/collections/{collection_name}")
async def delete_collection(
    service_id: str,
    collection_name: str,
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Delete a collection from the vector database.
    
    This endpoint proxies to the orchestrator's collection deletion API.
    
    For detailed documentation, operation details, and error handling, see the orchestrator API documentation at:
    **DELETE /api/vector-db/{service_id}/collections/{collection_name}** on the orchestrator service.
    """
    try:
        result = orchestrator.delete_collection(service_id, collection_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/vector-db/{service_id}/collections/{collection_name}/points")
async def upsert_points(
    service_id: str,
    collection_name: str,
    request: Dict[str, Any] = Body(..., examples={
        "simple": {
            "summary": "Insert a single point",
            "value": {
                "points": [
                    {
                        "id": 1,
                        "vector": [0.1, 0.2, 0.3, 0.4],
                        "payload": {"text": "Example document"}
                    }
                ]
            }
        },
        "multiple": {
            "summary": "Insert multiple points",
            "value": {
                "points": [
                    {"id": 1, "vector": [0.1, 0.2, 0.3], "payload": {"text": "First doc"}},
                    {"id": 2, "vector": [0.4, 0.5, 0.6], "payload": {"text": "Second doc"}}
                ]
            }
        }
    }),
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Insert or update points (vectors with payloads) in a collection.
    
    This endpoint proxies to the orchestrator's vector upsert API.
    
    For detailed documentation, point formats, payload structures, and batch operations, see the orchestrator API documentation at:
    **PUT /api/vector-db/{service_id}/collections/{collection_name}/points** on the orchestrator service.
    """
    try:
        points = request.get("points")
        if not points or not isinstance(points, list):
            raise HTTPException(status_code=400, detail="points must be a non-empty list")
        
        result = orchestrator.upsert_points(service_id, collection_name, points)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vector-db/{service_id}/collections/{collection_name}/points/search")
async def search_points(
    service_id: str,
    collection_name: str,
    request: Dict[str, Any] = Body(..., examples={
        "basic": {
            "summary": "Basic similarity search",
            "value": {
                "query_vector": [0.1, 0.2, 0.3, 0.4],
                "limit": 5
            }
        }
    }),
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Search for similar vectors in a collection.
    
    This endpoint proxies to the orchestrator's vector search API.
    
    For detailed documentation, query parameters, scoring methods, and filtering options, see the orchestrator API documentation at:
    **POST /api/vector-db/{service_id}/collections/{collection_name}/points/search** on the orchestrator service.
    """
    try:
        query_vector = request.get("query_vector")
        if not query_vector or not isinstance(query_vector, list):
            raise HTTPException(status_code=400, detail="query_vector must be a non-empty list")
        
        limit = request.get("limit", 10)
        result = orchestrator.search_points(service_id, collection_name, query_vector, limit)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orchestrator/endpoint")
async def get_orchestrator_endpoint(orchestrator = Depends(get_orchestrator_proxy)):
    """Get the internal endpoint of the orchestrator service.
    
    This endpoint returns the internal URL of the orchestrator running on the compute node.
    Clients can use this to communicate directly with the orchestrator if needed.
    
    **Returns:**
    ```json
    {
      "endpoint": "http://mel1234:8003"
    }
    ```
    """
    endpoint = orchestrator.get_orchestrator_url()
    if not endpoint:
        raise HTTPException(status_code=404, detail="Orchestrator endpoint not available")
    return {"endpoint": endpoint}


@router.post("/vllm/{service_id}/prompt", summary="Send a prompt to a running vLLM service")
async def prompt_vllm_service(
    service_id: str,
    request: Dict[str, Any] = Body(..., examples={
        "simple": {
            "summary": "Basic prompt",
            "value": {"prompt": "Write a short haiku about AI."}
        },
        "with_model": {
            "summary": "Prompt specifying model",
            "value": {"prompt": "Hello", "model": "gpt2", "max_tokens": 64}
        }
    }),
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Send a text prompt to a running vLLM inference service.
    
    This endpoint proxies to the orchestrator's vLLM prompt API.
    
    For detailed documentation, request parameters, response formats, and examples, see the orchestrator API documentation at:
    **POST /api/vllm/{service_id}/prompt** (or /api/data-plane/vllm/{service_id}/prompt) on the orchestrator service.
    """
    try:
        prompt = request.get("prompt")
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")

        # Extract optional parameters
        kwargs = {
            "max_tokens": request.get("max_tokens", 150),
            "temperature": request.get("temperature", 0.7),
            "model": request.get("model")
        }
        # Remove None values
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        result = orchestrator.prompt_vllm_service(service_id, prompt, **kwargs)
        return result
    except HTTPException:
        # Re-raise HTTPExceptions (like our 400 error) without wrapping them
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/{service_id}/models")
async def get_vllm_models(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get the list of models served by a running vLLM service.
    
    This endpoint proxies to the orchestrator's vLLM model discovery API.
    
    For detailed documentation, model formats, and service status handling, see the orchestrator API documentation at:
    **GET /api/vllm/{service_id}/models** (or /api/data-plane/vllm/{service_id}/models) on the orchestrator service.
    """
    try:
        result = orchestrator.get_vllm_models(service_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{service_id}")
async def get_service_metrics_generic(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """Get Prometheus metrics from any service (generic endpoint).
    
    This is a unified metrics endpoint that automatically routes to the appropriate
    service-specific metrics endpoint based on the service's recipe type.
    
    **Path Parameters:**
    - `service_id`: The SLURM job ID or service group ID of the service
    
    **Returns (Success):**
    - Content-Type: `text/plain; version=0.0.4`
    - Body: Prometheus text format metrics
    
    **Returns (Error):**
    - Content-Type: `application/json`
    - Body: JSON error object with details
    
    **Examples:**
    ```bash
    # Get metrics from any service
    curl http://localhost:8001/api/v1/metrics/3642874
    ```
    
    **Integration with Prometheus:**
    ```yaml
    scrape_configs:
      - job_name: 'managed-services'
        static_configs:
          - targets: ['server:8001']
        metrics_path: '/api/v1/metrics/<service_id>'
        scrape_interval: 15s
    ```
    
    **Note:** This endpoint determines the service type automatically and routes
    to the appropriate metrics fetcher (vLLM, Qdrant, etc.).
    """
    from fastapi.responses import PlainTextResponse
    
    try:
        # Delegate to orchestrator which will handle service type detection
        result = orchestrator.get_service_metrics(service_id)
        
        # If successful, return metrics as plain text
        if result.get("success"):
            return PlainTextResponse(
                content=result.get("metrics", ""),
                media_type="text/plain; version=0.0.4"
            )
        else:
            # Return error as JSON
            error = result.get("error", "Unknown error")
            status_code = result.get("status_code", 500)
            raise HTTPException(status_code=status_code, detail=error)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
