"""
Log Categorization Service.
Organizes and categorizes logs by service/microservice type.
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime
import re


class LogCategorizer:
    """Categorizes logs into service-specific directories."""
    
    # Define log patterns for different services
    SERVICE_PATTERNS = {
        'server': [
            r'server[-_]',
            r'orchestrator',
        ],
        'client': [
            r'client[-_]',
            r'loadgen[-_]',
        ],
        'monitoring': [
            r'monitor',
            r'prometheus',
            r'grafana',
        ],
        'vllm': [
            r'vllm',
            r'model[-_]server',
            r'inference',
        ],
        'slurm': [
            r'\.err$',
            r'\.out$',
            r'slurm[-_]',
            r'sbatch',
        ],
        'logs': [
            r'logs[-_]service',
        ],
    }
    
    def __init__(self, source_dir: Path, categorized_dir: Path):
        """Initialize log categorizer.
        
        Args:
            source_dir: Source directory containing raw synced logs
            categorized_dir: Destination directory for categorized logs
        """
        self.logger = logging.getLogger(__name__)
        self.source_dir = source_dir
        self.categorized_dir = categorized_dir
        
        # Ensure categorized directories exist
        self.categorized_dir.mkdir(parents=True, exist_ok=True)
        for service in self.SERVICE_PATTERNS.keys():
            (self.categorized_dir / service).mkdir(parents=True, exist_ok=True)
        
        # Uncategorized directory for logs that don't match any pattern
        (self.categorized_dir / 'uncategorized').mkdir(parents=True, exist_ok=True)
    
    def categorize_log_file(self, log_file: Path) -> str:
        """Determine which service category a log file belongs to.
        
        Args:
            log_file: Path to the log file
            
        Returns:
            Service name or 'uncategorized'
        """
        filename = log_file.name.lower()
        
        # Check each service's patterns
        for service, patterns in self.SERVICE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename, re.IGNORECASE):
                    return service
        
        return 'uncategorized'
    
    def categorize_all_logs(self) -> Dict[str, int]:
        """Categorize all logs from source directory into service-specific subdirectories.
        
        Returns:
            Dictionary with counts per category
        """
        if not self.source_dir.exists():
            self.logger.warning(f"Source directory does not exist: {self.source_dir}")
            return {}
        
        stats = {service: 0 for service in self.SERVICE_PATTERNS.keys()}
        stats['uncategorized'] = 0
        
        # Process all log files recursively
        log_files = list(self.source_dir.rglob('*'))
        
        for log_file in log_files:
            # Skip directories
            if log_file.is_dir():
                continue
            
            # Skip hidden files and system files
            if log_file.name.startswith('.'):
                continue
            
            # Categorize the log file
            category = self.categorize_log_file(log_file)
            
            # Create destination path maintaining subdirectory structure
            relative_path = log_file.relative_to(self.source_dir)
            dest_file = self.categorized_dir / category / relative_path
            
            # Create symlink in categorized location
            try:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                if dest_file.exists() or dest_file.is_symlink():
                    dest_file.unlink()
                dest_file.symlink_to(log_file)
                stats[category] += 1
                self.logger.debug(f"Categorized {log_file.name} -> {category} (symlink)")
            except Exception as e:
                self.logger.error(f"Failed to link {log_file} to {dest_file}: {e}")
        
        # Log summary
        total = sum(stats.values())
        self.logger.info(f"Categorized {total} log files:")
        for service, count in sorted(stats.items()):
            if count > 0:
                self.logger.info(f"  {service}: {count} files")
        
        return stats
    
    def get_categorized_logs(self, service: str = None, limit: int = None) -> List[Path]:
        """Get list of categorized log files.
        
        Args:
            service: Filter by service name (optional)
            limit: Maximum number of files to return (optional)
            
        Returns:
            List of log file paths
        """
        if service:
            search_dir = self.categorized_dir / service
            if not search_dir.exists():
                return []
        else:
            search_dir = self.categorized_dir
        
        # Get all log files sorted by modification time (newest first)
        log_files = sorted(
            [f for f in search_dir.rglob('*') if f.is_file() and not f.name.startswith('.')],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        if limit:
            log_files = log_files[:limit]
        
        return log_files
    
    def get_log_content(self, log_path: Path, tail_lines: int = None) -> str:
        """Read log file content.
        
        Args:
            log_path: Path to log file
            tail_lines: If specified, return only the last N lines
            
        Returns:
            Log content as string
        """
        try:
            if not log_path.exists():
                return ""
            
            content = log_path.read_text()
            
            if tail_lines:
                lines = content.split('\n')
                content = '\n'.join(lines[-tail_lines:])
            
            return content
        except Exception as e:
            self.logger.error(f"Failed to read log file {log_path}: {e}")
            return ""
    
    def get_service_stats(self) -> Dict[str, Dict]:
        """Get statistics for each service category.
        
        Returns:
            Dictionary with service statistics
        """
        stats = {}
        
        for service in list(self.SERVICE_PATTERNS.keys()) + ['uncategorized']:
            service_dir = self.categorized_dir / service
            if not service_dir.exists():
                stats[service] = {
                    'count': 0,
                    'total_size_bytes': 0,
                    'latest_modified': None
                }
                continue
            
            log_files = [f for f in service_dir.rglob('*') if f.is_file()]
            
            total_size = sum(f.stat().st_size for f in log_files)
            
            latest_modified = None
            if log_files:
                latest_file = max(log_files, key=lambda x: x.stat().st_mtime)
                latest_modified = datetime.fromtimestamp(
                    latest_file.stat().st_mtime
                ).isoformat()
            
            stats[service] = {
                'count': len(log_files),
                'total_size_bytes': total_size,
                'latest_modified': latest_modified
            }
        
        return stats
