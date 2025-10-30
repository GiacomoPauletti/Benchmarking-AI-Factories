````markdown
# AI Factory Client Services - Architecture Guide

## 🏗️ Architectural Overview

The AI Factory Client Services system implements a distributed microservices architecture designed for scalable management of AI benchmarks on HPC infrastructures. The architecture is organized into three main layers that ensure separation of responsibilities and horizontal scalability.

## 📊 Architectural Diagram

```mermaid
graph TB
    subgraph "Frontend Layer"
        FE[Frontend/CLI] --> CS[Client Service]
    end
    
    subgraph "Service Layer"
        CS --> CM[Client Manager]
        CS --> FR[Frontend Router]
        CS --> CR[Client Router]
        CS --> MR[Monitor Router]
        
        CM --> CG[Client Group]
        CM --> SCD[Slurm Client Dispatcher]
    end
    
    subgraph "Client Layer"
        SCD --> SJ[Slurm Jobs]
        SJ --> CP[Client Processes]
        CP --> VC[VLLM Clients]
        CP --> CG2[Local Client Group]
        CP --> CO[Client Observer]
    end
    
    subgraph "Infrastructure Layer"
        SCD --> SLURM[Slurm Cluster]
        VC --> AS[AI Server]
        CS --> MON[Monitoring Service]
    end
    
    subgraph "Storage Layer"
        CM --> CFG[Configuration]
        SCD --> JWT[JWT Tokens]
        CS --> LOGS[Logs]
    end
```

## 🎯 Main Components

### 1. Service Layer (Client Service)

The service layer is the central orchestration point of the system.

#### ClientManager (Singleton)
```python
class ClientManager:
    """Manages client groups and coordinates Slurm deployment"""
    
    # Responsibilities:
    # - Client group lifecycle management
    # - Coordination with Slurm scheduler
    # - Proxy requests to client processes
    # - Configuration management
```

**Key Features:**
- **Singleton Pattern**: Single instance per service
- **Thread Safety**: Safe handling of concurrent requests  
- **State Management**: benchmark_id → Client Group mapping
- **Slurm Integration**: Automatic job dispatch

#### Frontend Router
Exposes REST APIs for system management:

```yaml
Endpoints:
  POST /api/v1/client-group/{id}:
    description: Create new client group
    payload: {num_clients: int, time_limit: int}
    
  GET /api/v1/client-group/{id}:
    description: Get client group info
    
  DELETE /api/v1/client-group/{id}:
    description: Remove client group
    
  POST /api/v1/client-group/{id}/run:
    description: Start benchmark execution
```

#### Client Router
Manages client process registration:

```yaml
Endpoints:
  POST /api/v1/client-group/{id}/connect:
    description: Register client process
    payload: {client_address: string}
```

### 2. Client Layer (Client Processes)

The client layer executes actual benchmarks on compute nodes.

#### VLLMClient
```python
class VLLMClient:
    """Specialized client for vLLM services"""
    
    # Shared static variables:
    _service_id: str = None      # vLLM service ID
    _server_base_url: str = None # AI server URL
    
    @staticmethod
    def setup_benchmark(server_url: str) -> str:
        """Setup shared vLLM service"""
        # Create vLLM service on server
        # Set static variables for all clients
```

**Configuration Pattern:**
1. **Setup Benchmark**: Called once per group
2. **Shared State**: All instances use same service_id
3. **Dynamic Server**: Runtime configurable server URL

#### ClientGroup (Local Singleton)
```python
class ClientGroup:
    """Manages client group on single process"""
    
    # Responsibilities:
    # - Local client coordination
    # - Observer registration
    # - Parallel thread execution
    # - Status reporting
```

#### Observer Pattern
```mermaid
classDiagram
    class ClientObserver {
        +update(data: dict)
    }
    
    class VLLMClient {
        -observers: List[ClientObserver]
        +subscribe(observer)
        +notify_observers(data)
    }
    
    class MonitorProxy {
        +update(data: dict)
        +send_to_monitor(data)
    }
    
    ClientObserver <|-- MonitorProxy
    VLLMClient --> ClientObserver
```

