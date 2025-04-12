"""
Command-line interface for the pymotiva package.

This module provides a command-line interface for controlling Emotiva devices.
"""

import argparse
import logging
import sys
import asyncio
from typing import Optional, Dict, Any, List

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
    
    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Get the current device status"
    )
    status_parser.add_argument(
        "--properties",
        nargs="+",
        default=["power", "zone2_power", "volume", "input", "mode", "audio_input", "video_input"],
        help="Properties to query (default includes common ones)"
    )
    
    # Power command
    power_parser = subparsers.add_parser(
        "power",
        help="Control device power"
    )
    power_parser.add_argument(
        "state",
        choices=["on", "off", "toggle", "status"],
        help="Power state to set or query"
    )
    
    # Volume command
    volume_parser = subparsers.add_parser(
        "volume",
        help="Control device volume"
    )
    volume_parser.add_argument(
        "level",
        type=int,
        help="Volume level (0-100) or relative change (+/-)"
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
    
    # Input command (legacy)
    input_parser = subparsers.add_parser(
        "input",
        help="Set input source (legacy method)"
    )
    input_parser.add_argument(
        "source",
        choices=list(INPUT_SOURCES.keys()),
        help="Input source to set"
    )
    
    # Source command (legacy)
    source_parser = subparsers.add_parser(
        "source",
        help="Set source using source command (legacy method)"
    )
    source_parser.add_argument(
        "source",
        choices=list(INPUT_SOURCES.keys()),
        help="Source to set"
    )
    
    # HDMI command (enhanced)
    hdmi_parser = subparsers.add_parser(
        "hdmi",
        help="Set HDMI input using enhanced method"
    )
    hdmi_parser.add_argument(
        "number",
        type=int,
        choices=range(1, 9),
        help="HDMI port number (1-8)"
    )
    
    # Switch command (enhanced)
    switch_parser = subparsers.add_parser(
        "switch",
        help="Switch to any source using enhanced method"
    )
    switch_parser.add_argument(
        "source",
        choices=list(INPUT_SOURCES.keys()),
        help="Source to switch to"
    )
    
    # Zone 2 commands
    zone2_parser = subparsers.add_parser(
        "zone2",
        help="Control Zone 2"
    )
    zone2_subparsers = zone2_parser.add_subparsers(dest="zone2_command", help="Zone 2 command")
    
    # Zone 2 power
    zone2_power_parser = zone2_subparsers.add_parser(
        "power",
        help="Control Zone 2 power"
    )
    zone2_power_parser.add_argument(
        "state",
        choices=["on", "off", "toggle"],
        help="Power state to set"
    )
    
    # Zone 2 volume
    zone2_volume_parser = zone2_subparsers.add_parser(
        "volume",
        help="Control Zone 2 volume"
    )
    zone2_volume_parser.add_argument(
        "level",
        type=int,
        help="Volume level (-96 to 11) or relative change (+/-)"
    )
    
    # Zone 2 source
    zone2_source_parser = zone2_subparsers.add_parser(
        "source",
        help="Set Zone 2 source"
    )
    zone2_source_parser.add_argument(
        "source",
        choices=[k for k in INPUT_SOURCES.keys() if k.startswith("zone2_") or not any(x.startswith("zone2_") for x in INPUT_SOURCES.keys())],
        help="Source to set for Zone 2"
    )
    
    # Mode preset commands
    for mode in MODE_PRESETS:
        mode_preset_parser = subparsers.add_parser(
            f"mode_{mode}",
            help=f"Set {MODE_PRESETS[mode]} mode"
        )
    
    # Query command for getting specific status information
    query_parser = subparsers.add_parser(
        "query",
        help="Query specific device information"
    )
    query_subparsers = query_parser.add_subparsers(dest="query_type", help="Type of information to query")
    
    # Power query
    power_query_parser = query_subparsers.add_parser(
        "power",
        help="Query power status"
    )
    
    # Zone 2 power query
    zone2_power_query_parser = query_subparsers.add_parser(
        "zone2_power",
        help="Query Zone 2 power status"
    )
    
    # Input query
    input_query_parser = query_subparsers.add_parser(
        "input",
        help="Query current input source"
    )
    
    # Mode query
    mode_query_parser = query_subparsers.add_parser(
        "mode",
        help="Query current audio mode"
    )
    
    # Custom query for multiple properties
    custom_query_parser = query_subparsers.add_parser(
        "custom",
        help="Query custom properties"
    )
    custom_query_parser.add_argument(
        "properties",
        nargs="+",
        help="Properties to query"
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
                print(f"  Model: {discovery_result.get('info', {}).get('model')}")
                print(f"  Protocol: {discovery_result.get('info', {}).get('protocol')}")
                return 0
            else:
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
        elif args.command == "status":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            # Subscribe to the properties we want to query
            await emotiva.subscribe_to_notifications(args.properties)
            
            # Request updates for those properties
            response = await emotiva.update_properties(args.properties)
            
            # Wait a moment for notifications
            await asyncio.sleep(0.5)
            
            # Create a formatted output of current device status
            print(f"Device Status ({args.ip}):")
            print("-" * 40)
            print(f"  Model: {discovery_result.get('info', {}).get('model')}")
            print(f"  Protocol: {discovery_result.get('info', {}).get('protocol')}")
            print("-" * 40)
            
            return 0
            
        elif args.command == "power":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            # Use the appropriate power method
            if args.state == "on":
                response = await emotiva.set_power_on()
                print(f"Power on command response: {response}")
            elif args.state == "off":
                response = await emotiva.set_power_off()
                print(f"Power off command response: {response}")
            elif args.state == "toggle":
                response = await emotiva.toggle_power()
                print(f"Power toggle command response: {response}")
            elif args.state == "status":
                response = await emotiva.get_power()
                print(f"Power status query sent: {response.get('status')}")
                # Wait a moment for notifications
                await asyncio.sleep(1.0)
                # Add a more user-friendly status display
                print("\nCurrent Power Status:")
                print("-" * 40)
            
        elif args.command == "volume":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            # Check if the level is relative or absolute
            if args.level > 0 and args.level < 100:
                # Absolute volume level
                response = await emotiva.send_command("set_volume", {"value": str(args.level), "ack": "yes"})
            else:
                # Relative volume change
                response = await emotiva.send_command("volume", {"value": args.level, "ack": "yes"})
                
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
            
        elif args.command == "hdmi":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            response = await emotiva.switch_to_hdmi(args.number)
            print(f"HDMI command response: {response}")
            
        elif args.command == "switch":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            response = await emotiva.switch_to_source(args.source)
            print(f"Switch command response: {response}")
            
        elif args.command == "zone2" and args.zone2_command:
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            if args.zone2_command == "power":
                if args.state == "on":
                    response = await emotiva.set_zone2_power_on()
                elif args.state == "off":
                    response = await emotiva.set_zone2_power_off()
                else:  # toggle
                    response = await emotiva.toggle_zone2_power()
                print(f"Zone 2 power command response: {response}")
                
            elif args.zone2_command == "volume":
                # For zone2 volume, we'll use the send_command method
                # since there's no specific method for zone2 volume yet
                if args.level >= -96 and args.level <= 11:
                    # Absolute volume
                    response = await emotiva.send_command("zone2_set_volume", {"value": args.level, "ack": "yes"})
                else:
                    # Relative volume change
                    response = await emotiva.send_command("zone2_volume", {"value": args.level, "ack": "yes"})
                print(f"Zone 2 volume command response: {response}")
                
            elif args.zone2_command == "source":
                # For zone2 source, we need to use the appropriate command
                source_cmd = f"zone2_{args.source}" if not args.source.startswith("zone2_") else args.source
                response = await emotiva.send_command(source_cmd, {"value": "0", "ack": "yes"})
                print(f"Zone 2 source command response: {response}")
            
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
            
        elif args.command == "query":
            # Ensure device is discovered first
            discovery_result = await emotiva.discover()
            if discovery_result.get("status") != "success":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
            
            if args.query_type == "power":
                response = await emotiva.get_power()
                print(f"Power status query sent: {response.get('status')}")
                # Wait a moment for notifications
                await asyncio.sleep(1.0)
                print("\nCurrent Power Status:")
                print("-" * 40)
                
            elif args.query_type == "zone2_power":
                response = await emotiva.get_zone2_power()
                print(f"Zone 2 power status query sent: {response.get('status')}")
                # Wait a moment for notifications
                await asyncio.sleep(1.0)
                print("\nCurrent Zone 2 Power Status:")
                print("-" * 40)
                
            elif args.query_type == "input":
                await emotiva.subscribe_to_notifications(["input", "audio_input", "video_input"])
                response = await emotiva.update_properties(["input", "audio_input", "video_input"])
                print(f"Input status query sent: {response.get('status')}")
                # Wait a moment for notifications
                await asyncio.sleep(1.0)
                print("\nCurrent Input Status:")
                print("-" * 40)
                
            elif args.query_type == "mode":
                await emotiva.subscribe_to_notifications(["mode"])
                response = await emotiva.update_properties(["mode"])
                print(f"Mode status query sent: {response.get('status')}")
                # Wait a moment for notifications
                await asyncio.sleep(1.0)
                print("\nCurrent Mode Status:")
                print("-" * 40)
                
            elif args.query_type == "custom" and args.properties:
                await emotiva.subscribe_to_notifications(args.properties)
                response = await emotiva.update_properties(args.properties)
                print(f"Custom status query sent: {response.get('status')}")
                # Wait a moment for notifications
                await asyncio.sleep(1.0)
                print(f"\nCurrent Status for {', '.join(args.properties)}:")
                print("-" * 40)
            
            else:
                print("No query type specified. Use --help for usage information.")
                return 1
            
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