#!/usr/bin/env python3
"""
Simple Qdrant Vector Database Example

This script demonstrates the basic operations available with the Qdrant vector database service:
1. Creating a Qdrant service
2. Creating a collection
3. Adding vectors (points) to the collection
4. Searching for similar vectors
5. Listing collections
6. Getting collection info
7. Cleaning up

No embeddings or complex RAG - just pure vector operations with sample data.
"""

import requests
import time
import os


def wait_for_server(server_url: str, max_wait: int = 30) -> bool:
    """Wait for server to be ready."""
    print(f"Waiting for server at {server_url}...")
    start = time.time()
    
    while time.time() - start < max_wait:
        try:
            response = requests.get(f"{server_url}/health", timeout=2)
            if response.status_code == 200:
                print("Server is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    
    print("Server not available")
    return False


def wait_for_service(server_url: str, service_id: str, max_wait: int = 300) -> bool:
    """Wait for a Qdrant service to be running."""
    print(f"Waiting for Qdrant service {service_id} to be ready...")
    api_base = f"{server_url}/api/v1"
    start = time.time()
    last_status = None
    
    while time.time() - start < max_wait:
        try:
            response = requests.get(
                f"{api_base}/services/{service_id}/status",
                timeout=10
            )
            
            if response.status_code == 200:
                status_data = response.json()
                current_status = status_data.get("status")
                
                if current_status != last_status:
                    elapsed = int(time.time() - start)
                    print(f"  Status: {current_status} (waited {elapsed}s)")
                    last_status = current_status
                
                if current_status == "running":
                    print("Qdrant service is ready!")
                    return True
                
                if current_status in ["failed", "cancelled"]:
                    print(f"Service failed with status: {current_status}")
                    return False
        except requests.exceptions.RequestException:
            pass
        
        time.sleep(3)
    
    print(f"Service did not become ready within {max_wait}s")
    return False


def main():
    """Run the simple vector database example."""
    print("Simple Vector Database Example: Basic Qdrant Operations")
    
    server_url = os.getenv("SERVER_URL", "http://localhost:8001")
    api_base = f"{server_url}/api/v1"
    service_id = None
    
    try:
        # Step 1: Wait for server
        print("\n[1/7] Checking server availability...")
        if not wait_for_server(server_url):
            print("\nServer is not running. Please start it first.")
            return
        
        # Step 2: Create Qdrant service
        print("\n[2/7] Creating Qdrant vector database service...")
        response = requests.post(
            f"{api_base}/services",
            json={
                "recipe_name": "vector-db/qdrant",
                "config": {
                    "nodes": 1,
                    "memory": "16G"
                }
            },
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to create Qdrant service: {response.text}")
        
        service_id = response.json()["id"]
        print(f"Qdrant service created with ID: {service_id}")
        
        # Step 3: Wait for service to be ready
        print("\n[3/7] Waiting for Qdrant service to start...")
        if not wait_for_service(server_url, service_id):
            return
        
        # Step 4: Create a collection
        print("\n[4/7] Creating a collection...")
        collection_name = "demo_vectors"
        
        response = requests.put(
            f"{api_base}/vector-db/{service_id}/collections/{collection_name}",
            json={
                "vector_size": 128,  # Simple 128-dimensional vectors
                "distance": "Cosine"  # Using cosine similarity
            },
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to create collection: {response.text}")
        
        print(f"Collection '{collection_name}' created (128-dim vectors, Cosine distance)")
        
        # Step 5: Add some sample vectors (points)
        print("\n[5/7] Adding sample vectors to the collection...")
        
        # Create some simple sample vectors (normally these would be embeddings)
        import random
        random.seed(42)  # For reproducibility
        
        points = []
        for i in range(10):
            # Generate a random 128-dimensional vector
            vector = [random.random() for _ in range(128)]
            
            points.append({
                "id": f"point_{i}",
                "vector": vector,
                "payload": {
                    "name": f"Sample Vector {i}",
                    "category": "even" if i % 2 == 0 else "odd",
                    "value": i
                }
            })
        
        response = requests.put(
            f"{api_base}/vector-db/{service_id}/collections/{collection_name}/points",
            json={"points": points},
            timeout=60
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to add points: {response.text}")
        
        print(f"Added {len(points)} vectors to the collection")
        
        # Step 6: List all collections
        print("\n[6/7] Listing all collections...")
        response = requests.get(
            f"{api_base}/vector-db/{service_id}/collections",
            timeout=10
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to list collections: {response.text}")
        
        collections_data = response.json()
        collections = collections_data.get("collections", [])
        
        print(f"Found {len(collections)} collection(s):")
        for coll in collections:
            print(f"  - {coll}")
        
        # Step 7: Get collection info
        print("\n[7/7] Getting collection information...")
        response = requests.get(
            f"{api_base}/vector-db/{service_id}/collections/{collection_name}",
            timeout=10
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get collection info: {response.text}")
        
        info = response.json()
        collection_info = info.get("collection_info", {})
        
        print(f"Collection '{collection_name}' details:")
        print(f"  - Points count: {collection_info.get('points_count', 'N/A')}")
        print(f"  - Vector size: {collection_info.get('config', {}).get('params', {}).get('vectors', {}).get('size', 'N/A')}")
        print(f"  - Distance metric: {collection_info.get('config', {}).get('params', {}).get('vectors', {}).get('distance', 'N/A')}")
        
        # Step 8: Search for similar vectors
        print("\n[DEMO] Searching for vectors similar to 'point_0'...")
        
        # Use the first point's vector as a query
        query_vector = points[0]["vector"]
        
        response = requests.post(
            f"{api_base}/vector-db/{service_id}/collections/{collection_name}/points/search",
            json={
                "query_vector": query_vector,
                "limit": 3,
                "with_payload": True
            },
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Search failed: {response.text}")
        
        search_data = response.json()
        results = search_data.get("result", [])
        
        print(f"Found {len(results)} similar vectors:")
        for i, result in enumerate(results, 1):
            payload = result.get("payload", {})
            score = result.get("score", 0)
            print(f"  [{i}] {payload.get('name', 'N/A')} (similarity: {score:.4f})")
            print(f"      Category: {payload.get('category', 'N/A')}, Value: {payload.get('value', 'N/A')}")
        
        # Success summary
        print("All vector database operations completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if service_id:
            print("\n[CLEANUP] Stopping Qdrant service...")
            try:
                response = requests.post(
                    f"{api_base}/services/{service_id}/status",
                    json={"status": "cancelled"},
                    timeout=10
                )
                if response.status_code == 200:
                    print(f"Stopped service: {service_id}")
                else:
                    print(f"Failed to stop service: {response.text}")
            except Exception as e:
                print(f"Error stopping service: {e}")
        
        print("\nDone!")


if __name__ == "__main__":
    main()
