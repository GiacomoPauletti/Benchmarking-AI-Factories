"""
Unit tests for slurm_token module
"""

import unittest
from unittest.mock import Mock, patch
import base64
import json
import time

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from client_service.deployment.slurm_token import SlurmToken


class TestSlurmToken(unittest.TestCase):
    
    def setUp(self):
        """Set up test JWT tokens"""
        # Create a valid JWT token for testing
        self.current_time = int(time.time())
        
        # Valid token data
        self.valid_header = {"alg": "HS256", "typ": "JWT"}
        self.valid_payload = {
            "sun": "testuser",
            "iat": self.current_time - 300,  # Issued 5 minutes ago
            "exp": self.current_time + 300,  # Expires in 5 minutes
            "aud": "slurm",
            "custom_claim": "test_value"
        }
        
        # Create encoded token
        header_encoded = base64.b64encode(json.dumps(self.valid_header).encode()).decode().rstrip('=')
        payload_encoded = base64.b64encode(json.dumps(self.valid_payload).encode()).decode().rstrip('=')
        signature = "fake_signature"
        
        self.valid_token_string = f"{header_encoded}.{payload_encoded}.{signature}"
        
        # Expired token
        self.expired_payload = {
            "sun": "testuser",
            "iat": self.current_time - 600,  # Issued 10 minutes ago
            "exp": self.current_time - 300,  # Expired 5 minutes ago
            "aud": "slurm"
        }
        
        expired_payload_encoded = base64.b64encode(json.dumps(self.expired_payload).encode()).decode().rstrip('=')
        self.expired_token_string = f"{header_encoded}.{expired_payload_encoded}.{signature}"
    
    def test_valid_token_initialization(self):
        """Test initialization with valid token"""
        token = SlurmToken(self.valid_token_string)
        
        self.assertTrue(token.is_valid)
        self.assertEqual(token.header, self.valid_header)
        self.assertEqual(token.payload, self.valid_payload)
        self.assertEqual(token.signature, "fake_signature")
    
    def test_token_with_whitespace(self):
        """Test token initialization with whitespace"""
        token_with_whitespace = f"  {self.valid_token_string}  \n"
        token = SlurmToken(token_with_whitespace)
        
        self.assertTrue(token.is_valid)
        self.assertEqual(str(token), self.valid_token_string)
    
    def test_invalid_token_format(self):
        """Test initialization with invalid token format"""
        # Token with wrong number of parts
        invalid_token = "header.payload"  # Missing signature
        token = SlurmToken(invalid_token)
        
        self.assertFalse(token.is_valid)
        self.assertIsNone(token.header)
        self.assertIsNone(token.payload)
        self.assertIsNone(token.signature)
    
    def test_invalid_base64_encoding(self):
        """Test initialization with invalid base64 encoding"""
        invalid_token = "invalid_base64.invalid_base64.signature"
        token = SlurmToken(invalid_token)
        
        self.assertFalse(token.is_valid)
    
    def test_invalid_json_in_token(self):
        """Test initialization with invalid JSON in token parts"""
        # Create token with invalid JSON
        invalid_json = "not_json"
        invalid_encoded = base64.b64encode(invalid_json.encode()).decode()
        invalid_token = f"{invalid_encoded}.{invalid_encoded}.signature"
        
        token = SlurmToken(invalid_token)
        
        self.assertFalse(token.is_valid)
    
    def test_username_property(self):
        """Test username extraction"""
        token = SlurmToken(self.valid_token_string)
        
        self.assertEqual(token.username, "testuser")
    
    def test_username_missing(self):
        """Test username when 'sun' field is missing"""
        payload_without_user = {"iat": self.current_time, "exp": self.current_time + 300}
        payload_encoded = base64.b64encode(json.dumps(payload_without_user).encode()).decode().rstrip('=')
        header_encoded = base64.b64encode(json.dumps(self.valid_header).encode()).decode().rstrip('=')
        token_string = f"{header_encoded}.{payload_encoded}.signature"
        
        token = SlurmToken(token_string)
        
        self.assertTrue(token.is_valid)
        self.assertIsNone(token.username)
    
    def test_timestamp_properties(self):
        """Test issued_at and expires_at properties"""
        token = SlurmToken(self.valid_token_string)
        
        self.assertEqual(token.issued_at, self.current_time - 300)
        self.assertEqual(token.expires_at, self.current_time + 300)
    
    def test_timestamp_properties_missing(self):
        """Test timestamp properties when fields are missing"""
        payload_without_timestamps = {"sun": "testuser"}
        payload_encoded = base64.b64encode(json.dumps(payload_without_timestamps).encode()).decode().rstrip('=')
        header_encoded = base64.b64encode(json.dumps(self.valid_header).encode()).decode().rstrip('=')
        token_string = f"{header_encoded}.{payload_encoded}.signature"
        
        token = SlurmToken(token_string)
        
        self.assertTrue(token.is_valid)
        self.assertIsNone(token.issued_at)
        self.assertIsNone(token.expires_at)
    
    def test_has_expired_valid_token(self):
        """Test expiration check for valid token"""
        token = SlurmToken(self.valid_token_string)
        
        self.assertFalse(token.has_expired())
    
    def test_has_expired_expired_token(self):
        """Test expiration check for expired token"""
        token = SlurmToken(self.expired_token_string)
        
        self.assertTrue(token.has_expired())
    
    def test_has_expired_no_expiration(self):
        """Test expiration check when expiration field is missing"""
        payload_without_exp = {"sun": "testuser", "iat": self.current_time}
        payload_encoded = base64.b64encode(json.dumps(payload_without_exp).encode()).decode().rstrip('=')
        header_encoded = base64.b64encode(json.dumps(self.valid_header).encode()).decode().rstrip('=')
        token_string = f"{header_encoded}.{payload_encoded}.signature"
        
        token = SlurmToken(token_string)
        
        # Should return True (assume expired) when expiration cannot be determined
        self.assertTrue(token.has_expired())
    
    def test_remaining_lifetime(self):
        """Test remaining lifetime calculation"""
        token = SlurmToken(self.valid_token_string)
        
        remaining = token.remaining_lifetime()
        # Should be around 300 seconds (5 minutes), allow some tolerance for test execution time
        self.assertTrue(290 <= remaining <= 310)
    
    def test_remaining_lifetime_expired(self):
        """Test remaining lifetime for expired token"""
        token = SlurmToken(self.expired_token_string)
        
        remaining = token.remaining_lifetime()
        self.assertEqual(remaining, 0)
    
    def test_remaining_lifetime_no_expiration(self):
        """Test remaining lifetime when expiration is missing"""
        payload_without_exp = {"sun": "testuser"}
        payload_encoded = base64.b64encode(json.dumps(payload_without_exp).encode()).decode().rstrip('=')
        header_encoded = base64.b64encode(json.dumps(self.valid_header).encode()).decode().rstrip('=')
        token_string = f"{header_encoded}.{payload_encoded}.signature"
        
        token = SlurmToken(token_string)
        
        self.assertEqual(token.remaining_lifetime(), 0)
    
    def test_lifetime_minutes(self):
        """Test remaining lifetime in minutes"""
        token = SlurmToken(self.valid_token_string)
        
        minutes = token.lifetime_minutes()
        # Should be around 5 minutes
        self.assertTrue(4.8 <= minutes <= 5.2)
    
    def test_total_lifetime(self):
        """Test total lifetime calculation"""
        token = SlurmToken(self.valid_token_string)
        
        total = token.total_lifetime()
        # Should be 600 seconds (10 minutes total: 5 minutes passed + 5 minutes remaining)
        self.assertEqual(total, 600)
    
    def test_total_lifetime_missing_fields(self):
        """Test total lifetime when timestamp fields are missing"""
        payload_partial = {"sun": "testuser", "iat": self.current_time}  # Missing exp
        payload_encoded = base64.b64encode(json.dumps(payload_partial).encode()).decode().rstrip('=')
        header_encoded = base64.b64encode(json.dumps(self.valid_header).encode()).decode().rstrip('=')
        token_string = f"{header_encoded}.{payload_encoded}.signature"
        
        token = SlurmToken(token_string)
        
        self.assertIsNone(token.total_lifetime())
    
    def test_is_expiring_soon_true(self):
        """Test is_expiring_soon when token expires within threshold"""
        token = SlurmToken(self.valid_token_string)
        
        # With default threshold of 60 seconds, and token expiring in ~300 seconds
        self.assertFalse(token.is_expiring_soon())
        
        # With high threshold, should be expiring soon
        self.assertTrue(token.is_expiring_soon(threshold_seconds=400))
    
    def test_is_expiring_soon_false(self):
        """Test is_expiring_soon when token has plenty of time left"""
        token = SlurmToken(self.valid_token_string)
        
        # With low threshold, should not be expiring soon
        self.assertFalse(token.is_expiring_soon(threshold_seconds=30))
    
    def test_is_expiring_soon_expired(self):
        """Test is_expiring_soon for expired token"""
        token = SlurmToken(self.expired_token_string)
        
        # Expired token should always be considered as expiring soon
        self.assertTrue(token.is_expiring_soon())
    
    def test_get_all_claims(self):
        """Test getting all claims from token"""
        token = SlurmToken(self.valid_token_string)
        
        claims = token.get_all_claims()
        
        self.assertEqual(claims, self.valid_payload)
        self.assertIsNot(claims, self.valid_payload)  # Should be a copy
    
    def test_get_all_claims_invalid_token(self):
        """Test getting claims from invalid token"""
        token = SlurmToken("invalid.token.format")
        
        claims = token.get_all_claims()
        
        self.assertEqual(claims, {})
    
    def test_str_representation(self):
        """Test string representation returns original token"""
        token = SlurmToken(self.valid_token_string)
        
        self.assertEqual(str(token), self.valid_token_string)
    
    def test_repr_valid_token(self):
        """Test repr for valid token"""
        token = SlurmToken(self.valid_token_string)
        
        repr_str = repr(token)
        
        self.assertIn("SlurmToken", repr_str)
        self.assertIn("testuser", repr_str)
        self.assertIn("expires_in=", repr_str)
        self.assertIn("valid=True", repr_str)
    
    def test_repr_invalid_token(self):
        """Test repr for invalid token"""
        token = SlurmToken("invalid.token")
        
        repr_str = repr(token)
        
        self.assertEqual(repr_str, "SlurmToken(invalid)")
    
    def test_base64_padding_handling(self):
        """Test that base64 padding is handled correctly"""
        # Create token parts that need padding
        header_data = json.dumps({"alg": "HS256", "typ": "JWT"})
        payload_data = json.dumps({"sun": "user", "exp": self.current_time + 300})
        
        # Encode without padding
        header_encoded = base64.b64encode(header_data.encode()).decode().rstrip('=')
        payload_encoded = base64.b64encode(payload_data.encode()).decode().rstrip('=')
        
        token_string = f"{header_encoded}.{payload_encoded}.signature"
        
        token = SlurmToken(token_string)
        
        self.assertTrue(token.is_valid)
        self.assertEqual(token.username, "user")
    
    @patch('time.time')
    def test_expiration_edge_cases(self, mock_time):
        """Test expiration checking at exact expiration time"""
        # Set current time to exactly match expiration
        mock_time.return_value = self.current_time + 300
        
        token = SlurmToken(self.valid_token_string)
        
        # At exact expiration time, should be considered expired
        self.assertTrue(token.has_expired())
        self.assertEqual(token.remaining_lifetime(), 0)
    
    def test_negative_remaining_lifetime_handled(self):
        """Test that negative remaining lifetime is handled correctly"""
        token = SlurmToken(self.expired_token_string)
        
        # Should never return negative remaining lifetime
        self.assertEqual(token.remaining_lifetime(), 0)
        self.assertTrue(token.remaining_lifetime() >= 0)


if __name__ == '__main__':
    unittest.main()