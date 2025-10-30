# Code Refactoring: SSH/Connection Logic Separation

## Overview

Separated SSH and connection management logic from `slurm.py` into a dedicated `ssh_manager.py` module for better code organization and reusability.

## Changes Made

### 1. Created `ssh_manager.py`

New file: `services/server/src/ssh_manager.py`

**Class: `SSHManager`**

Provides centralized SSH operations:

#### Methods:
- `__init__(ssh_host, ssh_user)` - Initialize SSH manager with connection details
- `setup_slurm_rest_tunnel(local_port, remote_host, remote_port)` - Create SSH tunnel for SLURM REST API
- `_is_tunnel_active(local_port)` - Check if tunnel already exists
- `fetch_remote_file(remote_path, local_path)` - Download files from MeluXina via SSH
- `sync_directory_to_remote(local_dir, remote_dir, exclude_patterns)` - Rsync directories to HPC
- `execute_remote_command(command, timeout)` - Run arbitrary commands on MeluXina
- `check_remote_file_exists(remote_path)` - Test if remote file exists
- `check_remote_dir_exists(remote_path)` - Test if remote directory exists
- `create_remote_directory(remote_path)` - Create directory on MeluXina

#### Features:
- ✅ Automatic SSH target construction (`user@host`)
- ✅ Comprehensive error handling and logging
- ✅ Timeout support for all operations
- ✅ Rsync with exclude patterns
- ✅ Return tuples for command execution (success, stdout, stderr)

### 2. Updated `slurm.py`

**Changes:**
- **Added import**: `from ssh_manager import SSHManager`
- **Removed import**: `subprocess` (no longer needed)
- **Removed methods**:
  - `_setup_ssh_tunnel_for_rest_api()` - moved to SSHManager
  - Direct SSH/subprocess logic from `_sync_recipe_to_remote()`
  - Direct SSH/subprocess logic from `_fetch_remote_log_file()`

**Simplified methods:**

```python
# Before: 50+ lines with subprocess calls
def _sync_recipe_to_remote(self, recipe_name: str) -> bool:
    # ... complex subprocess and ssh logic ...

# After: Clean delegation to SSH manager
def _sync_recipe_to_remote(self, recipe_name: str) -> bool:
    local_recipe_dir = self.local_base_path / "recipes" / recipe_name
    remote_recipe_dir = f"{self.remote_base_path}/recipes/{recipe_name}"
    return self.ssh_manager.sync_directory_to_remote(
        local_recipe_dir, remote_recipe_dir, exclude_patterns=['*.pyc', '__pycache__/', '.git/']
    )
```

```python
# Before: 40+ lines with subprocess
def _fetch_remote_log_file(self, remote_path: str, local_path: Path) -> bool:
    # ... subprocess.run(...) ...

# After: Single line delegation
def _fetch_remote_log_file(self, remote_path: str, local_path: Path) -> bool:
    return self.ssh_manager.fetch_remote_file(remote_path, local_path)
```

**Updated initialization:**

```python
# Before:
self.ssh_host = os.getenv('SSH_TUNNEL_HOST', 'login.lxp.lu')
self.ssh_user = os.getenv('SSH_TUNNEL_USER')
# ... validation logic ...
self.rest_api_port = self._setup_ssh_tunnel_for_rest_api()

# After:
self.ssh_manager = SSHManager()
self.ssh_user = self.ssh_manager.ssh_user
self.ssh_host = self.ssh_manager.ssh_host
self.rest_api_port = self.ssh_manager.setup_slurm_rest_tunnel()
```

## Benefits

### 1. **Separation of Concerns**
- `slurm.py` focuses on SLURM API and job management
- `ssh_manager.py` handles all SSH/connection operations
- Clear responsibility boundaries

### 2. **Reusability**
- `SSHManager` can be imported and used by other modules
- No duplication of SSH logic across the codebase
- Easy to add new SSH operations

### 3. **Testability**
- Can mock `SSHManager` for unit testing `SlurmDeployer`
- SSH operations can be tested independently
- Easier to test error conditions

### 4. **Maintainability**
- Changes to SSH logic only affect `ssh_manager.py`
- Cleaner, more readable code
- Easier to debug connection issues

