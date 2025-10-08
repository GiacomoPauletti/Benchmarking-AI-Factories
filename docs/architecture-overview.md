# Architecture Diagrams 

## End-user Experience Flow
1. User opens web dashboard in browser
2. User selects "Start New Benchmark Experiment"
3. User chooses:
   - AI Service: "vLLM Inference" 
   - Nodes: 4
   - Test Type: "Throughput Test"
   - Duration: 10 minutes
4. User clicks "Start"

Behind the scenes:
-> Web UI -> Server Service (deploy vLLM on 4 nodes)
-> Web UI -> Client Service (generate load against vLLM)  
-> Web UI -> Monitor Service (collect metrics)
-> Web UI -> Logs Service (capture logs)

5. User sees real-time dashboard with:
   - Service status
   - Performance graphs
   - Live metrics
   - Log streams

## Microservices Architecture
The end-user will have access to the UI on which his actions will trigger RESTs (via FastAPI backend) to the services we implemented, which will then deploy K8s pods. 

```mermaid
graph TB
    subgraph "Frontend"
        UI[Web Dashboard<br/>React + FastAPI]
    end

    subgraph "Microservices - All REST APIs"
        Server[Server Service<br/>Port 8000]
        Client[Client Service<br/>Port 8001]
        Monitor[Monitor Service<br/>Port 8002]
        Logs[Logs Service<br/>Port 8003]
    end

    subgraph "Infrastructure"
        K8s[Kubernetes Cluster<br/>MeluXina HPC]
    end

    %% Frontend to Services (REST calls)
    UI -->|HTTP REST| Server
    UI -->|HTTP REST| Client
    UI -->|HTTP REST| Monitor
    UI -->|HTTP REST| Logs

    %% Service-to-Service (REST calls)
    Client -->|GET /services| Server
    Monitor -->|GET /services| Server
    Logs -->|GET /services| Server
    
    %% Services to Infrastructure
    Server -->|K8s API| K8s
    Client -->|K8s API| K8s

    %% Simple styling
    classDef yourService fill:#e3f2fd,stroke:#1976d2,stroke-width:3px
    classDef service fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef frontend fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef infra fill:#e8f5e8,stroke:#388e3c,stroke-width:2px

    class Server yourService
    class Client,Monitor,Logs service
    class UI frontend
    class K8s infra
```





