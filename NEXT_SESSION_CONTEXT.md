# Session Handover: Grafana & Metrics Infrastructure Optimization

## Overall Objective
The goal is to provide a robust, user-friendly benchmarking platform for AI factories. This involves:
1.  **Reliable Metrics Collection:** Ensuring metrics from compute nodes (GPU usage, power, etc.) are reliably transmitted to the central monitoring server, even across network boundaries (reverse tunnels).
2.  **Functional Frontend:** A Grafana dashboard that correctly accepts user inputs (like benchmark duration) and successfully communicates with the backend API (start/stop services) without CORS or DNS errors.

## Accomplishments in Previous Session

### 1. Backend Metrics Infrastructure (Completed)
- **Problem:** Metrics from compute nodes were lost or not reaching the Prometheus/Grafana server due to network isolation.
- **Solution:**
    -  Implemented **Pushgateway** integration in `services/server/src/service_orchestration/exporters/gpu_exporter.py`.
    -  Added a **buffering mechanism** to store metrics locally if Pushgateway is unreachable and retry later.
    -  Configured **reverse tunneling** in `services/server/src/ssh_manager.py` to forward local Pushgateway ports to the central server.
    -  Updated `services/prometheus/prometheus.yml` to scrape the Pushgateway.
- **Verification:** User confirmed metrics are now visible.

### 2. Frontend Connectivity Fix (Completed)
- **Problem:** API calls from the Grafana browser client (e.g., "Cancel Service") failed with `net::ERR_NAME_NOT_RESOLVED` because the browser cannot resolve the Docker container name `grafana` or backend service names.
- **Solution:**
    -  Updated `services/grafana/grafana.ini` to change `domain = grafana` to `domain = localhost`. Use `localhost` for client-side redirection and links.
- **Verification:** User implicitly confirmed success by moving to the next issue (duration bug).

### 3. "Start Benchmark" Duration Bug (Fixed & Deployed)
- **Problem:** The "Start Benchmark" panel in Grafana ignored the "Duration (min)" input, always defaulting to 60 seconds.
- **Root Cause:** The Volkov Labs Business Forms plugin was configured with `"payloadMode": "all"`. In this mode, the plugin sends the raw form values directly to the API, ignoring any custom JavaScript transformation logic in `getPayload` that converts minutes to seconds.
- **Fix Applied:**
    -  Modified `services/grafana/dashboards/src/administration/panels/03_start_benchmark.json`.
    -  Changed `"payloadMode"` from `"all"` to `"custom"`.
    -  Ensured `"sync": true` is set.
    -  Added extensive `console.log` statements in the `getPayload` function for debugging.
    -  Rebuilt the dashboard files (`python3 services/grafana/dashboards/build_dashboards.py`) and the Grafana container.

## Immediate Next Steps (Start Here)

### 1. Verification of Benchmark Duration
The fix has been deployed, but the user has not yet verified it in the browser.
- **Action:** Ask user to hard refresh the browser (Ctrl+Shift+R) and run a benchmark with `Duration: 5`.
- **Expected Outcome:** The backend logs should show a request with `duration_seconds: 300` (5 * 60).
- **Debugging:** If it fails, check the browser console (F12) for the `Benchmark payload:` logs added in the fix.

### 2. Verify "Service" Dropdown Logic
- There was a brief discussion about the "Service" dropdown in the administration panel. Ensure it correctly lists running services or services available for benchmarking.
- **File:** `services/grafana/dashboards/src/administration/panels/03_start_benchmark.json` (defines the elements) or the variables definition in the dashboard.

## Critical Files

### Frontend / Grafana
- `services/grafana/dashboards/src/administration/panels/03_start_benchmark.json`: The form definition. Contains the critical JavaScript logic for payload transformation.
- `services/grafana/grafana.ini`: Server configuration (domain, protocols).
- `services/grafana/dashboards/build_dashboards.py`: Script to generate the final JSON dashboard from source fragments.

### Backend / Metrics
- `services/server/src/api/routes.py`: API endpoint receiving the benchmark request.
- `services/server/src/service_orchestration/exporters/gpu_exporter.py`: Metric collection logic.
- `docker-compose.yml`: Defines the infrastructure stack.

## Strategy for Next Session
1.  **Confirm Fix:** Do not make new code changes until the duration fix is verified. If the duration is still 60s, the issue is likely browser caching or a syntax error in the JS within the JSON file.
2.  **Monitor Logs:** Use `docker logs -f benchmarking-ai-server` to see the incoming payload during the test.
3.  **Cleanup:** Once verified, remove the debugging `console.log` statements from `03_start_benchmark.json`.
