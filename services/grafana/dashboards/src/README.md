# Grafana Dashboards Source

This directory contains the source code for Grafana dashboards, split into modular components for easier maintenance.

## Structure

Each dashboard has its own directory (e.g., `administration`, `service`).
Inside each directory:
- `dashboard.json`: The base configuration of the dashboard (templating, annotations, etc.), excluding panels.
- `panels/`: A directory containing individual panel JSON files.

## Building Dashboards

To generate the final single-file JSON dashboards required by Grafana, run the build script:

```bash
python3 services/grafana/dashboards/build_dashboards.py
```

This script will:
1. Read the `dashboard.json` base.
2. Read all JSON files in `panels/` (sorted alphabetically).
3. Merge them into the `panels` array of the dashboard.
4. Save the result to `services/grafana/dashboards/<dashboard_name>.json`.

## Workflow

1. Edit the JSON files in `src/`.
2. Run `python3 services/grafana/dashboards/build_dashboards.py`.
3. Commit both the `src/` changes and the generated dashboards.
