# kert — Technical Specification (MVP, v0.1)

Status: APPROVED FOR IMPLEMENTATION
Language of codebase, comments, commits: English
Target runtime: Python 3.14 (pinned), cross-platform (Windows Terminal, Linux, macOS)
Tooling: uv (environment, lockfile, task runner). Methodology: strict TDD (section 13).

---

## 1. Product Summary

`kert` is a minimalist terminal eBook reader for high-focus reading. Instead of
page rendering, it splits sentences into short reading fragments (syntagmas,
target 5–12 words), highlights only the active fragment, and dims surrounding
context. It ships as two decoupled components:

1. **Compiler** (`kert compile`) — offline CLI pipeline: parses input text,
   runs spaCy dependency analysis, extracts *ranked split-point candidates*
   per sentence, persists everything into a single SQLite file (`.kert`).
2. **Reader** (`kert read`) — terminal UI built on **Rich** (NOT Textual):
   loads the `.kert` file, assembles chunks from split-point candidates
   according to the user's chunk-width setting, renders the current paragraph
   with the active chunk highlighted, navigates via Vim-style keys.

### Decision Log (locked)

| ID | Decision |
|----|----------|
| D1 | Format roadmap: `.txt` (MVP) → `.md` (v0.2) → EPUB/FB2 (v0.3). Compiler is structured as `Ingest → Normalize → Segment → Chunk-Candidates → Persist`; Ingest is a pluggable adapter. |
| D2 | Paragraph boundary in `.txt`: blank line (default). CLI flag `--paragraph-mode blank|indent|single-newline` reserved; only `blank` implemented in MVP. |
| D3 | One SQLite file per book (`book.kert`). No central library DB. |
| D4 | DB stores ranked split-point candidates, NOT baked chunks. Reader assembles chunks at book-open time for the current chunk-width setting. Changing width never requires recompilation. |
| D5 | MVP: manual advancement only. v0.2: RSVP auto-advance (WPM). v0.3: adaptive RSVP calibrated from the user's manual advance tempo. MVP already logs a timestamp for every advance event to enable future calibration. |
| D6 | UI surface: reading pane + status line only. Settings via Vim-style `:` command line. Framework: Rich (`rich.live.Live`) + manual key loop. Textual explicitly rejected. |
| D7 | Language: MVP requires `--lang ru|en` at compile time. Auto-detect is v0.2. |
| D8 | Reader state (position, settings, advance log) is stored inside the `.kert` file, in tables isolated from content tables. Content tables are write-never after compilation. `PRAGMA journal_mode=WAL`. |
| D9 | Split-point candidates stored as a msgpack blob column on `sentences` (not a normalized table) — optimized for the single full-scan read at book open. |
| D10 | RU dialogue MVP rule: paragraph starting with em-dash `—` → block type `dialogue`; em-dash boundaries inside the paragraph are split candidates with maximum weight; leading dash preserved in rendering. Speaker detection is out of scope. |
| D11 | Status line MVP content: book progress percent only. |
| D12 | No reliance on ANSI DIM (`\x1b[2m`). Explicit colors: active chunk `bold white`, context `grey50` (Rich color, degrades safely on 8-color terminals). |

### Non-goals (MVP)
- EPUB/FB2/Markdown ingestion (documented workaround: convert via pandoc to
  txt). *Superseded by §14 (2026-10-28): these formats are now ingested.*
- RSVP / timed advancement.
- Speaker attribution in dialogues.
- Search, TOC, bookmarks beyond "last position", statistics screens.
- Mouse support.
- Mixed-language books (single `--lang` per book).
- Chapter-heading detection in `.txt` (heuristics are brittle; "Глава 1" /
  "Chapter I" lines become ordinary one-chunk paragraphs in MVP; the
  `heading` block type and `chapter` column are reserved for formats with
  explicit structure, starting with Markdown in v0.2).

---

## 2. Repository Layout

```
kert/
  pyproject.toml            # PEP 621; console script entry point `kert`
  src/kert/
    __init__.py
    cli.py                  # argparse/typer dispatch: compile | read
    common/
      dbschema.py           # schema DDL, schema_version constant, migrations stub
      model.py              # dataclasses: Block, Sentence, SplitCandidate, ChunkSpan
    compiler/
      ingest_txt.py         # TxtIngester (adapter interface: Ingester protocol)
      normalize.py          # unicode NFC, whitespace, dash normalization
      segment.py            # spaCy sentence segmentation per block
      candidates.py         # split-candidate extraction from dependency tree
      persist.py            # SQLite writer
      pipeline.py           # orchestrates Ingest→Normalize→Segment→Candidates→Persist
    reader/
      store.py              # SQLite reader: full scan at open, state read/write
      chunker.py            # chunk assembly from candidates (DP, section 6)
      render.py             # Rich rendering of paragraph + status line
      keys.py               # cross-platform key input (see section 8.3)
      commands.py           # `:` command parser (:set, :goto, :q)
      app.py                # main loop
  tests/
    fixtures/               # small RU + EN txt fixtures, golden chunk outputs
    test_candidates_ru.py
    test_candidates_en.py
    test_chunker.py
    test_ingest_txt.py
    test_roundtrip.py       # compile fixture → open → assemble → golden compare
```

### 2.1 Environment & Tooling (uv)

- **Python: 3.14, pinned** via `.python-version` (`3.14`) and `requires-python = ">=3.14,<3.15"` in `pyproject.toml`. uv manages the interpreter (`uv python install 3.14`).
- **uv is the only entry point** for env management: `uv sync` (create/refresh env from lockfile), `uv run pytest`, `uv run kert …`. `uv.lock` is committed. No `pip`, no manually managed venvs, no `requirements.txt`.
- Dev dependencies go into the `dev` dependency group (`uv add --group dev pytest pytest-cov ruff`): `pytest`, `pytest-cov`, `ruff` (lint + format).
- Runtime dependencies: `rich`, `spacy`, `msgpack`, `readchar`, `typer`, `platformdirs`.
- **spaCy / Python 3.14 compatibility gate.** spaCy supports 3.14 (Thinc ≥ 8.3.13, Pydantic v2), but cp314 wheels have repeatedly been missing from PyPI for individual releases. Therefore:
  - Pin spaCy to a version verified to have cp314 wheels on PyPI for all three target platforms — known-good baseline: `spacy==3.8.13`. At project setup, attempt the newest 3.8.x; if `uv lock` cannot resolve binary wheels for cp314 (or tries to build blis/thinc from source), fall back to the pin above.
  - Task 0 of the implementation plan includes an explicit smoke check: `uv run python -c "import spacy; spacy.load('ru_core_news_sm')"` on the target platform. If the ecosystem is broken for cp314 at implementation time, the documented fallback is downgrading the project to 3.13 — a one-line change to `.python-version` and `requires-python`; nothing else in this spec depends on 3.14-only features, and the implementer must not use them.
