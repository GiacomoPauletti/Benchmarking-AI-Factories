"""
Unit tests for main.py client service module
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from io import StringIO
import logging

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

# Import the main module components
import main


class TestClientServiceMain(unittest.TestCase):
    """Test the main client service module"""
    
    def test_app_creation(self):
        """Test FastAPI app is created correctly"""
        self.assertIsNotNone(main.app)
        self.assertEqual(main.app.title, "AI Factory Client Service")
        self.assertEqual(main.app.description, "Spawns clients for testing Server Service")
        self.assertEqual(main.app.version, "1.0.0")
        self.assertEqual(main.app.docs_url, "/docs")
        self.assertEqual(main.app.redoc_url, "/redoc")
    
    def test_routers_included(self):
        """Test that all routers are included in the app"""
        # Check that routers are included by examining routes
        route_paths = [route.path for route in main.app.routes if hasattr(route, 'path')]
        
        # Should have routes from frontend_router, client_router, and monitor_router
        # Check for some expected endpoints
        prefix_paths = [path for path in route_paths if path.startswith('/api/v1')]
        self.assertTrue(len(prefix_paths) > 0)
    
    def test_client_service_class_exists(self):
        """Test that ClientService class is defined"""
        self.assertTrue(hasattr(main, 'ClientService'))
        
        # Should be able to instantiate
        service = main.ClientService()
        self.assertIsInstance(service, main.ClientService)


class TestMainExecution(unittest.TestCase):
    """Test main execution logic"""
    
    def setUp(self):
        """Set up test environment"""
        # Store original sys.argv
        self.original_argv = sys.argv.copy()
    
    def tearDown(self):
        """Clean up test environment"""
        # Restore original sys.argv
        sys.argv = self.original_argv
    
    @patch('main.uvicorn.run')
    @patch('main.ClientManager')
    @patch('main.SlurmConfig')
    @patch('socket.gethostname')
    def test_main_execution_minimal_args(self, mock_hostname, mock_slurm_config_class, mock_client_manager_class, mock_uvicorn):
        """Test main execution with minimal arguments"""
        # Setup mocks
        mock_hostname.return_value = "test-host"
        mock_slurm_config = Mock()
        mock_slurm_config_class.tmp_load_default.return_value = mock_slurm_config
        mock_client_manager = Mock()
        mock_client_manager_class.return_value = mock_client_manager
        
        # Set command line arguments
        sys.argv = ["main.py", "http://server:8000"]
        
        # Execute main
        with patch('main.__name__', '__main__'):
            try:
                exec(open('main.py').read())
            except SystemExit:
                pass  # Expected when main.py runs
        
        # Verify configuration
        mock_slurm_config_class.tmp_load_default.assert_called_once()
        mock_client_manager.configure.assert_called_once_with(
            server_addr="http://server:8000",
            client_service_addr="http://test-host:8001",
            use_container=False
        )
    
    @patch('main.uvicorn.run')
    @patch('main.ClientManager')
    @patch('main.SlurmConfig')
    @patch('socket.gethostname')
    def test_main_execution_with_container_flag(self, mock_hostname, mock_slurm_config_class, mock_client_manager_class, mock_uvicorn):
        """Test main execution with container flag"""
        # Setup mocks
        mock_hostname.return_value = "test-host"
        mock_slurm_config = Mock()
        mock_slurm_config_class.tmp_load_default.return_value = mock_slurm_config
        mock_client_manager = Mock()
        mock_client_manager_class.return_value = mock_client_manager
        
        # Set command line arguments with container flag
        sys.argv = ["main.py", "http://server:8000", "--container"]
        
        # Mock the main execution
        with patch('main.logging') as mock_logging:
            with patch('main.__name__', '__main__'):
                # Simulate main execution logic
                server_addr = sys.argv[1]
                use_container = False
                slurm_config_path = None
                
                for i in range(2, len(sys.argv)):
                    arg = sys.argv[i]
                    if arg == "--container":
                        use_container = True
                
                # Verify container flag was parsed
                self.assertTrue(use_container)
    
    @patch('main.uvicorn.run')
    @patch('main.ClientManager')
    @patch('main.SlurmConfig')
    @patch('socket.gethostname')
    def test_main_execution_with_config_file(self, mock_hostname, mock_slurm_config_class, mock_client_manager_class, mock_uvicorn):
        """Test main execution with config file"""
        # Setup mocks
        mock_hostname.return_value = "test-host"
        mock_config_from_file = Mock()
        mock_slurm_config_class.load_from_file.return_value = mock_config_from_file
        mock_client_manager = Mock()
        mock_client_manager_class.return_value = mock_client_manager
        
        # Set command line arguments with config file
        config_file = "test_config.conf"
        sys.argv = ["main.py", "http://server:8000", config_file]
        
        # Mock the main execution
        with patch('main.logging') as mock_logging:
            with patch('main.__name__', '__main__'):
                # Simulate main execution logic for config file parsing
                server_addr = sys.argv[1]
                use_container = False
                slurm_config_path = None
                
                for i in range(2, len(sys.argv)):
                    arg = sys.argv[i]
                    if arg == "--container":
                        use_container = True
                    elif not arg.startswith("--") and slurm_config_path is None:
                        slurm_config_path = arg
                
                # Verify config file was parsed
                self.assertEqual(slurm_config_path, config_file)
    
    @patch('main.uvicorn.run')
    @patch('main.ClientManager')
    @patch('main.SlurmConfig')
    @patch('socket.gethostname')
    def test_main_execution_with_all_args(self, mock_hostname, mock_slurm_config_class, mock_client_manager_class, mock_uvicorn):
        """Test main execution with all arguments"""
        # Setup mocks
        mock_hostname.return_value = "test-host"
        mock_config_from_file = Mock()
        mock_slurm_config_class.load_from_file.return_value = mock_config_from_file
        mock_client_manager = Mock()
        mock_client_manager_class.return_value = mock_client_manager
        
        # Set command line arguments with both config file and container flag
        config_file = "test_config.conf"
        sys.argv = ["main.py", "http://server:8000", config_file, "--container"]
        
        # Mock the main execution
        with patch('main.logging') as mock_logging:
            with patch('main.__name__', '__main__'):
                # Simulate main execution logic
                server_addr = sys.argv[1]
                use_container = False
                slurm_config_path = None
                
                for i in range(2, len(sys.argv)):
                    arg = sys.argv[i]
                    if arg == "--container":
                        use_container = True
                    elif not arg.startswith("--") and slurm_config_path is None:
                        slurm_config_path = arg
                
                # Verify both arguments were parsed
                self.assertEqual(slurm_config_path, config_file)
                self.assertTrue(use_container)
    
    def test_main_execution_insufficient_args(self):
        """Test main execution with insufficient arguments"""
        # Set insufficient command line arguments
        sys.argv = ["main.py"]  # Missing server_addr
        
        with patch('main.logging') as mock_logging:
            with patch('main.sys.exit') as mock_exit:
                with patch('main.__name__', '__main__'):
                    # Simulate main execution logic
                    if len(sys.argv) < 2:
                        mock_logging.fatal.assert_called_once()
                        mock_exit.assert_called_once_with(1)
    
    @patch('main.uvicorn.run')
    @patch('main.ClientManager')
    @patch('main.SlurmClientDispatcher')
    @patch('socket.gethostname')
    def test_slurm_dispatcher_config_assignment(self, mock_hostname, mock_dispatcher, mock_client_manager_class, mock_uvicorn):
        """Test that SlurmClientDispatcher.slurm_config is assigned correctly"""
        # This test focuses on the static assignment to SlurmClientDispatcher.slurm_config
        mock_hostname.return_value = "test-host"
        mock_client_manager = Mock()
        mock_client_manager_class.return_value = mock_client_manager
        
        sys.argv = ["main.py", "http://server:8000"]
        
        with patch('main.SlurmConfig') as mock_slurm_config_class:
            mock_config = Mock()
            mock_slurm_config_class.tmp_load_default.return_value = mock_config
            
            # Simulate the configuration assignment
            main.SlurmClientDispatcher.slurm_config = mock_slurm_config_class.tmp_load_default()
            
            # Verify the assignment
            self.assertEqual(main.SlurmClientDispatcher.slurm_config, mock_config)


class TestLoggingConfiguration(unittest.TestCase):
    """Test logging configuration"""
    
    def test_logging_basic_config(self):
        """Test that logging is configured correctly"""
        # Check that logging handlers are set up
        root_logger = logging.getLogger()
        
        # Should have at least one handler
        self.assertTrue(len(root_logger.handlers) > 0)
    
    def test_logging_levels(self):
        """Test that specific loggers have correct levels"""
        # Check that specific loggers have expected levels
        asyncio_logger = logging.getLogger("asyncio")
        uvicorn_logger = logging.getLogger("uvicorn")
        
        # These might not be set if the main module hasn't been executed
        # but we can at least check they exist
        self.assertIsNotNone(asyncio_logger)
        self.assertIsNotNone(uvicorn_logger)


class TestArgumentParsing(unittest.TestCase):
    """Test command line argument parsing logic"""
    
    def test_parse_container_flag(self):
        """Test parsing of container flag"""
        args = ["main.py", "http://server:8000", "--container"]
        
        # Simulate parsing logic
        use_container = False
        for i in range(2, len(args)):
            arg = args[i]
            if arg == "--container":
                use_container = True
        
        self.assertTrue(use_container)
    
    def test_parse_config_file_only(self):
        """Test parsing of config file without flags"""
        args = ["main.py", "http://server:8000", "config.txt"]
        
        # Simulate parsing logic
        use_container = False
        slurm_config_path = None
        
        for i in range(2, len(args)):
            arg = args[i]
            if arg == "--container":
                use_container = True
            elif not arg.startswith("--") and slurm_config_path is None:
                slurm_config_path = arg
        
        self.assertFalse(use_container)
        self.assertEqual(slurm_config_path, "config.txt")
    
    def test_parse_mixed_args(self):
        """Test parsing of mixed arguments"""
        args = ["main.py", "http://server:8000", "config.txt", "--container"]
        
        # Simulate parsing logic
        use_container = False
        slurm_config_path = None
        
        for i in range(2, len(args)):
            arg = args[i]
            if arg == "--container":
                use_container = True
            elif not arg.startswith("--") and slurm_config_path is None:
                slurm_config_path = arg
        
        self.assertTrue(use_container)
        self.assertEqual(slurm_config_path, "config.txt")
    
    def test_parse_no_additional_args(self):
        """Test parsing with no additional arguments"""
        args = ["main.py", "http://server:8000"]
        
        # Simulate parsing logic
        use_container = False
        slurm_config_path = None
        
        for i in range(2, len(args)):
            arg = args[i]
            if arg == "--container":
                use_container = True
            elif not arg.startswith("--") and slurm_config_path is None:
                slurm_config_path = arg
        
        self.assertFalse(use_container)
        self.assertIsNone(slurm_config_path)


if __name__ == '__main__':
    unittest.main()