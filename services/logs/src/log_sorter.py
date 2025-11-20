import os
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class LogSorter:
    def __init__(self, source_dir: Path, target_dir: Path):
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.categories = {
            "client": ["client"],
            "server": ["server"],
            "monitoring": ["monitor", "prometheus", "grafana", "loki"],
        }

    def sort(self):
        if not self.source_dir.exists():
            logger.warning(f"Source directory {self.source_dir} does not exist.")
            return

        self.target_dir.mkdir(parents=True, exist_ok=True)

        for item in self.source_dir.rglob("*"):
            if item.is_file():
                # Skip if it's already in the target structure (if source is parent of target, which shouldn't be)
                # But here we assume source and target are separate or target is outside source.
                
                category = "other"
                filename_lower = item.name.lower()
                
                for cat, keywords in self.categories.items():
                    if any(keyword in filename_lower for keyword in keywords):
                        category = cat
                        break
                
                dest_dir = self.target_dir / category
                dest_dir.mkdir(parents=True, exist_ok=True)
                
                dest_file = dest_dir / item.name
                
                # Copy if not exists or newer
                if not dest_file.exists() or item.stat().st_mtime > dest_file.stat().st_mtime:
                    try:
                        shutil.copy2(item, dest_file)
                        logger.info(f"Sorted {item.name} to {category}")
                    except Exception as e:
                        logger.error(f"Failed to copy {item.name}: {e}")