- **Determinism policy: pin everything.** All runtime dependencies are declared with exact pins (`==`) in `pyproject.toml`; `uv.lock` freezes the full transitive tree and is committed. Dependency upgrades are deliberate, separate commits (`uv lock --upgrade-package X`), never side effects.
- Models: `ru_core_news_sm`, `en_core_web_sm` — NOT bundled. Installed as direct URL dependencies with **exact versions** in a `models` dependency group in `pyproject.toml` (pip-installable model wheels from the spaCy release GitHub URLs, version-matched to the pinned spaCy), so `uv sync --group models` provisions them reproducibly. The compiler checks model presence at runtime and prints the exact remediation command on failure.
- **Model version = part of the test contract.** Golden candidate tests (§13.2 task 4) encode the parses of the pinned model versions; a model upgrade WILL silently change dependency parses and break goldens. Therefore: the pinned model version is recorded in `meta` (`model_version`), CI installs exactly the pinned models, and a model upgrade is its own task that includes regenerating and re-reviewing the goldens.
- CI: `uv sync --all-groups` → `uv run ruff check` → `uv run pytest`.

---

## 3. SQLite Schema (`.kert` file)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Immutable after compilation ------------------------------------------

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Required keys: schema_version ('1'), title, language ('ru'|'en'),
-- source_format ('txt'), source_filename, paragraph_mode,
-- compiler_version, compiled_at (ISO 8601 UTC),
-- spacy_model, spacy_version, model_version, word_count (int as text).

CREATE TABLE blocks (
    id      INTEGER PRIMARY KEY,          -- ordinal, contiguous from 1
    type    TEXT NOT NULL CHECK (type IN
            ('paragraph','dialogue','heading','code','list_item')),
            -- MVP produces only 'paragraph' and 'dialogue';
            -- remaining values reserved for v0.2 (Markdown).
    chapter INTEGER                        -- reserved, NULL in MVP
);

CREATE TABLE sentences (
    id            INTEGER PRIMARY KEY,     -- ordinal, contiguous from 1, global reading order
    block_id      INTEGER NOT NULL REFERENCES blocks(id),
    seq           INTEGER NOT NULL,        -- order within block, from 0
    text          TEXT NOT NULL,           -- normalized sentence text
    tokens        BLOB NOT NULL,           -- msgpack: list[[char_start, char_end], ...]
                                           -- char offsets into `text`, spaCy tokens,
                                           -- whitespace excluded
    candidates    BLOB NOT NULL            -- msgpack: list[[token_index, weight], ...]
                                           -- token_index = index of FIRST token of the
                                           -- chunk that would start at this cut;
                                           -- weight: float 0..1; sorted by token_index;
                                           -- token_index 0 never present
);
CREATE INDEX idx_sentences_block ON sentences(block_id, seq);

-- Mutable reader state ---------------------------------------------------

CREATE TABLE reader_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Keys: position (JSON: {"sentence_id": int, "chunk_start_token": int}),
--       chunk_width (int as text, default '8'),
--       created/updated lazily by Reader.

