# pymotivaxmc2

A Python library for controlling eMotiva A/V receivers.
This is a full rewrite of the original pymotiva project (https://github.com/thecynic/pymotiva), with additional features and improvements.
It was tested to work with eMotiva XMC-2. Original functionality should still work, but I don't have devices to test with.

## Features

- Control eMotiva A/V receivers over the network
- Support for various commands (power, volume, source selection, etc.)
- Multi-zone control with dedicated Zone 2 methods
- Property subscription and notification handling
- Asynchronous operation with optimized notification management
- Efficient resource cleanup and socket handling
- Command-line interface
- Type hints and modern Python features

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

```python
from pymotivaxmc2 import Emotiva, EmotivaConfig

# Basic initialization and control
# Create a configuration
config = EmotivaConfig(ip="192.168.1.100")

# Create an instance
emotiva = Emotiva(config)

# Discover the device
discovery_result = emotiva.discover()

# Power control
emotiva.set_power_on()    # Turn main zone on
emotiva.set_power_off()   # Turn main zone off
emotiva.toggle_power()    # Toggle main zone power
emotiva.get_power()       # Get current main zone power status

# Source/Input Selection
# Method 1: Using legacy methods (backward compatibility)
emotiva.set_source('hdmi1')
emotiva.set_input('hdmi1')

# Method 2: Enhanced direct HDMI selection with multiple methods (recommended)
emotiva.switch_to_hdmi(1)  # Tries multiple methods to set both video and audio to HDMI 1

# Method 3: Using any source command from API specification section 4.1
emotiva.switch_to_source('hdmi1')      # HDMI inputs (same as switch_to_hdmi)
emotiva.switch_to_source('analog1')    # Analog inputs
emotiva.switch_to_source('optical2')   # Digital inputs
emotiva.switch_to_source('tuner')      # Tuner
emotiva.switch_to_source('source_tuner')  # Alternative tuner command format

# Other commands
emotiva.set_volume(1)  # Increase volume by 1dB

# Zone 2 Control
emotiva.get_zone2_power()  # Request Zone 2 power status via notification
emotiva.set_zone2_power_on()  # Turn on Zone 2
emotiva.set_zone2_power_off()  # Turn off Zone 2
emotiva.toggle_zone2_power()  # Toggle Zone 2 power

# Property Subscriptions and Updates
# Set up a callback to receive notifications
def handle_notification(data):
    print(f"Notification received: {data}")
    
emotiva.set_callback(handle_notification)

# Subscribe to specific properties
emotiva.subscribe_to_notifications([
    "power", "zone2_power", "volume", "source"
])

# Request updates for specific properties
emotiva.update_properties([
    "power", "zone2_power", "volume", "source"
])
```

### Command Line Interface

The package includes a command-line interface for basic operations:

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

# Input/Source selection (legacy methods)
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

#### EmotivaConfig

Configuration class for Emotiva devices:

```python
class EmotivaConfig:
    ip: str           # Device IP address
    timeout: int = 5  # Connection timeout in seconds
    discover_request_port: int = 7000  # Port for discovery requests
    discover_response_port: int = 7001  # Port for discovery responses
    notify_port: int = 7003  # Port for notifications
    max_retries: int = 3  # Maximum number of retry attempts
    keepalive_interval: int = 10000  # Keepalive interval in milliseconds
    default_subscriptions: Optional[List[str]] = None  # Default notification subscriptions
```

#### Emotiva

Main class for device control:

```python
class Emotiva:
    # Core methods
    def discover(timeout: float = 1.0) -> Dict[str, Any]
    def send_command(cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]
    
    # Power control
    def set_power_on() -> Dict[str, Any]
    def set_power_off() -> Dict[str, Any]
    def toggle_power() -> Dict[str, Any]
    def get_power() -> Dict[str, Any]
    
    # Source/Input Selection
    def set_source(source: str) -> Dict[str, Any]  # Legacy method
    def set_input(input_source: str) -> Dict[str, Any]  # Legacy method
    
    # Enhanced Source/Input Selection (recommended)
    def switch_to_hdmi(hdmi_number: int) -> Dict[str, Any]  # Specifically for HDMI inputs
    def switch_to_source(source_command: str) -> Dict[str, Any]  # For any input type
    
    # Audio Mode control
    def set_mode(mode: str) -> Dict[str, Any]
    
    # Zone 2 control
    def get_zone2_power() -> Dict[str, Any]
    def set_zone2_power_on() -> Dict[str, Any]
    def set_zone2_power_off() -> Dict[str, Any]
    def toggle_zone2_power() -> Dict[str, Any]
    
    # Notification handling
    def set_callback(callback: Optional[Callable[[Dict[str, Any]], None]]) -> None
    def subscribe_to_notifications(event_types: Optional[List[str]] = None) -> Dict[str, Any]
    def update_properties(properties: List[str]) -> Dict[str, Any]
    
    # Resource management
    def close() -> None  # Clean up resources with timeout handling
```

This class now features optimized notification handling with automatic subscription tracking and improved resource cleanup, including timeout protection and graceful shutdown.

## Input Source Selection

This library provides multiple methods for input source selection, with enhanced methods that better follow the API specification:

### Legacy Methods (Basic)
- `set_source(source)` - Sets the source using a string identifier
- `set_input(input_source)` - Alternative method for setting the input source

### Enhanced Methods (Recommended)
- `switch_to_hdmi(hdmi_number)` - HDMI-specific method that tries multiple approaches to set both video and audio inputs to the specified HDMI port (1-8). This method is optimized for reliable HDMI switching.

- `switch_to_source(source_command)` - General-purpose method that accepts any source command from the API specification (section 4.1), such as:
  - `hdmi1` through `hdmi8` (will use specialized HDMI switching)
  - `analog1` through `analog5`
  - `optical1` through `optical4`
  - `coax1` through `coax4`
  - `tuner`
  - `source_tuner`
  - `source_1` through `source_8`
  - `ARC`
  - `usb_stream`

The enhanced methods handle proper notification subscription and provide detailed response information.

## Working with Notifications

The library includes an optimized notification system that efficiently manages subscriptions and resource cleanup:

### Automatic Subscription Management
- Default notifications are configured at initialization time
- The library automatically tracks which events are already subscribed to
- Duplicate subscription requests are detected and skipped
- Subscriptions are set up automatically when a callback is registered

```python
# Configure default subscriptions during initialization
config = EmotivaConfig(
    ip="192.168.1.100",
    default_subscriptions=["power", "volume", "input", "audio_input", "video_input"]
)

# Create an instance with optimized notification handling
emotiva = Emotiva(config)

# Set up a callback to receive notifications
def handle_notification(data):
    print(f"Notification received: {data}")
    
# This will automatically set up the notification listener and subscribe to default events
emotiva.set_callback(handle_notification)

# Any additional subscriptions will only subscribe to truly new events
emotiva.subscribe_to_notifications(["zone2_power", "zone2_volume"])
```

### Resource Management
The library implements robust resource management for notifications:

- Socket bindings are properly handled to prevent conflicts
- Notification listeners use efficient asynchronous I/O
- Cleanup operations include timeouts to prevent hanging
- Multiple cleanup mechanisms ensure proper socket closure

```python
# Proper resource cleanup
try:
    # Use the emotiva instance
    await emotiva.subscribe_to_notifications(["power", "volume"])
    await emotiva.set_power_on()
    
    # Other operations...
    
finally:
    # Clean shutdown with timeout protection
    await emotiva.close()
```

### Available Notification Properties

The library supports subscribing to notifications from the device and receiving updates when properties change. Here are some key notification properties you can subscribe to:

### Zone 1 Properties
- `power` - Zone 1 power status ("On"/"Off")
- `volume` - Zone 1 volume level in dB
- `source` - Current input source
- `mode` - Current audio processing mode

### Zone 2 Properties
- `zone2_power` - Zone 2 power status ("On"/"Off")
- `zone2_volume` - Zone 2 volume level in dB
- `zone2_input` - Zone 2 input source
- `zone2_mute` - Zone 2 mute status

### Audio/Video Properties
- `audio_input` - Current audio input
- `audio_bitstream` - Audio bitstream format
- `audio_bits` - Audio bit depth and sample rate
- `video_input` - Current video input
- `video_format` - Video format
- `video_space` - Color space

A full list of available notification properties can be found in the Emotiva Remote Interface Description document.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License 