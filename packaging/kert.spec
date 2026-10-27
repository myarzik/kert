# PyInstaller spec for the standalone kert build (one directory, both models).
# Build: uv run pyinstaller packaging/kert.spec --distpath dist --workpath build

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []
# spaCy loads pipelines, registries and model data by name at runtime.
for package in (
    "spacy",
    "thinc",
    "ru_core_news_sm",
    "en_core_web_sm",
    "pymorphy3",
    "pymorphy3_dicts_ru",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
# importlib.metadata lookups: `kert --version`, and readchar at import time.
for distribution in ("kert", "readchar"):
    datas += copy_metadata(distribution)

a = Analysis(
    [f"{SPECPATH}/kert_entry.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "_pytest", "ruff", "PyInstaller"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="kert", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="kert")