CREATE TABLE advance_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,             -- time.time()
    sentence_id INTEGER NOT NULL,
    chunk_words INTEGER NOT NULL,          -- word count of the chunk just left
    direction   INTEGER NOT NULL           -- +1 forward, -1 backward
);
-- Capped: Reader deletes oldest rows beyond 10 000 on session close.
```

Rationale for `candidates` as blob (D9): Reader performs exactly one full
sequential scan at book open; per-row msgpack decode of a small array is
cheaper and simpler than joining a candidates table with millions of rows for
long books.

---

## 4. Compiler Pipeline

`kert compile INPUT.txt -o BOOK.kert --lang ru [--paragraph-mode blank]`

### 4.1 Ingest (`TxtIngester`)
- Read file as UTF-8; on `UnicodeDecodeError`, retry with `utf-8-sig`, then
  `cp1251` if `--lang ru`, else fail with a clear message naming the flag
  `--encoding` (flag itself reserved for later, not implemented).
- Output: ordered list of raw paragraph strings. Paragraph boundary: one or
  more blank lines (lines matching `^\s*$`). Consecutive non-blank lines
  within a paragraph are joined with a single space.

### 4.2 Normalize
- Unicode NFC.
- Remove soft hyphens (U+00AD); replace no-break spaces (U+00A0, U+202F) with regular spaces.
- Collapse internal whitespace runs to single spaces; strip.
- Dash normalization for RU: a paragraph-initial `-` or `–` followed by a
  space is normalized to `—` (em-dash) BEFORE dialogue detection; inline
  ` - ` / ` – ` surrounded by spaces normalized to ` — `. EN: no dash
  normalization.
- Drop empty paragraphs.

### 4.3 Block typing
- If normalized paragraph starts with `— ` → block type `dialogue` (D10).
- Else → `paragraph`.

### 4.4 Segment
- Run spaCy pipeline (parser enabled, NER disabled for speed:
  `nlp = spacy.load(model, disable=["ner", "lemmatizer"])`).
- Use `nlp.pipe(paragraph_texts, batch_size=64)` for throughput.
- Sentence boundaries: spaCy's dependency-parser sentencizer (default for
  these models). Each sentence becomes a `sentences` row; store token char
  spans relative to the sentence text.

### 4.5 Split-candidate extraction (per sentence)

For every token `t` at index `i > 0`, evaluate rules in order; the first
matching rule assigns the weight; if a prohibition applies, no candidate is
emitted at `i`. A candidate at index `i` means "a new chunk may start at
token `i`".

**Weights (candidate at position of the boundary):**

| Priority | Rule | Cut position | Weight |
|---|---|---|---|
| 1 | Sentence-internal punctuation token with `dep_ == "punct"` and text in `, ; : — –` | AFTER the punct token (candidate index = punct_index + 1) | 1.0 |
| 2 | Token with `dep_ in {"mark", "cc"}` (subordinating/coordinating conjunction) | BEFORE the conjunction (candidate index = its index) | 0.8 |
| 3 | Token is the leftmost token of a subtree whose root has `dep_ in {"advcl", "ccomp", "xcomp", "acl", "acl:relcl", "conj"}` | BEFORE that leftmost token | 0.6 |
| 4 | Token is the leftmost token of a subtree whose root has `dep_ in {"nsubj", "obj", "iobj", "obl"}` and the subtree spans ≥ 2 tokens | BEFORE that leftmost token | 0.4 |

If two rules yield the same index, keep the max weight.

**Prohibitions (suppress a candidate at index `i` when):**
- Token `i-1` or `i` is inside a `flat`, `flat:name`, `flat:foreign`, or
  `fixed` relation chain (never split multiword names/idioms).
- Token `i-1` has `dep_ == "case"` (preposition must stay with its NP) —
  i.e., never start a chunk immediately after a bare preposition.
- Token `i-1` is `like_num` and token `i` is a noun (number + unit stay
  together).
- Token `i` is punctuation (chunks never start with punctuation).
- Resulting left fragment would be a single token that is punctuation only.

**Dialogue augmentation (block type `dialogue`):** every inline `—` token
inside the sentence emits a candidate AFTER it with weight 1.0 (D10),
overriding prohibitions except "chunk never starts with punctuation".

**Guaranteed fallback:** if a sentence longer than 15 tokens produced zero
candidates, emit candidates every 10 tokens with weight 0.2 so the Reader can
always split pathological sentences.

### 4.6 Persist
- Single transaction; write `meta`, `blocks`, `sentences`.
- `word_count` = total tokens with `is_alpha or like_num`.
- Print summary: blocks, sentences, candidates/sentence mean, elapsed time.

**Performance target:** ≤ 90 s for a 150 000-word book on a mid-range laptop
(sm models). Not a hard gate; log a warning in README if models are large.

---

## 5. Reader — Startup & Data Flow

`kert read BOOK.kert`

1. Open DB (WAL). Validate `meta.schema_version == '1'`; refuse politely otherwise.
2. Full scan of `blocks` + `sentences` into memory (dataclasses). Decode msgpack lazily is NOT required — decode eagerly during the scan; for a 500k-word book this is a few MB and < 1 s.
3. Read `reader_state`: `chunk_width` (default 8), `position` (default: first sentence, token 0).
4. Assemble chunks (section 6) for ALL sentences at the current width into a flat global list `chunks: list[ChunkSpan]`, where `ChunkSpan = (sentence_id, start_token, end_token)`. Build index `sentence_id → first chunk index` and resolve saved position to the nearest chunk (chunk containing `chunk_start_token`, else the first chunk of that sentence).
5. Enter render/key loop.

On `:set width=N` (N in 5..12): re-run step 4 (re-chunk whole book in memory — sub-second), re-resolve position to the chunk containing the previously active token, persist new width.

On exit (`q`, `:q`, SIGINT): persist position, trim `advance_log`, run
`PRAGMA wal_checkpoint(TRUNCATE)` so the `.kert` file remains a single
portable artifact (no lingering `-wal`/`-shm` sidecars), close DB. README
must note: do not copy a `.kert` file while a Reader session is open.

---

## 6. Chunk Assembly Algorithm (Reader-side)

Input per sentence: token count `n`, candidate list `C = [(idx, w), ...]`,
target width `W` (user setting, 5–12, default 8).

Cut set = `{0, n}` ∪ chosen subset of candidate indices. Chunks are the token
spans between consecutive cuts. Choose the subset minimizing total cost via
dynamic programming over candidate positions (candidates per sentence are
few, so O(k²) DP is fine):

```
cost(chunk of length L, entered via candidate weight w) =
      length_penalty(L) + cut_penalty(w)

length_penalty(L) = ((L - W) / W) ** 2          # quadratic, symmetric
                    + (4.0 if L > 2*W else 0)    # hard discourage
                    + (1.0 if L < 3  else 0)     # avoid crumbs
cut_penalty(w)    = (1 - w) * 0.75               # prefer strong boundaries
                    (0 for the sentence-start pseudo-cut)
```

- Sentences with `n <= W + 2`: single chunk, no DP.
- The last chunk of a sentence has no `cut_penalty` on its right side (sentence end is a natural boundary, weight 1.0 implicitly).
- Deterministic: ties broken by preferring the earlier cut.

Unit tests must pin golden outputs for fixture sentences (RU and EN) at
W = 6, 8, 12.

---

## 7. Rendering (Rich)

### 7.1 Layout
- Single `rich.live.Live` region, `screen=True` (alternate screen buffer), redraw on every navigation event only (no timers in MVP).
- Content: the **current paragraph (block)** rendered as wrapped text, width = min(terminal width − 4, 88).
- **Center focus ("typewriter" layout):** the active chunk is anchored at the vertical center of the reading area — its first wrapped line sits on row `(H − h) // 2`, where `H` is the reading-area height and `h` the chunk's wrapped line count. Text flows continuously around it like a tape: above, the rest of the active block, then the previous blocks; below, the rest of the active block, then the next blocks. Consecutive blocks are separated by one blank line; non-active blocks are fully dimmed. Text that does not fit is cut at the screen edge with no marker; at the start/end of the book the space beyond the text stays empty. A block taller than the screen needs no special case — the window always follows the active chunk, which is therefore always fully visible.
- Bottom line (status): right-aligned `NN.N%` — **percent is word-based**: (words before the active chunk) / `meta.word_count`. Word-based progress is stable across chunk-width changes (chunk-index-based percent is not). The Reader precomputes cumulative word counts during chunk assembly (§5 step 4). Left-aligned: transient message area (command feedback, errors) and the `:` command input when active.

### 7.2 Styles (D12) — two hardcoded theme presets

Selected via `:set theme=dark|light`; default `dark`. Stored like other
settings (§8.4).

| Element | `dark` (dark background) | `light` (light background) |
|---|---|---|
| Active chunk | `bold white` | `bold black` |
| Rest of active block | `grey50` | `grey62` |
| Neighbor blocks | `grey35` | `grey74` |
| Status line | `grey50` | `grey62` |
| Dialogue leading `—` | part of text, same rules | part of text, same rules |

No `dim` attribute anywhere. No 24-bit-only colors. Themes are the only two
presets in MVP; no custom colors.

