import sys
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from kert.common.errors import KertError

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_INTERNAL_ERROR = 2

app = typer.Typer(no_args_is_help=True)


class LangOption(StrEnum):
    ru = "ru"
    en = "en"


class ParagraphMode(StrEnum):
    blank = "blank"
    indent = "indent"
    single_newline = "single-newline"


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"kert {version('kert')}")
        raise typer.Exit()


@app.callback()
def root(
    show_version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """Terminal focus-reader."""


@app.command("compile")
def compile_command(
    input_path: Annotated[
        Path, typer.Argument(metavar="INPUT", exists=True, dir_okay=False)
    ],
    output: Annotated[Path, typer.Option("-o", "--output", help="Target .kert file.")],
    lang: Annotated[LangOption, typer.Option("--lang", help="Book language.")],
    paragraph_mode: Annotated[
        ParagraphMode, typer.Option("--paragraph-mode")
    ] = ParagraphMode.blank,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite an existing OUTPUT.")
    ] = False,
) -> None:
    """Compile a .txt book into a .kert file."""
    if paragraph_mode is not ParagraphMode.blank:
        raise KertError(
            f"--paragraph-mode {paragraph_mode.value} is not implemented yet; "
            "only 'blank' is supported."
        )
    from kert.compiler import pipeline

    summary = pipeline.compile_book(input_path, output, lang.value, force=force)
    typer.echo(
        f"Compiled {output}: {summary.blocks} blocks, {summary.sentences} sentences, "
        f"{summary.candidates_per_sentence:.2f} candidates/sentence, "
        f"{summary.elapsed:.1f}s"
    )


@app.command("read")
def read_command(book: Annotated[Path, typer.Argument(metavar="BOOK")]) -> None:
    """Read a compiled .kert book in the terminal."""
    from kert.reader import app as reader_app

    reader_app.run(book)


@app.command("inspect")
def inspect_command(
    book: Annotated[Path, typer.Argument(metavar="BOOK")],
    sentence: Annotated[int | None, typer.Option("--sentence")] = None,
    block: Annotated[int | None, typer.Option("--block")] = None,
    span: Annotated[str | None, typer.Option("--range", metavar="A:B")] = None,
    width: Annotated[int, typer.Option("--width", min=5, max=12)] = 8,
) -> None:
    """Show split candidates and assembled chunks (plain text)."""
    from kert.reader import inspect
    from kert.reader.store import BookStore

    parsed_span = None if span is None else inspect.parse_range(span)
    with BookStore.open(book) as store:
        selected = inspect.select_sentences(
            store.sentences, sentence=sentence, block=block, span=parsed_span
        )
    typer.echo("\n\n".join(inspect.render_inspection(s, width) for s in selected))


def main(argv: list[str] | None = None) -> int:
    """Entry point; maps outcomes to exit codes (spec §9)."""
    for stream in (sys.stdout, sys.stderr):  # §7.3: Windows consoles
        encoding = (getattr(stream, "encoding", None) or "").lower()
        if encoding not in ("utf-8", "utf8") and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        code = app(args=argv, prog_name="kert", standalone_mode=False)
    except typer.TyperException as exc:  # bad arguments / usage
        show = getattr(exc, "show", None)
        if show is not None:
            show()
        else:
            typer.echo(f"Error: {exc}", err=True)
        return EXIT_USER_ERROR
    except typer.Abort:
        typer.echo("Aborted.", err=True)
        return EXIT_USER_ERROR
    except KertError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return EXIT_USER_ERROR
    except Exception as exc:
        typer.echo(f"kert: internal error: {exc!r}", err=True)
        return EXIT_INTERNAL_ERROR
    return code or EXIT_OK
