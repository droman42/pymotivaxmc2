# Command-line interface

The package ships **`emu-cli`**, a thin command-line front end over `EmotivaController`. It's the quickest
way to poke at a processor — power it on, nudge the volume, read a status snapshot — without writing any
code. Everything it does maps directly to a [controller helper](commands.md).

```bash
emu-cli --host 192.168.1.50 power on
```

`--host` is required and names the device's IP or hostname. Every invocation connects, runs the one
subcommand, prints `Connection OK`, and disconnects.

## Subcommands

### Power

```bash
emu-cli --host 192.168.1.50 power on
emu-cli --host 192.168.1.50 power off
emu-cli --host 192.168.1.50 power toggle
```

### Volume

Absolute set takes a dB value; up/down take an optional `--step` (default 1 dB):

```bash
emu-cli --host 192.168.1.50 volume set -28.5
emu-cli --host 192.168.1.50 volume up --step 2
emu-cli --host 192.168.1.50 volume down
```

### Mute

```bash
emu-cli --host 192.168.1.50 mute on
emu-cli --host 192.168.1.50 mute off
emu-cli --host 192.168.1.50 mute toggle
```

### Input

Selects a physical connector by name (an [`Input`](commands.md#the-enums) member, lower-cased):

```bash
emu-cli --host 192.168.1.50 input set hdmi3
emu-cli --host 192.168.1.50 input set coax2
```

### Status

Prints the current value of one or more properties. Argument names match `Property` members (lower-cased):

```bash
emu-cli --host 192.168.1.50 status power volume source
# power    : On
# volume   : -25.0
# source   : HDMI 1
```

An unknown property name exits with an error, so stick to real `Property` names — `power`, `volume`,
`source`, `mode`, `bass`, `treble`, `loudness`, `zone2_power`, `zone2_volume`, and so on (see
[`enums.py`](../../pymotivaxmc2/enums.py)).

### Zone 2

A subset of the controls, scoped to Zone 2:

```bash
emu-cli --host 192.168.1.50 zone2 power on
emu-cli --host 192.168.1.50 zone2 volume down
emu-cli --host 192.168.1.50 zone2 volume set -30
```

## Exit codes and errors

The CLI maps the library's exceptions to friendly messages on `stderr` and exits non-zero:

| Situation | Message | Exit |
|---|---|---|
| No ack after retries | `Error: No ack received for command ...` | 1 |
| Bad argument (unknown input/property) | `Error: unknown input '...'` / `Unknown property '...'` | 1 |
| Device unreachable | `Error: Device at <host> did not respond in time ...` | 1 |
| Anything else | `Unexpected error: ...` | 1 |

By default the CLI sets logging to `ERROR` with XML dumping enabled, so a failed run shows the offending
frames. Run any subcommand with `--help` for its exact arguments.

## When to reach for the API instead

`emu-cli` is one-shot: it connects and disconnects per command, so it's not the tool for *watching* the
device. For live notifications, long-running control, or anything programmatic, use
[`EmotivaController`](quickstart.md) directly — the CLI is just a wrapper over the same helpers.

## Where to go next

- **[Commands](commands.md)** — the helpers each subcommand calls.
- **[Quickstart](quickstart.md)** — the same operations in code, plus subscriptions.
