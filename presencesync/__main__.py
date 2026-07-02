"""`python -m presencesync` → the headless CLI."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
