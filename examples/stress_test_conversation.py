#!/usr/bin/env python3
"""
Conversational/multi-turn stress test using HuggingFace datasets.

Simulates realistic chat applications where each request includes conversation
history, testing:
- Context window management with growing conversation length
- KV cache efficiency with repeated context
- Memory usage patterns with long conversations
- Throughput degradation as context grows

Usage:
    # Use ShareGPT conversations
    python examples/stress_test_conversation.py --dataset sharegpt
    
    # Use Anthropic HH conversations
    python examples/stress_test_conversation.py --dataset anthropic_hh
    
    # Control conversation depth
    python examples/stress_test_conversation.py --dataset openassistant --max-turns 10
"""

import requests
import time
import json
import argparse
from typing import List, Dict, Tuple
from utils.utils import wait_for_server, wait_for_client, wait_for_service_ready
from utils.dataset_loader import DatasetLoader, get_dataset_preset, DATASET_PRESETS

# API endpoints
SERVER_API = "http://localhost:8001/api/v1"
SERVER_BASE = "http://localhost:8001"
CLIENT_API = "http://localhost:8003/api/v1"
CLIENT_BASE = "http://localhost:8003"


def load_conversations(args) -> List[str]:
    """Load conversational data from HuggingFace or local files."""
    loader = DatasetLoader()
    
    if args.dataset:
        print(f"Loading conversations from: {args.dataset}")
        preset = get_dataset_preset(args.dataset)
        
        # Use conversation-friendly datasets
        if args.dataset not in ["sharegpt", "anthropic_hh", "openassistant"]:
            print(f"Warning: {args.dataset} may not contain conversational data")
        
        prompts = loader.from_huggingface(
            preset["dataset_name"],
            text_column=preset["text_column"],
            max_samples=args.max_samples,
            split=args.split
        )
        
        print(f"  Description: {preset['description']}")
        print(f"  Loaded: {len(prompts)} conversation starters")
        
    else:
        print("Using default conversation starters")
        prompts = [
            "Hello! Can you help me understand quantum computing?",
            "I'm learning about machine learning. Where should I start?",
            "What's the difference between AI and machine learning?",
            "Can you explain neural networks to me?",
            "I'm interested in learning Python programming."
        ]
    
    return prompts


def create_conversation_turns(
    initial_prompts: List[str],
    max_turns: int = 5
) -> Dict[int, List[str]]:
    """Create conversation prompts with varying numbers of turns.
    
    Args:
        initial_prompts: Starting conversation prompts
        max_turns: Maximum conversation depth to simulate
        
    Returns:
        Dict mapping turn count to list of prompts with that much history
    """
    conversation_turns = {}
    
    # Simulated conversation patterns
    follow_ups = [
        "Can you elaborate on that?",
        "That's interesting. Tell me more.",
        "I see. What else should I know?",
        "Thanks! Can you give me an example?",
        "How does that work in practice?",
        "What are the key takeaways?",
        "Could you clarify that point?",
        "What are some real-world applications?"
    ]
    
    assistant_responses = [
        "Here's more detail on that topic: [explanation continues].",
        "Let me explain further: [additional context provided].",
        "To add to that: [more information shared].",
        "Here's what you need to know: [knowledge expanded].",
    ]
    
    for turn in range(1, max_turns + 1):
        conversation_turns[turn] = []
        
        for initial_prompt in initial_prompts[:10]:  # Limit to avoid explosion
            # Build conversation history
            conversation = f"User: {initial_prompt}\n"
            
            for t in range(1, turn):
                # Add assistant response
                conversation += f"Assistant: {assistant_responses[t % len(assistant_responses)]}\n"
                # Add user follow-up
                conversation += f"User: {follow_ups[t % len(follow_ups)]}\n"
            
            # Add final user turn (the actual prompt)
            final_prompt = follow_ups[(turn - 1) % len(follow_ups)]
            conversation += f"User: {final_prompt}"
            
            conversation_turns[turn].append(conversation)
    
    return conversation_turns


def create_vllm_service(args) -> str:
    """Create a vLLM inference service with appropriate context length."""
    print("\n" + "="*80)
    print("Creating vLLM Service")
    print("="*80)
    
    payload = {
        "recipe_name": "inference/vllm-single-node",
        "config": {
            "resources": {
                "time_limit": args.time_limit
            },
            "environment": {
                "VLLM_MAX_MODEL_LEN": args.max_model_len
            }
        }
    }
    
    response = requests.post(f"{SERVER_API}/services", json=payload)
    response.raise_for_status()
    
    service = response.json()
    service_id = service["id"]
    
    print(f"Service ID: {service_id}")
    print(f"Max context length: {args.max_model_len}")
    
    return service_id


