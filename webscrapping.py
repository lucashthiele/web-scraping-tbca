"""Compatibility entry point for running ``python webscrapping.py``."""

import sys

from tbca_scraper.cli import main


if __name__ == "__main__":
    sys.exit(main())
