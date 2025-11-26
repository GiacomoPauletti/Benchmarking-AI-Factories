#!/usr/bin/env python3
"""
Variable-length prompt stress test using HuggingFace datasets.

Tests vLLM service performance with prompts of varying lengths to identify:
- Throughput degradation with longer contexts
- Latency patterns across different prompt sizes
- Memory usage scaling
- Optimal context window utilization

Usage:
    # Use HuggingFace dataset
    python examples/stress_test_variable_length.py --dataset sharegpt
    
    # Use local files
    python examples/stress_test_variable_length.py --data-dir examples/data
    
    # Custom length ranges
    python examples/stress_test_variable_length.py --min-tokens 100 --max-tokens 3000
"""

import requests
import time
import json
import argparse
from typing import List, Dict
from utils.utils import wait_for_server, wait_for_client, wait_for_service_ready
from utils.dataset_loader import DatasetLoader, get_dataset_preset, DATASET_PRESETS

# API endpoints
SERVER_API = "http://localhost:8001/api/v1"
SERVER_BASE = "http://localhost:8001"
CLIENT_API = "http://localhost:8003/api/v1"
CLIENT_BASE = "http://localhost:8003"


def load_prompts(args) -> List[str]:
    """Load prompts based on command-line arguments."""
    loader = DatasetLoader()
    
    if args.dataset:
        print(f"Loading prompts from HuggingFace dataset: {args.dataset}")
        preset = get_dataset_preset(args.dataset)
        
        # Handle dataset_config if present
        dataset_config = preset.pop("dataset_config", None)
        if dataset_config:
            prompts = loader.from_huggingface(
                preset["dataset_name"],
                name=dataset_config,
                text_column=preset["text_column"],
                max_samples=args.max_samples,
                split=args.split
            )
        else:
            prompts = loader.from_huggingface(
                preset["dataset_name"],
                text_column=preset["text_column"],
                max_samples=args.max_samples,
                split=args.split
            )
        
        print(f"  Description: {preset['description']}")
        print(f"  Loaded: {len(prompts)} prompts")
        
    elif args.data_dir:
        print(f"Loading prompts from directory: {args.data_dir}")
        prompts = loader.from_directory(
            args.data_dir,
            max_samples=args.max_samples
        )
        
    elif args.data_file:
        print(f"Loading prompts from file: {args.data_file}")
        prompts = loader.from_file(
            args.data_file,
            max_samples=args.max_samples
        )
        
    else:
        # Default: use built-in examples
        print("Using default example prompts")
        prompts = [
            "Explain quantum computing in detail.",
            "Write a comprehensive guide to machine learning.",
            "Describe the history of artificial intelligence.",
            "What are the key principles of distributed systems?"
        ]
    
    return prompts


def create_variable_length_prompts(base_prompts: List[str], args) -> Dict[str, List[str]]:
    """Create prompts of different lengths for testing.
    
    Returns:
        Dict mapping length category to list of prompts
    """
    loader = DatasetLoader()
    
    # Define length buckets (in approximate tokens)
    length_buckets = {
        "tiny": [10, 50],
        "short": [100, 200],
        "medium": [500, 1000],
        "long": [2000, 3000],
        "very_long": [4000, 6000]
    }
    
    # Filter based on args
    if args.min_tokens or args.max_tokens:
        min_tok = args.min_tokens or 10
        max_tok = args.max_tokens or 6000
        length_buckets = {
            k: v for k, v in length_buckets.items()
            if any(min_tok <= length <= max_tok for length in v)
        }
    
    categorized_prompts = {}
    
    for category, lengths in length_buckets.items():
        print(f"\nGenerating {category} prompts (tokens: {lengths})...")
        prompts = loader.create_variable_length(
            base_prompts[:5],  # Use subset to avoid too many permutations
            target_lengths=lengths,
            padding_text="This is additional context to extend the prompt length. "
        )
        categorized_prompts[category] = prompts
        print(f"  Created {len(prompts)} prompts")
        print(f"  Example length: {len(prompts[0])} chars (~{len(prompts[0])//4} tokens)")
    
    return categorized_prompts


def create_vllm_service(args) -> str:
    """Create a vLLM inference service."""
    print("\n" + "="*80)
    print("Creating vLLM Service")
    print("="*80)
    
    payload = {
        "recipe_name": "inference/vllm-single-node",
        "config": {
            "resources": {
                "time_limit": args.time_limit
            }
        }
    }
    
    if args.max_model_len:
        payload["config"]["environment"] = {
            "VLLM_MAX_MODEL_LEN": args.max_model_len
        }
    
    response = requests.post(f"{SERVER_API}/services", json=payload)
    response.raise_for_status()
    
    service = response.json()
    service_id = service["id"]
    
    print(f"Service ID: {service_id}")
    print(f"Status: {service['status']}")
    
    return service_id


