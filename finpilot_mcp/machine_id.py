"""Stable machine signature for anonymous guest sessions.

Generates a 24-char hex ID seeded from hardware signals on first run,
then persists it to ~/.finpilot/machine_id so it survives IP changes,
VPN switches, and network adapter replacements.

The raw MAC / hostname never leave the machine — only the SHA-256 hash
is sent to the server as X-Machine-ID.
"""

import hashlib
import platform
import uuid
from pathlib import Path

_ID_FILE = Path.home() / ".finpilot" / "machine_id"
_ID_LENGTH = 24

_cached: str | None = None


def get() -> str:
    """Return the stable machine ID, generating and persisting it if needed."""
    global _cached
    if _cached is None:
        _cached = _load_or_generate()
    return _cached


def _load_or_generate() -> str:
    if _ID_FILE.exists():
        val = _ID_FILE.read_text().strip()
        if len(val) == _ID_LENGTH and all(c in "0123456789abcdef" for c in val):
            return val
    mid = _generate()
    _ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ID_FILE.write_text(mid)
    return mid


def _generate() -> str:
    """Seed from hardware signals; pure random fallback for VMs / sandboxes."""
    try:
        mac = uuid.getnode()
        node = platform.node()
        system = platform.system()
        machine = platform.machine()
        raw = f"{mac}:{node}:{system}:{machine}"
    except Exception:
        # Fully sandboxed environment — fall back to random seed
        raw = str(uuid.uuid4())
    return hashlib.sha256(raw.encode()).hexdigest()[:_ID_LENGTH]
