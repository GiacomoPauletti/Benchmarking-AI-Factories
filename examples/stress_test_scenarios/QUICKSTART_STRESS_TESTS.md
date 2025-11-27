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
python examples/stress_test_scenarios/stress_test_variable_length.py --dataset sharegpt --max-samples 50

# Spike pattern with conversations
python examples/stress_test_scenarios/stress_test_burst_patterns.py --pattern spike --dataset sharegpt
```

### Test with Alpaca (Instructions)

```bash
# Variable-length instruction test
python examples/stress_test_scenarios/stress_test_variable_length.py --dataset alpaca

# Gradual ramp with instructions
python examples/stress_test_scenarios/stress_test_burst_patterns.py --pattern ramp --dataset alpaca
```

### Test with Code Problems

```bash
# Long-form code problem testing
python examples/stress_test_scenarios/stress_test_variable_length.py \
  --dataset code_contests \
  --min-tokens 500 \
  --max-tokens 3000
```

### Test with Local Files

```bash
# Use existing text files
python examples/stress_test_scenarios/stress_test_variable_length.py --data-dir examples/data
```

## High-Load Scenarios

### Maximum Throughput Test

```bash
python examples/stress_test_scenarios/stress_test_burst_patterns.py \
  --pattern sustained \
  --dataset sharegpt \
  --scale-clients 3.0 \
  --scale-rps 2.0 \
  --max-samples 200
```

### Long Context Stress Test

```bash
python examples/stress_test_scenarios/stress_test_variable_length.py \
  --dataset wikitext \
  --min-tokens 2000 \
  --max-tokens 6000 \
  --max-model-len 8192 \
  --num-clients 10
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
| `ramp` | Gradual Low → Peak | Test scaling behavior |
| `sustained` | Continuous high load | Test stability under pressure |



