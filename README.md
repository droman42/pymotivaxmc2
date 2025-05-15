# PyEmotivaXMC2

Python interface for controlling Emotiva XMC-series processors over the network.

## Features

- Device discovery and automatic connection
- Command sending and response handling
- Notification handling and state tracking
- Connection monitoring with automatic reconnection
- Common controls for power, volume, input selection, audio modes
- Zonal control for multi-zone setups
- Menu navigation and control

## CHANGELOG

### Version 0.5.0
- **Major architecture refactoring**: Complete rewrite into a modular, maintainable architecture
- **New controller interface**: Introduced `EmotivaController` as the primary interface
- **Improved state management**: Added robust state tracking with validation
- **Enhanced notification system**: New observer pattern for flexible event handling
- **Robust network layer**: Improved connection handling and command execution
- **Removed legacy compatibility**: Removed backward compatibility layers for a cleaner codebase
- **Comprehensive test suite**: Added extensive test coverage for all components

## Architecture

The PyEmotivaXMC2 codebase is organized into several modular components:

### Core Components

- **Controller Module**: `EmotivaController` is the main interface for controlling Emotiva devices. It provides easy access to device features like volume control, input selection, and power management.

- **Network Layer**: Handles socket management and communications with the device:
  - `SocketManager`: Flexible socket creation and management
  - `EmotivaNetworkDiscovery`: Dedicated component for device discovery
  - `BroadcastListener`: Listens for device broadcasts on the network
  - `ConnectionManager`: Monitors connection health and handles reconnection
  - `CommandExecutor`: Executes commands with retry logic and error handling

- **Notification System**: Implements the observer pattern for device notifications:
  - `NotificationRegistry`: Manages subscriptions to notifications
  - `NotificationDispatcher`: Routes notifications to callbacks
  - `NotificationListener`: Interface for notification handlers
  - `NotificationFilter`: Filters notifications by type, property, and device

- **Protocol Handling**: Manages communication protocol details:
  - `CommandFormatter`: Formats commands according to the Emotiva protocol
  - `ResponseParser`: Parses responses from the device
  - `EmotivaCommand`: Encapsulates command metadata

- **State Management**: Manages device state tracking and validation:
  - `EmotivaState`: Core state container with property validation
  - `PropertyValidator`: Validates property values against defined constraints
  - `StateChangeNotifier`: Notifies subscribers of state changes
  - `PropertyChangeNotification`: Represents a property change event

### Design Patterns

- **Observer Pattern**: The notification system uses the observer pattern to allow components to subscribe to specific notifications without tight coupling.
- **Command Pattern**: Encapsulates requests as objects, allowing for parameterization, queuing, and retry logic.
- **Factory Method**: Used for creating different types of sockets and notification handlers.
- **Facade Pattern**: The `EmotivaController` provides a simplified interface to the complex subsystem of components.

## Installation

Install the library using pip:

```bash
pip install pymotivaxmc2
```

For development installation, clone the repository and install in editable mode:

```bash
git clone https://github.com/droman42/pymotivaxmc2.git
cd pymotivaxmc2
pip install -e .
```

## Device Configuration

Before using this library, ensure your Emotiva device is properly configured for network control:

1. Network Settings:
   - Connect the device to your local network
   - Ensure it has a valid IP address (static or DHCP)
   - Power on the device

2. Protocol Version:
   - The device defaults to Protocol Version 2.0
   - This library automatically requests Protocol 3.1 features
   - No manual configuration needed

3. Port Configuration:
   - Discovery requests: UDP port 7000
   - Discovery responses: UDP port 7001
   - Command communication: Port specified in transponder response (typically 7002)
   - Notification communication: Port specified in transponder response (typically 7003)

4. Device Settings:
   - Enable network control in the device's settings menu:
     1. Press the Menu button on the remote or front panel
     2. Navigate to "Settings" using the arrow keys
     3. Select "Network" from the settings menu
     4. Choose "Network Control"
     5. Set to "Enabled"
   - Set a friendly name for the device (optional):
     1. In the same Network menu
     2. Select "Device Name"
     3. Enter desired name using the on-screen keyboard
   - Ensure no firewall is blocking the required UDP ports

5. Network Requirements:
   - Enable UDP broadcast on your network
   - Keep the device on the same subnet as your control application
   - Avoid network isolation or VLAN separation that would prevent UDP communication

To verify the device is properly configured:
```bash
emotiva-cli discover --ip <device_ip>
```

If properly configured, you should receive a response with:
- Model name
- Revision number
- Friendly name
- Protocol version
- Control port
- Notification port
- Keepalive interval

Troubleshooting:
1. Check the device's network settings
2. Verify UDP ports 7000-7003 are not blocked
3. Confirm network control is enabled in device settings
4. Ensure your network allows UDP broadcast traffic

## Usage

### As a Library

The library is fully asynchronous and uses Python's asyncio framework. Make sure to use `await` with all method calls.

