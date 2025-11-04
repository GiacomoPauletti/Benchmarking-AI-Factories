"""
Unit tests for slurm_config module
"""

import unittest
from unittest.mock import Mock, patch, mock_open
import os

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from client_service.deployment.slurm_config import SlurmConfig, DEFAULT_URL, DEFAULT_API_VER, DEFAULT_ACCOUNT


class TestSlurmConfig(unittest.TestCase):
    
    @patch('client_service.deployment.slurm_config.SlurmToken')
    @patch('os.getenv')
    @patch('getpass.getuser')
    def test_initialization_with_env_token(self, mock_getuser, mock_getenv, mock_slurm_token_class):
        """Test SlurmConfig initialization with environment token"""
        # Setup mocks
        mock_getenv.side_effect = lambda key: {
            'USER': 'testuser',
            'SLURM_JWT': 'test-jwt-token'
        }.get(key)
        
        mock_token = Mock()
        mock_slurm_token_class.return_value = mock_token
        
        # Create config
        with patch.object(SlurmConfig, 'create_new_token', return_value='test-jwt-token'):
            config = SlurmConfig()
        
        # Verify initialization
        self.assertEqual(config.url, DEFAULT_URL)
        self.assertEqual(config.api_ver, DEFAULT_API_VER)
        self.assertEqual(config.account, DEFAULT_ACCOUNT)
        self.assertEqual(config.user_name, 'testuser')
        self.assertEqual(config.token, mock_token)
        
        # Verify token creation was called
        mock_slurm_token_class.assert_called_once_with('test-jwt-token')
    
    @patch('client_service.deployment.slurm_config.SlurmToken')
    @patch('os.getenv')
    @patch('getpass.getuser')
    def test_initialization_without_env_token(self, mock_getuser, mock_getenv, mock_slurm_token_class):
        """Test SlurmConfig initialization without environment token"""
        # Setup mocks
        mock_getenv.side_effect = lambda key: {
            'USER': 'testuser'
        }.get(key)  # No SLURM_JWT
        
        # Create config
        with patch.object(SlurmConfig, 'create_new_token', return_value=None):
            config = SlurmConfig()
        
        # Verify initialization
        self.assertEqual(config.user_name, 'testuser')
        self.assertIsNone(config.token)
        self.assertIsNone(config.jwt)
    
    @patch('os.getenv')
    @patch('getpass.getuser')
    def test_detect_username_from_env(self, mock_getuser, mock_getenv):
        """Test username detection from environment variables"""
        # Setup mock for USER env var
        mock_getenv.side_effect = lambda key: {
            'USER': 'env_user'
        }.get(key)
        
        with patch.object(SlurmConfig, 'create_new_token', return_value=None):
            config = SlurmConfig()
        
        self.assertEqual(config.user_name, 'env_user')
        mock_getuser.assert_not_called()  # Should not fallback to getpass
    
    @patch('os.getenv')
    @patch('getpass.getuser')
    def test_detect_username_from_username_env(self, mock_getuser, mock_getenv):
        """Test username detection from USERNAME environment variable"""
        # Setup mock for USERNAME env var (no USER)
        mock_getenv.side_effect = lambda key: {
            'USERNAME': 'username_user'
        }.get(key)
        
        with patch.object(SlurmConfig, 'create_new_token', return_value=None):
            config = SlurmConfig()
        
        self.assertEqual(config.user_name, 'username_user')
        mock_getuser.assert_not_called()
    
    @patch('os.getenv')
    @patch('getpass.getuser')
    def test_detect_username_fallback_to_getpass(self, mock_getuser, mock_getenv):
        """Test username detection fallback to getpass"""
        # Setup mocks - no env vars, getpass returns user
        mock_getenv.return_value = None
        mock_getuser.return_value = 'getpass_user'
        
        with patch.object(SlurmConfig, 'create_new_token', return_value=None):
            config = SlurmConfig()
        
        self.assertEqual(config.user_name, 'getpass_user')
        mock_getuser.assert_called_once()
    
    @patch('os.getenv')
    @patch('getpass.getuser')
    def test_detect_username_fallback_failure(self, mock_getuser, mock_getenv):
        """Test username detection when all methods fail"""
        # Setup mocks - no env vars, getpass raises exception
        mock_getenv.return_value = None
        mock_getuser.side_effect = Exception("getpass failed")
        
        with patch.object(SlurmConfig, 'create_new_token', return_value=None):
            config = SlurmConfig()
        
        self.assertEqual(config.user_name, '')
    
    @patch('os.getenv')
    def test_create_new_token_with_env_jwt(self, mock_getenv):
        """Test token creation with environment JWT"""
        # Setup mock
        mock_getenv.side_effect = lambda key: {
            'SLURM_JWT': 'env-jwt-token',
            'USER': 'testuser'
        }.get(key)
        
        config = SlurmConfig.__new__(SlurmConfig)  # Create without __init__
        token = config.create_new_token()
        
        self.assertEqual(token, 'env-jwt-token')
    
    @patch('os.getenv')
    def test_create_new_token_without_env_jwt(self, mock_getenv):
        """Test token creation without environment JWT"""
        # Setup mock - no SLURM_JWT
        mock_getenv.side_effect = lambda key: {
            'USER': 'testuser'
        }.get(key)
        
        config = SlurmConfig.__new__(SlurmConfig)  # Create without __init__
        token = config.create_new_token()
        
        self.assertIsNone(token)
    
    @patch('builtins.open', new_callable=mock_open, read_data="""url=http://custom.url
user_name=fileuser
api_ver=v1.0.0
account=fileaccount
jwt=file-jwt-token
""")
    @patch('client_service.deployment.slurm_config.SlurmToken')
    def test_load_from_file_success(self, mock_slurm_token_class, mock_file):
        """Test successful loading from file"""
        mock_token = Mock()
        mock_slurm_token_class.return_value = mock_token
        
        config = SlurmConfig.load_from_file('test_config.txt')
        
        # Verify file was opened
        mock_file.assert_called_once_with('test_config.txt', 'r')
        
        # Verify configuration was loaded
        self.assertEqual(config.url, 'http://custom.url')
        self.assertEqual(config.user_name, 'fileuser')
        self.assertEqual(config.api_ver, 'v1.0.0')
        self.assertEqual(config.account, 'fileaccount')
        self.assertEqual(config.token, mock_token)
        
        # Verify token was created with file JWT
        mock_slurm_token_class.assert_called_with('file-jwt-token')
    
    @patch('builtins.open', new_callable=mock_open, read_data="""url=http://partial.url
user_name=partialuser
""")
    def test_load_from_file_partial_config(self, mock_file):
        """Test loading from file with partial configuration"""
        with patch.object(SlurmConfig, 'create_new_token', return_value='auto-token'):
            config = SlurmConfig.load_from_file('partial_config.txt')
        
        # Verify partial config was loaded with defaults
        self.assertEqual(config.url, 'http://partial.url')
        self.assertEqual(config.user_name, 'partialuser')
        self.assertEqual(config.api_ver, DEFAULT_API_VER)  # Default
        self.assertEqual(config.account, DEFAULT_ACCOUNT)  # Default
    
    @patch('builtins.open', side_effect=FileNotFoundError("File not found"))
    def test_load_from_file_failure(self, mock_file):
        """Test loading from file when file doesn't exist"""
        with patch.object(SlurmConfig, 'create_new_token', return_value='auto-token'):
            config = SlurmConfig.load_from_file('nonexistent.txt')
        
        # Should continue with auto-detected values
        self.assertEqual(config.url, DEFAULT_URL)
        self.assertEqual(config.api_ver, DEFAULT_API_VER)
        self.assertEqual(config.account, DEFAULT_ACCOUNT)
    
    def test_tmp_load_default(self):
        """Test temporary default loading"""
        with patch.object(SlurmConfig, '__init__', return_value=None) as mock_init:
            config = SlurmConfig.tmp_load_default()
            mock_init.assert_called_once()
            self.assertIsInstance(config, SlurmConfig)
    
    @patch('client_service.deployment.slurm_config.SlurmToken')
    def test_property_accessors(self, mock_slurm_token_class):
        """Test all property accessors"""
        mock_token = Mock()
        mock_token.__str__ = Mock(return_value='token-string')
        mock_slurm_token_class.return_value = mock_token
        
        with patch.object(SlurmConfig, 'create_new_token', return_value='test-token'):
            config = SlurmConfig()
        
        # Test all properties
        self.assertEqual(config.url, DEFAULT_URL)
        self.assertEqual(config.api_ver, DEFAULT_API_VER)
        self.assertEqual(config.account, DEFAULT_ACCOUNT)
        self.assertEqual(config.token, mock_token)
        self.assertEqual(config.jwt, 'token-string')
        self.assertIsNotNone(config.user_name)
    
    def test_jwt_property_when_no_token(self):
        """Test jwt property when no token is available"""
        with patch.object(SlurmConfig, 'create_new_token', return_value=None):
            config = SlurmConfig()
        
        self.assertIsNone(config.jwt)
    
    @patch('client_service.deployment.slurm_config.SlurmToken')
    def test_refresh_token_if_needed_no_token(self, mock_slurm_token_class):
        """Test token refresh when no token is available"""
        config = SlurmConfig.__new__(SlurmConfig)  # Create without __init__
        config._token = None
        
        result = config.refresh_token_if_needed()
        
        self.assertFalse(result)
    
    @patch('client_service.deployment.slurm_config.SlurmToken')
    def test_refresh_token_if_needed_expired(self, mock_slurm_token_class):
        """Test token refresh when token has expired"""
        mock_token = Mock()
        mock_token.has_expired.return_value = True
        
        config = SlurmConfig.__new__(SlurmConfig)  # Create without __init__
        config._token = mock_token
        
        result = config.refresh_token_if_needed()
        
        self.assertFalse(result)
        mock_token.has_expired.assert_called_once()
    
    @patch('client_service.deployment.slurm_config.SlurmToken')
    def test_refresh_token_if_needed_expiring_soon(self, mock_slurm_token_class):
        """Test token refresh when token is expiring soon"""
        mock_token = Mock()
        mock_token.has_expired.return_value = False
        mock_token.is_expiring_soon.return_value = True
        
        config = SlurmConfig.__new__(SlurmConfig)  # Create without __init__
        config._token = mock_token
        
        result = config.refresh_token_if_needed(threshold_seconds=120)
        
        self.assertFalse(result)
        mock_token.has_expired.assert_called_once()
        mock_token.is_expiring_soon.assert_called_once_with(120)
    
    @patch('client_service.deployment.slurm_config.SlurmToken')
    def test_refresh_token_if_needed_valid(self, mock_slurm_token_class):
        """Test token refresh when token is still valid"""
        mock_token = Mock()
        mock_token.has_expired.return_value = False
        mock_token.is_expiring_soon.return_value = False
        
        config = SlurmConfig.__new__(SlurmConfig)  # Create without __init__
        config._token = mock_token
        
        result = config.refresh_token_if_needed(threshold_seconds=60)
        
        self.assertFalse(result)
        mock_token.has_expired.assert_called_once()
        mock_token.is_expiring_soon.assert_called_once_with(60)
    
    @patch('client_service.deployment.slurm_config.SlurmToken')
    def test_str_representation_with_token(self, mock_slurm_token_class):
        """Test string representation with valid token"""
        mock_token = Mock()
        mock_token.is_valid = True
        
        config = SlurmConfig.__new__(SlurmConfig)  # Create without __init__
        config._url = "http://test.url"
        config._api_ver = "v1.0"
        config._user_name = "testuser"
        config._account = "testaccount"
        config._token = mock_token
        
        str_repr = str(config)
        
        self.assertIn("http://test.url", str_repr)
        self.assertIn("jwt=***", str_repr)  # Should show *** for valid token
        self.assertIn("v1.0", str_repr)
        self.assertIn("testuser", str_repr)
        self.assertIn("testaccount", str_repr)
    
    def test_str_representation_without_token(self):
        """Test string representation without token"""
        config = SlurmConfig.__new__(SlurmConfig)  # Create without __init__
        config._url = "http://test.url"
        config._api_ver = "v1.0"
        config._user_name = "testuser"
        config._account = "testaccount"
        config._token = None
        
        str_repr = str(config)
        
        self.assertIn("jwt=None", str_repr)


if __name__ == '__main__':
    unittest.main()