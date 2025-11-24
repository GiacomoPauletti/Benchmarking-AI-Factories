"""
Client Service Tests

This package contains tests for the AI Factory Client Service.

Test Organization:
- conftest.py: Shared fixtures and test configuration
- test_api.py: Unit tests for API endpoints and components
- test_integration.py: Integration tests for full workflows

Run Tests:
    # All tests
    pytest tests/
    
    # Only unit tests (fast)
    pytest tests/test_api.py -v
    
    # Only integration tests
    pytest tests/test_integration.py -v
    
    # Skip integration tests
    pytest tests/ -v -m "not integration"
    
    # With coverage
    pytest tests/ --cov=src --cov-report=html
"""
