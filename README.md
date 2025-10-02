# EU AI Factories benchmark project
EUMaster4HPC challenge a.y. 2025-2026

Objective: Develop a framework to evaluate performance of AI Factory components widely used, specifically in the context of the EU

# General structure
The project must run on the MeluXina supercomputer. The various components are:
 - A server: the server must take care of running the services that need to be benchmarked (databases, LLMs, etc.).
 - A client: the client must take care of testing the services that are being benchmarked (ex: running prompts, etc.).
 - A monitor: the monitor must take care of ingesting various metrics about both the running benchmarks' application and the underlying computer system, then store it into a Prometheus database for real-time and later analysis.
 - A log ingester: the log ingester must take care of ingesting the logs produced both by the running benchmark's application and the underlying infrastructure. It then stores it into a Grafana Loki database for real-time and later observability into the benchmarks.
 - A UI: the UI is based upon a Grafana dashboard. It fetches data from the logs' & metrics's respective databases, then displays it for analysis. During a benchmark, a live view is available. Post-mortem, aggregates & trends can also be viewed in dedicated pages. Logs are of course present in those views. Lastly, the UI must also be able to interact with the infrastructure to control it (startup and shutdown of the components, startup and shutdown of benchmarks).

To ease development, a microservice architecture has been chosen, where each part of the application is started as a separate process.

# Core modules
The various modules / processes that will be needed and their respective tasks is highlighted below:
 - Slurm: runs the various jobs on the physical MeluXina system. Controlled by the Server.
 - Server: interacts with Slurm via the REST API to start up services, and keep monitoring them. The process is developed by the team in Python.
 - Client: interacts with an AI server to benchmark it. The process is developed by the team in Spark.
 - Service monitor: runs with the service, and responsible for ingesting various metrics and sending it to Prometheus. Developed by the team in Python.
 - Prometheus: time-series database. Interface between the metrics ingesters and the UI. Configured by the team.
 - Service log ingester: runs with the service. Forwards the slurm logs to the Grafana Loki database. Developed by the team in Rust.
 - Grafana Loki: logs database. Interface between the log ingesters and the UI. Configured by the team.
 - Grafana: dashboard frontend. Configured & extended by the team.
 - K8s: to ease the deployment of the various components & to provide automatic restart, the infrastructure will be deployed in docker containers for a K8s setup.

# Interfaces between modules
The interface between the modules is as follow:
 - Service and client: service-dependent, depending on the benchmark. HTTP-based.
 - Service and monitor: through the linux system (proc, top, etc.)
 - Service and log ingester: through the filesystem (.out and .err files)
 - Server and Slurm: through the REST API
 - Server and monitor: through the linux system (proc, top, etc.) and through a custom REST API
 - Server and log ingester: through the filesystem (dedicated log files)
 - Monitor and Prometheus: through the REST API
 - Prometheus and Grafana: through the REST API; handled automatically by Grafana
 - Log ingester and Loki: through the REST API
 - Loki and Grafana: through the REST API; handled automatically by Grafana
