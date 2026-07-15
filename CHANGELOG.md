# Changelog

All notable changes to this project are documented in this file.

## [0.8.0] - 2026-07-15

### Added
- **`EmotivaController.keepalive_interval_ms`** — the device-advertised
  keepAlive interval from the transponder, previously parsed and dropped;
  consumers no longer need to read private state or hard-code the interval.
- **Notification sequence surfacing** — `notification_sequence` /
  `notification_gaps` on the controller (dispatcher tracks the `emotivaNotify`
  sequence attribute, spec §2.6): a gap means notifications were MISSED and
  state may be stale; refresh selectively instead of blind-polling.
- **Per-call retry control**: every controller command helper, `status()`, and
  the protocol transactions accept `retries=` — the number of RE-sends after
  the first attempt (`retries=0` = exactly one packet, for readiness-sensitive
  callers that must not multiply traffic at a device mid-transition).
- **`ack=False` fire-and-forget commands**: builds the command with `ack="no"`
  (the spec makes the ack optional), sends once, awaits nothing, returns
  `None` — the always-awaited ack was the retry-ladder entry point exactly
  when the device is busy.
- **Command pacing**: `EmotivaController(..., min_send_interval=0.1)` enforces
  a minimum gap between all control-port sends (the device has limited
  processing power); `max_retries=` is now constructor-configurable too.

### Fixed
- **`disconnect()` now actually unsubscribes** — the controller tracks the
  session's subscribed properties and names them explicitly (the protocol has
  no "unsubscribe all"; the previous empty `<emotivaUnsubscribe>` cleared
  nothing on the device). No frame is sent when nothing was subscribed.
- **Sockets bind with `SO_REUSEADDR`** — the fixed control/notify ports
  (7002/7003) no longer risk "address already in use" on a rapid
  disconnect→connect cycle (watchdog recovery).

### Changed
- **Batch status reads retry only the missing properties** — a partial Update
  response re-requests just the absent names, never the whole batch, and
  results accumulate across attempts. An empty property request no longer
  sends an empty Update packet.
- **Control-port transactions are now serialized** — exactly one command /
  subscribe / status transaction in flight at a time (was `Semaphore(5)`).
  Emotiva processors have limited processing power (concurrent control traffic
  can make the unit unresponsive — the openHAB Emotiva binding documents the
  same failure), and all control replies arrive on one unkeyed UDP socket, so
  concurrent transactions could steal each other's replies (false timeouts →
  silent retry storms, observed against a live XMC-2). Serialization removes
  both failure modes; the public API is unchanged (concurrent callers queue).
- **Stale control-port frames no longer fail transactions.** Late replies from
  an earlier timed-out attempt are drained before each send
  (`SocketManager.drain`) and discarded if they arrive mid-wait, instead of
  being misread as the current transaction's response and burning a retry.

## [0.7.0] - 2026-06-09

### Added
- `py.typed` marker (PEP 561) — downstream type checkers now honour the inline
  annotations instead of treating the package as untyped.
- User-facing documentation set under `docs/` (architecture overview + guides for
  quickstart, commands, subscriptions, connection/discovery, and the CLI), with
  Graphviz diagrams in `docs/images/`.

### Changed
- Adopted the shared `droman42/py-dev-gates` health gates (import-linter layering
  contracts, a no-`TYPE_CHECKING` gate, and `pyright` pinned at zero errors),
  enforced in CI. See `CONTRIBUTING.md`.

## [0.6.9] - 2026-05-30

### Added
- `subscribe()` now also dispatches initial property values through registered
  `@on(prop)` callbacks, in addition to returning them in the dict. Consumers
  that use the callback pattern no longer need to manually pipe the return value
  to reach a consistent state after subscription — subscribe-time state and
  ongoing notifications now flow through the same callback path. The device
  already sends the current values inside the Subscribe response (Emotiva Remote
  Interface spec §2.1.3), so no extra round-trip is involved.
- `Dispatcher.has_listeners(prop)` and `Dispatcher.dispatch(prop, value)` — the
  public hooks the subscribe-time fan-out uses (the same path as the
  notification loop).

### Changed
- `EmotivaController.subscribe(props)` now delegates to `Protocol.subscribe`,
  returning the `{name: {"value", "visible"}}` dict (previously returned `None`)
  and waiting for the `<emotivaSubscription>` confirmation. Callbacks registered
  via `on()` therefore receive subscribe-time initial values automatically.

### Unchanged (compatibility)
- `subscribe()`'s dict return value is unchanged for callers that don't register
  callbacks (e.g. one-shot scripts); the fan-out is purely additive. A
  misbehaving consumer callback cannot break the subscription — each initial
  dispatch is guarded, mirroring the notification path's resilience.

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
