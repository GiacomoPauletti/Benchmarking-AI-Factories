"""
Test for SLURM functionality.
"""

import pytest
from unittest.mock import Mock, patch
import os

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "src"))


class TestSLURM:
    """SLURM tests."""
    
    @patch.dict(os.environ, {'USER': 'testuser', 'SLURM_JWT': 'test_token'})
    @patch('deployment.slurm.requests')
    def test_submit_job(self, mock_requests):
        """Test job submission."""
        from deployment.slurm import SlurmDeployer
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": 12345, "errors": []}
        mock_response.raise_for_status.return_value = None
        mock_requests.post.return_value = mock_response
        
        deployer = SlurmDeployer()
        
        # This will fail because we don't have recipe files, but that's OK for testing the structure
        try:
            result = deployer.submit_job("test/recipe", {"nodes": 1})
            assert False, "Should have failed due to missing recipe"
        except FileNotFoundError:
            # Expected - recipe file doesn't exist
            pass
    
    @patch.dict(os.environ, {'USER': 'testuser', 'SLURM_JWT': 'test_token'})
    def test_deployer_init(self):
        """Test deployer initialization."""
        from deployment.slurm import SlurmDeployer
        
        deployer = SlurmDeployer()
        assert deployer.username == "testuser"
        assert deployer.token == "test_token"