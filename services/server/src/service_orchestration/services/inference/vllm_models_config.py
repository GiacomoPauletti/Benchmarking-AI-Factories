"""
vLLM model compatibility and architecture information.

This module provides information about vLLM's supported model architectures
and integrates with HuggingFace Hub API to search for compatible models.

vLLM downloads models from HuggingFace Hub and supports a wide range of architectures.
This module queries the HuggingFace API to find models that match vLLM's supported architectures.
"""

from typing import List, Dict, Any, Optional
import logging
import os

logger = logging.getLogger(__name__)

# Optional HuggingFace Hub integration
try:
    from huggingface_hub import HfApi
    HF_HUB_AVAILABLE = True
except ImportError:
    HF_HUB_AVAILABLE = False
    logger.warning("huggingface_hub not installed. Model search functionality will be limited.")

def _get_hf_token() -> Optional[str]:
    """Get HuggingFace token from environment variables."""
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")

# vLLM supported model architectures (as of vLLM 0.6.x+)
# Source: https://docs.vllm.ai/en/latest/models/supported_models.html
VLLM_SUPPORTED_ARCHITECTURES = {
    "text-generation": [
        "LlamaForCausalLM",  # Llama, Llama 2, Llama 3, Vicuna, Alpaca, etc.
        "MistralForCausalLM",  # Mistral, Mixtral
        "Qwen2ForCausalLM",  # Qwen 2, Qwen 2.5
        "GPT2LMHeadModel",  # GPT-2
        "GPTNeoXForCausalLM",  # GPT-NeoX, Pythia, Dolly, StableLM
        "GPTJForCausalLM",  # GPT-J
        "FalconForCausalLM",  # Falcon
        "BloomForCausalLM",  # BLOOM
        "OPTForCausalLM",  # OPT
        "MPTForCausalLM",  # MPT
        "PhiForCausalLM",  # Phi, Phi-2
        "Phi3ForCausalLM",  # Phi-3
        "GemmaForCausalLM",  # Gemma
        "Gemma2ForCausalLM",  # Gemma 2
        "StableLmForCausalLM",  # StableLM
        "BaichuanForCausalLM",  # Baichuan
        "InternLMForCausalLM",  # InternLM
        "InternLM2ForCausalLM",  # InternLM 2
        "AquilaForCausalLM",  # Aquila
        "XverseForCausalLM",  # Xverse
        "CommandRForCausalLM",  # Cohere Command-R
        "DbrxForCausalLM",  # DBRX
        "DeepseekV2ForCausalLM",  # DeepSeek V2
        "MiniCPMForCausalLM",  # MiniCPM
        "OlmoForCausalLM",  # OLMo
        "Starcoder2ForCausalLM",  # StarCoder 2
    ],
    "vision-language": [
        "LlavaForConditionalGeneration",  # LLaVA
        "LlavaNextForConditionalGeneration",  # LLaVA-NeXT
        "Qwen2VLForConditionalGeneration",  # Qwen2-VL
        "InternVLChatModel",  # InternVL
        "MiniCPMV",  # MiniCPM-V
        "ChameleonForConditionalGeneration",  # Chameleon
    ],
    "embedding": [
        "BertModel",  # BERT-based models
        "RobertaModel",  # RoBERTa
    ],
}


def get_supported_architectures() -> Dict[str, List[str]]:
    """Get dictionary of vLLM supported model architectures by task type.
    
    Returns:
        Dictionary with keys: "text-generation", "vision-language", "embedding"
        Each containing a list of supported architecture class names
    """
    return VLLM_SUPPORTED_ARCHITECTURES


