# pymotivaxmc2

A Python library for controlling Emotiva A/V receivers.
This is a full rewrite of the original pymotiva project (https://github.com/thecynic/pymotiva), with additional features and improvements.
It was tested to work with eMotiva XMC-2. Original functionality should still work, but I don't have devices to test with.

## Features

- Control Emotiva A/V receivers over the network
- Support for various commands (power, volume, source selection, etc.)
- Asynchronous operation
- Command-line interface
- Type hints and modern Python features

## Installation

1. Clone the repository:
```bash
git clone https://github.com/droman42/pymotivaxmc2.git
cd pymotivaxmc2
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

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