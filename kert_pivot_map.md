# kert — Pivot Map (strategy artifact)

Status: REFERENCE — not part of the implementation spec (`kert_spec.md`).
Not for the implementer. Revisit after the MVP validation gate (spec §11.1).

---

## Decision timeline

1. Build MVP per `kert_spec.md` (txt → chunking engine → Reader).
2. Run the validation gate (§11.1): one fiction chapter + one technical
   chapter read through kert for real.
3. Choose: Branch F (fiction, spec §11.2), Branch N (non-fiction/technical,
   spec §11.1), or one of the pivots below.
4. The browser extension for longreads is classified as a **separate
   product**, not an evolution of kert — decided 2026-07-11.

## Three transferable assets

Every pivot is defined by which asset survives:

- **Asset A — Algorithm:** dependency-based split-point extraction
  (spec §4.5 weights + prohibitions) + DP chunk assembly with cost function
  (spec §6). Pure logic, portable to any language.
- **Asset B — UX pattern:** active syntagma highlighted, surrounding context
  dimmed, manual Vim-paced advancement.
- **Asset C — Data:** `advance_log` — per-chunk reading tempo joinable with
  syntactic structure of chunks.

The MVP design already hedges all branches: D4 (split-points, not baked
chunks) keeps the engine detachable; `kert inspect` is a prototype of the
linter pivot; `advance_log` accumulates from day one. Testing the MVP is
simultaneous reconnaissance of all branches below.

---

## Branch 1 — UX works, terminal is the friction

Trigger signal: chunked reading feels good, but you avoid opening the
terminal / precompiling books.

| Pivot | Essence | Assessment |
|---|---|---|
| Browser extension for longreads | chunk+dim on live DOM (Readability-style extraction, TS heuristics instead of spaCy) | Strongest product logic of all pivots: universal audience, zero-friction install, existing distribution (Web Store). Cost: loses spaCy (≈80% quality via JS heuristics, worse for RU); new hard problem = article extraction. Separate product. |
| **Obsidian plugin** | focus-reading mode for MD notes and clippings | Undervalued: audience is exactly the target persona (MD-native longread hoarders), distribution ready (community plugins), content already structured — no extraction problem. Technically cheaper than the extension. |
| VS Code extension | reading docs/README inside the editor | Same logic, wider audience, but "reading in the editor" is a weaker habit hypothesis. |
| KOReader plugin (e-ink) | chunk mode on e-readers | Lua; tiny niche, but fanatical and feature-hungry audience. |

## Branch 1.5 — Web demo / online service (decided 2026-07-13)

- **Full online reader service (accounts, cloud library, position sync):
  REJECTED as a first pivot** — worst cost/hypothesis ratio of all options:
  competes with mature funded products on their turf with one
  differentiating feature; adds unique burdens no other pivot has (hosting
  ops, storage costs, users uploading copyrighted content to YOUR server =
  your legal problem, mandatory monetization). Technical silver lining
  recorded: the Compiler half (§4.4–4.6) ports to a Python backend almost
  verbatim — D1/D4 architecture maps 1:1 onto "backend pipeline → DB → thin
  web front". Legitimate only as a **v3** after an extension/plugin proves
  demand for cross-device sync.
- **Static web demo: APPROVED as a cheap post-MVP step.** One page: paste
  text / upload file → on-the-fly compile → chunk-mode reading. No accounts,
  no storage, nothing retained. Purpose: algorithm showcase, feedback
  collection, portfolio, cheap demand test before any Branch 1 investment.
  Cost: ~1 evening on top of the finished compiler (FastAPI + thin JS front).

## Branch 2 — Algorithm is good, the reading mode isn't


Trigger signal: `kert inspect` shows linguistically clean splits, but you
don't enjoy reading this way.