### 3. Deployment Layer

Manages deployment and configuration on HPC infrastructure.

#### Slurm Client Dispatcher
```python
class SlurmClientDispatcher:
    """Dispatch Slurm jobs for client processes"""
    
    def dispatch(self, num_clients: int, benchmark_id: int, time: int):
        # Build Slurm script
        # Submit job via REST API
        # Configure environment variables
        # Handle container mode
```

**Container Support:**
```bash
# Native execution
./start_client.sh 3 http://server:8000 http://service:8001 123

# Container execution  
./start_client.sh 3 http://server:8000 http://service:8001 123 --container
```

#### Slurm Configuration Management
```python
class SlurmConfig:
    """Automatic Slurm configuration management"""
    
    # Auto-detection:
    # - Username from environment
    # - JWT token from SLURM_JWT env var
    # - Cluster configuration from defaults
    
    # Container mode:
    # - Pre-generated token on host
    # - Refresh disabled
    # - Environment variables injection
```

#### JWT Token Management
```python
class SlurmToken:
    """Advanced Slurm JWT token management"""
    
    # Capabilities:
    # - Automatic JWT parsing
    # - Expiration validation
    # - Claims extraction
    # - Remaining lifetime calculation
```

## 🔄 Execution Workflow

### 1. System Initialization

```mermaid
sequenceDiagram
    participant CLI
    participant CS as Client Service
    participant CM as Client Manager
    participant SC as Slurm Config
    
    CLI->>CS: python main.py http://server:8000
    CS->>SC: Load/Generate Slurm Config
    CS->>CM: Configure(server_addr, use_container)
    CS->>CS: Start FastAPI Server
```

### 2. Client Group Creation

```mermaid
sequenceDiagram
    participant API
    participant FR as Frontend Router
    participant CM as Client Manager
    participant CG as Client Group
    participant SCD as Slurm Dispatcher
    participant SLURM
    
    API->>FR: POST /client-group/123 {num_clients: 5}
    FR->>CM: add_client_group(123, 5, time_limit)
    CM->>CG: new ClientGroup(123, 5, ...)
    CG->>SCD: dispatch(5, 123, time_limit)
    SCD->>SLURM: Submit job via REST API
    SLURM-->>SCD: Job ID
    SCD-->>CG: Success
    CG-->>CM: Group created
    CM-->>FR: OK
    FR-->>API: 201 Created
```

### 3. Client Process Startup

```mermaid
sequenceDiagram
    participant SLURM
    participant CP as Client Process
    participant CS as Client Service
    participant CM as Client Manager
    
    SLURM->>CP: Start job on compute node
    CP->>CP: Initialize ClientGroup singleton
    CP->>CP: Create VLLMClient instances
    CP->>CP: Start FastAPI server
    CP->>CS: POST /client-group/123/connect
    CS->>CM: register_client(123, client_addr)
    CM-->>CS: Registration OK
    CS-->>CP: 201 Created
```

### 4. Benchmark Execution

```mermaid
sequenceDiagram
    participant API
    participant CS as Client Service
    participant CM as Client Manager
    participant CP as Client Process
    participant VC as VLLMClient
    participant AS as AI Server
    
    API->>CS: POST /client-group/123/run
    CS->>CM: run_client_group(123)
    CM->>CP: POST /run
    CP->>VC: VLLMClient.setup_benchmark(server_url)
    VC->>AS: Create vLLM service
    AS-->>VC: Service ID
    CP->>CP: Start all VLLMClient threads
    loop For each client
        VC->>AS: Send prompts to vLLM service
        AS-->>VC: Responses
        VC->>VC: Notify observers
    end
```

## 🔧 Configuration and Deployment

