#!/usr/bin/env python3
"""
Mock AI Server for integration testing.

This server simulates the behavior of a real AI/vLLM server for testing purposes.
"""

import asyncio
import argparse
import json
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mock AI Server", version="1.0.0")

# Mock data storage
mock_models = {
    "meta-llama/Llama-2-7b-chat-hf": {
        "id": "meta-llama/Llama-2-7b-chat-hf",
        "object": "model",
        "created": 1677610602,
        "owned_by": "meta",
        "permission": [],
        "root": "meta-llama/Llama-2-7b-chat-hf",
        "parent": None
    },
    "microsoft/DialoGPT-medium": {
        "id": "microsoft/DialoGPT-medium",
        "object": "model", 
        "created": 1677610602,
        "owned_by": "microsoft",
        "permission": [],
        "root": "microsoft/DialoGPT-medium",
        "parent": None
    }
}

mock_completions = [
    "This is a mock completion response from the AI server.",
    "Another example response for testing purposes.",
    "Mock AI is working correctly for your integration tests.",
    "The client-server communication is functioning as expected.",
    "Integration test successful - all systems operational."
]

completion_counter = 0

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "mock-ai-server", "version": "1.0.0"}

@app.get("/v1/models")
async def list_models():
    """List available models (mock)"""
    return {
        "object": "list",
        "data": list(mock_models.values())
    }

@app.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    """Get specific model information"""
    if model_id not in mock_models:
        raise HTTPException(status_code=404, detail="Model not found")
    return mock_models[model_id]

@app.post("/v1/completions")
async def create_completion(request: dict):
    """Create text completion (mock)"""
    global completion_counter
    
    # Validate basic request structure
    if "model" not in request:
        raise HTTPException(status_code=400, detail="Model is required")
    
    model = request["model"]
    prompt = request.get("prompt", "")
    max_tokens = request.get("max_tokens", 100)
    temperature = request.get("temperature", 0.7)
    
    # Log the request for debugging
    logger.info(f"Completion request: model={model}, prompt_length={len(str(prompt))}")
    
    # Generate mock response
    completion_text = mock_completions[completion_counter % len(mock_completions)]
    completion_counter += 1
    
    response = {
        "id": f"cmpl-mock-{completion_counter}",
        "object": "text_completion",
        "created": 1677610602,
        "model": model,
        "choices": [
            {
                "text": completion_text,
                "index": 0,
                "logprobs": None,
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(str(prompt).split()),
            "completion_tokens": len(completion_text.split()),
            "total_tokens": len(str(prompt).split()) + len(completion_text.split())
        }
    }
    
    return response

@app.post("/v1/chat/completions")
async def create_chat_completion(request: dict):
    """Create chat completion (mock)"""
    global completion_counter
    
    # Validate basic request structure
    if "model" not in request:
        raise HTTPException(status_code=400, detail="Model is required")
    if "messages" not in request:
        raise HTTPException(status_code=400, detail="Messages are required")
    
    model = request["model"]
    messages = request["messages"]
    max_tokens = request.get("max_tokens", 100)
    temperature = request.get("temperature", 0.7)
    
    # Log the request for debugging
    logger.info(f"Chat completion request: model={model}, messages_count={len(messages)}")
    
    # Generate mock response
    completion_text = mock_completions[completion_counter % len(mock_completions)]
    completion_counter += 1
    
    response = {
        "id": f"chatcmpl-mock-{completion_counter}",
        "object": "chat.completion",
        "created": 1677610602,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": completion_text
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": sum(len(msg.get("content", "").split()) for msg in messages),
            "completion_tokens": len(completion_text.split()),
            "total_tokens": sum(len(msg.get("content", "").split()) for msg in messages) + len(completion_text.split())
        }
    }
    
    return response

@app.get("/stats")
async def get_stats():
    """Get server statistics (mock endpoint for testing)"""
    return {
        "requests_served": completion_counter,
        "models_available": len(mock_models),
        "status": "running",
        "uptime_seconds": 3600  # Mock uptime
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Mock AI Server",
        "version": "1.0.0",
        "endpoints": [
            "/health",
            "/v1/models",
            "/v1/completions", 
            "/v1/chat/completions",
            "/stats"
        ]
    }

def main():
    parser = argparse.ArgumentParser(description="Mock AI Server for integration testing")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    
    args = parser.parse_args()
    
    # Configure logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    
    logger.info(f"Starting Mock AI Server on {args.host}:{args.port}")
    
    # Run the server
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower()
    )

if __name__ == "__main__":
    main()