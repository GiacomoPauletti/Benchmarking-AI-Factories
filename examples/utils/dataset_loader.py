"""
Dataset loading utilities for realistic load testing.

Supports loading prompts from:
- HuggingFace datasets
- Local text files
- Custom prompt generators
"""

import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
import random

logger = logging.getLogger(__name__)

try:
    from datasets import load_dataset
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False
    logger.warning("HuggingFace datasets not available. Install with: pip install datasets")


class DatasetLoader:
    """Load and prepare prompts from various sources for load testing."""
    
    @staticmethod
    def from_huggingface(
        dataset_name: str,
        split: str = "train",
        text_column: str = "text",
        max_samples: Optional[int] = None,
        filter_fn: Optional[Callable] = None,
        shuffle: bool = True,
        seed: int = 42
    ) -> List[str]:
        """Load prompts from a HuggingFace dataset.
        
        Args:
            dataset_name: HF dataset identifier (e.g., "wikitext", "openai/summarize_from_feedback")
            split: Dataset split to use ("train", "test", "validation")
            text_column: Column name containing the text/prompts
            max_samples: Maximum number of samples to load (None = all)
            filter_fn: Optional function to filter samples (receives dict, returns bool)
            shuffle: Whether to shuffle the dataset
            seed: Random seed for shuffling
            
        Returns:
            List of prompt strings
            
        Example:
            >>> loader = DatasetLoader()
            >>> # Load from ShareGPT-style dataset
            >>> prompts = loader.from_huggingface(
            ...     "anon8231489123/ShareGPT_Vicuna_unfiltered",
            ...     text_column="conversations",
            ...     max_samples=1000
            ... )
        """
        if not HF_AVAILABLE:
            raise ImportError("HuggingFace datasets not installed. Run: pip install datasets")
        
        logger.info(f"Loading dataset: {dataset_name} (split={split})")
        
        try:
            # Load dataset - use force_redownload to work around cache bugs in some datasets versions
            from datasets import DownloadMode
            dataset = load_dataset(
                dataset_name,
                split=split,
                download_mode=DownloadMode.REUSE_CACHE_IF_EXISTS,
                verification_mode="no_checks",
            )

            if shuffle:
                dataset = dataset.shuffle(seed=seed)
            
            if max_samples:
                dataset = dataset.select(range(min(max_samples, len(dataset))))
            
            # Extract prompts
            prompts = []
            for item in dataset:
                if filter_fn and not filter_fn(item):
                    continue
                
                # Handle different data formats
                text = DatasetLoader._extract_text(item, text_column)
                if text:
                    prompts.append(text)
            
            logger.info(f"Loaded {len(prompts)} prompts from {dataset_name}")
            return prompts
            
        except Exception as e:
            logger.error(f"Failed to load dataset {dataset_name}: {e}")
            raise
    
    @staticmethod
    def _extract_text(item: Dict[str, Any], text_column: str) -> Optional[str]:
        """Extract text from various dataset formats."""
        if text_column not in item:
            # Try common alternatives
            for alt in ["text", "prompt", "input", "question", "instruction"]:
                if alt in item:
                    text_column = alt
                    break
            else:
                logger.warning(f"Could not find text column. Available: {list(item.keys())}")
                return None
        
        data = item[text_column]
        
        # Handle different formats
        if isinstance(data, str):
            return data.strip()
        
        elif isinstance(data, list):
            # For conversation formats (e.g., ShareGPT)
            if data and isinstance(data[0], dict):
                # Extract user messages
                user_messages = [
                    msg.get("value", msg.get("content", ""))
                    for msg in data
                    if msg.get("from") == "human" or msg.get("role") == "user"
                ]
                return " ".join(user_messages).strip() if user_messages else None
            else:
                return " ".join(str(x) for x in data).strip()
        
        elif isinstance(data, dict):
            # Try common keys
            for key in ["text", "content", "value", "prompt"]:
                if key in data:
                    return str(data[key]).strip()
        
        return str(data).strip() if data else None
    
    @staticmethod
    def from_file(
        file_path: str,
        max_samples: Optional[int] = None,
        shuffle: bool = True,
        seed: int = 42
    ) -> List[str]:
        """Load prompts from a text file.
        
        Args:
            file_path: Path to text file (one prompt per line, or full document)
            max_samples: Maximum number of prompts to return
            shuffle: Whether to shuffle the prompts
            seed: Random seed for shuffling
            
        Returns:
            List of prompt strings
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        logger.info(f"Loading prompts from file: {file_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try splitting by lines first
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        # If we have very few lines, treat as a single document and chunk it
        if len(lines) < 10:
            prompts = [content.strip()]
        else:
            prompts = lines
        
        if shuffle:
            random.seed(seed)
            random.shuffle(prompts)
        
        if max_samples:
            prompts = prompts[:max_samples]
        
        logger.info(f"Loaded {len(prompts)} prompts from {file_path}")
        return prompts
    
    @staticmethod
    def from_directory(
        dir_path: str,
        pattern: str = "*.txt",
        max_samples: Optional[int] = None,
        shuffle: bool = True,
        seed: int = 42
    ) -> List[str]:
        """Load prompts from all files in a directory.
        
        Args:
            dir_path: Path to directory containing text files
            pattern: Glob pattern for files to include
            max_samples: Maximum number of prompts to return
            shuffle: Whether to shuffle the prompts
            seed: Random seed for shuffling
            
        Returns:
            List of prompt strings
        """
        dir_path = Path(dir_path)
        
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {dir_path}")
        
        logger.info(f"Loading prompts from directory: {dir_path} (pattern={pattern})")
        
        prompts = []
        for file_path in dir_path.glob(pattern):
            try:
                file_prompts = DatasetLoader.from_file(str(file_path), shuffle=False)
                prompts.extend(file_prompts)
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")
        
        if shuffle:
            random.seed(seed)
            random.shuffle(prompts)
        
        if max_samples:
            prompts = prompts[:max_samples]
        
        logger.info(f"Loaded {len(prompts)} prompts from {dir_path}")
        return prompts
    
    @staticmethod
    def create_variable_length(
        base_prompts: List[str],
        target_lengths: List[int],
        padding_text: Optional[str] = None
    ) -> List[str]:
        """Create prompts of specific token lengths for stress testing.
        
        Args:
            base_prompts: Starting prompts to extend
            target_lengths: Desired token lengths (approximate)
            padding_text: Text to use for padding (default: repeat base prompt)
            
        Returns:
            List of prompts with varying lengths
        """
        variable_prompts = []
        
        for base_prompt in base_prompts:
            for target_length in target_lengths:
                # Rough estimate: 1 token ≈ 4 characters
                target_chars = target_length * 4
                
                if len(base_prompt) >= target_chars:
                    # Truncate if already too long
                    prompt = base_prompt[:target_chars]
                else:
                    # Extend with padding
                    padding = padding_text or base_prompt
                    repeats = (target_chars - len(base_prompt)) // len(padding) + 1
                    prompt = base_prompt + " " + (padding + " ") * repeats
                    prompt = prompt[:target_chars]
                
                variable_prompts.append(prompt.strip())
        
        return variable_prompts


# Preset dataset configurations
DATASET_PRESETS = {
    "sharegpt": {
        "dataset_name": "anon8231489123/ShareGPT_Vicuna_unfiltered",
        "text_column": "conversations",
        "description": "Real conversations from ShareGPT"
    },
    "anthropic_hh": {
        "dataset_name": "Anthropic/hh-rlhf",
        "text_column": "chosen",
        "description": "Anthropic's helpful and harmless conversations"
    },
    "openassistant": {
        "dataset_name": "OpenAssistant/oasst1",
        "text_column": "text",
        "description": "Open Assistant conversations"
    },
    "alpaca": {
        "dataset_name": "tatsu-lab/alpaca",
        "text_column": "instruction",
        "description": "Stanford Alpaca instruction dataset"
    },
    "code_contests": {
        "dataset_name": "deepmind/code_contests",
        "text_column": "description",
        "description": "Competitive programming problems"
    },
    "wikitext": {
        "dataset_name": "wikitext",
        "dataset_config": "wikitext-103-v1",
        "text_column": "text",
        "description": "Wikipedia articles"
    },
}


def get_dataset_preset(preset_name: str) -> Dict[str, Any]:
    """Get configuration for a preset dataset.
    
    Args:
        preset_name: Name of the preset (see DATASET_PRESETS)
        
    Returns:
        Configuration dict for DatasetLoader.from_huggingface()
    """
    if preset_name not in DATASET_PRESETS:
        available = ", ".join(DATASET_PRESETS.keys())
        raise ValueError(f"Unknown preset '{preset_name}'. Available: {available}")
    
    return DATASET_PRESETS[preset_name].copy()
