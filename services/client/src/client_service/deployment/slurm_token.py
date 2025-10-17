import base64
import json
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SlurmToken:
    """
    A class to handle Slurm JWT tokens with automatic decoding, expiration checking,
    and useful utility methods.
    """
    
    def __init__(self, encoded_token: str):
        """
        Initialize SlurmToken with an encoded JWT token.
        
        Args:
            encoded_token: The base64-encoded JWT token string
        """
        self._encoded_token = encoded_token.strip()
        self._header: Optional[Dict[str, Any]] = None
        self._payload: Optional[Dict[str, Any]] = None
        self._signature: Optional[str] = None
        self._decoded_successfully = False
        
        self._decode_token()
    
    def _decode_token(self) -> None:
        """Decode the JWT token into its components."""
        try:
            # JWT tokens have three parts separated by dots: header.payload.signature
            parts = self._encoded_token.split('.')
            if len(parts) != 3:
                raise ValueError(f"Invalid JWT format: expected 3 parts, got {len(parts)}")
            
            # Decode header
            header_data = self._base64_decode(parts[0])
            self._header = json.loads(header_data)
            
            # Decode payload
            payload_data = self._base64_decode(parts[1])
            self._payload = json.loads(payload_data)
            
            # Store signature (not decoded, just kept as is)
            self._signature = parts[2]
            
            self._decoded_successfully = True
            logger.debug(f"Successfully decoded JWT token for user: {self.username}")
            
        except Exception as e:
            logger.error(f"Failed to decode JWT token: {e}")
            self._decoded_successfully = False
    
    def _base64_decode(self, data: str) -> str:
        """
        Decode base64 data, handling padding if necessary.
        
        Args:
            data: Base64 encoded string
            
        Returns:
            Decoded string
        """
        # Add padding if necessary
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        
        return base64.b64decode(data).decode('utf-8')
    
    @property
    def is_valid(self) -> bool:
        """Check if the token was decoded successfully."""
        return self._decoded_successfully
    
    @property
    def header(self) -> Optional[Dict[str, Any]]:
        """Get the decoded header."""
        return self._header
    
    @property
    def payload(self) -> Optional[Dict[str, Any]]:
        """Get the decoded payload."""
        return self._payload
    
    @property
    def signature(self) -> Optional[str]:
        """Get the signature part."""
        return self._signature
    
    @property
    def username(self) -> Optional[str]:
        """Get the username from the token (usually in 'sun' field)."""
        if self._payload:
            return self._payload.get('sun')
        return None
    
    @property
    def issued_at(self) -> Optional[int]:
        """Get the issued at timestamp (iat)."""
        if self._payload:
            return self._payload.get('iat')
        return None
    
    @property
    def expires_at(self) -> Optional[int]:
        """Get the expiration timestamp (exp)."""
        if self._payload:
            return self._payload.get('exp')
        return None
    
    def has_expired(self) -> bool:
        """
        Check if the token has expired.
        
        Returns:
            True if expired, False if still valid, None if expiration cannot be determined
        """
        if not self.expires_at:
            logger.warning("Cannot determine expiration: 'exp' field not found in token")
            return True  # Assume expired if we can't determine
        
        current_time = int(time.time())
        return current_time >= self.expires_at
    
    def remaining_lifetime(self) -> int:
        """
        Get the remaining lifetime of the token in seconds.
        
        Returns:
            Seconds remaining until expiration, or 0 if expired/invalid
        """
        if not self.expires_at:
            return 0
        
        current_time = int(time.time())
        remaining = self.expires_at - current_time
        return max(0, remaining)  # Don't return negative values
    
    def lifetime_minutes(self) -> float:
        """
        Get the remaining lifetime in minutes.
        
        Returns:
            Minutes remaining until expiration
        """
        return self.remaining_lifetime() / 60.0
    
    def total_lifetime(self) -> Optional[int]:
        """
        Get the total lifetime of the token in seconds.
        
        Returns:
            Total lifetime from issued_at to expires_at, or None if cannot be determined
        """
        if not self.issued_at or not self.expires_at:
            return None
        
        return self.expires_at - self.issued_at
    
    def is_expiring_soon(self, threshold_seconds: int = 60) -> bool:
        """
        Check if the token is expiring soon.
        
        Args:
            threshold_seconds: Consider token as "expiring soon" if less than this many seconds remain
            
        Returns:
            True if expiring within threshold, False otherwise
        """
        return self.remaining_lifetime() <= threshold_seconds
    
    def get_all_claims(self) -> Dict[str, Any]:
        """
        Get all claims from the token payload.
        
        Returns:
            Dictionary of all claims, or empty dict if token is invalid
        """
        return self._payload.copy() if self._payload else {}
    
    def __str__(self) -> str:
        """Return the original encoded token when converted to string."""
        return self._encoded_token
    
    def __repr__(self) -> str:
        """Return a detailed representation of the token."""
        if not self.is_valid:
            return f"SlurmToken(invalid)"
        
        return (f"SlurmToken(user={self.username}, "
                f"expires_in={self.remaining_lifetime()}s, "
                f"valid={not self.has_expired()})")