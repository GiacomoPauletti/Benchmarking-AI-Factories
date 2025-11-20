"""
Logs Service - Main FastAPI Application
Handles periodic log syncing from MeluXina and provides REST API for log access.
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from logging_setup import setup_logging
from ssh_manager import SSHManager
from log_categorizer import LogCategorizer


# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Configuration
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "60"))
REMOTE_BASE_PATH = os.getenv("REMOTE_BASE_PATH", "~/ai-factory-benchmarks")
DATA_DIR = Path("/app/data")
LOGS_DIR = DATA_DIR / "logs"
CATEGORIZED_DIR = DATA_DIR / "categorized"

# Global state
ssh_manager: Optional[SSHManager] = None
log_categorizer: Optional[LogCategorizer] = None
sync_task: Optional[asyncio.Task] = None
sync_running = False


class SyncStatus(BaseModel):
    """Status of the log sync service"""
    sync_enabled: bool
    last_sync_time: Optional[str] = None
    sync_interval_seconds: int
    total_syncs: int
    failed_syncs: int
    logs_directory: str
    categorized_directory: str


class LogFileInfo(BaseModel):
    """Information about a log file"""
    filename: str
    path: str
    size_bytes: int
    modified_time: str
    service: str


class ServiceStats(BaseModel):
    """Statistics for a service category"""
    service: str
    file_count: int
    total_size_bytes: int
    latest_modified: Optional[str]


# Sync statistics
sync_stats = {
    'total_syncs': 0,
    'failed_syncs': 0,
    'last_sync_time': None
}


async def periodic_sync():
    """Background task that periodically syncs and categorizes logs."""
    global sync_stats
    
    logger.info(f"Starting periodic log sync (interval: {SYNC_INTERVAL}s)")
    
    while sync_running:
        try:
            logger.info("Starting log sync cycle...")
            
            # Sync logs from remote
            if ssh_manager:
                remote_logs_path = f"{REMOTE_BASE_PATH}/logs/"
                success = ssh_manager.sync_remote_logs(
                    remote_logs_path=remote_logs_path,
                    local_logs_dir=LOGS_DIR,
                    delete=False,
                    dry_run=False
                )
                
                if success:
                    logger.info("Log sync completed successfully")
                    sync_stats['total_syncs'] += 1
                    
                    # Categorize logs
                    if log_categorizer:
                        logger.info("Categorizing logs...")
                        categories = log_categorizer.categorize_all_logs()
                        logger.info(f"Categorization complete: {categories}")
                else:
                    logger.warning("Log sync failed")
                    sync_stats['failed_syncs'] += 1
            else:
                logger.warning("SSH manager not initialized, skipping sync")
            
            # Update last sync time
            from datetime import datetime
            sync_stats['last_sync_time'] = datetime.now().isoformat()
            
        except Exception as e:
            logger.error(f"Error in sync cycle: {e}", exc_info=True)
            sync_stats['failed_syncs'] += 1
        
        # Wait for next sync interval
        await asyncio.sleep(SYNC_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    global ssh_manager, log_categorizer, sync_task, sync_running
    
    logger.info("Starting Logs Service...")
    
    # Create data directories
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CATEGORIZED_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize SSH manager
    try:
        ssh_manager = SSHManager()
        logger.info("SSH manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize SSH manager: {e}")
        ssh_manager = None
    
    # Initialize log categorizer
    log_categorizer = LogCategorizer(
        source_dir=LOGS_DIR,
        categorized_dir=CATEGORIZED_DIR
    )
    logger.info("Log categorizer initialized")
    
    # Start background sync task
    sync_running = True
    sync_task = asyncio.create_task(periodic_sync())
    logger.info("Background sync task started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Logs Service...")
    sync_running = False
    
    if sync_task:
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass
    
    if ssh_manager:
        ssh_manager.close_control_master()
    
    logger.info("Logs Service stopped")


# Create FastAPI app
app = FastAPI(
    title="Logs Service",
    description="Microservice for syncing and categorizing logs from MeluXina HPC",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "logs",
        "ssh_configured": ssh_manager is not None,
        "sync_running": sync_running
    }


@app.get("/status", response_model=SyncStatus)
async def get_sync_status():
    """Get current sync status and statistics."""
    return SyncStatus(
        sync_enabled=sync_running,
        last_sync_time=sync_stats['last_sync_time'],
        sync_interval_seconds=SYNC_INTERVAL,
        total_syncs=sync_stats['total_syncs'],
        failed_syncs=sync_stats['failed_syncs'],
        logs_directory=str(LOGS_DIR),
        categorized_directory=str(CATEGORIZED_DIR)
    )


@app.post("/sync/trigger")
async def trigger_sync():
    """Manually trigger a log sync operation."""
    if not ssh_manager:
        raise HTTPException(status_code=503, detail="SSH manager not initialized")
    
    try:
        logger.info("Manual sync triggered via API")
        
        # Sync logs
        remote_logs_path = f"{REMOTE_BASE_PATH}/logs/"
        success = ssh_manager.sync_remote_logs(
            remote_logs_path=remote_logs_path,
            local_logs_dir=LOGS_DIR,
            delete=False,
            dry_run=False
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Log sync failed")
        
        # Categorize logs
        if log_categorizer:
            categories = log_categorizer.categorize_all_logs()
        else:
            categories = {}
        
        # Update stats
        from datetime import datetime
        sync_stats['total_syncs'] += 1
        sync_stats['last_sync_time'] = datetime.now().isoformat()
        
        return {
            "status": "success",
            "message": "Log sync completed",
            "categories": categories
        }
    
    except Exception as e:
        logger.error(f"Manual sync failed: {e}", exc_info=True)
        sync_stats['failed_syncs'] += 1
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/services", response_model=List[str])
async def list_services():
    """List all available service categories."""
    if not log_categorizer:
        raise HTTPException(status_code=503, detail="Log categorizer not initialized")
    
    services = list(log_categorizer.SERVICE_PATTERNS.keys()) + ['uncategorized']
    return services


@app.get("/services/stats", response_model=Dict[str, ServiceStats])
async def get_service_stats():
    """Get statistics for all service categories."""
    if not log_categorizer:
        raise HTTPException(status_code=503, detail="Log categorizer not initialized")
    
    stats = log_categorizer.get_service_stats()
    
    return {
        service: ServiceStats(
            service=service,
            file_count=data['count'],
            total_size_bytes=data['total_size_bytes'],
            latest_modified=data['latest_modified']
        )
        for service, data in stats.items()
    }


@app.get("/logs", response_model=List[LogFileInfo])
async def list_logs(
    service: Optional[str] = Query(None, description="Filter by service name"),
    limit: Optional[int] = Query(50, description="Maximum number of files to return", ge=1, le=1000)
):
    """List available log files, optionally filtered by service."""
    if not log_categorizer:
        raise HTTPException(status_code=503, detail="Log categorizer not initialized")
    
    log_files = log_categorizer.get_categorized_logs(service=service, limit=limit)
    
    result = []
    for log_file in log_files:
        try:
            stat = log_file.stat()
            from datetime import datetime
            
            # Determine service from path
            if CATEGORIZED_DIR in log_file.parents:
                relative = log_file.relative_to(CATEGORIZED_DIR)
                service_name = relative.parts[0] if relative.parts else 'unknown'
            else:
                service_name = 'unknown'
            
            result.append(LogFileInfo(
                filename=log_file.name,
                path=str(log_file.relative_to(DATA_DIR)),
                size_bytes=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                service=service_name
            ))
        except Exception as e:
            logger.warning(f"Failed to get info for {log_file}: {e}")
    
    return result


@app.get("/logs/content")
async def get_log_content(
    path: str = Query(..., description="Relative path to log file"),
    tail: Optional[int] = Query(None, description="Return only last N lines", ge=1, le=10000)
):
    """Get content of a specific log file."""
    if not log_categorizer:
        raise HTTPException(status_code=503, detail="Log categorizer not initialized")
    
    # Construct full path
    log_path = DATA_DIR / path
    
    # Security check: ensure path is within DATA_DIR
    try:
        log_path = log_path.resolve()
        if not str(log_path).startswith(str(DATA_DIR.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")
    
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    if not log_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")
    
    content = log_categorizer.get_log_content(log_path, tail_lines=tail)
    
    return PlainTextResponse(content)


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Logs Service",
        "version": "1.0.0",
        "description": "Microservice for syncing and categorizing logs from MeluXina HPC",
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "trigger_sync": "/sync/trigger (POST)",
            "list_services": "/services",
            "service_stats": "/services/stats",
            "list_logs": "/logs",
            "log_content": "/logs/content"
        }
    }