### 7.3 Windows specifics
- Entry point calls `sys.stdout.reconfigure(encoding="utf-8")` (and stderr) when encoding is not UTF-8.
- Rich handles VT enablement on Windows Terminal; document in README that legacy `conhost.exe` is unsupported/untested, Windows Terminal is the supported host.
- No `curses`, no `termios`-only code paths in shared modules.

---

## 8. Input & Commands

### 8.1 Keybindings (MVP)
| Key | Action |
|---|---|
| `Space`, `j`, `→` | next chunk |
| `b`, `k`, `←` | previous chunk |
| `J` (shift) | next block (first chunk of next block) |
| `K` (shift) | previous block |
| `g` then `g` | first chunk of book |
| `G` | last chunk |
| `:` | open command line |
| `q` | quit (persist state) |

Every forward/backward action appends one `advance_log` row (D5).

### 8.2 Command line (`:`)
Minimal parser, commands for MVP:
- `:set width=N` — N∈[5,12]; re-chunk; feedback message.
- `:set theme=dark|light` — switch preset (§7.2), immediate re-render.
- `:goto P` — P is percent (float 0–100, word-based); jump to nearest chunk.
- `:q` — quit.
Unknown command → error message in status area, never crash.

### 8.4 Settings storage & precedence

Two layers, one precedence rule:

1. **Global defaults** — TOML config at the `platformdirs` user-config
   location (`%APPDATA%\kert\config.toml` on Windows,
   `~/.config/kert/config.toml` on Linux/macOS). Keys: `chunk_width`,
   `theme`. Read once at startup via stdlib `tomllib`. Missing or corrupt
   file → silently fall back to hardcoded defaults (width 8, theme dark);
   never crash on config errors. The config stores ONLY preferences — never
   positions, never book references.
2. **Per-book state** — `reader_state` in the `.kert` file, written whenever
   the user changes a setting via `:set`.

Precedence: per-book `reader_state` > TOML > hardcoded. `:set` writes to
both layers (per-book value AND global default), so a preference set once
carries to future books while each book keeps its own last-used value.
Central library DB explicitly rejected for settings (fragility, D3); if a
library feature ever lands (v0.4+), it must be built as a derived,
regenerable cache — never as source of truth.

### 8.3 Key input implementation
Use `readchar.readkey()` in a loop running in the main thread; render updates
happen synchronously after each key. This is cross-platform (msvcrt on
Windows under the hood) and avoids async machinery entirely. `Ctrl+C` must be
caught and treated as quit-with-save.

---

## 9. CLI Surface

```
kert compile INPUT -o OUTPUT.kert --lang {ru,en} [--paragraph-mode blank] [--force]
kert read BOOK.kert
kert inspect BOOK.kert [--sentence N | --block N | --range A:B] [--width W]
kert --version
```

`kert inspect` — calibration/debug tool for the split pipeline. For the
selected sentences prints, in plain text:
1. the sentence with candidate cut positions marked inline as `⟨w⟩`
   (e.g. `Он вышел из дома,⟨1.0⟩ хотя⟨0.8⟩ шёл дождь.`), and
2. below it, the assembled chunk spans for width `W` (default 8) as
   `[chunk] [chunk] …`.
No Rich styling required (plain stdout, pipe-friendly). This tool is the
primary instrument for calibrating §4.5 weights and §6 cost coefficients on
real books.

- `compile` refuses to overwrite OUTPUT without `--force`.
- Exit codes: 0 ok, 1 user error (bad args, missing model — with actionable message), 2 internal error.

---

## 10. Testing & Acceptance

1. `test_ingest_txt`: paragraph splitting on blank lines, CRLF input, BOM input, line-joining.
2. `test_candidates_ru` / `_en`: for ~10 curated sentences each, assert exact candidate sets (index, weight) — these pin the linguistic rules of section 4.5. Skip gracefully (pytest `skip`) if the spaCy model is not installed, but CI must install both sm models.
3. `test_chunker`: golden chunk spans at W=6/8/12; property test: chunks partition the sentence, no chunk starts with punctuation, no chunk longer than 2·W+2.
4. `test_roundtrip`: compile a 2-page RU fixture with dialogue → open store → assemble → compare against golden; verify `reader_state` write/read; verify content tables untouched after a Reader session (hash comparison).
5. Manual acceptance checklist (README): run on Windows Terminal, macOS Terminal.app, Linux (any VT-capable emulator); verify highlight/dim contrast, RU text rendering, resize behavior (re-render on next keypress is acceptable; live resize handling not required in MVP).

---

## 11. Roadmap (context for implementer — do NOT build now)

### 11.1 Post-MVP validation gate & optional pivot

The MVP engine (txt → chunking → Reader) is positioning-neutral. Immediately
after the MVP is usable, a mandatory validation step decides the roadmap
branch:

**Validation protocol:** read (a) one chapter of fiction and (b) one chapter
of a technical book (converted to txt) through kert for real. Compare
subjective focus/comfort. Pick a branch:

**Branch F — Fiction focus (original plan):** proceed with §11.2 table as-is.

**Branch N — Non-fiction / technical pivot (optional, adopt if validation
favors study/technical reading):**
- Repositioning: "terminal-native focus reader for technical Markdown/EPUB".
- Rationale (recorded from design review): attention pain is real for study
  texts, syntagma chunking is functionally useful on dense 40+-word
  sentences (clause-by-clause reading technique), and the terminal-native
  audience actually reads docs/RFCs/MD-books. Fiction positioning has a
  near-zero niche.
- Consequences on scope, in priority order:
  1. v0.2 becomes: Markdown ingester (as before) + **structural navigation**
     — heading-based TOC (`heading` blocks + `chapter` column activate),
     jump-to-heading command, in-book text search (`/` Vim-style). Linear
     Space-Space reading is insufficient for study texts; cheap regressions
     and jumps become core, not polish.
  2. RSVP / adaptive RSVP (D5 v0.2–v0.3 items) are demoted to backlog-tail
     or dropped: timed advancement contradicts uneven comprehension speed of
     study material.
  3. v0.3 becomes: annotations — highlight current chunk/sentence, attach a
     note, export annotations to Markdown (Obsidian-compatible). Active
     reading loop is the differentiator for study use.
  4. EPUB ingester stays (tech books ship as EPUB); FB2 demoted.
  5. **PDF is a permanent non-goal** (extraction quality ceiling too low);
     corpus boundary is Markdown/EPUB/txt, domain boundary is
     CS/programming/DevOps texts (terminal cannot render math/diagrams).