def run_conversation_depth_test(
    service_id: str,
    turn_count: int,
    prompts: List[str],
    args
) -> int:
    """Run load test for a specific conversation depth."""
    print(f"\n{'='*80}")
    print(f"Testing: {turn_count}-turn conversations")
    print(f"{'='*80}")
    
    # Calculate approximate context length
    avg_prompt_len = sum(len(p) for p in prompts) // len(prompts)
    approx_tokens = avg_prompt_len // 4
    
    print(f"Conversation depth: {turn_count} turns")
    print(f"Approximate context: ~{approx_tokens} tokens")
    
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
    
    print(f"Load configuration:")
    print(f"  Clients: {args.num_clients}")
    print(f"  RPS: {args.rps}")
    print(f"  Duration: {args.duration}s")
    print(f"  Unique conversations: {len(prompts)}")
    
    response = requests.post(f"{CLIENT_API}/client-groups", json=payload)
    response.raise_for_status()
    
    result = response.json()
    group_id = result['group_id']
    
    print(f"Client group created: {group_id}")
    
    # Monitor
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
                print(f"Test completed for {turn_count}-turn conversations")
                break
                
        except Exception as e:
            print(f"  Error: {e}")
        
        time.sleep(15)
    
    return group_id


def main():
    parser = argparse.ArgumentParser(
        description="Conversational/multi-turn stress test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Recommended datasets for conversational testing:
  sharegpt: Real user-assistant conversations from ShareGPT
  anthropic_hh: Anthropic's helpful and harmless conversations
  openassistant: Open Assistant multi-turn dialogues

Examples:
  # Test with ShareGPT conversations
  python {parser.prog} --dataset sharegpt --max-turns 8
  
  # Test deep conversations with large context
  python {parser.prog} --dataset anthropic_hh --max-turns 15 --max-model-len 8192
  
  # High-load conversation test
  python {parser.prog} --dataset openassistant --num-clients 20 --rps 2.0
"""
    )
    
    # Data options
    parser.add_argument("--dataset", choices=list(DATASET_PRESETS.keys()),
                       help="HuggingFace dataset preset")
    parser.add_argument("--split", default="train", help="Dataset split")
    parser.add_argument("--max-samples", type=int, default=50,
                       help="Max conversation starters to load")
    
    # Conversation options
    parser.add_argument("--max-turns", type=int, default=5,
                       help="Maximum conversation depth to test")
    parser.add_argument("--max-model-len", type=int, default=4096,
                       help="Model context length")
    
    # Load test options
    parser.add_argument("--num-clients", type=int, default=5,
                       help="Concurrent clients")
    parser.add_argument("--rps", type=float, default=0.5,
                       help="Requests per second")
    parser.add_argument("--duration", type=int, default=60,
                       help="Test duration per conversation depth")
    parser.add_argument("--max-tokens-response", type=int, default=150,
                       help="Max tokens in response")
    parser.add_argument("--time-limit", type=int, default=30,
                       help="SLURM job time limit in minutes")
    
    # Control
    parser.add_argument("--no-cleanup", action="store_true",
                       help="Don't stop service after test")
    
    args = parser.parse_args()
    
    print("Conversational Stress Test")
    print("="*80)
    
    service_id = None
    group_ids = []
    
    try:
        # Check services
        if not wait_for_server(SERVER_BASE, max_wait=30):
            print("Server not available")
            return
        
        if not wait_for_client(CLIENT_BASE, max_wait=30):
            print("Client not available")
            return
        
        # Load conversations
        print("\n" + "="*80)
        print("Loading Conversations")
        print("="*80)
        initial_prompts = load_conversations(args)
        
        if not initial_prompts:
            print("No conversations loaded")
            return
        
        # Create multi-turn conversations
        print(f"\nGenerating multi-turn conversations (1-{args.max_turns} turns)...")
        conversation_turns = create_conversation_turns(initial_prompts, args.max_turns)
        
        for turn, prompts in conversation_turns.items():
            print(f"  {turn} turns: {len(prompts)} conversations")
            if prompts:
                print(f"    Example length: {len(prompts[0])} chars (~{len(prompts[0])//4} tokens)")
        
        # Create service
        service_id = create_vllm_service(args)
        
        # Wait for service
        print("\n" + "="*80)
        print("Waiting for Service")
        print("="*80)
        endpoint = wait_for_service_ready(SERVER_BASE, service_id, max_wait=600)
        
        if not endpoint:
            print("Service failed to start")
            return
        
        print(f"Service ready at: {endpoint}")
        
        # Run tests for each conversation depth
        for turn_count in sorted(conversation_turns.keys()):
            prompts = conversation_turns[turn_count]
            if not prompts:
                continue
            
            group_id = run_conversation_depth_test(
                service_id, turn_count, prompts, args
            )
            group_ids.append((f"{turn_count}-turn", group_id))
            
            # Pause between tests
            if turn_count < max(conversation_turns.keys()):
                print(f"\nPausing 30s before next test...")
                time.sleep(30)
        
        print("\n" + "="*80)
        print("All Tests Complete!")
        print("="*80)
        print(f"\nService ID: {service_id}")
        print(f"Endpoint: {endpoint}")
        print(f"\nClient Groups:")
        for depth, group_id in group_ids:
            print(f"  {depth}: {group_id}")
        
        print(f"\nCheck logs for detailed results.")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted")
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
                    print(f"Failed to stop: {e}")


if __name__ == "__main__":
    main()