```python
import asyncio
from pymotivaxmc2 import EmotivaController

async def main():
    # Create an instance of the controller
    controller = EmotivaController(ip="192.168.1.100")

    # Discover the device
    discovery_result = await controller.discover()

    # Power control
    await controller.set_power_on()    # Turn main zone on
    await controller.set_power_off()   # Turn main zone off
    await controller.toggle_power()    # Toggle main zone power
    await controller.get_power()       # Get current main zone power status

    # Source/Input Selection
    await controller.set_source('hdmi1')  # Set source to HDMI 1
    
    # Enhanced direct HDMI selection 
    await controller.switch_to_hdmi(1)    # Set both video and audio to HDMI 1

    # Using any source command
    await controller.switch_to_source('hdmi1')      # HDMI inputs
    await controller.switch_to_source('analog1')    # Analog inputs
    await controller.switch_to_source('optical2')   # Digital inputs
    await controller.switch_to_source('tuner')      # Tuner

    # Volume control
    await controller.set_volume(-40)  # Set absolute volume to -40dB
    await controller.set_volume(1)    # Increase volume by 1dB
    await controller.set_volume(-1)   # Decrease volume by 1dB

    # Zone 2 Control
    await controller.get_zone2_power()      # Request Zone 2 power status
    await controller.set_zone2_power_on()   # Turn on Zone 2
    await controller.set_zone2_power_off()  # Turn off Zone 2
    await controller.toggle_zone2_power()   # Toggle Zone 2 power

    # Property Subscriptions and Updates
    # Set up a callback to receive notifications
    def handle_notification(notification):
        print(f"Notification received: {notification}")
        
    controller.subscribe_to_events(handle_notification)

    # Subscribe to specific properties
    await controller.subscribe_to_notifications([
        "power", "zone2_power", "volume", "source"
    ])

    # Request updates for specific properties
    await controller.update_properties([
        "power", "zone2_power", "volume", "source"
    ])
    
    # Always close the connection when done
    await controller.close()

# Run the async function
asyncio.run(main())
```

### Command Line Interface

The package includes a command-line interface for basic operations. The CLI handles the async implementation internally for you:

```bash
# Device Discovery
emotiva-cli discover --ip 192.168.1.100

# Get device status
emotiva-cli status --ip 192.168.1.100

# Power control
emotiva-cli power on --ip 192.168.1.100
emotiva-cli power off --ip 192.168.1.100
emotiva-cli power toggle --ip 192.168.1.100
emotiva-cli power status --ip 192.168.1.100

# Query specific information
emotiva-cli query power --ip 192.168.1.100
emotiva-cli query zone2_power --ip 192.168.1.100
emotiva-cli query input --ip 192.168.1.100
emotiva-cli query mode --ip 192.168.1.100
emotiva-cli query custom power volume input --ip 192.168.1.100

# Volume control
emotiva-cli volume -40 --ip 192.168.1.100  # Set absolute volume
emotiva-cli volume +1 --ip 192.168.1.100   # Increase volume by 1dB
emotiva-cli volume -1 --ip 192.168.1.100   # Decrease volume by 1dB

# Input/Source selection
emotiva-cli source hdmi1 --ip 192.168.1.100
emotiva-cli input hdmi1 --ip 192.168.1.100

# Enhanced source selection
emotiva-cli hdmi 1 --ip 192.168.1.100      # Switch to HDMI 1 (recommended for HDMI)
emotiva-cli switch analog1 --ip 192.168.1.100  # Switch to any source (enhanced method)

# Audio modes
emotiva-cli mode stereo --ip 192.168.1.100
emotiva-cli mode_dolby --ip 192.168.1.100
emotiva-cli mode_dts --ip 192.168.1.100
emotiva-cli mode_movie --ip 192.168.1.100

# Zone 2 control
emotiva-cli zone2 power on --ip 192.168.1.100
emotiva-cli zone2 power off --ip 192.168.1.100
emotiva-cli zone2 power toggle --ip 192.168.1.100
emotiva-cli zone2 volume -30 --ip 192.168.1.100
emotiva-cli zone2 source analog1 --ip 192.168.1.100
```

## API Reference

### Main Classes

#### EmotivaController

Main class for device control. All methods are asynchronous and should be awaited:

```python
class EmotivaController:
    # Initialization
    def __init__(ip: str, port: Optional[int] = None, timeout: int = 5, 
                 discover_request_port: int = 7000, discover_response_port: int = 7001,
                 max_retries: int = 3, keepalive_interval: int = 10000)
                 
    # Core methods
    async def discover(timeout: float = 1.0) -> Dict[str, Any]
    async def send_command(cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]
    
    # Power control
    async def set_power_on() -> Dict[str, Any]
    async def set_power_off() -> Dict[str, Any]
    async def toggle_power() -> Dict[str, Any]
    async def get_power() -> Dict[str, Any]
    
    # Source/Input Selection
    async def set_source(source: str) -> Dict[str, Any]
    async def switch_to_hdmi(hdmi_number: int) -> Dict[str, Any]  # Specifically for HDMI inputs
    async def switch_to_source(source_command: str) -> Dict[str, Any]  # For any input type
    
    # Audio Mode control
    async def set_mode(mode: str) -> Dict[str, Any]
    
    # Zone 2 control
    async def get_zone2_power() -> Dict[str, Any]
    async def set_zone2_power_on() -> Dict[str, Any]
    async def set_zone2_power_off() -> Dict[str, Any]
    async def toggle_zone2_power() -> Dict[str, Any]
    
    # Notification handling
    def subscribe_to_events(callback: Callable[[Notification], None]) -> None
    async def subscribe_to_notifications(event_types: Optional[List[str]] = None) -> Dict[str, Any]
    async def update_properties(properties: List[str]) -> Dict[str, Any]
    
    # Resource management
    async def close() -> None  # Clean up resources with timeout handling
```

The controller features optimized notification handling with automatic subscription tracking and improved resource cleanup, including timeout protection and graceful shutdown.

## Input Source Selection

This library provides multiple methods for input source selection:

- `set_source(source)` - Sets the source using a string identifier

- `switch_to_hdmi(hdmi_number)` - HDMI-specific method that tries multiple approaches to set both video and audio inputs to the specified HDMI port (1-8). This method is optimized for reliable HDMI switching.

- `switch_to_source(source_command)` - General-purpose method that accepts any source command from the API specification (section 4.1), such as:
  - `hdmi1` through `hdmi8` (will use specialized HDMI switching)
  - `analog1`