| Pivot | Essence | Assessment |
|---|---|---|
| **Subtitle line-breaker** | optimize .srt/.vtt line breaks by syntagma | Same problem verbatim: subtitle industry guidelines require "don't break clauses, don't orphan prepositions" — §4.5 prohibitions map 1:1. Real commercial niche (post-production, localization). ~90% of the DP/cost-function reused. The only pivot with a clear commercial lane. |
| Readability linter | CI tool for tech writers: flags sentences with no natural split points (e.g., 25+ words without a pause point) | Fits the vale/alex ecosystem; `kert inspect` is already its prototype. |
| TTS pacing | syntagma-based pause insertion for natural prosody | Technically sound; market = integrating into others' TTS pipelines — hard to sell standalone. |
| `syntagma` library on PyPI | chunker as a standalone package | Not a product; cheap second life for the code + portfolio; feeds every other pivot. |
| Language learning reader | phrase-by-phrase L2 reading, tap-to-translate per syntagma | Pedagogically grounded (chunking is an accepted L2 reading technique), but crowded field (LingQ et al.). |

## Branch 3 — The data becomes interesting

Trigger signal: any mode is in regular use; `advance_log` accumulates.

- **Reading analytics:** which syntactic constructions slow *you* down
  (`advance_log` × dependency types of chunks). Weak as a standalone
  product; strong as a personal instrument, a write-up, or a killer feature
  inside the main product ("nested subordinate clauses slow you by 40%").

## Branch 4 — Nothing lands

Salvage plan: publish the chunker as a PyPI library + write-up on
dependency-based syntagma chunking (spec §4.5–§6 already contains half the
article: rules, weights, cost function). The project pays off as portfolio
and learning material — which was its baseline justification.

---

## Quality instrumentation — LLM-as-judge eval harness (post-MVP)

Idea recorded 2026-07-13. Closes the known TDD gap: hand-derived goldens
only validate §4.5 rules on short sentences (long fixtures get shortened by
protocol); quality on real 40+-word sentences is otherwise checked only by
eye via `kert inspect`. Syntagma splitting has no single correct answer, but
bad splits are objectively recognizable — an LLM judge scores acceptability
against a rubric.

**Hard separation — this is an eval loop, NOT tests:**

| | Deterministic tests (pytest) | LLM eval (separate loop) |
|---|---|---|
| Verifies | invariants + hand-derived goldens | split quality on a large corpus |
| Runs | every commit, CI, blocks merge | on demand / nightly, never blocking |
| Determinism | full | none (by nature) |
| Cost | zero | tokens + network |

Never in the CI gate: flaky by definition, needs network + secret, costs per
push.

**Shape:** `kert eval BOOK.kert --sample N --judge gemini --width W`.
Implementation: instructor over the Gemini client, Pydantic response model
(`score: int 1-5`, `violations: list[ViolationEnum]`, `comment`), rubric =
§4.5 prohibitions/weights translated into judge criteria, temperature 0,
one sentence per request. Output: per-sentence scores + aggregate (mean,
distribution, top-20 worst sentences with violated rule). Turns §4.5 weight
and §6 cost-coefficient calibration from eyeballing into a measured loop.

**Strategic value:** an absolute quality metric independent of the NLP
backend — the same scale measures the spaCy pipeline today, TS heuristics
of a Branch 1 port tomorrow. Better than "compare port against spaCy
output": sm-model parses are themselves imperfect, so agreement-with-spaCy
≠ good-split.

**Known pitfalls (respect all four):**
1. Calibrate the judge against yourself first: hand-score 30–50 splits (RU
   and EN separately), check agreement, iterate the rubric until it
   converges. A judge you disagree with produces noise, not signal.
2. Verify RU judging quality separately — LLM syntax judgment on Russian
   may lag English.
3. The judge only SCORES existing splits, never proposes them — otherwise
   the algorithm silently starts optimizing toward another model's opinion
   instead of the rubric.
4. Fixed prompt, temperature 0, one sentence per evaluation call
   (positional/batching noise is real).

Placement: after task 5a (`kert inspect`), before serious weight
calibration. External dependency + secret + nondeterminism = deliberately
outside the MVP spec.

---

## Standing observations

1. Most undervalued candidates: **Obsidian plugin** (Branch 1 — same
   audience as the extension at a fraction of the cost) and **subtitle
   line-breaker** (Branch 2 — commercial niche, near-zero algorithm rework).
2. Do a 30-minute prior-art check before committing to any Branch 1 pivot:
   syntagma-chunking-with-dimming appeared unoccupied as of 2026-07, verify
   at decision time.
3. Whatever branch wins, port Asset A from the Python reference
   implementation and validate the port against spaCy output on a shared
   corpus — the reference rig doubles as a quality metric for any
   reimplementation.