- Schema impact: none for MVP (block `type` enum and `chapter` column
  already reserved); annotations will add one mutable table
  (`annotations(id, sentence_id, start_token, end_token, note, created_at)`)
  alongside `reader_state` — same isolation rule (D8).

### 11.2 Version table (Branch F baseline)

| Version | Scope |
|---|---|
| v0.2 | Markdown ingester (code blocks / headings / lists as un-chunked `code`/`heading`/`list_item` blocks, Pygments highlighting); RSVP auto-advance with WPM setting; language auto-detect. |
| v0.3 | Adaptive RSVP (WPM derived from `advance_log` tempo); EPUB ingester; FB2 ingester. |
| Later | Dialogue speaker detection; bookmarks/history; search; per-chapter TOC. |

Design constraints already in place for both branches: block `type` enum,
`chapter` column, `advance_log`, Ingester adapter protocol, reserved CLI
flags, mutable-table isolation (D8) ready to host `annotations`.

---

## 12. Open Items (defaults assumed — confirm or amend)

| # | Item | Assumed default |
|---|---|---|
| O1 | Default chunk width | 8 words |
| O2 | spaCy pin | `3.8.13` baseline (newest 3.8.x with verified cp314 PyPI wheels wins); fallback protocol → Python 3.13, see §2.1 |
| O3 | Content wrap width cap | 88 cols |
| O4 | `advance_log` cap | 10 000 rows |
| O5 | Neighbor-block context in viewport | 1 above + 1 below, dimmed |
| O6 | Compile perf target | ≤ 90 s / 150k words |
| O7 | Settings storage | RESOLVED: two-layer (global TOML defaults + per-book state, §8.4) |
| O8 | Distribution | MVP: `uv tool install` from the repo (documented in README). Roadmap: PyPI publication (pip/pipx) in v0.2; standalone binaries considered later |

---

## 13. Implementation Plan for Claude Code — strict TDD

### 13.1 TDD protocol (mandatory for every module task)

Each module task below is executed as a red → green → refactor cycle:

1. **RED.** Write the module's test file FIRST, directly from the relevant
   spec section (referenced per task). Tests must encode the spec's contracts:
   exact function signatures agreed in the task, golden outputs, invariants,
   and error paths. Run `uv run pytest tests/test_<module>.py` and confirm
   tests FAIL for the right reason (module missing / NotImplementedError —
   not import typos). A stub module raising `NotImplementedError` may be
   created to make collection pass.
2. **GREEN.** Implement the module until its test file passes. No edits to
   tests during this phase EXCEPT when a test is discovered to contradict
   this spec — in that case fix the test, and record the discrepancy in a
   `SPEC_NOTES.md` entry (one line: test, spec section, resolution).
3. **REFACTOR.** Clean up with the full suite green: `uv run pytest` and
   `uv run ruff check` must both pass before the task is considered done.
4. **Commit discipline.** One task = minimum two commits: `test(<module>): …`
   (red) and `feat(<module>): …` (green/refactor). The red commit may ship
   with the stub.

Rules of engagement:
- Never implement functionality that has no failing test demanding it
  (rendering/key-loop exception below).
- Golden fixtures (candidate sets §4.5, chunk spans §6) are part of the RED
  phase: generate them by hand-reasoning from the spec, not by running the
  implementation and freezing its output. If hand-derivation is infeasible
  for a long sentence, shorten the fixture sentence instead.
- spaCy-dependent tests: marked `@pytest.mark.spacy`; skipped locally when
  models are absent, mandatory in CI.
- Terminal I/O (`render.py`, `keys.py`, `app.py`) is exempt from unit-TDD for
  the interactive layer only; everything below it must stay testable:
  `render.py` must expose a pure function `build_frame(state) -> rich
  renderable` that IS unit-tested (via `rich.console.Console(record=True)`
  text export assertions), and the key loop must dispatch through a pure
  `handle_key(state, key) -> state` function that IS unit-tested. Only the
  thin `Live`/`readkey` glue is untested.

### 13.2 Task order

**M0 — Scaffolding**
0. uv project init: `pyproject.toml` (deps + groups per §2.1), `.python-version`,
   `uv.lock`, package skeleton, `kert --version`, ruff config, CI
   (`uv sync --all-groups && uv run ruff check && uv run pytest`).
   Includes the cp314/spaCy smoke check from §2.1; resolve the fallback
   decision NOW, not mid-project.

**M1 — Compiler** (each task = one RED/GREEN cycle)
1. `common/dbschema.py` + `common/model.py` — tests: DDL creates all tables/
   constraints of §3, CHECK constraint rejects bad block types, WAL pragma set.
2. `ingest_txt.py` + `normalize.py` — tests from §4.1–4.3: blank-line
   splitting, CRLF, BOM, cp1251 fallback, line joining, NFC, dash
   normalization, dialogue block typing.
3. `segment.py` — spaCy wiring; smoke tests only (sentence counts on two
   fixture paragraphs), marked `spacy`.
4. `candidates.py` — **highest-risk module.** RED: `test_candidates_ru` /
   `_en` with ~10 hand-derived golden candidate sets each (§4.5), plus
   property tests (no candidate at index 0, prohibitions hold, fallback rule
   for >15-token candidate-less sentences). GREEN in isolation before
   pipeline wiring. Expect iteration here: sm-model parses will disagree with
   hand-derived goldens on some sentences — resolve per the §13.1 rule
   (spec wins; note in SPEC_NOTES.md).
5. `persist.py` + `pipeline.py` + `kert compile` CLI — tests: compile the RU
   fixture end-to-end, assert `meta` keys, row counts, `--force` behavior,
   exit codes (§9).
5a. `kert inspect` (§9) — tests: golden plain-text output for one fixture
   sentence (candidate markers + chunk spans at W=8). Build IMMEDIATELY
   after task 5: it is the calibration instrument for validating task 4's
   behavior on real books before investing in the Reader.

**M2 — Reader**
6. `store.py` — tests against the fixture `.kert` produced by task 5's test
   (fixture built via the compiler in a session-scoped pytest fixture):
   full-scan correctness, schema_version rejection, state read/write defaults.
7. `chunker.py` — RED: golden chunk spans at W=6/8/12 (§6) + property tests
   (partition, no punctuation-initial chunk, max length bound). GREEN: DP.
