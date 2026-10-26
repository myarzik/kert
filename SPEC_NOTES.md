# SPEC_NOTES

Deviations and resolutions against `kert_spec.md`. One line per entry.

- Task 0, §2.1/O2: spaCy pinned to `3.8.16` (newest 3.8.x with cp314 wheels for macOS/manylinux/win on PyPI) instead of `3.8.13` baseline; smoke check passed on 3.14.3 — Python 3.13 fallback NOT taken. Models: `ru_core_news_sm==3.8.0`, `en_core_web_sm==3.8.0`.
