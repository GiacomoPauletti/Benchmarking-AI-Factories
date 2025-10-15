The classes assume we can schedule Prometheus in a partition that’s reachable as --prom-host (e.g., a login/utility node). If Prometheus runs on a compute node that isn’t reachable from where we run the CLI, set --prom-host accordingly (fixed hostname).

# 0) ensure packages
touch services/__init__.py services/monitoring/__init__.py

# 1) create session
python -m services.monitoring.cli session-create --run-id test1 --prom-host localhost --port 9090

# 2) register one client node with exporters (optional; can be None)
python -m services.monitoring.cli client-connect --session test1 --client-id c1 --node nodeA \
  --node-exporter nodeA:9100 --dcgm-exporter nodeA:9400

# 3) register a service endpoint (e.g., Triton metrics)
python -m services.monitoring.cli service-register --session test1 --client-id c1 \
  --name triton --endpoint http://nodeA:8000/metrics

# 4) start Prometheus (put it on a partition you can reach)
python -m services.monitoring.cli start --session test1 --partition login

# 5) status
python -m services.monitoring.cli status --session test1

# 6) collect a 10-minute window
python -m services.monitoring.cli collect --session test1 \
  --from-iso "2025-10-01T10:00:00Z" --to-iso "2025-10-01T10:10:00Z" \
  --out results/metrics --run-id run01

# 7) stop and delete
python -m services.monitoring.cli stop --session test1
python -m services.monitoring.cli delete --session test1
