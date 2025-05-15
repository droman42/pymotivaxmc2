"""
Command-line interface for the pymotivaxmc2 package.

This module provides a command-line interface for controlling Emotiva devices.
"""

import argparse
import logging
import sys
import asyncio
from typing import Optional, Dict, Any, List

from .controller import EmotivaController
from .exceptions import EmotivaError, InvalidTransponderResponseError, InvalidSourceError, InvalidModeError
from .constants import MODE_PRESETS, INPUT_SOURCES
from .emotiva_types import EmotivaNotification, EmotivaConfig, EmotivaNotificationListener

_LOGGER = logging.getLogger(__name__)

class CLINotificationListener(EmotivaNotificationListener):
    """CLI notification listener that prints notifications to the console."""
    
    def on_notification(self, notification: EmotivaNotification) -> None:
        """Handle a notification by printing it to the console."""
        print(f"Notification: {notification.notification_type} from {notification.device_ip}")
        
        # Print additional details based on notification type
        if notification.data:
            if isinstance(notification.data, dict) and 'properties' in notification.data:
                for prop_name, prop_data in notification.data['properties'].items():
                    print(f"  Property: {prop_name} = {prop_data.get('value')}")
            else:
                print(f"  Data: {notification.data}")

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
        choices=list(MODE_PRESETS),
        help="Mode to set"
    )
    
    # Input command (legacy)
    input_parser = subparsers.add_parser(
        "input",
        help="Set input source (legacy method)"
    )
    input_parser.add_argument(
        "source",
        choices=list(INPUT_SOURCES),
        help="Input source to set"
    )
    
    # Source command (legacy)
    source_parser = subparsers.add_parser(
        "source",
        help="Set source using source command (legacy method)"
    )
    source_parser.add_argument(
        "source",
        choices=list(INPUT_SOURCES),
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
        choices=list(INPUT_SOURCES),
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
        choices=[k for k in INPUT_SOURCES if k.startswith("zone2_") or not any(x.startswith("zone2_") for x in INPUT_SOURCES)],
        help="Source to set for Zone 2"
    )
    
    # Mode preset commands
    for mode in MODE_PRESETS:
        mode_preset_parser = subparsers.add_parser(
            f"mode_{mode}",
            help=f"Set {mode} mode"
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

async def async_main() -> int:
    """Async main entry point for the CLI."""
    args = parse_args()
    setup_logging(args.verbose)
    
    try:
        # Create controller with command-line parameters
        config = EmotivaConfig(
            ip=args.ip,
            timeout=float(args.timeout)
        )
        controller = EmotivaController(config)
        
        # Register notification handler
        notification_listener = CLINotificationListener()
        await controller.notification_registry.register_listener(notification_listener)
        
        if args.command == "discover":
            discovery_result = await controller.discover()
            if discovery_result.get("status") == "ok":
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
            discovery_result = await controller.discover()
            if discovery_result.get("status") != "ok":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            # Subscribe to the properties we want to query
            await controller.subscribe_to_notifications(args.properties)
            
            # Request updates for those properties
            response = await controller.update_properties(args.properties)
            
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
            discovery_result = await controller.discover()
            if discovery_result.get("status") != "ok":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            # Use the appropriate power method
            if args.state == "on":
                response = await controller.power_on()
                print(f"Power on command response: {response}")
            elif args.state == "off":
                response = await controller.power_off()
                print(f"Power off command response: {response}")
            elif args.state == "toggle":
                current_power = await controller.get_power()
                if current_power is True:
                    response = await controller.power_off()
                else:
                    response = await controller.power_on()
                print(f"Power toggle command response: {response}")
            elif args.state == "status":
                power_status = await controller.get_power()
                print(f"Power status: {'ON' if power_status else 'OFF'}")
            
        elif args.command == "volume":
            # Ensure device is discovered first
            discovery_result = await controller.discover()
            if discovery_result.get("status") != "ok":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            # Set volume according to the requested level
            response = await controller.set_volume(args.level)
            print(f"Volume command response: {response}")
            
        elif args.command == "mode":
            # Ensure device is discovered first
            discovery_result = await controller.discover()
            if discovery_result.get("status") != "ok":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            response = await controller.set_mode(args.mode)
            print(f"Mode command response: {response}")
            
        elif args.command == "input" or args.command == "source":
            # Ensure device is discovered first
            discovery_result = await controller.discover()
            if discovery_result.get("status") != "ok":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            # Set source according to the requested source
            try:
                response = await controller.set_input(args.source)
                print(f"Input command response: {response}")
            except InvalidSourceError as e:
                print(f"Error: {e}")
                return 1
            
        elif args.command == "hdmi":
            # Ensure device is discovered first
            discovery_result = await controller.discover()
            if discovery_result.get("status") != "ok":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            try:
                # Format HDMI source and use set_input
                response = await controller.set_input(f"hdmi{args.number}")
                print(f"HDMI command response: {response}")
            except InvalidSourceError as e:
                print(f"Error: {e}")
                return 1
            
        elif args.command == "switch":
            # Ensure device is discovered first
            discovery_result = await controller.discover()
            if discovery_result.get("status") != "ok":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            try:
                response = await controller.set_input(args.source)
                print(f"Switch command response: {response}")
            except InvalidSourceError as e:
                print(f"Error: {e}")
                return 1
            
        elif args.command == "zone2" and args.zone2_command:
            # Ensure device is discovered first
            discovery_result = await controller.discover()
            if discovery_result.get("status") != "ok":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            if args.zone2_command == "power":
                if args.state == "on":
                    response = await controller.set_zone2_power(True)
                elif args.state == "off":
                    response = await controller.set_zone2_power(False)
                else:  # toggle
                    # Get current zone2 state
                    zone2_state = await controller.get_zone2_state()
                    zone2_power = zone2_state.get("data", {}).get("power") == "true"
                    response = await controller.set_zone2_power(not zone2_power)
                print(f"Zone 2 power command response: {response}")
                
            elif args.zone2_command == "volume":
                # For zone2 volume, we'll use the set_zone2_volume method
                if args.level >= -96 and args.level <= 11:
                    # Absolute volume
                    response = await controller.set_zone2_volume(args.level)
                else:
                    # Relative volume change not directly supported, convert to command
                    response = await controller.send_command("control", {
                        "command": "zone2_volume",
                        "value": str(args.level),
                        "ack": "true"
                    })
                print(f"Zone 2 volume command response: {response}")
                
            elif args.zone2_command == "source":
                # For zone2 source, use set_zone2_input
                try:
                    response = await controller.set_zone2_input(args.source)
                    print(f"Zone 2 source command response: {response}")
                except InvalidSourceError as e:
                    print(f"Error: {e}")
                    return 1
            
        elif args.command and args.command.startswith("mode_"):
            # Handle mode preset commands
            mode = args.command[5:]  # Strip "mode_" prefix
            
            # Ensure device is discovered first
            discovery_result = await controller.discover()
            if discovery_result.get("status") != "ok":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
                
            # Set mode using set_mode
            response = await controller.set_mode(mode)
            print(f"Mode command response: {response}")
            
        elif args.command == "query":
            # Ensure device is discovered first
            discovery_result = await controller.discover()
            if discovery_result.get("status") != "ok":
                print(f"Discovery failed: {discovery_result.get('message')}")
                return 1
            
            if args.query_type == "power":
                power_status = await controller.get_power()
                print(f"Power status: {'ON' if power_status else 'OFF'}")
                
            elif args.query_type == "zone2_power":
                # Get the zone2 state and extract power status
                zone2_state = await controller.get_zone2_state()
                zone2_power = zone2_state.get("data", {}).get("power") == "true"
                print(f"Zone 2 power status: {'ON' if zone2_power else 'OFF'}")
                
            elif args.query_type == "input":
                await controller.subscribe_to_notifications(["input", "audio_input", "video_input"])
                response = await controller.update_properties(["input", "audio_input", "video_input"])
                print(f"Input status query sent: {response.get('status')}")
                # Wait a moment for notifications
                await asyncio.sleep(1.0)
                input_source = await controller.get_input()
                print(f"Current input source: {input_source}")
                
            elif args.query_type == "mode":
                await controller.subscribe_to_notifications(["mode"])
                response = await controller.update_properties(["mode"])
                print(f"Mode status query sent: {response.get('status')}")
                # Wait a moment for notifications
                await asyncio.sleep(1.0)
                print("\nCurrent Mode Status:")
                print("-" * 40)
                
            elif args.query_type == "custom" and args.properties:
                await controller.subscribe_to_notifications(args.properties)
                response = await controller.update_properties(args.properties)
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
        await controller.close()
        
        return 0
        
    except EmotivaError as e:
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