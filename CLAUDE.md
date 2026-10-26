# CLAUDE.md — kert

Terminal focus-reader: Compiler (txt → spaCy split-point candidates → SQLite `.kert`)
+ Reader (Rich TUI, assembles chunks client-side, highlights active syntagma).
**The full specification is `kert_spec.md` in the repo root. It is the single
source of truth. When this file and the spec disagree, the spec wins.**

## Environment — uv only

- Python **3.14**, pinned (`.python-version`, `requires-python = ">=3.14,<3.15"`).
- ALL env operations through uv: `uv sync --all-groups`, `uv run pytest`,
  `uv run kert …`, `uv add --group dev <pkg>`. NEVER call `pip`, never create
  venvs manually, never generate `requirements.txt`.
- `uv.lock` is committed. Dependency changes are their own commits.
- **Pin everything**: runtime deps use exact `==` pins; spaCy baseline
  `spacy==3.8.13` (cp314 wheels verified); models installed as exact-version
  URL deps in the `models` group.
- Do NOT use Python 3.14-only language features (spec §2.1 keeps a
  one-line fallback to 3.13 open).

## TDD protocol — mandatory, no exceptions

Every module task follows RED → GREEN → REFACTOR (spec §13.1):

1. **RED**: write the test file FIRST, derived from the referenced spec
   section. Run it; confirm it fails for the right reason
   (NotImplementedError / missing module — not an import typo). A stub
   module raising NotImplementedError is allowed.
2. **GREEN**: implement until that test file passes.
   **Do not edit tests in this phase.** Sole exception: a test contradicts
   `kert_spec.md` → fix the test AND append one line to `SPEC_NOTES.md`
   (test, spec section, resolution).
3. **REFACTOR**: full `uv run pytest` and `uv run ruff check` green before
   the task is done.

Hard rules:
- Never implement behavior no failing test demands (exception: the thin
  `Live`/`readkey` glue in `keys.py`/`app.py` — but `build_frame(state)` and
  `handle_key(state, key) -> state` MUST stay pure and unit-tested).
- **Golden fixtures are hand-derived from the spec (§4.5, §6), never frozen
  from the implementation's own output.** If a sentence is too long to
  hand-derive, shorten the fixture instead.
- spaCy-dependent tests: mark `@pytest.mark.spacy`; skip locally without
  models; mandatory in CI.
- Golden candidate tests are bound to the **pinned model versions**. Never
  upgrade a model as a side effect; a model upgrade is its own task with
  golden regeneration and review.

## Commits

- Min two commits per task: `test(<module>): …` (RED, may include stub),
  then `feat(<module>): …` (GREEN/REFACTOR).
- Conventional commits; English; imperative mood.
- One task = one PR-sized unit. Task order and content: spec §13.2. Do not
  reorder or merge tasks without being asked.

## Architecture invariants (do not violate silently)

- Compiler and Reader are decoupled; they share only `common/`.
- DB stores **split-point candidates**, never baked chunks (spec D4).
- Content tables are write-never after compilation; only `reader_state`,
  `advance_log` (and later `annotations`) are mutable (D8). WAL;
  `wal_checkpoint(TRUNCATE)` on Reader exit.
- Rendering: Rich only, no Textual, no `dim` ANSI attribute, no
  24-bit-only colors, no curses/termios in shared modules (D6, D12).
- Ingest is a pluggable adapter (`Ingester` protocol); everything after
  Normalize consumes the intermediate block model only (D1).
- Settings precedence: per-book `reader_state` > user TOML > hardcoded
  (§8.4). TOML never stores positions.

## Commands quick reference

```
uv sync --all-groups          # provision env + dev tools + models
uv run pytest                 # full suite
uv run pytest -m "not spacy"  # fast suite without models
uv run ruff check && uv run ruff format --check
uv run kert compile fixtures/book_ru.txt -o /tmp/book.kert --lang ru
uv run kert read /tmp/book.kert
uv run kert inspect /tmp/book.kert --sentence 3 --width 8
```

## When in doubt

Re-read the relevant spec section before improvising. If the spec is
genuinely silent or ambiguous, stop and ask — do not invent behavior;
record the eventual resolution in `SPEC_NOTES.md`.