### Container Architecture

```mermaid
graph LR
    subgraph "Host Environment"
        H[Host] --> JWT[Generate JWT]
        H --> BLD[Build Containers]
    end
    
    subgraph "Container Environment"
        JWT --> ENV[SLURM_JWT env var]
        BLD --> SIF[.sif containers]
        
        subgraph "Client Service Container"
            SIF --> CSC[client_service.sif]
            ENV --> CSC
        end
        
        subgraph "Client Container"
            SIF --> CC[client_container.sif] 
            ENV --> CC
        end
    end
    
    subgraph "Slurm Cluster"
        CSC --> SN[Service Node]
        CC --> CN[Compute Nodes]
    end
```

### Configuration Hierarchy

```yaml
Configuration Sources (precedence order):
  1. Command line arguments:
     - server_addr (required)
     - --container flag
     - slurm_config_file (optional)
  
  2. Environment variables:
     - SLURM_JWT (token)
     - USER/USERNAME (username)
  
  3. Configuration file:
     - url, user_name, api_ver, account, jwt
  
  4. Auto-detection defaults:
     - Slurm cluster URL
     - Current user
     - Latest API version
```

## 🎛️ Monitoring and Observability

### Observer Pattern Implementation

```python
# Client-side monitoring
client = VLLMClient()
monitor_observer = MonitorProxy("monitor.host", "8080", preferences)
client.subscribe(monitor_observer)

# Automatic notifications
client.run()  # Triggers observer.update() on completion
```

### Logging Architecture

```yaml
Logging Levels:
  - DEBUG: Detailed execution flow
  - INFO: Major operations and status
  - WARNING: Recoverable issues
  - ERROR: Failures requiring attention

Log Destinations:
  - Console: Real-time feedback
  - Files: Persistent debugging
  - Slurm: Standard out/err capture
```

## 🔐 Security and Authentication

### JWT Token Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Host_Generation: scontrol token
    Host_Generation --> Environment_Injection: SLURM_JWT
    Environment_Injection --> Container_Usage: Token available
    Container_Usage --> Validation: Check expiration
    Validation --> Valid_Token: Not expired
    Validation --> Expired_Token: Expired
    Valid_Token --> API_Usage: Slurm REST calls
    Expired_Token --> [*]: Container restart required
```

### Security Features

- **No Token Refresh in Containers**: Prevents privilege escalation
- **Environment Isolation**: Safe token injection via env vars
- **Automatic Expiration Checking**: Continuous token validation
- **Least Privilege**: Client processes with minimal permissions

## 📈 Scalability and Performance

### Horizontal Scaling

```yaml
Scaling Patterns:
  Service Layer:
    - Multiple client service instances
    - Load balancer distribution
    - Shared state via external storage
  
  Client Layer:
    - Automatic Slurm node allocation
    - Dynamic client process spawning
    - Independent process execution
  
  Infrastructure:
    - Multi-node Slurm clusters
    - Container registry distribution
    - Network optimization
```

### Performance Considerations

- **Async Operations**: FastAPI async handlers
- **Thread Parallelism**: Multiple client threads per process
- **Container Caching**: Apptainer image reuse
- **Network Optimization**: Keep-alive connections
- **Resource Management**: Slurm allocation limits

## 🔧 Extensibility

### Plugin Architecture

```python
# Nuovo tipo di client
class CustomAIClient(VLLMClient):
    def run(self):
        # Custom implementation
        pass

# Nuovo dispatcher
class KubernetesDispatcher(AbstractClientDispatcher):
    def dispatch(self, num_clients, benchmark_id, time):
        # Kubernetes deployment logic
        pass
```

### Configuration Extension

```python
# Custom configuration providers
class DatabaseConfig(SlurmConfig):
    def load_from_database(self, connection_string):
        # Load from external database
        pass
```

This architecture provides a solid foundation for system evolution while maintaining flexibility and ease of maintenance.