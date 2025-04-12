# pymotivaxmc2

A Python library for controlling eMotiva A/V receivers.
This is a full rewrite of the original pymotiva project (https://github.com/thecynic/pymotiva), with additional features and improvements.
It was tested to work with eMotiva XMC-2. Original functionality should still work, but I don't have devices to test with.

## Features

- Control eMotiva A/V receivers over the network
- Support for various commands (power, volume, source selection, etc.)
- Asynchronous operation
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

# Create a configuration
config = EmotivaConfig(
    host="192.168.1.100",  # Your Emotiva device's IP address
    port=7025             # Default port for Emotiva devices
)

# Create an instance
emotiva = Emotiva(config)

# Connect to the device
await emotiva.connect()

# Send commands
await emotiva.power_on()
await emotiva.set_volume(-40)  # Volume in dB
await emotiva.set_source("XLR1")

# Disconnect when done
await emotiva.disconnect()
```

### Command Line Interface

The package includes a command-line interface for basic operations:

```bash
# Get device status
emotiva-cli status --host 192.168.1.100

# Power on the device
emotiva-cli power on --host 192.168.1.100

# Set volume
emotiva-cli volume -40 --host 192.168.1.100

# Change source
emotiva-cli source XLR1 --host 192.168.1.100
```

## API Reference

### Main Classes

#### EmotivaConfig

Configuration class for Emotiva devices:

```python
class EmotivaConfig:
    host: str          # Device IP address
    port: int = 7025   # Device port (default: 7025)
    timeout: int = 5   # Connection timeout in seconds
```

#### Emotiva

Main class for device control:

```python
class Emotiva:
    async def connect() -> None
    async def disconnect() -> None
    async def power_on() -> None
    async def power_off() -> None
    async def set_volume(volume_db: float) -> None
    async def set_source(source: str) -> None
    async def get_status() -> dict
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License 