8. `reader/config.py` (§8.4) — tests: precedence chain, corrupt/missing TOML
   fallback, `:set` write-through to both layers (filesystem mocked via
   `tmp_path` + monkeypatched platformdirs).
8a. `render.py` (`build_frame`) + `commands.py` + `handle_key` state machine —
   tests: styles of both §7.2 presets present in recorded output, word-based
   percent math, tall-block clipping window (fixture block > frame height →
   `…` markers, active chunk visible), `:set width` re-chunk + position
   re-resolution, `:set theme`, `:goto`, unknown command error path.
9. `keys.py` + `app.py` — thin glue (exempt layer), plus full
   `test_roundtrip`: compile → open → assemble → navigate via `handle_key`
   sequence → quit → reopen → position restored; content-tables immutability
   hash check; `advance_log` rows written and capped.

**M3 — Polish**
10. Error-path hardening (each with a test where feasible): missing model
    message, corrupt `.kert`, terminal < 40 cols, Ctrl+C save.
11. README: uv-based dev setup (`uv sync --all-groups`), end-user install via
    `uv tool install` from the repo (O8), model provisioning, Windows
    Terminal support note, WAL copy warning (§5), keymap, config file
    location (§8.4), manual acceptance checklist (§10.5).

---

## 14. Format Ingesters — Markdown, FB2, EPUB (post-MVP work package)

Approved 2026-10-28. Extends D1 and §4.1–§4.3; everything else in this spec
stays in force. Out of scope here: chapter/TOC navigation (data is filled
now, commands come later), footnote/endnote bodies, images, tables, code
syntax highlighting (needs a per-block language, i.e. a schema change),
RSVP, language auto-detect.

### 14.1 Ingest contract (replaces the `list[str]` protocol of §4.1)

```python
@dataclass(frozen=True, slots=True)
class RawBlock:
    kind: Literal["paragraph", "heading", "code", "list_item"]
    text: str
    level: int | None = None  # heading level 1..6; None otherwise


@dataclass(frozen=True, slots=True)
class IngestResult:
    blocks: list[RawBlock]
    title: str | None = None  # document metadata title, if the format has one


class Ingester(Protocol):
    def ingest(self, path: Path) -> IngestResult: ...
```

- `TxtIngester` emits only `paragraph` blocks and `title=None`; its §4.1
  behavior is unchanged.
- `meta.title` = `IngestResult.title`, else the input file stem.
  `meta.source_format` ∈ `txt | md | fb2 | epub`.
- Format by input suffix (case-insensitive): `.txt`; `.md`, `.markdown`;
  `.fb2`, `.fb2.zip` (zip holding exactly one `.fb2`); `.epub`. Anything
  else → user error (exit 1) listing the supported suffixes.
  `--paragraph-mode` applies to `.txt` only.
- Decoding: Markdown follows the §4.1 chain (`utf-8-sig`, then `cp1251` for
  `--lang ru`). FB2/EPUB XML honor their XML encoding declaration
  (`windows-1251` FB2 files are common).
- Malformed input (bad zip, invalid XML, missing OPF/body) → user error
  naming the file and what is wrong; never a traceback.

### 14.2 Normalize & block typing (extends §4.2–§4.3)

- `paragraph`, `heading`, `list_item`: §4.2 normalization unchanged (NFC,
  soft hyphen, NBSP, whitespace collapse, RU dash normalization).
- `code`: NFC and `\r\n`/`\r` → `\n` only; indentation and line breaks are
  kept verbatim; leading and trailing blank lines stripped (HTML also drops
  the newline right after `<pre>`), indentation of the first code line kept.
- Empty blocks are dropped (code: empty after stripping).
- Block type: `heading`, `code`, `list_item` map 1:1; `paragraph` goes
  through the §4.3 dialogue rule.
- `chapter`: let `L` = the smallest heading level that occurs at least twice
  in the document (so a lone book-title `h1` above `h2` chapters does not
  swallow them); if no level occurs twice, the smallest level present.
  Each heading of level `L` starts a new chapter, numbered from 1; every
  block from that heading up to the next level-`L` heading carries that
  number. Deeper headings do not change it. Blocks before the first
  level-`L` heading (and all blocks of a document with no headings) have
  `chapter = NULL`.

### 14.3 Segment, candidates, word count for un-chunked blocks

- `paragraph`, `dialogue`, `list_item`: §4.4–§4.5 unchanged (spaCy
  sentences + candidates). A list item is chunked like a paragraph.
- `heading`, `code`: **not** parsed. The whole block is one sentence row
  (`seq = 0`); tokens are the `\S+` runs of the text (char spans); the
  candidate list is empty. With no candidates, §6 always yields exactly one
  chunk, so these blocks are a single reading stop at any width — no
  chunker change.
- Word predicate is shared by Compiler and Reader (`common/`): a token is a
  word if it is alphabetic or numeric (`\d+([.,]\d+)*`). The Compiler uses
  spaCy's `is_alpha or like_num` for parsed blocks (§4.6) and the shared
  predicate for un-chunked blocks; the Reader uses the shared predicate
  throughout (SPEC_NOTES, Task 8a).

### 14.4 Markdown (`MarkdownIngester`, CommonMark via `markdown-it-py`)

- Leading YAML front matter (a first line `---` up to the next `---` line)
  is skipped.
- `#`…`######` / setext headings → `heading` (level from the tag).
- Paragraphs, including those inside block quotes → `paragraph`.
- List items → `list_item`, one block per item paragraph. The first
  paragraph of an item gets the prefix `• ` (bullet list) or `N. ` (ordered
  list, numbered from the list's start). Nested lists are flattened in
  document order with the same prefix rules.
- Fenced and indented code → `code` (content only; the fence info string
  is dropped).
- Inline content → plain text: text, inline code content, link text,
  image alt text; soft and hard line breaks → a space. Emphasis markers
  vanish.
- Skipped: HTML blocks, thematic breaks, tables.

### 14.5 FB2 (`Fb2Ingester`, `xml.etree`)

- Title: `description/title-info/book-title`.
- Read only the first `<body>` that has no `name` attribute; bodies named
  `notes`/`comments` (footnotes) and `<binary>` are skipped.
- `<body>/<title>` → `heading` level 1. `<section>` titles → `heading` with
  level = 1 + section nesting depth (top-level section = 2), capped at 6.
  Multiple `<p>` inside one `<title>` join with a space.
- `<subtitle>` → `heading` one level below its section's title (capped at
  6).
