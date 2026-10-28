# kert: how it works

Four views of the project: data flow from a book file to the screen, the
Reader loop, the development workflow, and CI and release. The specification
(`kert_spec.md`) is the source of truth; section numbers below point into it.

## 1. Data flow: book file → `.kert` → screen

The Compiler and the Reader share only `common/` and the `.kert` file format.
The file stores split-point candidates, not finished fragments (D4), so the
Reader can re-chunk at any width without recompiling.

```mermaid
flowchart TD
    subgraph inputs["Input (by suffix, §14.1)"]
        txt[".txt"]
        md[".md / .markdown"]
        fb2[".fb2 / .fb2.zip"]
        epub[".epub"]
    end

    subgraph compiler["kert compile"]
        ingest["Ingest<br/>TxtIngester · MarkdownIngester<br/>Fb2Ingester · EpubIngester<br/>→ RawBlock list + title"]
        normalize["Normalize §4.2 / §14.2<br/>NFC, dashes, code verbatim,<br/>block types, chapters"]
        segment["Segment §4.4<br/>spaCy sentences<br/>(paragraph, dialogue, list_item)"]
        unchunked["Un-chunked §14.3<br/>heading, code:<br/>one sentence, no candidates"]
        candidates["Candidates §4.5<br/>ranked split points<br/>from the dependency parse"]
        persist["Persist §4.6<br/>one SQLite transaction,<br/>atomic file replace"]
    end

    kert[(".kert<br/>meta · blocks · sentences<br/>reader_state · advance_log")]

    subgraph reader["kert read"]
        store["BookStore §5<br/>full scan into memory"]
        settings["Settings §8.4<br/>book > TOML > defaults"]
        chunker["Chunker §6<br/>DP over candidates<br/>at width W"]
        state["ReaderState<br/>handle_key(state, key)"]
        render["build_frame §7<br/>center-focus tape"]
    end

    screen["Terminal<br/>Rich Live"]

    txt & md & fb2 & epub --> ingest --> normalize
    normalize --> segment --> candidates --> persist
    normalize --> unchunked --> persist
    persist --> kert
    kert --> store --> chunker
    settings --> chunker
    chunker --> state --> render --> screen
```

`kert inspect` reads the same `.kert` file and prints the candidates and
fragments as plain text. Use it to calibrate the §4.5 weights and §6 costs.

## 2. Reader loop

`handle_key` is pure: it returns a new state and a list of effects. The loop
in `app.py` performs the side effects: it writes `advance_log` rows and `:set`
values, and saves the position on exit.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant App as app.run
    participant State as handle_key
    participant Store as BookStore (.kert)
    participant Config as config.toml

    App->>Store: open_session: scan book, load position
    App->>Config: load_global (precedence §8.4)
    App->>User: build_frame(state)
    loop until q, :q or Ctrl+C
        User->>App: key (readchar)
        App->>State: handle_key(state, key)
        State-->>App: new state + effects
        alt Advance (j / k)
            App->>Store: log_advance(ts, sentence, words, ±1)
        else SaveSetting (:set width / theme)
            App->>Store: reader_state
            App->>Config: rewrite known keys
        end
        App->>User: build_frame(new state)
    end
    App->>Store: close_session: save position,<br/>trim advance_log to 10 000,<br/>WAL checkpoint, close
```

```mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> Normal: j k Space b arrows (step, logged)
    Normal --> Normal: J K G (jump, not logged)
    Normal --> PendingG: g
    PendingG --> Normal: g (first chunk)
    PendingG --> Normal: any other key (run it)
    Normal --> Command: colon
    Command --> Command: printable key / Backspace
    Command --> Normal: Esc / Backspace on empty line
    Command --> Normal: Enter (run set / goto, show message)
    Command --> [*]: Enter on q
    Normal --> [*]: q / Ctrl+C (save and quit)
```

## 3. Development workflow (strict TDD, §13.1)

```mermaid
flowchart TD
    task["Task from §13.2 / §14.8"] --> spec{"Is the spec clear?"}
    spec -- no --> ask["Ask, then record the<br/>resolution in SPEC_NOTES.md"] --> spec
    spec -- yes --> red["RED: write tests from the spec<br/>(hand-derived goldens)"]
    red --> fails{"Fails for the right reason?<br/>(NotImplementedError, missing behavior)"}
    fails -- no --> red
    fails -- yes --> c1["commit test(module): …"]
    c1 --> green["GREEN: implement<br/>(tests are not edited)"]
    green --> contra{"Does a test contradict the spec?"}
    contra -- yes --> fix["Fix the test +<br/>one line in SPEC_NOTES.md"] --> green
    contra -- no --> refactor["REFACTOR: uv run pytest<br/>+ ruff check / format"]
    refactor --> c2["commit feat(module): …"]
    c2 --> push["git push → CI"]
```

Dependency changes are separate `chore(deps)` commits. Upgrading a model is
its own task, together with regenerating the goldens.

## 4. CI and release

```mermaid
flowchart TD
    subgraph ci["ci.yml: push to main, pull request"]
        lint["Lint<br/>ruff check + format"]
        tests["Tests<br/>ubuntu · macos · windows<br/>(spaCy tests mandatory)"]
    end

    rel["scripts/release.sh<br/>git-cliff --bumped-version<br/>uv version · CHANGELOG.md<br/>pytest · ruff · commit · tag"]
    push["git push origin main vX.Y.Z"]

    subgraph release["release.yml: tag v*.*.* (or manual dry run)"]
        version["Check version<br/>tag == pyproject"]
        reuse["Tests<br/>(calls ci.yml)"]
        build["Build PyInstaller bundle<br/>macos-arm64 · linux-x86_64 · windows-x86_64"]
        smoke["Smoke test the binary<br/>outside Python: --version,<br/>compile RU/EN, inspect golden"]
        publish["Publish GitHub Release<br/>archives + SHA256SUMS<br/>+ notes from git-cliff"]
    end

    rel --> push --> version
    push --> reuse
    version & reuse --> build --> smoke --> publish
```

Semantic versions come from conventional commits. While the major version is
0, `feat` bumps the minor version and `fix` bumps the patch version. `test:`,
`ci:` and release commits stay out of the changelog.
