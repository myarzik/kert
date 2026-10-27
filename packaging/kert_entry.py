"""Entry point for the frozen (PyInstaller) build."""

import sys

from kert.cli import main

sys.exit(main())
