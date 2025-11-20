import os
import shlex
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class LogSyncer:
    def __init__(self, local_logs_dir: Path):
        self.local_logs_dir = local_logs_dir
        self.ssh_host = os.getenv("SSH_HOST")
        self.ssh_user = os.getenv("SSH_USER")
        self.ssh_port = os.getenv("SSH_PORT", "22")
        self.ssh_key = os.getenv("SSH_KEY_PATH")
        self.remote_base = os.getenv("REMOTE_BASE_PATH", "~/ai-factory-benchmarks")

        if not self.ssh_host or not self.ssh_user:
            logger.warning("SSH_HOST and SSH_USER must be defined in environment variables for LogSyncer to work.")

    def sync(self):
        if not self.ssh_host or not self.ssh_user:
            return

        self.local_logs_dir.mkdir(parents=True, exist_ok=True)

        remote_logs = f"{self.remote_base.rstrip('/')}/logs/"

        ssh_cmd = ["ssh", "-p", self.ssh_port]
        if self.ssh_key:
            # In docker, the key might be mounted.
            # We need to ensure permissions are correct if we copy it, 
            # but usually we just point to it.
            # However, ssh requires strict permissions.
            ssh_cmd.extend(["-i", os.path.expanduser(self.ssh_key)])
        
        # Disable strict host key checking for automation
        ssh_cmd.extend(["-o", "StrictHostKeyChecking=no"])
        ssh_cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])

        rsync_cmd = [
            "rsync",
            "-avz",
            "--partial",
            # "--progress", # clutter logs
            "-e",
            " ".join(shlex.quote(part) for part in ssh_cmd),
            f"{self.ssh_user}@{self.ssh_host}:{remote_logs}",
            str(self.local_logs_dir),
        ]

        try:
            logger.info("Starting log sync...")
            subprocess.run(rsync_cmd, check=True, capture_output=True, text=True)
            logger.info("Log sync completed successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Log sync failed: {e.stderr}")
        except Exception as e:
            logger.error(f"An error occurred during log sync: {e}")