### 5. **Extensibility**
- Easy to add new SSH operations (e.g., `fetch_multiple_files`, `sync_with_progress`)
- Can add connection pooling or caching in one place
- Can implement retry logic centrally

## File Size Reduction

### `slurm.py`
- **Before**: ~840 lines
- **After**: ~730 lines
- **Reduction**: ~110 lines (13% smaller)

### Code Organization
- **Removed**: ~90 lines of subprocess/SSH code
- **Added**: 1 import, simplified 3 methods to ~20 lines
- **Net result**: Cleaner, more focused code

## Usage Example

### Direct Use of SSHManager

```python
from ssh_manager import SSHManager

# Initialize
ssh = SSHManager(ssh_host='meluxina', ssh_user='u103056')

# Create tunnel
port = ssh.setup_slurm_rest_tunnel()

# Fetch a file
ssh.fetch_remote_file(
    '/project/home/p200981/u103056/test.log',
    Path('/app/logs/test.log')
)

# Sync directory
ssh.sync_directory_to_remote(
    local_dir=Path('./recipes'),
    remote_dir='/project/home/p200981/u103056/recipes',
    exclude_patterns=['*.pyc', '__pycache__/']
)

# Execute command
success, stdout, stderr = ssh.execute_remote_command('ls -la /tmp')
if success:
    print(f"Output: {stdout}")
```

### Use via SlurmDeployer

```python
from slurm import SlurmDeployer

deployer = SlurmDeployer()

# SSH manager available as attribute
if deployer.ssh_manager.check_remote_dir_exists('/project/home/...'):
    print("Remote directory exists")

# Or use high-level methods that internally use SSH manager
deployer._sync_recipe_to_remote('inference/vllm')
```

## Future Enhancements

Possible additions to `SSHManager`:

1. **Connection Pooling** - Reuse SSH connections
2. **Async Operations** - Support for asyncio
3. **Progress Callbacks** - Report sync progress
4. **Batch Operations** - Fetch multiple files efficiently
5. **SFTP Support** - Alternative to rsync for some operations
6. **Connection Health Checks** - Periodic keepalive/reconnect
7. **Credential Management** - Key rotation, token refresh

## Testing Recommendations

### Unit Tests for SSHManager

```python
def test_ssh_manager_init():
    """Test SSHManager initialization"""
    ssh = SSHManager(ssh_host='test', ssh_user='testuser')
    assert ssh.ssh_target == 'testuser@test'

def test_tunnel_active_check(mock_requests):
    """Test tunnel detection"""
    ssh = SSHManager()
    # Mock requests.get to simulate active tunnel
    assert ssh._is_tunnel_active(6820) == True

def test_fetch_remote_file(tmp_path, mock_subprocess):
    """Test file fetching"""
    ssh = SSHManager()
    local_path = tmp_path / "test.log"
    success = ssh.fetch_remote_file("/remote/test.log", local_path)
    assert success == True
    assert local_path.exists()
```

### Integration Tests

```python
def test_slurm_deployer_uses_ssh_manager():
    """Test that SlurmDeployer properly delegates to SSHManager"""
    deployer = SlurmDeployer()
    assert hasattr(deployer, 'ssh_manager')
    assert isinstance(deployer.ssh_manager, SSHManager)
```

## Migration Notes

### Breaking Changes
- None - all public APIs remain the same

### Internal Changes
- `SlurmDeployer` now requires `ssh_manager.py` in the same directory
- Methods that were using `subprocess` now delegate to `SSHManager`

### Backward Compatibility
- ✅ All existing functionality preserved
- ✅ Same environment variables used
- ✅ Same behavior and error handling
- ✅ Same return types

## Summary

This refactoring successfully separates SSH/connection concerns from SLURM business logic, resulting in:
- **Cleaner code** - Each module has a single responsibility
- **Better structure** - Logical separation of concerns
- **Easier maintenance** - Changes isolated to appropriate modules
- **Enhanced testability** - Can mock SSH operations easily
- **Improved reusability** - SSH operations available to other modules

The refactoring was done with zero breaking changes to external APIs while significantly improving internal code quality.
