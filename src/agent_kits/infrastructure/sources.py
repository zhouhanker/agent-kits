"""Untrusted source inspection and quarantine operations."""

from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from agent_kits.domain.errors import PolicyError, ValidationError
from agent_kits.infrastructure.paths import user_state_root

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_BUNDLE_FILES = 256
MAX_BUNDLE_UNCOMPRESSED_BYTES = 16 * 1024 * 1024


class _SafeRedirectHandler(HTTPRedirectHandler):
    """Permit only a small number of HTTPS-to-HTTPS redirects."""

    def __init__(self) -> None:
        super().__init__()
        self.redirects = 0

    def redirect_request(self, req, newurl, code, msg, headers, newdata):  # type: ignore[no-untyped-def]
        self.redirects += 1
        if self.redirects > 3 or not newurl.startswith("https://"):
            raise PolicyError("Source redirects must remain HTTPS and stay within three hops")
        return super().redirect_request(req, newurl, code, msg, headers, newdata)


@dataclass(frozen=True)
class SourceInspection:
    """Stable, non-executable facts about one source."""

    source: str
    source_type: str
    size_bytes: int
    sha256: str
    content_type: str | None
    markdown: bool
    zip_safe: bool | None


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_local(path: Path, max_bytes: int) -> tuple[bytes, str | None]:
    if not path.is_file() or path.is_symlink():
        raise PolicyError(f"Source must be a regular, non-symlink file: {path}")
    if path.stat().st_size > max_bytes:
        raise PolicyError(f"Source exceeds configured size limit ({max_bytes} bytes)")
    return path.read_bytes(), None


def _read_remote(url: str, max_bytes: int) -> tuple[bytes, str | None]:
    if not url.startswith("https://"):
        raise PolicyError("Remote sources must use HTTPS")
    request = Request(url, headers={"User-Agent": "agent-kits-source-inspector/0.1"})
    try:
        opener = build_opener(_SafeRedirectHandler())
        with opener.open(request, timeout=10) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise PolicyError(f"Source exceeds configured size limit ({max_bytes} bytes)")
            content = response.read(max_bytes + 1)
            content_type = response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise PolicyError(f"Could not fetch HTTPS source: {error}") from error
    if len(content) > max_bytes:
        raise PolicyError(f"Source exceeds configured size limit ({max_bytes} bytes)")
    return content, content_type


def read_source(source: str, max_bytes: int = MAX_SOURCE_BYTES) -> tuple[bytes, str | None, str]:
    """Read a local file or HTTPS URL under size and protocol policy."""

    if source.startswith(("http://", "https://")):
        content, content_type = _read_remote(source, max_bytes)
        return content, content_type, "https"
    path = Path(source).expanduser()
    content, content_type = _read_local(path, max_bytes)
    return content, content_type, "file"


def _zip_safety(content: bytes) -> bool:
    if not zipfile.is_zipfile(__import__("io").BytesIO(content)):
        return False
    total = 0
    with zipfile.ZipFile(__import__("io").BytesIO(content)) as archive:
        members = archive.infolist()
        if len(members) > MAX_BUNDLE_FILES:
            raise PolicyError(f"Bundle contains more than {MAX_BUNDLE_FILES} files")
        for member in members:
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
                raise PolicyError(f"Bundle contains an unsafe path: {member.filename}")
            if member.filename.endswith("/"):
                continue
            mode = (member.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise PolicyError(f"Bundle contains a symbolic link: {member.filename}")
            total += member.file_size
            if total > MAX_BUNDLE_UNCOMPRESSED_BYTES:
                raise PolicyError("Bundle exceeds total uncompressed size limit")
    return True


def _inspection(source: str, content: bytes, content_type: str | None, source_type: str) -> SourceInspection:
    """Derive stable inspection facts from bytes already accepted by source policy."""

    suffix = Path(source.split("?", 1)[0]).suffix.lower()
    markdown = suffix in {".md", ".markdown"} or content.lstrip().startswith((b"# ", b"## "))
    zip_safe: bool | None = None
    if suffix in {".zip", ".whl"} or content[:4] == b"PK\x03\x04":
        zip_safe = _zip_safety(content)
    return SourceInspection(source, source_type, len(content), _digest(content), content_type, markdown, zip_safe)


def read_inspected_source(source: str, max_bytes: int = MAX_SOURCE_BYTES) -> tuple[bytes, SourceInspection]:
    """Read and inspect exactly one source version to avoid source/digest races."""

    content, content_type, source_type = read_source(source, max_bytes)
    return content, _inspection(source, content, content_type, source_type)


def inspect_source(source: str, max_bytes: int = MAX_SOURCE_BYTES) -> SourceInspection:
    """Inspect source bytes without executing or importing them."""

    _, inspection = read_inspected_source(source, max_bytes)
    return inspection


def quarantine_source(
    source: str,
    source_kind: str,
    state_root: Path | None = None,
    max_bytes: int = MAX_SOURCE_BYTES,
) -> dict[str, object]:
    """Store untrusted source bytes and metadata outside the catalog."""

    if source_kind not in {"document", "bundle"}:
        raise ValidationError("source kind must be document or bundle")
    content, content_type, source_type = read_source(source, max_bytes)
    digest = _digest(content)
    if source_kind == "bundle":
        if not _zip_safety(content):
            raise PolicyError("Bundle source must be a ZIP archive")
    suffix = ".md" if source_kind == "document" else ".zip"
    root = (state_root or user_state_root()) / "quarantine" / ("documents" if source_kind == "document" else "bundles") / digest
    root.mkdir(parents=True, exist_ok=True)
    payload_path = root / f"source{suffix}"
    payload_path.write_bytes(content)
    metadata = asdict(SourceInspection(source, source_type, len(content), digest, content_type, source_kind == "document", True if source_kind == "bundle" else None))
    metadata_path = root / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"directory": str(root), "payload": str(payload_path), "metadata": str(metadata_path), **metadata}
