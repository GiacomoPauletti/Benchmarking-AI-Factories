# Quick Start: Stress Testing with HuggingFace Datasets

## Installation

```bash
# Install HuggingFace datasets library
pip install datasets

# Optional: Login for gated datasets
pip install huggingface_hub
huggingface-cli login
```

## Quick Examples

### Test with ShareGPT (Realistic Conversations)

```bash
# Variable-length test with real conversations
python examples/stress_test_variable_length.py --dataset sharegpt --max-samples 50

# Multi-turn conversation test
python examples/stress_test_conversation.py --dataset sharegpt --max-turns 5

# Spike pattern with conversations
python examples/stress_test_burst_patterns.py --pattern spike --dataset sharegpt
```

### Test with Alpaca (Instructions)

```bash
# Variable-length instruction test
python examples/stress_test_variable_length.py --dataset alpaca

# Gradual ramp with instructions
python examples/stress_test_burst_patterns.py --pattern ramp --dataset alpaca
```

### Test with Code Problems

```bash
# Long-form code problem testing
python examples/stress_test_variable_length.py \
  --dataset code_contests \
  --min-tokens 500 \
  --max-tokens 3000

# Burst pattern for code generation
python examples/stress_test_burst_patterns.py \
  --pattern burst \
  --dataset code_contests
```

### Test with Local Files

```bash
# Use existing text files
python examples/stress_test_variable_length.py --data-dir examples/data

# Single file test
python examples/stress_test_conversation.py --data-file examples/data/climate_change.txt
```

## High-Load Scenarios

### Maximum Throughput Test

```bash
python examples/stress_test_burst_patterns.py \
  --pattern sustained \
  --dataset sharegpt \
  --scale-clients 3.0 \
  --scale-rps 2.0 \
  --max-samples 200
```

### Long Context Stress Test

```bash
python examples/stress_test_variable_length.py \
  --dataset wikitext \
  --min-tokens 2000 \
  --max-tokens 6000 \
  --max-model-len 8192 \
  --num-clients 10
```

### Deep Conversation Test

```bash
python examples/stress_test_conversation.py \
  --dataset anthropic_hh \
  --max-turns 15 \
  --max-model-len 8192 \
  --num-clients 8 \
  --duration 120
```

## Available Datasets

| Dataset | Type | Best For |
|---------|------|----------|
| `sharegpt` | Conversations | Realistic chat testing |
| `anthropic_hh` | Conversations | Helpful/harmless dialogues |
| `openassistant` | Conversations | Diverse chat styles |
| `alpaca` | Instructions | Instruction-following |
| `code_contests` | Code | Programming problems |
| `wikitext` | Articles | Long-form text |

## Load Patterns

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `spike` | Idle → Peak → Idle | Test sudden load spikes |
| `ramp` | Gradual 0 → Peak | Test scaling behavior |
| `sustained` | Continuous high load | Test stability |
| `burst` | Repeated bursts + gaps | Test bursty traffic |
| `wave` | Sinusoidal pattern | Test variable load |

## Common Parameters

```bash
# Data
--dataset PRESET          # HuggingFace dataset preset
--max-samples N           # Limit dataset size

# Load
--num-clients N           # Concurrent clients
--rps FLOAT               # Requests per second
--duration SECONDS        # Test duration

# Context
--max-model-len TOKENS    # Model context window
--max-tokens TOKENS       # Response length

# Control
--no-cleanup              # Keep service running
--time-limit MINUTES      # SLURM time limit
```