def search_hf_models(
    query: Optional[str] = None,
    architecture: Optional[str] = None,
    limit: int = 20,
    sort_by: str = "downloads"
) -> List[Dict[str, Any]]:
    """Search HuggingFace Hub for models compatible with vLLM.
    
    Args:
        query: Search query string (e.g., "llama", "mistral", "qwen")
        architecture: Filter by specific architecture (e.g., "LlamaForCausalLM")
        limit: Maximum number of results to return
        sort_by: Sort results by "downloads", "likes", "trending", or "created_at"
        
    Returns:
        List of model dictionaries with id, downloads, likes, and metadata
        
    Raises:
        RuntimeError: If huggingface_hub is not installed
    """
    if not HF_HUB_AVAILABLE:
        raise RuntimeError(
            "huggingface_hub package not installed. "
            "Install it with: pip install huggingface-hub"
        )
    
    try:
        token = _get_hf_token()
        api = HfApi(token=token)
        
        # Search models - use pipeline_tag for filtering by task type
        models = api.list_models(
            pipeline_tag="text-generation",
            search=query,
            sort=sort_by,
            direction=-1,  # Descending
            limit=limit,
        )
        
        results = []
        for model in models:
            # Try to get architecture from model card
            model_arch = None
            try:
                # Get model info with config
                model_info = api.model_info(model.id, files_metadata=False)
                if hasattr(model_info, 'config') and model_info.config:
                    model_arch = model_info.config.get('architectures', [None])[0]
            except Exception as e:
                # Redact token from error message if present
                error_msg = str(e)
                if token and token in error_msg:
                    error_msg = error_msg.replace(token, "[REDACTED]")
                logger.debug(f"Could not fetch architecture for {model.id}: {error_msg}")
            
            # Filter by architecture if specified
            if architecture and model_arch != architecture:
                continue
            
            # Check if architecture is supported by vLLM
            is_supported = False
            if model_arch:
                for task_archs in VLLM_SUPPORTED_ARCHITECTURES.values():
                    if model_arch in task_archs:
                        is_supported = True
                        break
            
            results.append({
                "id": model.id,
                "downloads": model.downloads if hasattr(model, 'downloads') else 0,
                "likes": model.likes if hasattr(model, 'likes') else 0,
                "architecture": model_arch,
                "vllm_compatible": is_supported if model_arch else None,
                "created_at": str(model.created_at) if hasattr(model, 'created_at') else None,
                "tags": model.tags if hasattr(model, 'tags') else [],
            })
        
        return results
        
    except Exception as e:
        logger.error(f"Error searching HuggingFace Hub: {e}")
        raise


