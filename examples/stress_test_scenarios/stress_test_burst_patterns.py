#!/usr/bin/env python3
"""
Burst and spike pattern stress test.

Tests vLLM service behavior under variable load patterns:
- Sudden traffic spikes (idle -> high load -> idle)
- Gradual ramps (0 -> peak load over time)
- Sustained high loads

Usage:
    # Test sudden spike pattern
    python examples/stress_test_scenarios/stress_test_burst_patterns.py --pattern spike --dataset alpaca
    
    # Test gradual ramp-up
    python examples/stress_test_scenarios/stress_test_burst_patterns.py --pattern ramp
    
    # Test sustained high load
    python examples/stress_test_scenarios/stress_test_burst_patterns.py --pattern sustained
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import time
import json
import argparse
from typing import List, Dict
from utils.utils import wait_for_server, wait_for_client, wait_for_service_group_ready
from utils.dataset_loader import DatasetLoader, get_dataset_preset, DATASET_PRESETS

# API endpoints
SERVER_API = "http://localhost:8001/api/v1"
SERVER_BASE = "http://localhost:8001"
CLIENT_API = "http://localhost:8002/api/v1"
CLIENT_BASE = "http://localhost:8002"


LOAD_PATTERNS = {
    "spike": {
        "description": "Sudden spike: idle -> peak -> idle (tests burst handling)",
        "phases": [
            {"name": "baseline", "clients": 2, "rps": 0.5, "duration": 60},
            {"name": "spike", "clients": 25, "rps": 4.0, "duration": 120},
            {"name": "recovery", "clients": 2, "rps": 0.5, "duration": 60},
        ]
    },
    "ramp": {
        "description": "Gradual ramp: low -> peak (tests scaling behavior)",
        "phases": [
            {"name": "warmup", "clients": 2, "rps": 0.5, "duration": 30},
            {"name": "ramp_low", "clients": 8, "rps": 1.0, "duration": 60},
            {"name": "ramp_mid", "clients": 16, "rps": 2.0, "duration": 60},
            {"name": "peak", "clients": 30, "rps": 4.0, "duration": 90},
        ]
    },
    "sustained": {
        "description": "Sustained high load (tests stability under pressure)",
        "phases": [
            {"name": "warmup", "clients": 5, "rps": 1.0, "duration": 30},
            {"name": "sustained", "clients": 20, "rps": 3.0, "duration": 300},
            {"name": "cooldown", "clients": 5, "rps": 1.0, "duration": 30},
        ]
    },
}


def load_prompts(args) -> List[str]:
    """Load prompts for the test."""
    loader = DatasetLoader()
    
    if args.dataset:
        print(f"Loading prompts from: {args.dataset}")
        preset = get_dataset_preset(args.dataset)
        prompts = loader.from_huggingface(
            preset["dataset_name"],
            text_column=preset["text_column"],
            max_samples=args.max_samples,
            split=args.split
        )
        print(f"  Loaded: {len(prompts)} prompts")
    else:
        print("Using default prompts")
        prompts = [
            "Explain artificial intelligence briefly.",
            "What is machine learning?",
            "Describe neural networks.",
            "How does deep learning work?",
            "What are transformers in AI?",
            "Explain gradient descent.",
            "What is backpropagation?",
            "Describe reinforcement learning.",
            "What are GANs?",
            "Explain computer vision."
        ]
    
    return prompts


def create_vllm_service_group(args) -> str:
    """Create a vLLM replica service group."""
    print("\n" + "="*80)
    print("Creating vLLM Service Group (Replicas)")
    print("="*80)
    
    payload = {
        "recipe_name": "inference/vllm-replicas",
        "config": {
            "resources": {
                "nodes": 3,
                "time_limit": args.time_limit
            }
        }
    }
    
    response = requests.post(f"{SERVER_API}/services", json=payload)
    response.raise_for_status()
    
    service = response.json()
    # For replica recipes, the response contains group_id
    group_id = service.get("group_id") or service.get("id")
    total_replicas = service.get("total_replicas", "N/A")
    
    print(f"Service Group ID: {group_id}")
    print(f"Total Replicas: {total_replicas}")
    
    return group_id


def run_load_phase(
    service_id: str,
    phase: Dict,
    prompts: List[str],
    args,
    phase_num: int,
    total_phases: int
) -> int:
    """Run a single load phase."""
    print(f"\n{'='*80}")
    print(f"Phase {phase_num}/{total_phases}: {phase['name'].upper()}")
    print(f"{'='*80}")
    
    # Apply scaling factors from args
    clients = int(phase['clients'] * args.scale_clients)
    rps = phase['rps'] * args.scale_rps
    duration = phase['duration']
    
    print(f"Load configuration:")
    print(f"  Clients: {clients}")
    print(f"  RPS: {rps}")
    print(f"  Duration: {duration}s")
    
    payload = {
        "service_id": service_id,
        "num_clients": clients,
        "requests_per_second": rps,
        "duration_seconds": duration,
        "prompts": prompts,
        "max_tokens": args.max_tokens,
        "temperature": 0.7,
        "time_limit": args.time_limit
    }
    
    response = requests.post(f"{CLIENT_API}/client-groups", json=payload)
    response.raise_for_status()
    
    result = response.json()
    group_id = result['group_id']
    
    print(f"Client group {group_id} started")
    
    # Monitor this phase
    monitor_duration = duration + 60
    start = time.time()
    
    while time.time() - start < monitor_duration:
        try:
            resp = requests.get(f"{CLIENT_API}/client-groups/{group_id}")
            resp.raise_for_status()
            info = resp.json().get('info', {})
            status = info.get('status', 'unknown')
            
            elapsed = int(time.time() - start)
            print(f"  [{elapsed}s] {phase['name']}: {status}")
            
            if status == 'stopped':
                print(f"Phase '{phase['name']}' completed")
                break
                
        except Exception as e:
            print(f"  Error: {e}")
        
        time.sleep(10)
    
    return group_id


def run_pattern(
    service_id: str,
    pattern_name: str,
    prompts: List[str],
    args
) -> List[int]:
    """Run a complete load pattern."""
    pattern = LOAD_PATTERNS[pattern_name]
    
    print("\n" + "="*80)
    print(f"Load Pattern: {pattern_name.upper()}")
    print("="*80)
    print(f"Description: {pattern['description']}")
    print(f"Total phases: {len(pattern['phases'])}")
    
    total_duration = sum(p['duration'] for p in pattern['phases'])
    print(f"Total duration: {total_duration}s (~{total_duration//60}min)")
    
    group_ids = []
    
    for i, phase in enumerate(pattern['phases'], 1):
        group_id = run_load_phase(
            service_id, phase, prompts, args,
            phase_num=i,
            total_phases=len(pattern['phases'])
        )
        group_ids.append(group_id)
        
        # Brief pause between phases
        if i < len(pattern['phases']):
            print(f"\nPausing 15s before next phase...")
            time.sleep(15)
    
    return group_ids


def main():
    patterns_text = "\n".join(
        f"  {name}: {info['description']}" for name, info in LOAD_PATTERNS.items()
    )

    epilog = f"""
