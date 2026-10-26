# SPEC_NOTES

Deviations and resolutions against `kert_spec.md`. One line per entry.

- Task 0, §2.1/O2: spaCy pinned to `3.8.16` (newest 3.8.x with cp314 wheels for macOS/manylinux/win on PyPI) instead of `3.8.13` baseline; smoke check passed on 3.14.3 — Python 3.13 fallback NOT taken. Models: `ru_core_news_sm==3.8.0`, `en_core_web_sm==3.8.0`.
- Task 1, test_model::test_content_models_are_immutable, §3/D8: test defect (not a spec conflict) — assigned non-existent `id` on SplitCandidate/ChunkSpan; fixed in GREEN to assign the first declared field.
- Task 2, test_ingest_txt::test_utf8_bom_is_stripped, §4.1: a BOM is valid UTF-8, so the literal order `utf-8` → `utf-8-sig` would never reach `utf-8-sig` and leave U+FEFF in text; resolution: decode with `utf-8-sig` first (identical to `utf-8` for BOM-less input), then `cp1251` for `--lang ru`.
- Task 2, test_normalize::test_en_paragraph_starting_with_em_dash_is_dialogue, §4.3/D10: typing rule applied language-independently (§4.3 has no language condition); only dash normalization (§4.2) is RU-only.