- `<p>` → `paragraph`; inside `<epigraph>`, `<cite>`, `<annotation>` as
  well. `<text-author>` → `paragraph`. `<poem>`: each `<v>` → `paragraph`;
  a poem `<title>` → `heading` as for a subtitle.
- Inline markup (`emphasis`, `strong`, `strikethrough`, `sub`, `sup`,
  `code`, `a`) → its text; note references keep their visible text.
- Skipped: `<empty-line>`, `<image>`, `<table>`.

### 14.6 EPUB (`EpubIngester`, `zipfile` + `xml.etree` + `html.parser`)

- `META-INF/container.xml` → first rootfile → OPF package document.
- Title: OPF `dc:title`.
- Reading order: the OPF spine; items with `linear="no"` and the EPUB 3
  navigation document (manifest `properties` contains `nav`) are skipped.
  Only XHTML/HTML media types are read.
- Per content document (lenient `html.parser`):
  - `h1`…`h6` → `heading` (level from the tag);
  - `p` → `paragraph`; `li` → `list_item` with the §14.4 prefix rules
    (`ul` → `• `, `ol` → `N. ` honoring `start`); `pre` → `code`;
  - text directly inside other block containers (`div`, `section`,
    `article`, `blockquote`, `body`, …) that is not inside one of the
    elements above is flushed as a `paragraph` when the container closes
    or the next block element starts;
  - `br` → a space (inside `pre`: a line break);
  - skipped with their content: `head`, `script`, `style`, `nav`, and any
    element whose `epub:type` contains `footnote`, `endnote`, `rearnote` or
    `toc`;
  - character references are decoded; inline elements contribute their
    text.
- Documents are concatenated in spine order; chapter numbering (§14.2)
  runs over the whole book.

### 14.7 Reader (extends §7)

- `heading`: rendered as its own block. Style: the active-chunk style when
  active, else the neighbor style, plus `bold` in both cases.
- `code`: rendered with its line breaks and indentation kept (lines longer
  than the text width wrap). Styles as for any block (active-chunk style
  when active, neighbor style otherwise); no syntax highlighting yet.
- `list_item`: a normal block; its prefix is part of the text.
- Navigation unchanged: each heading and each code block is one stop for
  `j`/`k`; `J`/`K` treat every block, headings included, as a block.

### 14.8 Task order (strict TDD per §13.1)

12. `common/text.py` shared word predicate; ingest contract refactor —
    `RawBlock`/`IngestResult`, `TxtIngester` and `normalize` ported, chapter
    numbering, un-chunked segmentation in `pipeline` (tests: unchanged
    goldens for `.txt`, new unit tests on hand-built `RawBlock` lists).
13. Reader support for `heading`/`code` (render styles, verbatim code lines;
    tests via `build_frame`).
14. `MarkdownIngester` + format dispatch by suffix + `meta.source_format` /
    `meta.title` (tests: small hand-written `.md` fixtures, CLI compile).
15. `Fb2Ingester` (`.fb2`, `.fb2.zip`, `windows-1251` declaration) — tests
    with small hand-written FB2 fixtures.
16. `EpubIngester` — tests build minimal EPUBs in `tmp_path` with
    `zipfile` (EPUB 2 NCX-only and EPUB 3 nav variants).
17. Docs: README formats section, CHANGELOG via the release flow; remove the
    pandoc workaround from Non-goals for these formats.

---

## 15. Distribution Builds (extends O8)

Approved 2026-10-28. Two PyInstaller builds per release target:

| Build | Mode | Contents | Commands |
|---|---|---|---|
| `kert` (full) | one directory, archived | everything, both spaCy models | `compile`, `read`, `inspect`, `--version` |
| `kert-reader` | **one file** | Reader only: no spaCy, numpy, models or `kert.compiler` | `read`, `inspect`, `--version` |

