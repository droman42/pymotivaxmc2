# pymotivaxmc2 — agent notes

Async client for Emotiva XMC-2 (and compatible) processors over their UDP remote interface. A typed
library (`py.typed`) consumed by `wb-mqtt-bridge` and others — so its public surface and its docs are
contracts.

## Invariants — apply to EVERY task

Referenced by **name** (stable slug), never by number — names survive reordering, so references don't
break. These are always-on; they are not optional per task.

- **`work-on-main`** — Work directly on `main`. Branch only when the maintainer explicitly asks; if you
  branch transiently, fast-forward merge back into `main` and delete the branch (local + remote).
  **Releases ship by pushing a lightweight `vX.Y.Z` git tag**: `release.yml` validates that the tag equals
  `version` in `pyproject.toml`, then builds and publishes to PyPI. Keep `pyproject.toml` `version` and
  `pymotivaxmc2/__init__.py` `__version__` in sync, and add the matching entry to **`CHANGELOG.md`** in the
  same change; `setup.py` is a stale shim that defers to `pyproject.toml` and is otherwise ignored.

- **`no-cycles-no-type-checking`** — No circular dependencies between modules, and **no `TYPE_CHECKING`**
  in particular: `from typing import TYPE_CHECKING` and `if TYPE_CHECKING:` guards are forbidden (they are
  the usual band-aid for a cycle — fix the layering instead). The import layering is strict and
  one-directional: `cli` → `controller` → `core` (`protocol`/`dispatcher`/`socket_mgr`/`discovery`/
  `xmlcodec`) → leaf `enums` / `exceptions` (every import points down, never up; see
  [docs/architecture/overview.md](docs/architecture/overview.md)). Enforced as **hard CI gates**
  (`droman42/py-dev-gates`); run all three locally before pushing:
  ```bash
  lint-imports                          # import-linter layering contracts (catches cycles/backwards imports)
  check-no-type-checking pymotivaxmc2   # forbids TYPE_CHECKING
  pyright                               # 0 errors, no blanket suppressions
  ```
  Any type suppression must be a per-line `# type: ignore[<rule>]` with a justifying comment — never a
  blanket `report*: "none"`. See [CONTRIBUTING.md](CONTRIBUTING.md).

- **`user-facing-docs-are-done`** — User-facing docs must always reflect code reality. A task isn't done
  until the docs it touched are verified and, if needed, adjusted **in the same change** — this includes
  **diagrams**. The doc set:
  - `README.md` (facade-first overview + doc index), `docs/architecture/`, `docs/guides/` (quickstart,
    commands, subscriptions, connection, cli). `docs/Emotiva_Remote_Interface_Description.md` is the
    vendored protocol spec (deeper reference); `docs/emotiva_lib_fixes.md` is frozen historical review (not
    linked from the README).
  - **Diagrams are Graphviz `.dot` sources rendered to `.png`, committed as a pair.** Shared palette and
    the render command live in each `.dot` header comment. After editing a `.dot`, regenerate and commit
    both files:
    ```bash
    dot -Tpng docs/images/<name>.dot -o docs/images/<name>.png
    ```
  - When a change alters the public API, a property/notification payload, the layering, or the wire
    protocol, update the matching guide (and its diagram) so an example never describes code that no longer
    exists.

## This is a library: 0 errors is a contract

`pymotivaxmc2` ships a `py.typed` marker (PEP 561), so every type you write is a type your consumers (e.g.
`wb-mqtt-bridge`) see at *their* pyright step. Annotate the full public surface; a pyright error you
introduce becomes one in every consumer that pins the release. Keep `pymotivaxmc2/py.typed` present (shipped
via `[tool.setuptools.package-data]`). A change to any public signature or a new public method is a
**minor** bump; internals / tests / CI only is a **patch**. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
full policy.

## Where things are

- Source: `pymotivaxmc2/` — `controller.py` (the `EmotivaController` facade), `core/` (`protocol.py`
  command/ack + subscribe, `dispatcher.py` notification loop, `socket_mgr.py` UDP ports, `discovery.py`
  ping/transponder, `xmlcodec.py` XML build/parse, `logging.py`), `cli.py` (`emu-cli`), `enums.py`
  (`Command`/`Property`/`Input`/`Zone`), `exceptions.py`.
- Tests: `tests/` (unit, CI-gated). Run the suite with `pytest`.
