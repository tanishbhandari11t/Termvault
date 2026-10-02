"""Allow ``python -m termvault`` / ``py -m termvault`` as a CLI entrypoint."""

from __future__ import annotations

from termvault.cli import run

if __name__ == "__main__":
    run()
