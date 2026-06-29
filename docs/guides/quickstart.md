# Quickstart

Install the library, connect to your processor, and send a command. The whole flow is async — everything
below runs inside `asyncio.run(...)`.

> **You need:** an Emotiva XMC-2 (or compatible) processor powered on and reachable on the same network,
> and its IP address. There's no pairing step and no cloud account.

---

## 1. Install

```bash
pip install pymotivaxmc2
```

Requires Python 3.11+. The only runtime dependency is `typing-extensions`.

## 2. Connect and control

The recommended entry point is the high-level **`EmotivaController`**. `connect()` finds the device, reads
its capabilities, negotiates the protocol version, and binds the UDP ports; `disconnect()` tears it all
down. Wrap your work in `try` / `finally` so you always disconnect cleanly:

```python
import asyncio
from pymotivaxmc2 import EmotivaController, Property

async def main():
    ctrl = EmotivaController("192.168.1.50")     # your processor's IP
    await ctrl.connect()
    try:
        await ctrl.power_on()
        await ctrl.set_volume(-25.0)              # absolute dB
        await ctrl.select_input("hdmi1")

        # Read a snapshot of some properties
        snap = await ctrl.status(Property.POWER, Property.VOLUME, Property.SOURCE)
        for prop, value in snap.items():
            print(f"{prop.name.lower():<8} = {value}")
    finally:
        await ctrl.disconnect()

asyncio.run(main())
```

`connect()` does several things for you:

| Step | What happens |
|---|---|
| Discovery | A `<emotivaPing>` to UDP 7000; the device answers on 7001 with its model and ports |
| Protocol negotiation | Uses the lower of the device's version and your `protocol_max` (default `"3.1"`) |
| Port binding | Binds the control port (commands/acks) and notify port (events) |
| Dispatcher | Starts the background loop that delivers subscriptions to your callbacks |

See **[Connection & discovery](connection.md)** for the details, and **[Commands](commands.md)** for the
full helper surface.

## 3. Listen for changes

Instead of polling, subscribe to the properties you care about and the device pushes you an event whenever
they change. Register the callback with `@ctrl.on(...)`, then `subscribe(...)`. The callback is an
`async def` (a plain `def` works too) taking a single argument — the new value:

```python
import asyncio
from pymotivaxmc2 import EmotivaController, Property

async def main():
    ctrl = EmotivaController("192.168.1.50")
    await ctrl.connect()
    try:
        @ctrl.on(Property.VOLUME)
        async def on_volume(value):
            print("Volume:", value, "dB")

        @ctrl.on(Property.POWER)
        async def on_power(value):
            print("Power:", value)

        # Subscribe AFTER registering — subscribe() replays the current value
        # through your callbacks, so you start from a known state.
        await ctrl.subscribe([Property.VOLUME, Property.POWER])

        await asyncio.sleep(60)                    # events arrive for a minute
    finally:
        await ctrl.disconnect()

asyncio.run(main())
```

See **[Subscriptions](subscriptions.md)** for every detail — the value shape, error handling, and what
happens across a reconnect.

---

## A two-zone note

Every power / volume / mute helper takes a keyword-only `zone`:

```python
from pymotivaxmc2 import Zone

await ctrl.power_on(zone=Zone.ZONE2)
await ctrl.set_volume(-30.0, zone=Zone.ZONE2)
```

`Zone.MAIN` is the default. Input/source selection and `get_input_names()` are main-zone only — see
[Commands](commands.md).

## Logging

The library logs through the standard `logging` module under the `pymotivaxmc2` namespace. Turn it on (and
optionally dump every XML frame) with the bundled helper:

```python
import logging
from pymotivaxmc2 import setup_logging

setup_logging(level=logging.DEBUG, show_xml=True)   # show_xml logs sent/received XML
```

## Dropping to the protocol core

`EmotivaController` is the protocol core (`SocketManager` + `Protocol` + `Dispatcher`) with the wiring done
for you. When you want that wiring yourself — embedding in a larger supervisor, say — assemble the pieces
by hand:

```python
import asyncio
from pymotivaxmc2.core.discovery import Discovery
from pymotivaxmc2.core.socket_mgr import SocketManager
from pymotivaxmc2.core.protocol import Protocol
from pymotivaxmc2.core.dispatcher import Dispatcher

async def main():
    info = await Discovery("192.168.1.50").fetch_transponder()
    ports = {
        "controlPort": info.get("controlPort", 7002),
        "notifyPort": info.get("notifyPort", 7003),
    }
    sockets = SocketManager("192.168.1.50", ports)
    await sockets.start()

    protocol = Protocol(sockets, protocol_version=info.get("protocolVersion", "2.0"))
    dispatcher = Dispatcher(sockets, "notifyPort")
    protocol.dispatcher = dispatcher          # so subscribe() can fan initial values out
    await dispatcher.start()

    await protocol.send_command("power_on")
    # ... do work ...

    await dispatcher.stop()
    await sockets.stop()

asyncio.run(main())
```

Everything the facade does, you can do here — it just hands you the moving parts. See the
[Architecture overview](../architecture/overview.md) for how the two relate.

## Where to go next

- **[Commands](commands.md)** — the full command surface and the enums.
- **[Subscriptions](subscriptions.md)** — real-time events.
- **[Connection & discovery](connection.md)** — how `connect()` finds the device.
- **[Command-line interface](cli.md)** — drive the device from the shell with `emu-cli`.
