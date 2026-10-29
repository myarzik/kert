"""Smoke-test the frozen kert builds, then package them for release (§15).

Usage: python packaging/smoke_package.py DIST_DIR TARGET
  DIST_DIR  PyInstaller output: the full build folder `kert/` and the
            single-file Reader build `kert-reader[.exe]`
  TARGET    platform label for the asset names, e.g. linux-x86_64

Runs both binaries outside any Python environment and checks the §9 commands
against hand-derived goldens shared with the test suite.
"""

import importlib.util
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


def run(binary: Path, *args: str, cwd: Path, expect: int = 0) -> str:
    env = {k: v for k, v in os.environ.items() if k not in HIDDEN_ENV}
    result = subprocess.run(
        [str(binary), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != expect:
        sys.exit(
            f"FAIL: {binary.name} {' '.join(args)} exited {result.returncode}, "
            f"expected {expect}\n{result.stdout}{result.stderr}"
        )
    return result.stdout + result.stderr if expect else result.stdout


def check_version(binary: Path, work: Path, version: str) -> None:
    out = run(binary, "--version", cwd=work).strip()
    if out != f"kert {version}":
        sys.exit(f"FAIL: {binary.name} --version printed {out!r}, expected {version}")


def check_inspect(binary: Path, work: Path) -> None:
    out = run(binary, "inspect", "ru.kert", "--sentence", "4", "--width", "6", cwd=work)
    if out != INSPECT_GOLDEN:
        sys.exit(
            f"FAIL: {binary.name} inspect differs:\n{out!r}\n!=\n{INSPECT_GOLDEN!r}"
        )


def smoke(full: Path, reader: Path, version: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copy(FIXTURE, work / "book_ru.txt")
        (work / "en.txt").write_text(
            "He went home, although it was raining.\n", encoding="utf-8"
        )

        # Full build: compile both languages, inspect against the golden.
        check_version(full, work, version)
        for txt, out, lang in (
            ("book_ru.txt", "ru.kert", "ru"),
            ("en.txt", "en.kert", "en"),
        ):
            run(full, "compile", txt, "-o", out, "--lang", lang, cwd=work)
        check_inspect(full, work)
        print(f"smoke OK: kert {version}")

        # Reader build: reads what the full build compiled; cannot compile.
        check_version(reader, work, version)
        check_inspect(reader, work)
        err = run(reader, "compile", "en.txt", "-o", "x.kert", "--lang", "en",
                  cwd=work, expect=1)  # fmt: skip
        if "cannot compile" not in err or (work / "x.kert").exists():
            sys.exit(f"FAIL: kert-reader compile should refuse:\n{err}")
        print(f"smoke OK: kert-reader {version}")


def main() -> None:
    dist, target = Path(sys.argv[1]).resolve(), sys.argv[2]
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    exe = ".exe" if os.name == "nt" else ""
    full, reader = dist / "kert" / f"kert{exe}", dist / f"kert-reader{exe}"
    smoke(full, reader, version)

    # Licenses travel with the binaries (§15): kert's own and every bundled
    # component's; the Reader's components are a subset of the full build's.
    notices = _notices().render("full")
    shutil.copy(ROOT / "LICENSE", dist / "kert" / "LICENSE")
    (dist / "kert" / "THIRD_PARTY_NOTICES.txt").write_text(notices, encoding="utf-8")
    (dist / f"THIRD_PARTY_NOTICES-{target}.txt").write_text(notices, encoding="utf-8")

    archive = shutil.make_archive(
        str(dist / f"kert-{version}-{target}"),
        "zip" if os.name == "nt" else "gztar",
        root_dir=dist,
        base_dir="kert",
    )
    single = shutil.copy2(reader, dist / f"kert-reader-{version}-{target}{exe}")
    print(f"assets: {archive}, {single}")


def _notices():
    path = Path(__file__).with_name("third_party_notices.py")
    spec = importlib.util.spec_from_file_location("third_party_notices", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    main()
