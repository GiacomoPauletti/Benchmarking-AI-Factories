#!/usr/bin/env python3
"""
Simple Example with Metrics: Qdrant Service Usage + Prometheus Metrics

This script demonstrates the extended workflow:
1. Connect to the server
2. Create a Qdrant vector database service
3. Create a collection and insert vectors
4. Perform a search operation
5. Query Prometheus metrics from the Qdrant service
6. Display key metrics
"""

import requests
import time
import os
import random

# Import utilities
from utils import (
    wait_for_server,
    wait_for_service_ready,
    fetch_metrics,
    save_metrics_to_file,
    display_qdrant_metrics
)


def main():
    """Run the simple example with metrics."""
    print("Simple Example: Qdrant Service Usage with Metrics")
    
    # Configuration
    server_url = os.getenv("SERVER_URL", "http://localhost:8001")
    api_base = f"{server_url}/api/v1"
    
    service_id = None
    collection_name = "test_collection"
    
    try:
        # Step 1: Check server
        if not wait_for_server(server_url):
            print("\nServer is not running. Please start it first:")
            print("   docker compose up -d server")
            return
        
        # Step 2: Create Qdrant service
        print(f"\n[*] Creating Qdrant vector database service...")
        response = requests.post(
            f"{api_base}/services",
            json={
                "recipe_name": "vector-db/qdrant",
                "config": {
                    "nodes": 1
                }
            },
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"Failed to create service: {response.text}")
            return
        
        data = response.json()
        service_id = data["id"]
        print(f"Service created with ID: {service_id}")
        
        # Step 3: Wait for service to be ready
        if not wait_for_service_ready(server_url, service_id):
            return
        
        # Step 3a: Fetch initial metrics
        print("\n[*] Fetching initial metrics...")
        metrics_before = fetch_metrics(server_url, service_id, service_type="qdrant")
        if metrics_before:
            print("[+] Initial metrics retrieved")
            save_metrics_to_file(metrics_before, "before", service_id, service_type="qdrant")
        
        # Step 4: Create a collection
        print(f"\n[*] Creating collection '{collection_name}'...")
        response = requests.put(
            f"{api_base}/vector-db/{service_id}/collections/{collection_name}",
            json={
                "vector_size": 128,
                "distance": "Cosine"
            },
            timeout=10
        )
        
        if response.status_code not in [200, 201]:
            print(f"Failed to create collection: {response.text}")
            return
        
        print(f"[+] Collection created successfully")
        
        # Step 5: Insert some vectors
        print(f"\n[*] Inserting sample vectors...")
        
        points = [
            {
                "id": i,
                "vector": [random.random() for _ in range(128)],
                "payload": {"text": f"Sample document {i}", "index": i}
            }
            for i in range(1, 11)  # Insert 10 vectors
        ]
        
        response = requests.put(
            f"{api_base}/vector-db/{service_id}/collections/{collection_name}/points",
            json={"points": points},
            timeout=30
        )
        
        if response.status_code not in [200, 201]:
            print(f"Failed to insert vectors: {response.text}")
            return
        
        print(f"[+] Inserted {len(points)} vectors")
        
        # Step 6: Perform a search
        print(f"\n[*] Performing vector search...")
        query_vector = [random.random() for _ in range(128)]
        
        response = requests.post(
            f"{api_base}/vector-db/{service_id}/collections/{collection_name}/points/search",
            json={
                "query_vector": query_vector,
                "limit": 3
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                results = data.get("results", [])
                print(f"[+] Search returned {len(results)} results:")
                for i, result in enumerate(results[:3], 1):
                    print(f"    {i}. ID: {result.get('id')}, Score: {result.get('score', 0):.4f}")
            else:
                print(f"[-] Search failed: {data.get('error')}")
        else:
            print(f"[-] Search request failed: {response.text}")
        
        # Step 7: Fetch updated metrics after operations
        print("\n[*] Fetching updated metrics after operations...")
        time.sleep(1)  # Give service a moment to update metrics
        metrics_after = fetch_metrics(server_url, service_id, service_type="qdrant")
        
        if metrics_after:
            save_metrics_to_file(metrics_after, "after", service_id, service_type="qdrant")
            display_qdrant_metrics(metrics_after)
            
            # Show differences if we have before/after metrics
            if metrics_before:
                print("\nMetrics Delta (after - before):")
                print("=" * 50)
                
                if metrics_after.get("collections_total") is not None and \
                   metrics_before.get("collections_total") is not None:
                    delta_collections = (metrics_after["collections_total"] or 0) - \
                                      (metrics_before["collections_total"] or 0)
                    print(f"  Collections Delta: {delta_collections:+d}")
                
                if metrics_after.get("collections_vector_total") is not None and \
                   metrics_before.get("collections_vector_total") is not None:
                    delta_vectors = (metrics_after["collections_vector_total"] or 0) - \
                                  (metrics_before["collections_vector_total"] or 0)
                    print(f"  Vectors Delta: {delta_vectors:+d}")
                
                if metrics_after.get("rest_responses_total") is not None and \
                   metrics_before.get("rest_responses_total") is not None:
                    delta_responses = (metrics_after["rest_responses_total"] or 0) - \
                                    (metrics_before["rest_responses_total"] or 0)
                    print(f"  REST Responses Delta: {delta_responses:+d}")
                
                print("=" * 50)
        
        print("\n[+] Example completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n[!] Interrupted by user")
    except Exception as e:
        print(f"\n[-] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if service_id:
            print(f"\n[*] Stopping service {service_id}...")
            try:
                response = requests.delete(
                    f"{api_base}/services/{service_id}",
                    timeout=10
                )
                if response.status_code == 200:
                    print(f"[+] Service stopped")
                else:
                    print(f"[-] Failed to stop service: {response.text}")
            except Exception as e:
                print(f"[-] Error stopping service: {e}")

        print("Done!")


if __name__ == "__main__":
    main()
