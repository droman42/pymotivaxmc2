# Contributing to pymotivaxmc2

Thanks for helping improve the library. Please read the health-gate policy
below before opening a pull request — CI enforces it and will hard-fail
otherwise.

## Three health gates — CI-enforced

`pymotivaxmc2` runs the same Python health gates as its sibling projects, via
the shared composite action
[`droman42/py-dev-gates/.github/actions/python-health`](https://github.com/droman42/py-dev-gates).
All three hard-fail the build:

1. **import-linter** — layering contracts (`[tool.importlinter]` in
   `pyproject.toml`). The package is small but directional: `cli` →
   `controller` → `core` → leaf `enums` / `exceptions`. Dependencies point
   inward; the contracts fail if that reverses.
2. **check-no-type-checking** — AST-based gate that forbids
   `from typing import TYPE_CHECKING` and `if TYPE_CHECKING:` guards. A guard
   is a band-aid for an import cycle; hoist the import to module top or break
   the cycle instead.
3. **pyright** — pinned to `1.1.410`, **0 errors**, **empty suppression
   list**. Config lives in `pyrightconfig.json`.

### Run locally before pushing

```bash
# one-time: create a venv and install the dev extras
python -m venv .venv
.venv/bin/pip install -e ".[dev]"

# the check-no-type-checking CLI ships in py-dev-gates, which is intentionally
# NOT a declared dependency (it is a private git repo, and PyPI rejects packages
# with direct-URL deps in their metadata). Install it once, separately:
.venv/bin/pip install "py-dev-gates @ git+https://github.com/droman42/py-dev-gates@v0.1.1"

# the three gates
.venv/bin/lint-imports                    # import-linter contracts
.venv/bin/check-no-type-checking pymotivaxmc2
.venv/bin/pyright                         # must report 0 errors

# the test suite (behaviour must stay green)
.venv/bin/pytest -v
```

In CI these gates run via the shared `droman42/py-dev-gates` composite action,
which installs `py-dev-gates` itself — so it never needs to be a project
dependency. They live in the `health` job of the single CI workflow
(`.github/workflows/ci.yml`), which also runs the 3.11/3.12 test matrix in
parallel and — on a `vX.Y.Z` tag only, after both pass — the release jobs
(version validation, build, PyPI publish, GitHub release).

## This is a library: 0 errors is a contract, not a preference

`pymotivaxmc2` is consumed by other projects (e.g. `wb-mqtt-bridge`). Because
the package ships a `py.typed` marker (PEP 561), every type you write is a type
your consumers see at *their* pyright step. A fuzzy type here is a fuzzy type
downstream; a pyright error you introduce becomes a pyright error in every
consumer once they pin a release that contains it.

Consequences:

- **Annotate the full public surface** — every parameter and return type on
  public functions/methods. Library type hints are the consumer's autocomplete.
- **Keep `py.typed` present** (`pymotivaxmc2/py.typed`, shipped via
  `[tool.setuptools.package-data]`). Without it, downstream type checkers treat
  the whole package as untyped and ignore your annotations.
- **No blanket suppressions.** If a `# type: ignore` is genuinely unavoidable,
  it must be a *per-line* `# type: ignore[code]` with a comment justifying why.
  The suppression list **is** the audit trail — and it is currently empty.
- **Fix the code, not the test.** If the type sweep surfaces a failing test,
  the fix belongs in the code. Reverting a real type to `Any` is the same as a
  suppression — it just hides the lack of confidence.

## Versioning & release coordination

- A change to any **public signature** (return types, parameter types, even
  widening an `Optional`) or a new public method is a **minor** bump; internals
  / tests / CI only is a **patch**.
- Bump the version in **both** `pyproject.toml` and
  `pymotivaxmc2/__init__.py` (`__version__`) — the release workflow validates
  that the git tag matches `pyproject.toml`.
- After tagging, notify downstream consumers (e.g. bump the pin in
  `wb-mqtt-bridge`) so they pick up the improved types.