def get_model_info(model_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific model from HuggingFace Hub.
    
    Args:
        model_id: HuggingFace model ID (e.g., "meta-llama/Llama-2-7b-hf")
        
    Returns:
        Dictionary with model information including architecture, size, compatibility
        
    Raises:
        RuntimeError: If huggingface_hub is not installed
    """
    if not HF_HUB_AVAILABLE:
        raise RuntimeError(
            "huggingface_hub package not installed. "
            "Install it with: pip install huggingface-hub"
        )
    
    try:
        token = _get_hf_token()
        api = HfApi(token=token)
        model_info = api.model_info(model_id, files_metadata=True)
        
        # Extract architecture
        architecture = None
        if hasattr(model_info, 'config') and model_info.config:
            archs = model_info.config.get('architectures', [])
            architecture = archs[0] if archs else None
        
        # Check vLLM compatibility
        vllm_compatible = False
        task_type = None
        if architecture:
            for task, archs in VLLM_SUPPORTED_ARCHITECTURES.items():
                if architecture in archs:
                    vllm_compatible = True
                    task_type = task
                    break
        
        # Calculate approximate model size from safetensors files
        model_size_bytes = 0
        if hasattr(model_info, 'siblings') and model_info.siblings:
            for file in model_info.siblings:
                if hasattr(file, 'rfilename') and file.rfilename.endswith('.safetensors'):
                    if hasattr(file, 'size'):
                        model_size_bytes += file.size
        
        return {
            "id": model_id,
            "architecture": architecture,
            "vllm_compatible": vllm_compatible,
            "task_type": task_type,
            "downloads": model_info.downloads if hasattr(model_info, 'downloads') else None,
            "likes": model_info.likes if hasattr(model_info, 'likes') else None,
            "tags": model_info.tags if hasattr(model_info, 'tags') else [],
            "size_bytes": model_size_bytes if model_size_bytes > 0 else None,
            "size_gb": round(model_size_bytes / (1024**3), 2) if model_size_bytes > 0 else None,
            "pipeline_tag": model_info.pipeline_tag if hasattr(model_info, 'pipeline_tag') else None,
            "library_name": model_info.library_name if hasattr(model_info, 'library_name') else None,
        }
        
    except Exception as e:
        # Redact token from error message if present
        error_msg = str(e)
        if token and token in error_msg:
            error_msg = error_msg.replace(token, "[REDACTED]")
        logger.error(f"Error fetching model info for {model_id}: {error_msg}")
        raise


def get_architecture_info() -> Dict[str, Any]:
    """Get detailed information about vLLM's model compatibility.
    
    Returns:
        Dictionary containing:
        - supported_architectures: Dict of architecture types and their classes
        - model_source: Where models are downloaded from (HuggingFace Hub)
        - notes: Important compatibility information
        - examples: Example model IDs for common architectures
    """
    return {
        "model_source": "HuggingFace Hub (https://huggingface.co/models)",
        "supported_architectures": VLLM_SUPPORTED_ARCHITECTURES,
        "notes": [
            "vLLM can load any model from HuggingFace Hub that uses a supported architecture",
            "Model ID format: 'organization/model-name' (e.g., 'meta-llama/Llama-2-7b-hf')",
            "Some models require HuggingFace authentication and license acceptance",
            "Model compatibility depends on the architecture, not the specific model",
            "Check model's config.json on HuggingFace to see its architecture class"
        ],
        "examples": {
            "GPT-2 (small, for testing)": "gpt2",
            "Llama 2 7B Chat": "meta-llama/Llama-2-7b-chat-hf",
            "Llama 3.2 1B Instruct": "meta-llama/Llama-3.2-1B-Instruct",
            "Llama 3.2 3B Instruct": "meta-llama/Llama-3.2-3B-Instruct",
            "Mistral 7B Instruct": "mistralai/Mistral-7B-Instruct-v0.3",
            "Qwen 2.5 0.5B Instruct": "Qwen/Qwen2.5-0.5B-Instruct",
            "Qwen 2.5 1.5B Instruct": "Qwen/Qwen2.5-1.5B-Instruct",
            "Qwen 2.5 3B Instruct": "Qwen/Qwen2.5-3B-Instruct",
            "Qwen 2.5 7B Instruct": "Qwen/Qwen2.5-7B-Instruct",
            "Phi-3 Mini 4K Instruct": "microsoft/Phi-3-mini-4k-instruct",
            "Phi-3 Mini 128K Instruct": "microsoft/Phi-3-mini-128k-instruct",
            "Gemma 2B": "google/gemma-2b",
            "Gemma 2B Instruct": "google/gemma-2b-it",
        },
        "how_to_find_models": [
            "Browse HuggingFace: https://huggingface.co/models?pipeline_tag=text-generation",
            "Check model card for architecture (look for 'architectures' in config.json)",
            "Verify architecture is in vLLM's supported list",
            "Consider model size vs available GPU memory",
        ],
        "resource_guidelines": {
            "small_models": {
                "size_range": "< 1B parameters",
                "examples": ["gpt2", "Qwen/Qwen2.5-0.5B-Instruct"],
                "min_gpu_memory_gb": 4,
                "recommended_gpu_memory_gb": 8,
            },
            "medium_models": {
                "size_range": "1B - 7B parameters",
                "examples": ["Qwen/Qwen2.5-3B-Instruct", "meta-llama/Llama-3.2-3B-Instruct"],
                "min_gpu_memory_gb": 8,
                "recommended_gpu_memory_gb": 24,
            },
            "large_models": {
                "size_range": "7B - 15B parameters",
                "examples": ["meta-llama/Llama-2-7b-chat-hf", "mistralai/Mistral-7B-Instruct-v0.3"],
                "min_gpu_memory_gb": 24,
                "recommended_gpu_memory_gb": 40,
            },
            "very_large_models": {
                "size_range": "> 15B parameters",
                "examples": ["meta-llama/Llama-2-13b-chat-hf"],
                "min_gpu_memory_gb": 40,
                "recommended_gpu_memory_gb": 80,
                "notes": "May require tensor parallelism across multiple GPUs",
            }
        }
    }
