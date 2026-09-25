"""Small shared helpers: logging setup, hashing, filenames, atomic file writes."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once. Safe to call multiple times."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format=_LOG_FORMAT)
    root.setLevel(level)
    # Third-party libraries are chatty at INFO; keep them quieter.
    for noisy in ("httpx", "httpcore", "urllib3", "sentence_transformers", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")


def sanitize_filename(filename: str, max_length: int = 120) -> str:
    """Return a display-safe filename.

    Strips any directory components (defeats ``../../etc/passwd`` style names),
    removes characters outside a conservative whitelist and trims length while
    keeping the extension. The result is only used for *display* and metadata;
    files are stored on disk under their content hash, never under this name.
    """
    name = unicodedata.normalize("NFKC", filename or "")
    # Treat both separators as path separators regardless of OS.
    name = name.replace("\\", "/").split("/")[-1]
    name = _UNSAFE_FILENAME_CHARS.sub("_", name).strip(" .")
    if not name:
        name = "document.pdf"
    if len(name) > max_length:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 10:
            name = stem[: max_length - len(ext) - 1] + "." + ext
        else:
            name = name[:max_length]
    return name


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write to a temp file in the same directory, then rename over the target.

    ``os.replace`` is atomic on the same filesystem, so a crash mid-write never
    leaves a half-written index or metadata file behind.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_bytes(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