- Rationale: a onefile build unpacks itself on every launch. For the full
  build that means ~150 MB per run, and on macOS unsigned native libraries
  are re-verified each time (`compile` measured at 20–30 s instead of 1.5 s).
  The Reader-only build is small enough that unpacking it is negligible. It
  reads `.kert` files compiled elsewhere ("compile on the desktop, read
  anywhere").
- `kert-reader compile …` exits with code 1 and a message that this build
  cannot compile and that the full `kert` is needed (no traceback, no
  exit 2). The CLI recognises the missing compiler from a
  `ModuleNotFoundError` for `kert.compiler` or `spacy`.
- Release assets: `kert-<version>-<target>.tar.gz|zip` (full) and
  `kert-reader-<version>-<target>[.exe]` (single file), both covered by
  `SHA256SUMS.txt`. Smoke test for the Reader build: `--version`; `inspect` on
  a book compiled by the full build of the same target, against the golden;
  `compile` → exit 1 with the message.

---

## 16. Android Reader (stage 0, native Kotlin)

Approved 2026-10-28. Pivot-map "Android app" stage 0: a native Android app that
**reads `.kert` files compiled on the desktop**. Compiling on the phone is out
of scope (no spaCy on Android). The Python code stays the reference
implementation, and the app's behavior must match it.

### 16.1 Scope

In: open/import `.kert` files, a library of imported books, the
center-focus reading view (§7.1, §14.7), chunk/block/book navigation,
width 5–12 and dark/light theme settings, word-based percent and goto,
reading position and `advance_log` written into the book (D5, D8).
Out (later stages): compiling, chapter/TOC navigation, search, annotations,
sync between devices, Play Store publishing.

### 16.2 Repository layout & toolchain

```
android/                      Gradle project (Kotlin DSL, version catalog)
  gradle/libs.versions.toml   every dependency and plugin pinned exactly
  core/                       pure Kotlin/JVM: no Android imports
    model, blob decoding, offsets, word predicate, chunker, ReaderState
  app/                        Android application (Jetpack Compose)
```

- Gradle wrapper committed and pinned; builds run on JDK 21 (Robolectric
  needs it for SDK 36) and emit Java 17 bytecode. Exact pins for Kotlin,
  Android Gradle Plugin, Compose BOM and all libraries (same determinism
  policy as §2.1). `applicationId` `io.github.myarzik.kert`, `minSdk` 26,
  `targetSdk` 36, `compileSdk` 37 (raised independently: Compose 1.12
  requires compiling against API 37+).
- `core` is testable with the plain JDK (`./gradlew :core:test`), with no Android
  SDK. `app` needs the Android SDK and builds in CI (local SDK optional).
- Python stays on uv; the two toolchains share only the `.kert` format and
  the reference fixtures (§16.6).

### 16.3 Porting contract (core)

- **`.kert` reading:** schema version check (§5 step 1); full scan of `meta`,
  `blocks`, `sentences`; msgpack blobs decoded as in §3 (tokens: array of
  `[start, end]`; candidates: array of `[token_index, weight]`, weight a
  float).
- **Character offsets:** token offsets in `.kert` are **Unicode code point**
  offsets (Python `str` indexing). Kotlin strings index UTF-16 code units,
  so `core` converts offsets per sentence (`String.offsetByCodePoints`)
  before using them. Tests include a sentence with characters outside the
  BMP (e.g. emoji).
- **Word predicate (§14.3):** a token is a word if every code point is a
  letter (`Character.isLetter`, matching Python `str.isalpha`) or the token
  matches `\p{Nd}+([.,]\p{Nd}+)*`: any Unicode decimal digit, like Python's
  `\d` on `str` (Java's `\d` is ASCII-only). Percent = words before the
  active chunk / `meta.word_count`, clamped (SPEC_NOTES 8a).
- **Chunker:** §6 DP exactly as in `reader/chunker.py`, including the
  overlong-chunk lexicographic rule and the earliest-cut tie-break with
  epsilon 1e-9 (SPEC_NOTES, Task 7).
- **ReaderState:** a pure reducer `reduce(state, action) -> state` with the
  same semantics as `handle_key` (§8, SPEC_NOTES 8a). Actions: `Next`,
  `Previous`, `NextBlock`, `PreviousBlock`, `First`, `Last`,
  `GotoPercent(p)`, `SetWidth(n)`, `SetTheme(t)`. Effects as in Python:
  `Advance` only for `Next`/`Previous`; `SaveSetting` for width/theme.
  Position resolution on open and on width change is as in §5 step 4.

### 16.4 Books on the device

- Import via the system file picker (`ACTION_OPEN_DOCUMENT`) and by opening
  or sharing a `.kert` file from another app (`VIEW`/`SEND` intent
  filters). The app **copies** the file into its private storage, because
  SQLite needs a real file path and a content URI is not one. Reading
  position, settings and `advance_log` live in that copy (D8). Importing
  the same book again (same `meta.title` + `compiled_at`) asks before it
  replaces the copy and loses its position.
- The library screen lists imported books (title, percent, last read) and
  can delete a book. So that listing never re-chunks a book, the app also
  writes `percent` (one decimal) and `last_read` (Unix seconds) into
  `reader_state` when a session ends. The Python Reader ignores these keys.
- Library file name: the first 16 hex digits of SHA-256 of
  `meta.title + "\n" + meta.compiled_at`, plus `.kert`. A duplicate import
  therefore targets the same name. Import copies into a temporary file
  first, validates it with a full read (schema version, blobs, at least one
  sentence) and only then moves it into place, so a bad file leaves nothing
  behind.
- Each session opens the copy read-write (WAL). On leaving the reader
  (`onStop`), the app saves the position, trims `advance_log` to 10 000 rows
  and runs `PRAGMA wal_checkpoint(TRUNCATE)` (§5 on exit).

### 16.5 Reading UI

- Center-focus tape (§7.1): the active chunk's first line stays on the
  vertical center; the text scrolls smoothly to the next chunk. The rest of
  the active block, neighbor blocks, headings (bold), code (monospace,
  layout kept) and list items follow §7.2/§14.7 colors. Dark and light map
  the §7.2 xterm-256 greys to their RGB values. Default theme: follow the
  system dark mode until the user picks one.
- Input: tap on the right two thirds = next chunk; tap on the left third =
  previous chunk; volume down / up = next / previous (on by default);
  swipe up / down = next / previous block. Tapping the top edge opens a
  panel with percent, a goto slider, width 5–12 and theme.
- The status line shows the percent (one decimal place, like the terminal).
  The screen stays on while reading.
- Settings precedence (§8.4 adapted): per-book `reader_state` > app
  defaults (SharedPreferences) > hardcoded (width 8; theme follows the
  system). Changing a setting writes both.

### 16.6 Testing & cross-validation

- `core` follows strict TDD (§13.1) with JUnit 5. Hand-derived goldens from
  the Python suite are ported verbatim (`test_chunker`, `test_state`,
  `test_render` layout rules where they apply to `core`).
- **Reference cross-check:** `scripts/export_android_reference.py` (uv)
  compiles the fixture books (RU `.txt`, Markdown with code/lists, an EPUB
  with non-BMP characters) with the Python compiler. It writes the `.kert`
  files and a JSON reference with the Python chunk spans at W = 5…12, word
  counts and percents. `core` tests read those and must match exactly. The
  reference is **generated, not committed**: CI and local runs regenerate it
  first, so it always reflects the current Python code. This is the
  pivot-map validation rule ("validate the port against the reference
  implementation"). It complements the hand-derived goldens and does not
  replace them.
- `app`: JVM tests with Robolectric for import, persistence and the Compose
  reading screen (tap/volume mapping, centered active chunk). No emulator
  in CI.

### 16.7 CI & distribution

- `android.yml` on push/PR touching `android/` or the reference script:
  regenerate the reference with uv, then `./gradlew :core:test :app:test
  :app:lint :app:assembleRelease`.
- Signing: a release keystore kept in repository secrets
  (`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`,
  `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`). Without the secrets, CI
  builds an unsigned release APK (and a debug APK for testing). A stable
  key is needed so that updates install over older versions.
- `release.yml` attaches `kert-android-<version>.apk` to the GitHub Release
  when the signing secrets are present. The app's `versionName` = the
  Python package version; `versionCode` derived from it
  (`major*10000 + minor*100 + patch`).

### 16.8 Task order

18. Gradle skeleton (`core` + `app`, version catalog, wrapper), `android.yml`
    with a trivial test; reference export script.
19. `core` model + `.kert` reading through a small DB interface (JDBC
    SQLite in tests), blob decoding, code point offsets, word predicate.
20. `core` chunker port: hand goldens + reference cross-check.
21. `core` ReaderState reducer, percent, goto, width change: goldens from
    `test_state` + reference cross-check.
22. `app` storage: import/copy, library, Android SQLite implementation,
    session lifecycle (position, `advance_log` trim, checkpoint).
23. `app` reading screen: tape layout, gestures, volume keys, settings panel.
24. Signing and release integration; README "Android" section.
