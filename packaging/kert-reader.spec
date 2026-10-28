# PyInstaller spec for the Reader-only kert build: one file, no compiler (§15).
# Build: uv run pyinstaller packaging/kert-reader.spec --distpath dist --workpath build

from PyInstaller.utils.hooks import copy_metadata

datas = []
# importlib.metadata lookups: `kert --version`, and readchar at import time.
for distribution in ("kert", "readchar"):
    datas += copy_metadata(distribution)

a = Analysis(
    [f"{SPECPATH}/kert_entry.py"],
    datas=datas,
    # The CLI imports the compiler lazily; leave the whole NLP stack out.
    excludes=[
        "kert.compiler",
        "spacy",
        "thinc",
        "numpy",
        "blis",
        "cymem",
        "preshed",
        "murmurhash",
        "srsly",
        "catalogue",
        "confection",
        "wasabi",
        "weasel",
        "pydantic",
        "pymorphy3",
        "ru_core_news_sm",
        "en_core_web_sm",
        "pytest",
        "_pytest",
        "PyInstaller",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="kert-reader", console=True)
