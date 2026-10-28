# Changelog

All notable changes to kert. Versions follow [Semantic Versioning](https://semver.org);
this file is generated from conventional commits by [git-cliff](https://git-cliff.org).
## [0.2.0] — 2026-10-28

### Features

- **ingest:** Typed raw blocks with chapters and un-chunked headings and code
- **render:** Render headings bold and code blocks with their layout
- **ingest:** Add Markdown ingester and choose the ingester by input suffix
- **ingest:** Add FB2 ingester for .fb2 and .fb2.zip
- **ingest:** Add EPUB ingester (EPUB 2/3, spine order, lenient XHTML)

### Bug fixes

- **normalize:** Number chapters from the smallest repeated heading level

### Documentation

- **spec:** Add format ingesters work package for Markdown, FB2 and EPUB
- **spec:** Format the §14.1 code snippet for ruff
- **readme:** Document Markdown, FB2 and EPUB input formats
- Add Mermaid diagrams of data flow, reader loop, TDD and release

### Dependencies

- **deps:** Pin markdown-it-py as a direct dependency

## [0.1.0] — 2026-10-28

### Features

- **cli:** Implement --version, package skeleton and CI
- **common:** Implement .kert schema DDL and content models
- **compiler:** Implement txt ingester and paragraph normalization
- **segment:** Wire spaCy sentence segmentation
- **candidates:** Extract ranked split-point candidates from parses
- **compiler:** Persist compiled books and add kert compile
- **store:** Open .kert books with full scan and isolated reader state
- **chunker:** Assemble chunks via DP over split-point candidates
- **inspect:** Print split candidates and chunk spans via kert inspect
- **config:** Resolve reader settings across book, TOML and defaults
- **reader:** Add frame builder, command parser and key state machine
- **reader:** Run reading sessions with kert read
- **errors:** Turn missing models, corrupt books and Ctrl+C into clean exits
- **segment:** Add uv tool install remediation to the missing-model error
- **render:** Keep the active chunk on the center row as a scrolling tape

### Documentation

- Add specification and project instructions
- **readme:** Document install, usage, keys, config and acceptance checklist
- **claude:** Fix fixture path in commands quick reference
- **claude:** Sync spaCy baseline pin with pyproject (3.8.16)
- **readme:** Tick items from the first manual acceptance pass
- **readme:** Document prebuilt downloads and the release process
- **pivot:** Record parked Android app pivot in the pivot map

### Dependencies

- **deps:** Add release group with pinned PyInstaller and git-cliff

