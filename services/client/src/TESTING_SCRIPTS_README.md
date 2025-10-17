# 🧪 AI Factory Testing Scripts

These scripts allow you to easily test the `client_service` APIs with elegant formatting and interactive functions.

## 📋 Available Scripts

### 1. `start_shell.sh` - Interactive Shell on Compute Node
**Primary use**: Complete and interactive testing

```bash
./start_shell.sh
```

**Features:**
- 🏗️ Automatically allocates a compute node on Meluxina (account p200981, 2h)
- 🎨 Interactive shell with custom prompt `AI-Factory:`
- 🌈 Colorful and formatted output with JSON pretty-printing
- 🔧 Preloaded functions to test all APIs
- 📊 Automatic benchmark_id saving between commands

**Available commands in the shell:**
```bash
# Setup
set_url http://172.16.1.100:8000    # Set client service URL
test_health                         # Check service status

# API Testing
create_client_group [n] [recipe]    # Create group (default: 3 clients)
get_client_group [id]               # Group info
start_client_group [id]             # Start group  
list_client_groups                  # List all groups

# Utility
help                               # Show all commands
config                            # Show current configuration
```

### 2. `quick_test.sh` - Quick Test 
**Primary use**: Fast testing without Slurm allocation

```bash
# Test with defaults (localhost:8000, 3 clients, default recipe)
./quick_test.sh

# Test with custom URL
./quick_test.sh http://172.16.1.100:8000

# Full custom test
./quick_test.sh http://172.16.1.100:8000 5 performance
```

**Features:**
- ⚡ Immediate execution (no Slurm allocation)
- 🔄 Automatic sequence of complete tests
- 📊 Formatted output with colors
- 💾 Automatic benchmark_id extraction

**Automatic test sequence:**
1. Health Check
2. Create Client Group  
3. Get Client Group Info
4. List All Client Groups
5. Start Client Group
6. Get Updated Status

## 🎨 Output Formatting

Both scripts use elegant formatting:

```
╔══════════════════════════════════════════════════════════════╗
║          AI Factory Client Service Interactive Shell          ║
╠══════════════════════════════════════════════════════════════╣
║ Node: mel2345                                                ║
║ Time: Thu Oct 17 14:30:00 CEST 2025                         ║
╚══════════════════════════════════════════════════════════════╝

╭─────────────────────────────────────────────────────────────╮
│ Create Client Group                                         │
╰─────────────────────────────────────────────────────────────╯
🔧 Command: POST http://172.16.1.100:8000/api/v1/client-group

✅ Client group created successfully
Response:
{
  "benchmark_id": 123,
  "num_clients": 3,
  "recipe": "default",
  "status": "created"
}
```

## 🚀 Usage Examples

### Scenario 1: Complete Interactive Testing
```bash
# Start interactive shell on compute node
./start_shell.sh

# Inside the shell:
AI-Factory:~$ set_url http://172.16.1.100:8000
AI-Factory:~$ test_health
AI-Factory:~$ create_client_group 5 performance
AI-Factory:~$ start_client_group
AI-Factory:~$ get_client_group
```

### Scenario 2: Quick Automatic Testing
```bash
# Fast test with your client_service URL
./quick_test.sh http://172.16.1.100:8000 3 default
```

### Scenario 3: Testing with Dynamic IP
```bash
# If client_service is running on this node
CLIENT_IP=$(hostname -I | awk '{print $1}')
./quick_test.sh http://$CLIENT_IP:8000
```

## 🔧 Meluxina Configuration

Scripts are pre-configured for Meluxina with:
- **Account**: `p200981` 
- **QoS**: `default`
- **Time**: `2 hours`
- **Resources**: 1 node, 4 CPU, 8GB RAM

## 📁 Location

Scripts should be executed from the client src directory:
```bash
/home/users/u103213/Benchmarking-AI-Factories/services/client/src/
├── start_shell.sh              # Interactive shell
├── quick_test.sh               # Quick test
├── demo_scripts.sh             # Demo script
├── TESTING_SCRIPTS_README.md   # This documentation
├── client/                     # Client-side code
└── client_service/             # Client service code
```

## 🧪 Testing the Scripts

### Test Help Function
```bash
# Test the help system without Slurm allocation
./start_shell.sh --test-help
```

### Test Interactive Shell Locally
```bash
# Test the full interactive shell on login node (for debugging)
./start_shell.sh --test-local
```

### Demo Scripts
```bash
# Run demonstration of both scripts
./demo_scripts.sh
```

### Production Usage
```bash
# Full interactive shell with Slurm allocation on compute node
./start_shell.sh
```

## 🐛 Troubleshooting

### Issue: "Connection refused"
```bash
# Verify that client_service is running
# Check the correct IP of the node where the service is running
```

### Issue: "Slurm allocation failed" 
```bash
# Check account p200981 credits
sbalance -A p200981

# Check available queues
sinfo
```

### Issue: "jq command not found"
```bash
# Scripts work without jq, but JSON formatting is less elegant
# To install jq (if you have permissions):
module load tools/jq
```

## 💡 Tips

1. **Interactive Shell**: Use `start_shell.sh` for manual testing and debugging
2. **Automatic Testing**: Use `quick_test.sh` for quick verification
3. **Save benchmark_id**: Scripts automatically save the ID for reuse
4. **Monitor resources**: Interactive shell shows you the allocated node
5. **Formatted JSON**: If available, `jq` makes output more readable

Happy testing! 🎯