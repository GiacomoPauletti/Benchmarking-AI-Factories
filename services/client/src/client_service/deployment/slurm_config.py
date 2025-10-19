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
        logger.info("Initializing SlurmConfig and generating JWT token...")
        raw_token = self.create_new_token()
        if raw_token:
            self._token = SlurmToken(raw_token)
            logger.info("SlurmConfig initialized successfully with valid token")
        else:
            logger.warning("SlurmConfig initialized but no token available")

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
        
        This method is DISABLED in container mode. Tokens are generated on the host
        and passed to the container via environment variables.
        
        Args:
            lifetime: Token lifetime in seconds (ignored in container mode)
            
        Returns:
            JWT token string from environment or None if not available
        """
        logger.warning("create_new_token() called - token generation is disabled in container mode")
        logger.info("Tokens are generated on the host and passed via SLURM_JWT environment variable")
        
        # Only check for existing token in environment
        env_token = os.getenv('SLURM_JWT')
        if env_token:
            logger.info("Using token from SLURM_JWT environment variable")
            return env_token
        else:
            logger.error("No SLURM_JWT token found in environment")
            logger.error("This indicates the host failed to generate a token")
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
            logger.error("Continuing with auto-detected values")
            
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
        
        This method is DISABLED in container mode. Token refresh is not supported
        when running in containers.
        
        Args:
            threshold_seconds: Refresh token if it expires within this many seconds (ignored)
            
        Returns:
            False - refresh is not supported in container mode
        """
        logger.warning("refresh_token_if_needed() called - token refresh is disabled in container mode")
        logger.info("Container uses pre-generated tokens from the host, refresh is not supported")
        
        if not self._token:
            logger.error("No token available and refresh is disabled")
            return False
        elif self._token.has_expired():
            logger.error("Token has expired and refresh is disabled in container mode")
            logger.error("Please restart the container to get a new token from the host")
            return False
        elif self._token.is_expiring_soon(threshold_seconds):
            logger.warning(f"Token expires in less than {threshold_seconds} seconds but refresh is disabled")
            logger.warning("Please restart the container soon to get a new token")
            return False
        
        return False

    def __str__(self):
        token_status = '***' if self._token and self._token.is_valid else 'None'
        return f"SlurmConfig(url={self._url}, jwt={token_status}, api_ver={self._api_ver}, user_name={self._user_name}, account={self._account})"