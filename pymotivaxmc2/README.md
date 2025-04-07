# pymotiva

A Python library for controlling Emotiva A/V receivers over the network.

## Features

- Device discovery
- Command sending
- Event notification handling
- Thread-safe socket management
- Comprehensive error handling
- Type hints for better IDE support

## Installation

```bash
pip install pymotiva
```

## Usage

### Basic Usage

```python
from pymotiva import Emotiva, EmotivaConfig

# Create configuration
config = EmotivaConfig(
    ip="192.168.1.100",  # Replace with your device's IP
    timeout=2,
    max_retries=3
)

# Initialize the controller
emotiva = Emotiva(config)

# Discover the device
try:
    port = emotiva.discover()
    print(f"Device discovered on port {port}")
except InvalidTransponderResponseError as e:
    print(f"Discovery failed: {e}")

# Set up notification callback
def handle_notification(data):
    print(f"Received notification: {data}")

emotiva.set_callback(handle_notification)

# Send commands
try:
    response = emotiva.send_command("power", {"value": "on"})
    print(f"Command response: {response}")
except InvalidTransponderResponseError as e:
    print(f"Command failed: {e}")
```

### Advanced Usage

```python
from pymotiva import Emotiva, EmotivaConfig
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create configuration with custom settings
config = EmotivaConfig(
    ip="192.168.1.100",
    timeout=5,
    discover_request_port=7000,
    discover_response_port=7001,
    max_retries=5,
    retry_delay=2.0
)

# Initialize with custom configuration
emotiva = Emotiva(config)

# Handle specific error cases
try:
    emotiva.discover()
except InvalidTransponderResponseError as e:
    print(f"Device discovery failed: {e}")
except InvalidSourceError as e:
    print(f"Invalid source specified: {e}")
except InvalidModeError as e:
    print(f"Invalid mode specified: {e}")
```

## API Reference

### EmotivaConfig

Configuration class for Emotiva device settings.

```python
config = EmotivaConfig(
    ip="192.168.1.100",
    timeout=2,
    discover_request_port=7000,
    discover_response_port=7001,
    max_retries=3,
    retry_delay=1.0
)
```

### Emotiva

Main class for controlling Emotiva devices.

#### Methods

- `discover()`: Discover the device and get its transponder port
- `set_callback(callback)`: Set the notification callback function
- `send_command(cmd, params)`: Send a command to the device

### Exceptions

- `Error`: Base exception class
- `InvalidTransponderResponseError`: Raised for invalid device responses
- `InvalidSourceError`: Raised for invalid source specifications
- `InvalidModeError`: Raised for invalid mode specifications

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.