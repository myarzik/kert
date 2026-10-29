"""Third-party notices for the frozen builds (spec §15).

Usage: python packaging/third_party_notices.py {full,reader} OUT_FILE

Walks the installed dependency tree from each build's top-level
distributions and writes every component's name, version, license and the
full text of its license files, plus Python's own license and the
PyInstaller bootloader exception. Generated at build time, so the list
follows the pinned dependencies.
"""

import re
import sys
import sysconfig
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

# Top-level distributions of each build (packaging/kert*.spec).
ROOTS = {
    "full": ["kert", "ru-core-news-sm", "en-core-web-sm"],
    # kert-reader: the Reader's own imports; markdown-it-py comes with rich.
    "reader": ["rich", "typer", "readchar", "msgpack", "platformdirs"],
}
# Never bundled (kert.spec excludes): the RU lemmatizer is excluded at load
# time (§4.4), and kert itself is this project (see LICENSE).
EXCLUDED = {"kert", "pymorphy3", "pymorphy3-dicts-ru", "dawg2-python", "dawg-python"}
LICENSE_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE)", re.IGNORECASE)

PYINSTALLER_NOTE = """\
The executables are built with PyInstaller (GPL-2.0-or-later with the
PyInstaller bootloader exception): the bootloader and the files PyInstaller
adds to the bundle may be distributed under any license. See
https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt
"""


def _name(requirement: str) -> str:
    return re.split(r"[\s;<>=!~\[(@]", requirement, maxsplit=1)[0]


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def closure(roots: list[str]) -> list:
    """Installed distributions reachable from `roots`, extras excluded."""
    seen: dict[str, object] = {}
    pending = list(roots)
    while pending:
        name = _canonical(pending.pop())
        if name in seen:
            continue
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue  # an optional or platform-specific requirement
        seen[name] = dist
        for requirement in dist.requires or []:
            if "extra ==" not in requirement:
                pending.append(_name(requirement))
    return sorted(
        (d for n, d in seen.items() if n not in EXCLUDED),
        key=lambda d: _canonical(d.metadata["Name"]),
    )


def _license(dist) -> str:
    meta = dist.metadata
    if meta.get("License-Expression"):
        return meta["License-Expression"]
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    short = (meta.get("License") or "").strip().splitlines()
    return ", ".join(classifiers) or (short[0] if short else "see license text")


def _license_texts(dist) -> list[str]:
    texts = []
    for file in dist.files or []:
        if LICENSE_FILE.search(Path(str(file)).name) or "/licenses/" in str(file):
            try:
                texts.append(Path(dist.locate_file(file)).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return texts


def _python_license() -> str:
    for path in (
        Path(sysconfig.get_paths()["stdlib"]) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE.txt",
    ):
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return "Python is distributed under the PSF License Agreement: https://docs.python.org/3/license.html\n"


def render(build: str) -> str:
    lines = [
        f"Third-party software in the kert {build} build",
        "=" * 60,
        "",
        "kert itself is licensed under the MIT License (see LICENSE).",
        "It bundles the following components under their own licenses.",
        "",
        PYINSTALLER_NOTE,
    ]
    dists = closure(ROOTS[build])
    for dist in dists:
        lines.append(
            f"\n{_canonical(dist.metadata['Name'])} {dist.version}  [{_license(dist)}]"
        )
        for text in _license_texts(dist):
            lines += ["-" * 60, text.strip(), "-" * 60]
    py = sys.version.split()[0]
    lines += [
        f"\npython {py}  [PSF-2.0]",
        "-" * 60,
        _python_license().strip(),
        "-" * 60,
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    Path(sys.argv[2]).write_text(render(sys.argv[1]), encoding="utf-8")
