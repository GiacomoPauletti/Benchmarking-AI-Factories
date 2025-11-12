import os
import requests
import getpass
import logging
import subprocess
from typing import Optional
from .slurm_token import SlurmToken
from client_service.ssh_manager import SSHManager

# Default values
DEFAULT_URL = "http://slurmrestd.meluxina.lxp.lu:6820"
DEFAULT_API_VER = "v0.0.40"
DEFAULT_ACCOUNT = "p200981"

logger = logging.getLogger(__name__)


class SlurmConfig:
    """SLURM configuration manager (Singleton).
    
    Manages SLURM REST API configuration and JWT token handling.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super(SlurmConfig, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Prevent re-initialization of singleton
        if self._initialized:
            return
            
        self._ssh_manager = SSHManager.get_instance()

        self._url = DEFAULT_URL
        self._api_ver = DEFAULT_API_VER
        self._account = DEFAULT_ACCOUNT
        self._user_name = self._detect_username()
        self._token: Optional[SlurmToken] = None
        
        # Try to get token from environment first
        logger.info("Initializing SlurmConfig singleton...")
        raw_token = self.create_new_token()
        if raw_token:
            self._token = SlurmToken(raw_token)
            logger.info("SlurmConfig singleton initialized successfully with token from environment")
        else:
            logger.info("SlurmConfig initialized without token (will need SSH manager to fetch)")
        
        self._initialized = True
    
    @classmethod
    def get_instance(cls):
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

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

    def get_slurm_token(self) -> str:
        """Fetch a fresh SLURM JWT token from MeluXina via SSH.
        
            
        Returns:
            SLURM JWT token string
            
        Raises:
            RuntimeError: If token fetch fails
        """
        logger.info("Fetching SLURM JWT token from MeluXina...")
        success, stdout, stderr = self._ssh_manager.execute_remote_command("scontrol token", timeout=10)
        
        if not success:
            raise RuntimeError(f"Failed to fetch SLURM token: {stderr}")

        # Parse output: "SLURM_JWT=eyJhbGc..."
        for line in stdout.strip().split('\n'):
            if line.startswith('SLURM_JWT='):
                token = line.split('=', 1)[1].strip()
                logger.info("Successfully fetched SLURM JWT token")
                logger.info(f"SLURM JWT token: {token}")
                return token
        
        logger.error("SLURM token not found in command output. Raising error.")
        raise RuntimeError(f"Could not parse SLURM token from output: {stdout}")

    def create_new_token(self, lifetime: int = 300) -> Optional[str]:
        """
        Create a new JWT token for Slurm authentication.
        
        If ssh_manager is provided, will fetch token via SSH.
        Otherwise, checks environment for existing token.
        
        Args:
            ssh_manager: Optional SSHManager instance for fetching token via SSH
            lifetime: Token lifetime in seconds (ignored when using SSH)
            
        Returns:
            JWT token string or None if not available
        """
        # Try SSH method first if SSH manager is provided
        logger.info("Fetching new token via SSH...")
        return self.get_slurm_token()

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
        return SlurmConfig.get_instance()

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