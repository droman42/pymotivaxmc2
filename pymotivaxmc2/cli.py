"""
Command-line interface for the pymotiva package.

This module provides a command-line interface for controlling Emotiva devices.
"""

import argparse
import logging
import sys
from typing import Optional, Dict, Any

from . import Emotiva, EmotivaConfig
from .exceptions import Error, InvalidTransponderResponseError

_LOGGER = logging.getLogger(__name__)

def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Control Emotiva A/V receivers from the command line"
    )
    
    parser.add_argument(
        "--ip",
        required=True,
        help="IP address of the Emotiva device"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=2,
        help="Socket timeout in seconds"
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Discover command
    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover the device and get its transponder port"
    )
    
    # Power command
    power_parser = subparsers.add_parser(
        "power",
        help="Control device power"
    )
    power_parser.add_argument(
        "state",
        choices=["on", "off"],
        help="Power state to set"
    )
    
    # Volume command
    volume_parser = subparsers.add_parser(
        "volume",
        help="Control device volume"
    )
    volume_parser.add_argument(
        "level",
        type=int,
        help="Volume level (0-100)"
    )
    
    return parser.parse_args()

def handle_notification(data: Dict[str, Any]) -> None:
    """Handle device notifications."""
    _LOGGER.info("Received notification: %s", data)

def main() -> int:
    """Main entry point for the CLI."""
    args = parse_args()
    setup_logging(args.verbose)
    
    try:
        config = EmotivaConfig(ip=args.ip, timeout=args.timeout)
        emotiva = Emotiva(config)
        
        # Set up notification callback
        emotiva.set_callback(handle_notification)
        
        if args.command == "discover":
            port = emotiva.discover()
            print(f"Device discovered on port {port}")
            
        elif args.command == "power":
            emotiva.discover()  # Ensure device is discovered
            response = emotiva.send_command("power", {"value": args.state})
            print(f"Power command response: {response}")
            
        elif args.command == "volume":
            emotiva.discover()  # Ensure device is discovered
            response = emotiva.send_command("volume", {"value": args.level})
            print(f"Volume command response: {response}")
            
        else:
            print("No command specified. Use --help for usage information.")
            return 1
            
    except InvalidTransponderResponseError as e:
        _LOGGER.error("Device communication error: %s", e)
        return 1
    except Error as e:
        _LOGGER.error("Error: %s", e)
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main()) 