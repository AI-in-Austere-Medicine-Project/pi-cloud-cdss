"""EdgeCDSS — the version, in one place.

There were two "4.1.0" string literals in main.py: the FastAPI app metadata and
the /status payload. They were edited independently, which is why /status kept
reporting 4.1.0 through four merged PRs — nothing failed, the number was simply
never the same fact twice.

Anything that reports a version imports it from here. Tests assert that no
literal version string survives anywhere else, so the next bump is one edit and
cannot half-land.
"""

__version__ = "4.3.0"
VERSION = __version__