def run_length_category_test(
    service_id: str,
    category: str,
    prompts: List[str],
    args
) -> int:
    """Run load test for a specific prompt length category."""
    print(f"\n{'='*80}")
    print(f"Testing: {category.upper()} prompts")
    print(f"{'='*80}")
    
    payload = {
        "service_id": service_id,
        "num_clients": args.num_clients,
        "requests_per_second": args.rps,
        "duration_seconds": args.duration,
        "prompts": prompts,
        "max_tokens": args.max_tokens_response,
        "temperature": 0.7,
        "time_limit": args.time_limit
    }
    
    print(f"Configuration:")
    print(f"  Clients: {args.num_clients}")
    print(f"  RPS: {args.rps}")
    print(f"  Duration: {args.duration}s")
    print(f"  Prompts: {len(prompts)}")
    print(f"  Max response tokens: {args.max_tokens_response}")
    
    response = requests.post(f"{CLIENT_API}/client-groups", json=payload)
    response.raise_for_status()
    
    result = response.json()
    group_id = result['group_id']
    
    print(f"Client group created: {group_id}")
    
    # Monitor briefly
    monitor_duration = min(args.duration + 60, 300)
    print(f"Monitoring for {monitor_duration}s...")
    
    start = time.time()
    while time.time() - start < monitor_duration:
        try:
            resp = requests.get(f"{CLIENT_API}/client-groups/{group_id}")
            resp.raise_for_status()
            info = resp.json().get('info', {})
            status = info.get('status', 'unknown')
            
            elapsed = int(time.time() - start)
            print(f"  [{elapsed}s] Status: {status}")
            
            if status == 'stopped':
                print(f"Test completed for {category}")
                break
                
        except Exception as e:
            print(f"  Error: {e}")
        
        time.sleep(15)
    
    return group_id


def main():
    parser = argparse.ArgumentParser(
        description="Variable-length prompt stress test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available HuggingFace dataset presets:
{chr(10).join(f"  {name}: {info['description']}" for name, info in DATASET_PRESETS.items())}

Examples:
  # Use ShareGPT dataset
  python {parser.prog} --dataset sharegpt --max-samples 100
  
  # Use local files
  python {parser.prog} --data-dir examples/data
  
  # Focus on long prompts
  python {parser.prog} --dataset alpaca --min-tokens 1000 --max-tokens 4000
"""
    )
    
    # Data source options
    data_group = parser.add_mutually_exclusive_group()
    data_group.add_argument("--dataset", choices=list(DATASET_PRESETS.keys()),
                           help="HuggingFace dataset preset to use")
    data_group.add_argument("--data-dir", help="Directory containing text files")
    data_group.add_argument("--data-file", help="Single text file to use")
    
    parser.add_argument("--split", default="train", help="Dataset split (train/test/validation)")
    parser.add_argument("--max-samples", type=int, default=100,
                       help="Maximum samples to load from dataset")
    
    # Length options
    parser.add_argument("--min-tokens", type=int, help="Minimum prompt length in tokens")
    parser.add_argument("--max-tokens", type=int, help="Maximum prompt length in tokens")
    parser.add_argument("--max-model-len", type=int, help="Model context length (default: 4096)")
    
    # Load test options
    parser.add_argument("--num-clients", type=int, default=5, help="Concurrent clients")
    parser.add_argument("--rps", type=float, default=0.5, help="Requests per second")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--max-tokens-response", type=int, default=100,
                       help="Max tokens in response")
    parser.add_argument("--time-limit", type=int, default=30,
                       help="SLURM job time limit in minutes")
    
    # Control options
    parser.add_argument("--no-cleanup", action="store_true",
                       help="Don't stop service after test")
    
    args = parser.parse_args()
    
    print("Variable-Length Prompt Stress Test")
    print("="*80)
    
    service_id = None
    group_ids = []
    
    try:
        # Check services
        if not wait_for_server(SERVER_BASE, max_wait=30):
            print("Server not available. Start with: docker compose up server")
            return
        
        if not wait_for_client(CLIENT_BASE, max_wait=30):
            print("Client not available. Start with: docker compose up client")
            return
        
        # Load prompts
        print("\n" + "="*80)
        print("Loading Prompts")
        print("="*80)
        base_prompts = load_prompts(args)
        
        if not base_prompts:
            print("No prompts loaded. Exiting.")
            return
        
        # Create variable-length versions
        categorized_prompts = create_variable_length_prompts(base_prompts, args)
        
        # Create service
        service_id = create_vllm_service(args)
        
        # Wait for service
        print("\n" + "="*80)
        print("Waiting for Service")
        print("="*80)
        endpoint = wait_for_service_ready(SERVER_BASE, service_id, max_wait=600)
        
        if not endpoint:
            print("Service failed to start. Exiting.")
            return
        
        print(f"Service ready at: {endpoint}")
        
        # Run tests for each length category
        for category, prompts in categorized_prompts.items():
            group_id = run_length_category_test(service_id, category, prompts, args)
            group_ids.append((category, group_id))
            
            # Brief pause between tests
            if category != list(categorized_prompts.keys())[-1]:
                print(f"\nPausing 30s before next test...")
                time.sleep(30)
        
        print("\n" + "="*80)
        print("All Tests Complete!")
        print("="*80)
        print(f"\nService ID: {service_id}")
        print(f"Endpoint: {endpoint}")
        print(f"\nClient Groups:")
        for category, group_id in group_ids:
            print(f"  {category}: {group_id}")
        
        print(f"\nCheck logs directory for detailed results.")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if service_id and not args.no_cleanup:
            response = input(f"\nStop service {service_id}? [y/N]: ")
            if response.lower() == 'y':
                try:
                    requests.post(
                        f"{SERVER_API}/services/{service_id}/status",
                        json={"status": "cancelled"}
                    )
                    print("Service stopped")
                except Exception as e:
                    print(f"Failed to stop service: {e}")


if __name__ == "__main__":
    main()
