"""
Application entry point for the server service.
"""

from server_service import ServerService


def main():
    """Main application entry point."""
    server = ServerService()
    # Initialize and start the server
    print("Starting AI Factory Server Service...")
    

if __name__ == "__main__":
    main()