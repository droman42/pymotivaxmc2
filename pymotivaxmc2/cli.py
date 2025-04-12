"""
Command-line interface for the pymotiva package.

This module provides a command-line interface for controlling Emotiva devices.
"""

import argparse
import logging
import sys
import asyncio
from typing import Optional, Dict, Any

from . import Emotiva, EmotivaConfig
from .exceptions import Error, InvalidTransponderResponseError, InvalidSourceError, InvalidModeError
from .constants import MODE_PRESETS, INPUT_SOURCES

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
    
    # Mode command
    mode_parser = subparsers.add_parser(
        "mode",
        help="Set audio processing mode"
    )
    mode_parser.add_argument(
        "mode",
        choices=list(MODE_PRESETS.keys()),
        help="Mode to set"
    )
    
    # Input command
    input_parser = subparsers.add_parser(
        "input",
        help="Set input source"
    )
    input_parser.add_argument(
        "source",
        choices=list(INPUT_SOURCES.keys()),
        help="Input source to set"
    )
    
    # Source command
    source_parser = subparsers.add_parser(
        "source",
        help="Set source using source command"
    )
    source_parser.add_argument(
        "source",
        choices=list(INPUT_SOURCES.keys()),
        help="Source to set"
    )
    
    # Mode preset commands
    for mode in MODE_PRESETS:
        mode_preset_parser = subparsers.add_parser(
            f"mode_{mode}",
            help=f"Set {MODE_PRESETS[mode]} mode"
        )
    
    return parser.parse_args()

def handle_notification(data: Dict[str, Any]) -> None:
    """Handle device notifications."""
    print(f"Notification: {data}")

async def async_main() -> int:
    """Async main entry point for the CLI."""
    args = parse_args()
    setup_logging(args.verbose)
    
    try:
        config = EmotivaConfig(ip=args.ip, timeout=args.timeout)
        emotiva = Emotiva(config)
        
        # Set up notification callback
        emotiva.set_callback(handle_notification)
        
        if args.command == "discover":
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") == "success":
                print(f"Device discovered successfully:")
                print(f"  IP: {discovery_result.get('ip')}")
                print(f"  Port: {discovery_result.get('port')}")
                print(f"  Model: {discovery_result.get('model')}")
                print(f"  Protocol: {discovery_result.get('protocol')}")
                return 0
            else:
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
            
        elif args.command == "power":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            response = await emotiva.send_command("power", {"value": args.state})
            print(f"Power command response: {response}")
            
        elif args.command == "volume":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            response = await emotiva.send_command("volume", {"value": args.level})
            print(f"Volume command response: {response}")
            
        elif args.command == "mode":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            response = await emotiva.set_mode(args.mode)
            print(f"Mode command response: {response}")
            
        elif args.command == "input":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            response = await emotiva.set_input(args.source)
            print(f"Input command response: {response}")
            
        elif args.command == "source":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            response = await emotiva.set_source(args.source)
            print(f"Source command response: {response}")
            
        elif args.command and args.command.startswith("mode_"):
            # Handle mode preset commands
            mode = args.command[5:]  # Strip "mode_" prefix
            
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            # Use the appropriate mode method
            if mode == "stereo":
                response = await emotiva.set_stereo_mode()
            elif mode == "direct":
                response = await emotiva.set_direct_mode()
            elif mode == "dolby":
                response = await emotiva.set_dolby_mode()
            elif mode == "dts":
                response = await emotiva.set_dts_mode()
            elif mode == "movie":
                response = await emotiva.set_movie_mode()
            elif mode == "music":
                response = await emotiva.set_music_mode()
            elif mode == "all_stereo":
                response = await emotiva.set_all_stereo_mode()
            elif mode == "auto":
                response = await emotiva.set_auto_mode()
            elif mode == "reference_stereo":
                response = await emotiva.set_reference_stereo_mode()
            elif mode == "surround_mode":
                response = await emotiva.set_surround_mode()
            else:
                print(f"Unknown mode: {mode}")
                return 1
                
            print(f"Mode command response: {response}")
            
        else:
            print("No command specified. Use --help for usage information.")
            return 1
            
        # Allow time for any final notifications
        await asyncio.sleep(0.5)
        
        # Cleanup resources
        await emotiva.close()
        
        return 0
        
    except Error as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        _LOGGER.exception("Unexpected error")
        print(f"Unexpected error: {e}")
        return 1

def main() -> int:
    """Main entry point for the CLI."""
    return asyncio.run(async_main())

if __name__ == "__main__":
    sys.exit(main()) 