Available load patterns:
{patterns_text}

Examples:
  # Test sudden spike with custom dataset
  python %(prog)s --pattern spike --dataset alpaca --scale-clients 1.5

  # Test gradual ramp with higher load
  python %(prog)s --pattern ramp --scale-rps 2.0

  # Test sustained high load
  python %(prog)s --pattern sustained --max-tokens 200
"""

    parser = argparse.ArgumentParser(
        description="Burst and spike pattern stress test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )

    # Pattern selection
    parser.add_argument(
        "--pattern",
        choices=list(LOAD_PATTERNS.keys()),
        required=True,
        help="Load pattern to test",
    )

    # Data options
    parser.add_argument(
        "--dataset",
        choices=list(DATASET_PRESETS.keys()),
        help="HuggingFace dataset preset",
    )
    parser.add_argument("--split", default="train", help="Dataset split")
    parser.add_argument(
        "--max-samples", type=int, default=100, help="Max prompts to load"
    )

    # Scaling options
    parser.add_argument(
        "--scale-clients",
        type=float,
        default=1.0,
        help="Multiply client counts by this factor",
    )
    parser.add_argument(
        "--scale-rps",
        type=float,
        default=1.0,
        help="Multiply RPS by this factor",
    )

    # Service options
    parser.add_argument(
        "--max-tokens", type=int, default=100, help="Max tokens in response"
    )
    parser.add_argument(
        "--time-limit", type=int, default=60, help="SLURM job time limit in minutes"
    )

    # Control
    parser.add_argument(
        "--no-cleanup", action="store_true", help="Don't stop service after test"
    )

    args = parser.parse_args()

    print("Burst Pattern Stress Test")
    print("=" * 80)

    service_group_id = None
    client_group_ids = []

    try:
        # Check services
        if not wait_for_server(SERVER_BASE, max_wait=30):
            print("Server not available")
            return

        if not wait_for_client(CLIENT_BASE, max_wait=30):
            print("Client not available")
            return

        # Load prompts
        print("\n" + "=" * 80)
        print("Loading Prompts")
        print("=" * 80)
        prompts = load_prompts(args)

        if not prompts:
            print("No prompts loaded")
            return

        # Create service group
        service_group_id = create_vllm_service_group(args)

        # Wait for service group replicas to be ready
        print("\n" + "=" * 80)
        print("Waiting for Service Group")
        print("=" * 80)
        ready = wait_for_service_group_ready(
            SERVER_BASE,
            service_group_id,
            min_healthy=1,
            timeout=3000
        )

        if not ready:
            print("Service group failed to start")
            return

        endpoint = f"{SERVER_API}/vllm/{service_group_id}"
        print(f"Service group ready at: {endpoint}")

        # Run pattern
        client_group_ids = run_pattern(service_group_id, args.pattern, prompts, args)

        print("\n" + "=" * 80)
        print("Pattern Test Complete!")
        print("=" * 80)
        print(f"\nService Group ID: {service_group_id}")
        print(f"Endpoint: {endpoint}")
        print(f"Pattern: {args.pattern}")
        print(f"\nClient Groups Created: {len(client_group_ids)}")
        for i, gid in enumerate(client_group_ids, 1):
            print(f"  Phase {i}: {gid}")

        print("\nCheck logs for detailed metrics and analysis.")

    except KeyboardInterrupt:
        print("\n\nInterrupted")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if service_group_id and not args.no_cleanup:
            response = input(f"\nStop service group {service_group_id}? [y/N]: ")
            if response.lower() == "y":
                try:
                    requests.delete(
                        f"{SERVER_API}/service-groups/{service_group_id}",
                    )
                    print("Service group stopped")
                except Exception as e:
                    print(f"Failed to stop: {e}")


if __name__ == "__main__":
    main()
