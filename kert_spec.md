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
- EPUB/FB2/Markdown ingestion (documented workaround: convert via pandoc to txt).
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
