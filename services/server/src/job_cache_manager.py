"""
Job cache manager for SLURM jobs.
Handles caching of statuses, and job details with background updates.
"""

import logging
import threading
import time
from typing import Dict, Any, Tuple, Optional, Callable, List
from pathlib import Path


class JobCacheManager:
    """Manages caching and background updates for SLURM job data.
    
    This class provides:
    - In-memory caching with TTL for statuses, and job details
    - Background thread that periodically updates active jobs
    - Thread-safe operations
    """
    
    def __init__(self, 
                 cache_ttl: int = 10,
                 update_interval: int = 8):
        """Initialize the job cache manager.
        
        Args:
            cache_ttl: Cache time-to-live in seconds (default: 10s)
            update_interval: Background update interval in seconds (default: 8s)
        """
        self.logger = logging.getLogger(__name__)
        
        # Cache storage
        self._status_cache: Dict[str, Tuple[float, str]] = {}  # {job_id: (timestamp, status)}
        self._job_details_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}  # {job_id: (timestamp, details)}
        
        # Cache configuration
        self._cache_ttl = cache_ttl
        self._cache_lock = threading.RLock()
        
        # Background update system
        self._active_jobs: set = set()  # Jobs being actively tracked
        self._background_thread: Optional[threading.Thread] = None
        self._stop_background = threading.Event()
        self._update_interval = update_interval
        
        # Callbacks for fetching fresh data (set by SlurmDeployer)
        self._fetch_status_callback: Optional[Callable[[str], str]] = None
        self._fetch_details_callback: Optional[Callable[[str], Dict[str, Any]]] = None
        self._sync_logs: Optional[Callable[[], None]] = None
    
    def set_fetch_callbacks(self,
                            sync_logs: Callable[[], None],
                            fetch_status: Callable[[str], str],
                            fetch_details: Callable[[str], Dict[str, Any]]):
        """Set the callback functions for fetching fresh data.
        
        Args:
            sync_logs: Function to sync log files from remote
            fetch_status: Function to fetch job status from SLURM API
            fetch_details: Function to fetch job details from SLURM API
        """
        self._sync_logs = sync_logs
        self._fetch_status_callback = fetch_status
        self._fetch_details_callback = fetch_details
    
    def start_background_updates(self):
        """Start the background thread for periodic updates."""
        if self._background_thread is None or not self._background_thread.is_alive():
            self._stop_background.clear()
            self._background_thread = threading.Thread(
                target=self._background_update_worker,
                daemon=True,
                name="JobCacheBackgroundUpdater"
            )
            self._background_thread.start()
            self.logger.info(f"Started background update thread (interval: {self._update_interval}s, TTL: {self._cache_ttl}s)")
    
    def stop_background_updates(self):
        """Stop the background update thread gracefully."""
        if self._background_thread and self._background_thread.is_alive():
            self.logger.info("Stopping background update thread...")
            self._stop_background.set()
            self._background_thread.join(timeout=5)
            self.logger.info("Background update thread stopped")
    
    def _background_update_worker(self):
        """Background worker that periodically updates statuses for active jobs."""
        self.logger.info(f"Background updater started (interval: {self._update_interval}s)")
        
        while not self._stop_background.is_set():
            try:
                # Get snapshot of active jobs (thread-safe)
                with self._cache_lock:
                    jobs_to_update = list(self._active_jobs)

                if self._sync_logs is not None:
                    try:
                        self.logger.debug("Syncing log files")
                        self._sync_logs()
                    except Exception as e:
                        self.logger.warning(f"File sync failed: {e}")
                
                if jobs_to_update:
                    self.logger.debug(f"Updating {len(jobs_to_update)} active jobs in background")
                
                for job_id in jobs_to_update:
                    if self._stop_background.is_set():
                        break
                    
                    try:
                        # Update job details (includes node allocation info)
                        if self._fetch_details_callback:
                            details = self._fetch_details_callback(job_id)
                            self._cache_details(job_id, details)
                        
                        # Update basic status from SLURM API
                        if self._fetch_status_callback:
                            status = self._fetch_status_callback(job_id)
                            self._cache_status(job_id, status)
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to update job {job_id} in background: {e}")
                
                # Sleep until next update cycle
                self._stop_background.wait(timeout=self._update_interval)
                
            except Exception as e:
                self.logger.exception(f"Error in background update worker: {e}")
                # Continue running despite errors
                self._stop_background.wait(timeout=self._update_interval)
        
        self.logger.info("Background updater stopped")
    
    def track_job(self, job_id: str):
        """Add a job to the background update tracking list.
        
        Args:
            job_id: The SLURM job ID to track
        """
        with self._cache_lock:
            self._active_jobs.add(str(job_id))
        self.logger.debug(f"Now tracking job {job_id} for background updates")
    
    def untrack_job(self, job_id: str):
        """Remove a job from the background update tracking list.
        
        Args:
            job_id: The SLURM job ID to stop tracking
        """
        with self._cache_lock:
            self._active_jobs.discard(str(job_id))
        self.logger.debug(f"Stopped tracking job {job_id}")
    
    def _is_cache_valid(self, timestamp: float) -> bool:
        """Check if cached data is still valid based on TTL.
        
        Args:
            timestamp: The timestamp when data was cached
            
        Returns:
            True if cache is still valid, False if expired
        """
        return (time.time() - timestamp) < self._cache_ttl
    
    def _cache_status(self, job_id: str, status: str):
        """Cache a job status.
        
        Args:
            job_id: The SLURM job ID
            status: The status to cache
        """
        with self._cache_lock:
            self._status_cache[str(job_id)] = (time.time(), status)
    
    def _cache_details(self, job_id: str, details: Dict[str, Any]):
        """Cache job details.
        
        Args:
            job_id: The SLURM job ID
            details: The job details to cache
        """
        with self._cache_lock:
            self._job_details_cache[str(job_id)] = (time.time(), details)
    
    def get_status(self, job_id: str, fetch_if_missing: bool = True) -> Optional[str]:
        """Get job status from cache or fetch if needed.
        
        Args:
            job_id: The SLURM job ID
            fetch_if_missing: If True, fetch fresh data on cache miss (default: True)
            
        Returns:
            The job status, or None if not available and fetch_if_missing is False
        """
        job_id = str(job_id)
        
        # Check cache first
        with self._cache_lock:
            if job_id in self._status_cache:
                timestamp, cached_status = self._status_cache[job_id]
                if self._is_cache_valid(timestamp):
                    self.logger.debug(f"Cache hit for status of job {job_id}: {cached_status}")
                    return cached_status
        
        # Cache miss or expired
        if fetch_if_missing and self._fetch_status_callback:
            self.logger.debug(f"Cache miss for status of job {job_id}, fetching fresh data")
            status = self._fetch_status_callback(job_id)
            self._cache_status(job_id, status)
            return status
        
        return None
    
    def get_details(self, job_id: str, fetch_if_missing: bool = True) -> Optional[Dict[str, Any]]:
        """Get job details from cache or fetch if needed.
        
        Args:
            job_id: The SLURM job ID
            fetch_if_missing: If True, fetch fresh data on cache miss (default: True)
            
        Returns:
            The job details, or None if not available and fetch_if_missing is False
        """
        job_id = str(job_id)
        
        # Check cache first
        with self._cache_lock:
            if job_id in self._job_details_cache:
                timestamp, cached_details = self._job_details_cache[job_id]
                if self._is_cache_valid(timestamp):
                    self.logger.debug(f"Cache hit for details of job {job_id}")
                    return cached_details
        
        # Cache miss or expired
        if fetch_if_missing and self._fetch_details_callback:
            self.logger.debug(f"Cache miss for details of job {job_id}, fetching fresh data")
            details = self._fetch_details_callback(job_id)
            self._cache_details(job_id, details)
            return details
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the caching system for debugging.
        
        Returns:
            Dictionary containing cache statistics
        """
        with self._cache_lock:
            return {
                "active_jobs": len(self._active_jobs),
                "tracked_jobs": list(self._active_jobs),
                "cached_statuses": len(self._status_cache),
                "cached_details": len(self._job_details_cache),
                "cache_ttl_seconds": self._cache_ttl,
                "update_interval_seconds": self._update_interval,
                "background_thread_alive": self._background_thread.is_alive() if self._background_thread else False
            }
    
    def clear_cache(self, job_id: Optional[str] = None):
        """Clear cache entries.
        
        Args:
            job_id: If provided, clear cache only for this job. If None, clear all caches.
        """
        with self._cache_lock:
            if job_id:
                job_id = str(job_id)
                self._status_cache.pop(job_id, None)
                self._job_details_cache.pop(job_id, None)
                self.logger.debug(f"Cleared cache for job {job_id}")
            else:
                self._status_cache.clear()
                self._job_details_cache.clear()
                self.logger.info("Cleared all caches")
