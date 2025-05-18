# pymotivaxmc2

Slim asynchronous Python library for controlling Emotiva XMC‑2 (and compatible) devices
over their UDP remote interface.

Quick start:

```python
import asyncio
from pymotivaxmc2 import EmotivaController, Property, Command

async def main():
    ctrl = EmotivaController("192.168.1.50")
    await ctrl.connect()

    await ctrl.subscribe(Property.VOLUME)

    @ctrl.on(Property.VOLUME)
    async def vol_changed(value):
        print("Volume is now", value)

    await ctrl.send(Command.SET_VOLUME, db=-25.0)

    await asyncio.sleep(60)
    await ctrl.disconnect()

asyncio.run(main())
```


Version 0.6.0 adds full enums and high-level helpers.
