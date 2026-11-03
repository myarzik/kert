# kert

A minimalist terminal reader for high-focus reading. Instead of pages, kert
splits every sentence into short reading fragments (syntagmas, about 5–12
words), highlights only the active fragment and dims the surrounding text.

It has two parts:

- **`kert compile`** — an offline pipeline: plain text → spaCy dependency
  parse → ranked split-point candidates → one SQLite file per book (`.kert`).
- **`kert read`** — a Rich terminal UI that assembles fragments for your
  chosen width at open time and navigates with Vim-style keys.

Changing the fragment width never needs recompilation: the `.kert` file stores
split-point candidates, not fixed fragments.

Input formats: plain text, Markdown, FB2 and EPUB, in Russian or English. You
advance through the text manually. For other formats, convert to one of these
first, for example `pandoc book.docx -t markdown -o book.md`.

An Android reader (Kotlin, Jetpack Compose) for `.kert` files lives in
[`android/`](android/). It reads books compiled on the desktop; it cannot
compile. It is in early testing.

## Download a prebuilt build

Each [GitHub Release](https://github.com/myarzik/kert/releases) has two
self-contained builds per platform. Neither needs Python or uv:

- **`kert-reader`**: one file of about 14 MB that reads and inspects `.kert`
  books. It cannot compile them. Use it where you only read, with books compiled
  elsewhere.
- **`kert`**: the full build, an archive with Python and both spaCy models
  (about 150 MB unpacked). It compiles, reads and inspects.

The full build archives:

| Platform | Archive |
|---|---|
| macOS (Apple Silicon) | `kert-<version>-macos-arm64.tar.gz` (only when macOS builds are enabled, see [Releasing](#releasing)) |
| Linux x86-64 (glibc 2.35+) | `kert-<version>-linux-x86_64.tar.gz` |
| Windows x86-64 | `kert-<version>-windows-x86_64.zip` |

The Reader is `kert-reader-<version>-<platform>` (`.exe` on Windows); on macOS
and Linux, make it executable first with `chmod +x`. It unpacks itself on each
start, which adds about half a second.

Unpack the full archive and run `kert` (`kert.exe` on Windows) from the `kert`
folder. You can also add that folder to your `PATH`. Unpacked, a build takes
about 150 MB. `SHA256SUMS.txt` in the release lists checksums for the archives.

The builds are not code-signed:

- **macOS** blocks a downloaded unsigned binary. Clear the quarantine flag once
  after unpacking: `xattr -dr com.apple.quarantine kert`. The first launch can
  take up to half a minute while macOS scans the bundled libraries; after that
  kert starts instantly.
- **Windows** SmartScreen may warn on first run: choose *More info → Run
  anyway*.

A release can also include **`kert-android-<version>.apk`**, the Android reader
(Android 8.0+). Install it by opening the file on the phone and allowing
installs from that app. Updates install over the previous version because each
release is signed with the same key.

## Install from source

This path needs Python 3.14 and [uv](https://docs.astral.sh/uv/). There is no
PyPI release yet, so install from a clone of this repository.

The spaCy models are **not bundled**. With `uv tool install` you add the model
for each language you compile with `--with`. The pinned versions must match
the pinned spaCy (3.8.x):

```sh
git clone <this repository> kert && cd kert
uv tool install . --python 3.14 \
  --with "ru-core-news-sm @ https://github.com/explosion/spacy-models/releases/download/ru_core_news_sm-3.8.0/ru_core_news_sm-3.8.0-py3-none-any.whl" \
  --with "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
```

Drop either `--with` line if you only read one language. The models are small
(`ru_core_news_sm` ≈ 45 MB, `en_core_web_sm` ≈ 15 MB installed). The models
are only needed by `kert compile`; `kert read` works without them.

Upgrade or reinstall after pulling new commits with the same command plus
`--force`.

## Usage

```sh
kert compile book.txt -o book.kert --lang ru   # or --lang en
kert read book.kert
kert inspect book.kert --sentence 12 --width 8  # calibration/debug view
kert --version
```

- `compile` picks the input format from the file suffix:

  | Suffix | Format | Notes |
  |---|---|---|
  | `.txt` | plain text | A blank line is a paragraph boundary. |
  | `.md`, `.markdown` | Markdown (CommonMark) | Front matter, HTML blocks and tables are skipped. |
  | `.fb2`, `.fb2.zip` | FictionBook 2 | Footnote bodies are skipped; `windows-1251` files work. |
  | `.epub` | EPUB 2 and 3 | Read in spine order; navigation documents and footnotes are skipped. |

  Headings and code blocks are shown whole, as one stop each; paragraphs and
  list items are split into fragments. The book title comes from the FB2 or
  EPUB metadata, otherwise from the file name. Images and tables are not
  shown.
- `compile` refuses to overwrite an existing output file unless you pass
  `--force`.
- `inspect` prints, in plain text, each selected sentence with its candidate
  cut points marked `⟨weight⟩` and, below it, the fragments for `--width`.
  Select with `--sentence N`, `--block N` or `--range A:B` (sentence ids,
  inclusive); with no selector it prints the whole book.
- Exit codes: `0` ok, `1` user error (bad arguments, missing model, invalid
  book; the message says what to do), `2` internal error.

If `compile` reports a missing spaCy model, re-run the install command above
with the matching `--with` line (or `uv sync --group models` in a development
checkout).

### Keys

| Key | Action |
|---|---|
| `Space`, `j`, `→` | next fragment |
| `b`, `k`, `←` | previous fragment |
| `J` | first fragment of the next paragraph |
| `K` | first fragment of the previous paragraph |
| `g` `g` | first fragment of the book |
| `G` | last fragment of the book |
| `:` | open the command line |
| `q`, `Ctrl+C` | quit (position is saved) |

### Commands

| Command | Effect |
|---|---|
| `:set width=N` | fragment width, N from 5 to 12 (default 8); re-chunks instantly |
| `:set theme=dark` / `:set theme=light` | color preset for dark or light terminal backgrounds |
| `:goto P` | jump to P percent of the book (0–100, by words) |
| `:q` | quit |

On the command line, `Enter` runs the command, `Esc` cancels it and
`Backspace` on an empty line closes it. The status line shows progress as a
word-based percentage, which stays the same when you change the width.

### Where state lives

- **Reading position and per-book settings** are stored inside the `.kert`
  file itself (the `reader_state` table). Book content is never modified after
  compilation.
- **Global defaults** live in a TOML file:
  - Linux and macOS: `~/.config/kert/config.toml` (or
    `$XDG_CONFIG_HOME/kert/config.toml`)
  - Windows: `%APPDATA%\kert\config.toml`

  ```toml
  chunk_width = 8
  theme = "dark"
  ```

  Precedence: the book's own last-used value, then this file, then the
  built-in defaults (width 8, theme dark). `:set` writes to both the book and
  this file, so a preference you set once also applies to books you open
  later. A missing or broken file is ignored, and `:set` rewrites it with just
  these two keys. The file never stores positions.

> **Do not copy a `.kert` file while a `kert read` session on it is open.**
> The Reader uses SQLite WAL mode; until you quit, recent changes may live in
> `book.kert-wal`/`-shm` sidecar files. On exit kert folds them back so the
> `.kert` is again a single portable file.

### Terminals

- Supported: Windows Terminal, macOS Terminal.app, iTerm2, and any VT-capable
  Linux terminal emulator. The legacy Windows console host (`conhost.exe`) is
  unsupported and untested; use Windows Terminal.
- kert uses 256-color greys rather than the ANSI dim attribute, so contrast
  does not depend on how your terminal draws "dim".
- At least 40 columns are needed; a narrower window shows a notice until you
  resize it. Resizing takes effect on the next key press.

## Development

All environment operations go through uv. Python 3.14 is pinned in
`.python-version`.

```sh
uv sync --all-groups          # interpreter, deps, dev tools and pinned spaCy models
uv run pytest                 # full suite
uv run pytest -m "not spacy"  # fast suite without models
uv run ruff check && uv run ruff format --check
uv run kert compile tests/fixtures/book_ru.txt -o /tmp/book.kert --lang ru
uv run kert read /tmp/book.kert
```

- `kert_spec.md` is the specification and the single source of truth;
  `SPEC_NOTES.md` records each place where the implementation had to resolve
  something the spec left open.
- Development is strict TDD (spec §13.1): a `test(<module>)` commit with
  failing tests first, then a `feat(<module>)` commit that makes them pass.
- Tests that need the spaCy models are marked `spacy`. They are skipped
  locally when the models are missing and mandatory in CI.
- Golden candidate tests are bound to the pinned model versions. Upgrading a
  model is a separate task that includes regenerating and re-reviewing the
  goldens.

### Releasing

Versions follow [Semantic Versioning](https://semver.org). The next version
and `CHANGELOG.md` come from the conventional commit messages, generated with
[git-cliff](https://git-cliff.org) (`cliff.toml`). While the major version is
0, `feat` bumps the minor version and `fix` bumps the patch version.

```sh
scripts/release.sh          # bump version, regenerate CHANGELOG.md, run checks, commit, tag
git push origin main vX.Y.Z # the tag push starts the release workflow
```

`.github/workflows/release.yml` checks that the tag matches the version in
`pyproject.toml` and runs the full test suite. It then builds the PyInstaller
bundle (`packaging/kert.spec`) on macOS, Linux and Windows, and smoke-tests
each binary outside any Python environment (`packaging/smoke_package.py`).
Last, it publishes a GitHub Release with the archives, checksums and the
changelog section for that version. To build and smoke-test without
publishing, run the workflow manually from the Actions tab.

macOS runners are opt-in, because they use Actions minutes at 10x the Linux
rate on private repositories. CI and releases run on Linux and Windows unless
the repository variable `MACOS_CI` is set to `true` (Settings → Secrets and
variables → Actions → Variables). Without macOS builds, macOS users install
from source.

To build locally: `uv run pyinstaller packaging/kert.spec --distpath dist
--workpath build`.

The Android app takes its version from `pyproject.toml` (`versionCode` =
major·10000 + minor·100 + patch), so `scripts/release.sh` versions it too. The
release attaches a signed `kert-android-<version>.apk` only when these
repository secrets are set; without them the release has no APK:

| Secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | the release keystore, `base64 -i release.jks` |
| `ANDROID_KEYSTORE_PASSWORD` | keystore password |
| `ANDROID_KEY_ALIAS` | key alias |
| `ANDROID_KEY_PASSWORD` | key password |

Create the keystore once and keep a backup: a lost key means users must
uninstall the app to update. `keytool -genkeypair -keystore release.jks -alias
kert -keyalg RSA -keysize 4096 -validity 10000`. The Android workflow builds a
debug and a release APK on every change under `android/`; the release APK is
signed when the secrets are available and unsigned otherwise. To sign a local
build, set `KERT_ANDROID_KEYSTORE` to the keystore path plus the three password
and alias variables above, then run `./gradlew :app:assembleRelease` in
`android/`.

## How this was built

kert is a personal project built to solve my own trouble with focus on long
texts. It is developed with an AI coding assistant ([Claude
Code](https://claude.com/claude-code)): I own the product decisions, the
specification and the acceptance testing; most of the code and tests were
written by the assistant under that direction. Every such commit says so in its
`Co-Authored-By` trailer.

The process keeps that honest and reviewable:

- [`kert_spec.md`](kert_spec.md) is the single source of truth. Where the spec
  was silent or wrong, the resolution is recorded in
  [`SPEC_NOTES.md`](SPEC_NOTES.md).
- Strict TDD: a failing `test(...)` commit first, then the `feat(...)` commit.
  The golden outputs are hand-derived from the spec, never frozen from the
  implementation.
- The Kotlin port of the reading engine is cross-checked against the Python
  reference on every fixture and width (`scripts/export_android_reference.py`).
- CI runs lint and tests on Linux and Windows (macOS when enabled). Each release
  ships smoke-tested binaries.

## License

kert is released under the [MIT License](LICENSE). Prebuilt binaries bundle
third-party components under their own licenses. Each release includes their
notices (`THIRD_PARTY_NOTICES-<platform>.txt`, also inside the full archive).
The Android app shows its notices under *Licenses* in the library.

## Manual acceptance checklist

Run on **Windows Terminal**, **macOS Terminal.app** and **one Linux terminal
emulator**, with both `:set theme=dark` and `:set theme=light`:

- [x] `uv run kert compile tests/fixtures/book_ru.txt -o book.kert --lang ru`
      succeeds and prints a summary.
- [x] `uv run kert read book.kert` opens in the alternate screen; on quit the
      terminal is restored.
- [x] Russian text, including `—` dialogue dashes, renders correctly.
- [x] The active fragment is clearly brighter/bolder than the rest of its
      paragraph; neighbor paragraphs are dimmer still. Check contrast in both
      themes on the matching background.
- [x] `Space`/`j`/`→` and `b`/`k`/`←` move by fragment; `J`/`K`, `gg`, `G`
      jump as documented.
- [x] `:set width=5` and `:set width=12` re-chunk and keep the reading
      position; the percentage does not change.
- [x] `:goto 50` lands near the middle; an unknown command shows an error
      without crashing.
- [x] Resize the window: the layout updates on the next key press. Below 40
      columns the "Terminal too narrow" notice appears; widening restores the
      text.
- [x] Quit with `q`, reopen: the same fragment is active. Repeat with
      `Ctrl+C`.
- [x] After quitting, only `book.kert` remains (no `-wal`/`-shm` files).
