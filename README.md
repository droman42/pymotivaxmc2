# pymotivaxmc2

A slim asynchronous Python library for controlling Emotiva XMC‑2 (and compatible) devices over their UDP remote interface.

## Features

- Asynchronous API for non-blocking operation
- Type-safe command and property access via enums
- Automatic protocol version negotiation
- Property change notifications
- Command-line interface for quick testing

## Installation

```bash
pip install pymotivaxmc2
```

## Quick Start

```python
import asyncio
from pymotivaxmc2 import EmotivaController, Property, Command, Zone

async def main():
    # Create controller for device at 192.168.1.50
    ctrl = EmotivaController("192.168.1.50")
    
    # Connect to the device
    await ctrl.connect()
    
    # Subscribe to volume changes
    await ctrl.subscribe(Property.VOLUME)
    
    # Register callback for volume changes
    @ctrl.on(Property.VOLUME)
    async def vol_changed(value):
        print(f"Volume is now {value} dB")
    
    # Set volume to -25 dB
    await ctrl.set_volume(-25.0)
    
    # Power on the device
    await ctrl.power_on()
    
    # Wait a minute
    await asyncio.sleep(60)
    
    # Disconnect
    await ctrl.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

## Command-Line Interface

The package includes a command-line interface for quick testing:

```bash
# Power control
emu-cli --host 192.168.1.50 power on
emu-cli --host 192.168.1.50 power toggle

# Volume control
emu-cli --host 192.168.1.50 volume up --step 2
emu-cli --host 192.168.1.50 volume set -28.5

# Zone 2 control
emu-cli --host 192.168.1.50 zone2 power on
emu-cli --host 192.168.1.50 zone2 volume down

# Input selection
emu-cli --host 192.168.1.50 input set hdmi3

# Status query
emu-cli --host 192.168.1.50 status power volume mute input
```

## Documentation

For more detailed documentation, visit [pymotivaxmc2.readthedocs.io](https://pymotivaxmc2.readthedocs.io/).

## Requirements

- Python 3.11 or higher
- typing-extensions 3.7.4 or higher

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Version History

- 0.6.0: Added full enums and high-level helpers
- 0.5.0: Improved notification handling
- 0.4.0: Added command-line interface
- 0.3.0: Added property subscription
- 0.2.0: Initial public release
