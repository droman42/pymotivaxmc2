# pymotivaxmc2

An asynchronous Python library for controlling Emotiva XMC-2 (and compatible) processors over their UDP
remote-control interface — discovery, commands, and real-time property notifications, all on `asyncio`.

Python 3.11+ · MIT · typed (`py.typed`)

## Highlights

- **One controller, the whole device.** `EmotivaController` discovers the unit, negotiates the protocol
  version, binds the UDP ports, and hands you typed helpers for power, volume, mute, inputs, and sources —
  then tears it all down on `disconnect()`.
- **Events, not polling.** Subscribe to volume, power, source, mode, and more; the device pushes each
  change to an `async` callback. Subscribe-time values arrive through the same callback, so you reach a
  consistent state the moment you subscribe.
- **A typed command surface.** `Command`, `Property`, `Input`, and `Zone` enums replace magic strings, so
  a wrong input or property is a name error at your editor, not a silent no-op on the wire.
- **Speaks every protocol version.** Auto-negotiates protocol **2.0 / 3.0 / 3.1** from the device's own
  transponder reply and parses both the old element-per-property and the new `<property>`-attribute frame
  shapes.
- **Resilient by default.** Commands are concurrency-limited and retried with exponential backoff; so are
  discovery and subscription. Callbacks run with a timeout so one slow consumer can't stall the notify
  loop.
- **A CLI in the box.** `emu-cli` drives power, volume, mute, input, Zone 2, and status snapshots straight
  from the shell — handy for testing without writing code.
- **Typed end to end.** Ships `py.typed` (PEP 561), so consumers get real autocomplete and type-checking
  against the public surface.

## Install

```bash
pip install pymotivaxmc2
```

## Quick taste

```python
import asyncio
from pymotivaxmc2 import EmotivaController, Property

async def main():
    ctrl = EmotivaController("192.168.1.50")     # your processor's IP
    await ctrl.connect()                          # discover, negotiate, bind ports
    try:
        # React to volume changes the device pushes us
        @ctrl.on(Property.VOLUME)
        async def on_volume(value):
            print("Volume is now", value, "dB")

        await ctrl.subscribe(Property.VOLUME)     # initial value arrives on the callback too

        await ctrl.power_on()
        await ctrl.set_volume(-25.0)
        await asyncio.sleep(30)                    # live notifications for 30s
    finally:
        await ctrl.disconnect()

asyncio.run(main())
```

Register the callback **before** you subscribe — `subscribe()` replays the device's current value through
your `@on` callback, so ordering it first means you never miss the initial state. The
**[Quickstart](docs/guides/quickstart.md)** walks through the whole flow.

> **No pairing, no cloud.** The processor just has to be reachable on the LAN. `connect()` finds it with a
> UDP ping and reads its capabilities from the reply — see **[Connection &
> discovery](docs/guides/connection.md)**.

## Documentation

- **[Architecture overview](docs/architecture/overview.md)** — the layers, the one import rule, and the
  connection lifecycle.
- **[Quickstart](docs/guides/quickstart.md)** — install, connect, and send your first commands.
- **[Commands](docs/guides/commands.md)** — the full helper surface on `EmotivaController`, plus the enums.
- **[Subscriptions](docs/guides/subscriptions.md)** — real-time property events, their callbacks, and the
  reconnect contract.
- **[Connection & discovery](docs/guides/connection.md)** — how `connect()` finds the device, the UDP port
  map, and protocol negotiation.
- **[Command-line interface](docs/guides/cli.md)** — `emu-cli` for driving the device from the shell.

## Development

```bash
git clone https://github.com/locveil/pymotivaxmc2.git
cd pymotivaxmc2
pip install -e ".[dev]"
pytest
```

Three CI-enforced health gates (import layering, no `TYPE_CHECKING` guards, and `pyright` at zero errors)
guard every commit — see **[Contributing](CONTRIBUTING.md)** for how to run them locally and why a typed
library treats those as contracts.

## Acknowledgements

- The **Emotiva Remote Interface Description** (vendored under
  [`docs/Emotiva_Remote_Interface_Description.md`](docs/Emotiva_Remote_Interface_Description.md)) — the
  protocol specification this library implements.

## License

MIT — see [LICENSE](LICENSE).
