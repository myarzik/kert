"""Bridge from the Android app to the Python compiler (spike, §16).

Runs on Python 3.10 (Chaquopy): fills in the two 3.11+ / packaging bits the
compiler expects, then calls kert.compiler.pipeline.compile_book.
"""

import datetime
import importlib.metadata
from pathlib import Path

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc

_APP_VERSION = "android"
_real_version = importlib.metadata.version


def _version(name):
    # The compiler records its version in meta; kert is not pip-installed here.
    return _APP_VERSION if name == "kert" else _real_version(name)


importlib.metadata.version = _version


def compile_book(source: str, output: str, lang: str, app_version: str) -> str:
    """Compile `source` into `output`; returns a one-line summary."""
    global _APP_VERSION
    _APP_VERSION = app_version
    from kert.compiler.pipeline import compile_book as compile_

    summary = compile_(Path(source), Path(output), lang, force=True)
    return f"{summary.blocks} blocks, {summary.sentences} sentences, {summary.elapsed:.1f}s"
