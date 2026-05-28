# Changelog

All notable changes to this project are documented in this file.

## [0.6.8] - 2026-05-29

### Added
- `EmotivaController.select_source(source: int | str)` — selects a **logical
  source** (the physical remote's "Input N" buttons) via the `source_1`..`source_8`
  / `source_tuner` commands. Unlike `select_input` (a raw connector switch), this
  loads the full configured A/V source profile and carries the user-assigned input
  name. Accepts an integer `1`-`8` or the string `"tuner"`.
  Protocol ref: `docs/Emotiva_Remote_Interface_Description.md` lines 449-457.
- `EmotivaController.get_input_names(timeout=2.0) -> dict[int, dict]` — reads the
  user-assigned Input Button names with their `visible` flag, returning
  `{1: {"name": "ZAPPITI", "visible": True}, ...}`. Hidden buttons report
  `visible=False`. Protocol ref: properties `input_1`..`input_8`
  (`docs/Emotiva_Remote_Interface_Description.md` lines 642-649), reported with the
  `visible` attribute in the Update response (lines 305-312, 427-439).
- `Protocol.request_properties_full(properties, timeout)` — lower-level property
  query that preserves the per-property `visible` attribute, returning
  `{name: {"value": str, "visible": bool}}`.
- `EmotivaController(..., ack_timeout=2.0)` — the ack timeout is now configurable
  and passed through to the underlying `Protocol`.

### Changed
- `Protocol.request_properties` is now a thin wrapper over
  `request_properties_full` (returns the same name→value mapping as before; no
  behavior change).

### Unchanged (compatibility)
- `select_input(input)` still performs a raw physical-connector switch
  (`hdmi1`, `coax1`, …) and `status(*props)` still returns name→value only.
