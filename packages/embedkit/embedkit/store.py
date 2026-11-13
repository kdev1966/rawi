"""Model files: local cache, download with resume, sha256 check, strict offline mode (EK-1, EK-2)."""

from __future__ import annotations

import hashlib
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import EmbedkitError
from .registry import Manifest

ENV_CACHE = "EMBEDKIT_CACHE"
ENV_OFFLINE = "EMBEDKIT_OFFLINE"
ENV_ENDPOINT = "EMBEDKIT_HF_ENDPOINT"  # mirror or test server
DEFAULT_ENDPOINT = "https://huggingface.co"
CHUNK = 1 << 20


class StoreError(EmbedkitError):
    pass


def cache_dir() -> Path:
    return Path(os.environ.get(ENV_CACHE) or Path.home() / ".cache" / "embedkit")


def offline() -> bool:
    return os.environ.get(ENV_OFFLINE, "") in ("1", "true", "yes")


def model_path(m: Manifest) -> Path:
    """Where the model file lives once installed (one folder per id and pinned revision)."""
    return cache_dir() / m.id / m.source.revision[:12] / m.filename


def is_installed(m: Manifest) -> bool:
    return model_path(m).is_file()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def url_of(m: Manifest) -> str:
    endpoint = os.environ.get(ENV_ENDPOINT, DEFAULT_ENDPOINT).rstrip("/")
    return f"{endpoint}/{m.source.repo}/resolve/{m.source.revision}/{m.source.file}"


def verify(m: Manifest) -> bool:
    """True if the installed file matches the manifest's sha256."""
    path = model_path(m)
    return path.is_file() and sha256_of(path) == m.sha256


def _progress(done: int, total: int | None, started: float) -> None:
    rate = done / max(time.monotonic() - started, 1e-6) / 2**20
    if total:
        print(
            f"\r  {done / 2**20:7.1f} / {total / 2**20:.1f} Mo  ({rate:.1f} Mo/s)",
            end="",
            file=sys.stderr,
        )
    else:
        print(f"\r  {done / 2**20:7.1f} Mo  ({rate:.1f} Mo/s)", end="", file=sys.stderr)


def pull(m: Manifest, timeout: float = 60) -> Path:
    """Make sure the model file is in the cache and intact; download it if needed.

    An interrupted download resumes from its .part file (HTTP Range).
    """
    path = model_path(m)
    if path.is_file():
        return path
    if offline():
        raise StoreError(
            f"Mode hors ligne : le modèle « {m.id} » n'est pas installé. Lancez « embedkit models pull {m.id} » avec une connexion."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    request = urllib.request.Request(url_of(m), headers={"User-Agent": "embedkit"})
    if have:
        request.add_header("Range", f"bytes={have}-")
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and have:  # .part already complete
            response = None
        else:
            raise StoreError(
                f"Téléchargement de « {m.id} » impossible : HTTP {exc.code} ({url_of(m)})"
            ) from None
    except (urllib.error.URLError, OSError) as exc:
        raise StoreError(
            f"Téléchargement de « {m.id} » impossible : {exc}. Vérifiez la connexion."
        ) from None

    if response is not None:
        with response:
            if have and response.status != 206:  # server ignored Range: start over
                have = 0
            length = response.headers.get("Content-Length")
            total = have + int(length) if length else None
            started, done = time.monotonic(), have
            print(f"→ {m.id} ({m.size_mb:g} Mo)", file=sys.stderr)
            with open(part, "ab" if have else "wb") as out:
                while chunk := response.read(CHUNK):
                    out.write(chunk)
                    done += len(chunk)
                    _progress(done, total, started)
            print(file=sys.stderr)

    digest = sha256_of(part)
    if digest != m.sha256:
        part.unlink()
        raise StoreError(
            f"Fichier corrompu pour « {m.id} » (sha256 {digest[:12]}… au lieu de {m.sha256[:12]}…). "
            "Le fichier partiel a été supprimé ; relancez le téléchargement."
        )
    os.replace(part, path)
    return path
