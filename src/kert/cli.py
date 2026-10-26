from importlib.metadata import version

import typer

app = typer.Typer(no_args_is_help=True)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"kert {version('kert')}")
        raise typer.Exit()


@app.callback()
def root(
    show_version: bool = typer.Option(
        False,
        "--version",
        callback=_print_version,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Terminal focus-reader."""


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError
