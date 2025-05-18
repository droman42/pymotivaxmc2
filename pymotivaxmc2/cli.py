#!/usr/bin/env python3
"""emu-cli — command‑line controller for Emotiva processors

This tool exercises the **pymotivaxmc2 ≥ 0.2.0** async API.  It covers every
high‑level helper currently implemented in the facade:

* Main‑zone power / volume / mute / input
* Zone‑2 power / volume / mute
* Snapshot status queries on arbitrary properties

Usage examples
==============

```bash
# power control
emu-cli --host 192.168.1.50 power on
emu-cli --host 192.168.1.50 power toggle

# main‑zone volume
emu-cli --host 192.168.1.50 volume up --step 2
emu-cli --host 192.168.1.50 volume set -28.5

# zone 2
emu-cli --host 192.168.1.50 zone2 power on
emu-cli --host 192.168.1.50 zone2 volume down

# change input
emu-cli --host 192.168.1.50 input set hdmi3

# query status snapshot (multiple properties)
emu-cli --host 192.168.1.50 status power volume mute current_input
```

Run any sub‑command with `--help` for details.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Sequence
import logging
from pymotivaxmc2 import (
    EmotivaController,
    Command,
    Property,
    Input,
    Zone,
    AckTimeoutError,
    InvalidArgumentError,
    setup_logging,
)

# Configure logging
setup_logging(level=logging.ERROR, show_xml=True)

# ---------------------------------------------------------------------------
# Argument parsing helpers
# ---------------------------------------------------------------------------

def positive_float(value: str) -> float:
    try:
        f = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    return f


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emu-cli",
        description="Command‑line controller for Emotiva processors",
    )
    parser.add_argument("--host", required=True, help="IP address or hostname of the device")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- power ------------------------------------------------------------
    power = sub.add_parser("power", help="Main‑zone power control")
    power.add_argument("action", choices=["on", "off", "toggle"])

    # ---- volume -----------------------------------------------------------
    volume = sub.add_parser("volume", help="Main‑zone volume control")
    vol_sub = volume.add_subparsers(dest="action", required=True)

    up = vol_sub.add_parser("up", help="Volume +step dB (default 1)")
    up.add_argument("--step", type=positive_float, default=1.0)

    down = vol_sub.add_parser("down", help="Volume -step dB (default 1)")
    down.add_argument("--step", type=positive_float, default=1.0)

    set_ = vol_sub.add_parser("set", help="Set absolute volume in dB")
    set_.add_argument("value", type=float)

    # ---- mute -------------------------------------------------------------
    mute = sub.add_parser("mute", help="Main‑zone mute control")
    mute.add_argument("action", choices=["on", "off", "toggle"])

    # ---- input ------------------------------------------------------------
    inp = sub.add_parser("input", help="Main‑zone input selection")
    inp_sub = inp.add_subparsers(dest="action", required=True)
    set_in = inp_sub.add_parser("set", help="Select input")
    set_in.add_argument("name", help="input name, e.g. hdmi1, coax2, usb…")

    # ---- status -----------------------------------------------------------
    status = sub.add_parser("status", help="Query property values")
    status.add_argument("properties", nargs="+", help="property names (power, volume, …)")

    # ---- zone 2 -----------------------------------------------------------
    z2 = sub.add_parser("zone2", help="Zone‑2 commands")
    z2_sub = z2.add_subparsers(dest="z2cmd", required=True)

    # zone2 power
    z2_pow = z2_sub.add_parser("power", help="Zone‑2 power control")
    z2_pow.add_argument("action", choices=["on", "off", "toggle"])

    # zone2 volume
    z2_vol = z2_sub.add_parser("volume", help="Zone‑2 volume control")
    z2_vol_sub = z2_vol.add_subparsers(dest="action", required=True)
    z2_up = z2_vol_sub.add_parser("up")
    z2_up.add_argument("--step", type=positive_float, default=1.0)
    z2_down = z2_vol_sub.add_parser("down")
    z2_down.add_argument("--step", type=positive_float, default=1.0)
    z2_set = z2_vol_sub.add_parser("set")
    z2_set.add_argument("value", type=float)

    return parser

# ---------------------------------------------------------------------------
# High‑level action dispatch helpers
# ---------------------------------------------------------------------------

async def do_power(ctrl: EmotivaController, action: str, zone: Zone):
    if action == "on":
        await ctrl.power_on(zone=zone)
    elif action == "off":
        await ctrl.power_off(zone=zone)
    else:
        await ctrl.power_toggle(zone=zone)


async def do_volume(ctrl: EmotivaController, action: str, zone: Zone, **kwargs):
    if action == "set":
        await ctrl.set_volume(kwargs["value"], zone=zone)
    elif action == "up":
        await ctrl.vol_up(kwargs["step"], zone=zone)
    elif action == "down":
        await ctrl.vol_down(kwargs["step"], zone=zone)


async def do_mute(ctrl: EmotivaController, action: str, zone: Zone):
    if action == "on":
        await ctrl.mute_on(zone=zone)
    elif action == "off":
        await ctrl.mute_off(zone=zone)
    else:
        await ctrl.mute_toggle(zone=zone)


async def do_input(ctrl: EmotivaController, name: str):
    try:
        input_enum = Input[name.upper()]
    except KeyError as exc:
        raise InvalidArgumentError(f"unknown input '{name}'") from exc
    await ctrl.select_input(input_enum)


async def do_status(ctrl: EmotivaController, names: Sequence[str]):
    props: list[Property] = []
    for n in names:
        try:
            props.append(Property[n.upper()])
        except KeyError:
            print(f"Unknown property '{n}'", file=sys.stderr)
            sys.exit(1)
    values = await ctrl.status(*props)
    for p, v in values.items():
        print(f"{p.name.lower():<15}: {v}")


# ---------------------------------------------------------------------------
# Main async entry
# ---------------------------------------------------------------------------

async def main(argv: Sequence[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)

    ctrl = EmotivaController(args.host)
    try:
        await ctrl.connect()
        print(f"Connection OK")

        if args.cmd == "power":
            await do_power(ctrl, args.action, Zone.MAIN)
        elif args.cmd == "volume":
            # Create filtered kwargs that exclude 'action' to avoid parameter conflict
            filtered_kwargs = {k: v for k, v in vars(args).items() if k != 'action'}
            await do_volume(ctrl, args.action, Zone.MAIN, **filtered_kwargs)
        elif args.cmd == "mute":
            await do_mute(ctrl, args.action, Zone.MAIN)
        elif args.cmd == "input":
            await do_input(ctrl, args.name)
        elif args.cmd == "status":
            await do_status(ctrl, args.properties)
        elif args.cmd == "zone2":
            if args.z2cmd == "power":
                await do_power(ctrl, args.action, Zone.ZONE2)
            elif args.z2cmd == "volume":
                # Create filtered kwargs that exclude 'action' to avoid parameter conflict
                filtered_kwargs = {k: v for k, v in vars(args).items() if k != 'action'}
                await do_volume(ctrl, args.action, Zone.ZONE2, **filtered_kwargs)
        else:
            parser.error("Invalid command")

    except AckTimeoutError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except InvalidArgumentError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except asyncio.TimeoutError:
        print(f"Error: Device at {args.host} did not respond in time. Please check the connection and IP address.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        await ctrl.disconnect()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
