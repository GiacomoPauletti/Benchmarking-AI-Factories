import os
import requests
import getpass
import logging
import subprocess
from typing import Optional
from .slurm_token import SlurmToken

# Default values
DEFAULT_URL = "http://slurmrestd.meluxina.lxp.lu:6820"
DEFAULT_API_VER = "v0.0.40"
DEFAULT_ACCOUNT = "p200981"

logger = logging.getLogger(__name__)


class SlurmConfig:
    def __init__(self):
        self._url = DEFAULT_URL
        self._api_ver = DEFAULT_API_VER
        self._account = DEFAULT_ACCOUNT
        self._user_name = self._detect_username()
        self._token: Optional[SlurmToken] = None
        
        # Generate token automatically

    def _detect_username(self) -> str:
        """Automatically detect the current user"""
        # Try environment variables first
        username = os.getenv('USER') or os.getenv('USERNAME')
        if username:
            return username
        
        # Fallback to getpass
        try:
            return getpass.getuser()
        except Exception:
            logger.warning("Could not detect username automatically")
            return ""

    def create_new_token(self, lifetime: int = 300) -> Optional[str]:
        """
        Create a new JWT token for Slurm authentication.
        
        Args:
            lifetime: Token lifetime in seconds (default: 300)
            
        Returns:
            JWT token string or None if creation failed
        """
        if not self._user_name:
            logger.error("Cannot create token: username not available")
            return None
            
        try:
            logger.info(f"Creating new Slurm token for user {self._user_name} with lifetime {lifetime}s")
            
            # Try different methods to obtain a JWT token
            
            # Method 1: Try to use scontrol to generate a token
            import subprocess
            try:
                cmd = ["scontrol", "token", f"lifespan={lifetime}"]
                # Use older subprocess API for compatibility
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                stdout, stderr = process.communicate()
                
                if process.returncode == 0 and "SLURM_JWT=" in stdout:
                    # Extract token from output like "SLURM_JWT=eyJ..."
                    for line in stdout.split('\n'):
                        if line.strip().startswith('SLURM_JWT='):
                            token = line.split('=', 1)[1].strip()
                            logger.info("Successfully created token using scontrol")
                            return token
                else:
                    logger.debug(f"scontrol failed: {stderr}")
            except (OSError, FileNotFoundError) as e:
                logger.debug(f"scontrol not available or failed: {e}")
            
            # Method 2: Try to make REST API call to Slurm auth endpoint
            try:
                auth_url = f"{self._url}/slurm/{self._api_ver}/auth"
                
                # Try with different authentication methods
                # This would need proper authentication credentials
                # For now, we'll skip this as it requires user credentials
                logger.debug("REST API token creation requires user credentials - skipping")
                
            except Exception as e:
                logger.debug(f"REST API token creation failed: {e}")
            
            # Method 3: Check for existing token in environment
            env_token = os.getenv('SLURM_JWT')
            if env_token:
                logger.info("Using existing token from SLURM_JWT environment variable")
                return env_token
                
            # If all methods fail, return None
            logger.warning("Token creation not available - will need to use existing authentication method")
            return None
            
        except Exception as e:
            logger.error(f"Failed to create Slurm token: {e}")
            return None

    @classmethod
    def load_from_file(cls, file_path: str):
        """Load configuration from file (backward compatibility)"""
        instance = cls()
        
        try:
            with open(file_path, 'r') as file:
                lines = file.readlines()
                config_dict = {}
                for line in lines:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        config_dict[key] = value

                instance._url = config_dict.get('url', DEFAULT_URL)
                instance._user_name = config_dict.get('user_name', instance._user_name)
                instance._api_ver = config_dict.get('api_ver', DEFAULT_API_VER)
                instance._account = config_dict.get('account', DEFAULT_ACCOUNT)
                
                # If JWT is provided in file, use it; otherwise keep auto-generated one
                file_jwt = config_dict.get('jwt', '')
                if file_jwt:
                    instance._token = SlurmToken(file_jwt)
                
        except Exception as e:
            logger.error(f"Failed to load config from file {file_path}: {e}")
            # Continue with auto-detected values
            
        return instance

    @staticmethod
    def tmp_load_default():
        """Create default configuration with auto-detection"""
        return SlurmConfig()

        # Getter methods for external access
    @property
    def url(self) -> str:
        return self._url

    @property
    def jwt(self) -> Optional[str]:
        """Get the raw JWT token string for backward compatibility."""
        return str(self._token) if self._token else None

    @property
    def token(self) -> Optional[SlurmToken]:
        """Get the SlurmToken object with all its functionality."""
        return self._token

    @property
    def api_ver(self) -> str:
        return self._api_ver

    @property
    def user_name(self) -> str:
        return self._user_name

    @property
    def account(self) -> str:
        return self._account

    def refresh_token_if_needed(self, threshold_seconds: int = 60) -> bool:
        """
        Refresh the token if it's expiring soon or has expired.
        
        Args:
            threshold_seconds: Refresh token if it expires within this many seconds
            
        Returns:
            True if token was refreshed, False otherwise
        """
        if not self._token or self._token.has_expired() or self._token.is_expiring_soon(threshold_seconds):
            logger.info("Token is expired or expiring soon, attempting to refresh...")
            raw_token = self.create_new_token()
            if raw_token:
                self._token = SlurmToken(raw_token)
                logger.info("Token refreshed successfully")
                return True
            else:
                logger.error("Failed to refresh token")
                return False
        return False

    def __str__(self):
        token_status = '***' if self._token and self._token.is_valid else 'None'
        return f"SlurmConfig(url={self._url}, jwt={token_status}, api_ver={self._api_ver}, user_name={self._user_name}, account={self._account})"