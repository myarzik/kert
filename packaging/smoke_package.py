"""Smoke-test a frozen kert build, then archive it for release.

Usage: python packaging/smoke_package.py DIST_DIR TARGET
  DIST_DIR  directory holding the PyInstaller output folder `kert/`
  TARGET    platform label for the archive name, e.g. macos-arm64

Runs the binary outside any Python environment and checks the §9 commands
against hand-derived goldens shared with the test suite.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "book_ru.txt"
# Golden from tests/test_inspect.py (dialogue sentence, W=6).
INSPECT_GOLDEN = (
    "— Привет, —⟨1.0⟩ сказал он⟨0.8⟩ и улыбнулся.\n"
    "[— Привет, —] [сказал он и улыбнулся.]\n"
)
HIDDEN_ENV = ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT")


def run(binary: Path, *args: str, cwd: Path) -> str:
    env = {k: v for k, v in os.environ.items() if k not in HIDDEN_ENV}
    result = subprocess.run(
        [str(binary), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        sys.exit(
            f"FAIL: kert {' '.join(args)} exited {result.returncode}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout


def smoke(binary: Path, version: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copy(FIXTURE, work / "book_ru.txt")
        (work / "en.txt").write_text(
            "He went home, although it was raining.\n", encoding="utf-8"
        )

        assert run(binary, "--version", cwd=work).strip() == f"kert {version}"
        for txt, out, lang in (
            ("book_ru.txt", "ru.kert", "ru"),
            ("en.txt", "en.kert", "en"),
        ):
            run(binary, "compile", txt, "-o", out, "--lang", lang, cwd=work)
        out = run(
            binary, "inspect", "ru.kert", "--sentence", "4", "--width", "6", cwd=work
        )
        if out != INSPECT_GOLDEN:
            sys.exit(f"FAIL: inspect output differs:\n{out!r}\n!=\n{INSPECT_GOLDEN!r}")
    print(f"smoke OK: kert {version}")


def main() -> None:
    dist, target = Path(sys.argv[1]).resolve(), sys.argv[2]
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    binary = dist / "kert" / ("kert.exe" if os.name == "nt" else "kert")
    smoke(binary, version)

    name = f"kert-{version}-{target}"
    archive_format = "zip" if os.name == "nt" else "gztar"
    archive = shutil.make_archive(
        str(dist / name), archive_format, root_dir=dist, base_dir="kert"
    )
    print(f"archive: {archive}")


if __name__ == "__main__":
    main()
