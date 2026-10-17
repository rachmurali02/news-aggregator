"""Encrypted credentials stored in the repo (credentials.enc).

The file is encrypted with Fernet (AES-128-CBC + HMAC-SHA256). The key never
lives in the repo: it is supplied via the DIGEST_SECRET_KEY environment
variable (a GitHub Actions secret in CI).

    python -m digest.credentials genkey                   # print a new key
    python -m digest.credentials set SMTP_USER=a@b.com    # add/update values
    python -m digest.credentials show                     # list stored names
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "credentials.enc"
KEY_ENV = "DIGEST_SECRET_KEY"


def _fernet(key: str | None = None) -> Fernet:
    key = key or os.environ.get(KEY_ENV)
    if not key:
        raise SystemExit(f"{KEY_ENV} is not set")
    return Fernet(key.encode())


def read(path: Path = DEFAULT_PATH, key: str | None = None) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(_fernet(key).decrypt(path.read_bytes()))
    except InvalidToken:
        raise SystemExit(f"Could not decrypt {path.name}: wrong {KEY_ENV}?")


def write(values: dict[str, str], path: Path = DEFAULT_PATH, key: str | None = None) -> None:
    path.write_bytes(_fernet(key).encrypt(json.dumps(values, sort_keys=True).encode()))


def load_into_env(path: Path = DEFAULT_PATH) -> list[str]:
    """Export decrypted values as env vars; explicitly set env vars win."""
    if not os.environ.get(KEY_ENV) or not path.exists():
        return []
    loaded = []
    for name, value in read(path).items():
        if not os.environ.get(name):
            os.environ[name] = value
            loaded.append(name)
    return loaded


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in {"genkey", "set", "show"}:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "genkey":
        print(Fernet.generate_key().decode())
    elif cmd == "set":
        values = read()
        for pair in args:
            name, _, value = pair.partition("=")
            if not name or not _:
                raise SystemExit(f"Expected NAME=VALUE, got {pair!r}")
            values[name] = value
        write(values)
        print(f"Stored {', '.join(sorted(values))} in {DEFAULT_PATH.name}")
    else:
        print("\n".join(sorted(read())) or "(empty)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
