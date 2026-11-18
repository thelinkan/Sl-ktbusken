"""Merge_Journal and backup manifest (Requirements 27.14, 27.15, 27.25, 7.12). Qt-free.

Both documents carry their own SHA-256 over the canonical JSON of everything
except the checksum key. Reading never raises for bad content: it returns a
result with state VALID / DAMAGED / ABSENT / UNREADABLE (journal; UNREADABLE
only for I/O errors that persist after retries) or VALID / UNUSABLE /
ABSENT (manifest), so recovery can classify from read-only inspection. A
leftover ``<journal>.tmp`` is never read and never counts as a journal.

All I/O goes through the ``CommitFs`` protocol.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from slaktbusken.services.commit import fs_ops
from slaktbusken.services.commit.fs_ops import CommitFs
from slaktbusken.services.commit.preflight import journal_path_for, lock_path_for

__all__ = [
    "SCHEMA",
    "MANIFEST_NAME",
    "JournalState",
    "ManifestState",
    "JournalTarget",
    "MergeJournal",
    "JournalReadResult",
    "ManifestFile",
    "BackupManifest",
    "ManifestReadResult",
    "journal_path_for",
    "lock_path_for",
    "journal_tmp_path_for",
    "backup_dir_for",
    "manifest_path_for",
    "temp_path_for",
    "sha256_hex",
    "write_journal",
    "read_journal",
    "write_manifest",
    "read_manifest",
]

SCHEMA = 1
MANIFEST_NAME = "manifest.json"

# Indirection so tests can run the retry loop without waiting.
_sleep = time.sleep


class JournalState(str, Enum):
    VALID = "VALID"
    DAMAGED = "DAMAGED"
    ABSENT = "ABSENT"
    # Present or not, but reading failed with an I/O error that persisted after
    # retries. Says nothing about the content; recovery refuses (R11).
    UNREADABLE = "UNREADABLE"


class ManifestState(str, Enum):
    VALID = "VALID"
    UNUSABLE = "UNUSABLE"
    ABSENT = "ABSENT"


# --------------------------------------------------------------------------
# Paths


def journal_tmp_path_for(project_file: Path) -> Path:
    """``<journal>.tmp``: written first, then replaced onto the journal name."""
    jp = journal_path_for(project_file)
    return jp.with_name(jp.name + ".tmp")


def backup_dir_for(directory: Path, txid: str) -> Path:
    return Path(directory) / f".merge-backup-{txid}"


def manifest_path_for(directory: Path, txid: str) -> Path:
    return backup_dir_for(directory, txid) / MANIFEST_NAME


def temp_path_for(target: Path, txid: str) -> Path:
    """``<target>.<txid>.new`` in the same directory as the target."""
    return target.with_name(f"{target.name}.{txid}.new")


# --------------------------------------------------------------------------
# Checksums


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(doc: dict[str, Any]) -> bytes:
    return json.dumps(
        doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _with_checksum(body: dict[str, Any], key: str) -> dict[str, Any]:
    doc = dict(body)
    doc.pop(key, None)
    doc[key] = sha256_hex(_canonical(doc))
    return doc


def _checksum_ok(doc: dict[str, Any], key: str) -> bool:
    claimed = doc.get(key)
    if not isinstance(claimed, str):
        return False
    rest = {k: v for k, v in doc.items() if k != key}
    return sha256_hex(_canonical(rest)) == claimed


def _serialize(doc: dict[str, Any]) -> bytes:
    return (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


# --------------------------------------------------------------------------
# Field validation helpers (raise ValueError on any shape problem)


def _req(d: dict[str, Any], key: str, typ: type | tuple[type, ...]) -> Any:
    if key not in d:
        raise ValueError(f"saknar fältet {key}")
    v = d[key]
    # bool is an int subclass; reject it where a number is expected
    if isinstance(v, bool) and bool not in (typ if isinstance(typ, tuple) else (typ,)):
        raise ValueError(f"fältet {key} har fel typ")
    if not isinstance(v, typ):
        raise ValueError(f"fältet {key} har fel typ")
    return v


def _req_sha(d: dict[str, Any], key: str) -> str:
    v = _req(d, key, str)
    if len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
        raise ValueError(f"fältet {key} är ingen SHA-256")
    return v


def _req_size(d: dict[str, Any], key: str) -> int:
    v = _req(d, key, int)
    if v < 0:
        raise ValueError(f"fältet {key} är negativt")
    return v


# --------------------------------------------------------------------------
# Merge_Journal


@dataclass(frozen=True)
class JournalTarget:
    role: str
    target: str  # relative to the project directory
    tmp: str
    backup: str
    existed_before: bool
    old_sha256: str
    old_size: int
    new_sha256: str
    new_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "target": self.target,
            "tmp": self.tmp,
            "backup": self.backup,
            "existed_before": self.existed_before,
            "old_sha256": self.old_sha256,
            "old_size": self.old_size,
            "new_sha256": self.new_sha256,
            "new_size": self.new_size,
        }

    @staticmethod
    def from_dict(d: Any) -> "JournalTarget":
        if not isinstance(d, dict):
            raise ValueError("målet är inget objekt")
        return JournalTarget(
            role=_req(d, "role", str),
            target=_req(d, "target", str),
            tmp=_req(d, "tmp", str),
            backup=_req(d, "backup", str),
            existed_before=_req(d, "existed_before", bool),
            old_sha256=_req_sha(d, "old_sha256"),
            old_size=_req_size(d, "old_size"),
            new_sha256=_req_sha(d, "new_sha256"),
            new_size=_req_size(d, "new_size"),
        )


@dataclass(frozen=True)
class MergeJournal:
    txid: str
    created: str
    app_version: str
    targets: tuple[JournalTarget, ...]
    dirty_before: bool = False  # audit only; always False
    revision_before: int = 0
    schema: int = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        """Document including ``journal_sha256``."""
        body = {
            "schema": self.schema,
            "txid": self.txid,
            "created": self.created,
            "app_version": self.app_version,
            "dirty_before": self.dirty_before,
            "revision_before": self.revision_before,
            "targets": [t.to_dict() for t in self.targets],
        }
        return _with_checksum(body, "journal_sha256")

    def to_bytes(self) -> bytes:
        return _serialize(self.to_dict())

    @staticmethod
    def from_dict(doc: Any) -> "MergeJournal":
        """Parse a checksum-verified document; ValueError on any problem."""
        if not isinstance(doc, dict):
            raise ValueError("journalen är inget objekt")
        if not _checksum_ok(doc, "journal_sha256"):
            raise ValueError("kontrollsumman stämmer inte")
        if _req(doc, "schema", int) != SCHEMA:
            raise ValueError("okänt schema")
        targets = _req(doc, "targets", list)
        return MergeJournal(
            schema=SCHEMA,
            txid=_req(doc, "txid", str),
            created=_req(doc, "created", str),
            app_version=_req(doc, "app_version", str),
            dirty_before=_req(doc, "dirty_before", bool),
            revision_before=_req(doc, "revision_before", int),
            targets=tuple(JournalTarget.from_dict(t) for t in targets),
        )


@dataclass(frozen=True)
class JournalReadResult:
    state: JournalState
    journal: MergeJournal | None = None
    reason: str = ""

    @property
    def is_valid(self) -> bool:
        return self.state is JournalState.VALID


def write_journal(fs: CommitFs, project_file: Path, journal: MergeJournal) -> None:
    """Step (b): write ``<journal>.tmp`` durably, then replace it onto the journal.

    The journal appears atomically. The directory is fsynced afterwards
    (flush barrier, step (c)); a leftover ``.tmp`` from a crash in between is
    not a journal.
    """
    final = journal_path_for(project_file)
    tmp = journal_tmp_path_for(project_file)
    fs.write_file_durable(tmp, journal.to_bytes())
    fs.replace(tmp, final)
    fs.fsync_dir(final.parent)


def read_journal(fs: CommitFs, project_file: Path) -> JournalReadResult:
    """Read-only classification of the journal beside ``project_file``."""
    path = journal_path_for(project_file)
    # An I/O error is not evidence about the content: retry (same delays as the
    # commit's retry policy), then report UNREADABLE instead of guessing DAMAGED.
    delays = tuple(fs_ops.RETRY_DELAYS)
    last_error = ""
    raw: bytes | None = None
    for attempt in range(len(delays) + 1):
        try:
            if not fs.exists(path):
                return JournalReadResult(JournalState.ABSENT)
            raw = fs.read_bytes(path)
            break
        except OSError as exc:
            last_error = str(exc)
            if attempt < len(delays):
                _sleep(delays[attempt])
    if raw is None:
        return JournalReadResult(JournalState.UNREADABLE, reason=f"kan inte läsas: {last_error}")
    try:
        doc = json.loads(raw.decode("utf-8"))
        return JournalReadResult(JournalState.VALID, MergeJournal.from_dict(doc))
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        return JournalReadResult(JournalState.DAMAGED, reason=str(exc))


# --------------------------------------------------------------------------
# Backup manifest


@dataclass(frozen=True)
class ManifestFile:
    name: str  # file name inside the backup directory
    restore_to: str  # relative to the project directory
    sha256: str
    size: int


@dataclass(frozen=True)
class BackupManifest:
    txid: str
    files: tuple[ManifestFile, ...]
    # ``restore_to`` paths of targets that did not exist before the merge
    absent_before: tuple[str, ...] = field(default_factory=tuple)
    schema: int = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        body = {
            "schema": self.schema,
            "txid": self.txid,
            "files": [
                {"name": f.name, "restore_to": f.restore_to, "sha256": f.sha256, "size": f.size}
                for f in self.files
            ],
            "absent_before": list(self.absent_before),
        }
        return _with_checksum(body, "manifest_sha256")

    def to_bytes(self) -> bytes:
        return _serialize(self.to_dict())

    @staticmethod
    def from_dict(doc: Any) -> "BackupManifest":
        if not isinstance(doc, dict):
            raise ValueError("förteckningen är inget objekt")
        if not _checksum_ok(doc, "manifest_sha256"):
            raise ValueError("kontrollsumman stämmer inte")
        if _req(doc, "schema", int) != SCHEMA:
            raise ValueError("okänt schema")
        files: list[ManifestFile] = []
        for f in _req(doc, "files", list):
            if not isinstance(f, dict):
                raise ValueError("filposten är inget objekt")
            files.append(
                ManifestFile(
                    name=_req(f, "name", str),
                    restore_to=_req(f, "restore_to", str),
                    sha256=_req_sha(f, "sha256"),
                    size=_req_size(f, "size"),
                )
            )
        absent = _req(doc, "absent_before", list)
        if not all(isinstance(a, str) for a in absent):
            raise ValueError("absent_before innehåller andra värden än text")
        restore = [f.restore_to for f in files] + list(absent)
        if len(set(restore)) != len(restore):
            raise ValueError("samma mål förekommer flera gånger")
        return BackupManifest(
            schema=SCHEMA,
            txid=_req(doc, "txid", str),
            files=tuple(files),
            absent_before=tuple(absent),
        )


@dataclass(frozen=True)
class ManifestReadResult:
    state: ManifestState
    manifest: BackupManifest | None = None
    reason: str = ""

    @property
    def is_valid(self) -> bool:
        return self.state is ManifestState.VALID


def write_manifest(fs: CommitFs, directory: Path, manifest: BackupManifest) -> Path:
    """P2: write ``manifest.json`` into the backup directory, fsynced.

    The backup directory must exist already (the caller created it and copied
    the files). Returns the manifest path.
    """
    path = manifest_path_for(directory, manifest.txid)
    fs.write_file_durable(path, manifest.to_bytes())
    fs.fsync_dir(path.parent)
    return path


def read_manifest(fs: CommitFs, directory: Path, txid: str) -> ManifestReadResult:
    """Read-only classification of the manifest of backup ``txid``.

    A manifest whose recorded txid differs from the directory's is UNUSABLE.
    """
    path = manifest_path_for(directory, txid)
    try:
        present = fs.exists(path)
    except OSError as exc:
        return ManifestReadResult(ManifestState.UNUSABLE, reason=f"kan inte kontrolleras: {exc}")
    if not present:
        return ManifestReadResult(ManifestState.ABSENT)
    try:
        raw = fs.read_bytes(path)
    except OSError as exc:
        return ManifestReadResult(ManifestState.UNUSABLE, reason=f"kan inte läsas: {exc}")
    try:
        manifest = BackupManifest.from_dict(json.loads(raw.decode("utf-8")))
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        return ManifestReadResult(ManifestState.UNUSABLE, reason=str(exc))
    if manifest.txid != txid:
        return ManifestReadResult(ManifestState.UNUSABLE, reason="txid stämmer inte med mappen")
    return ManifestReadResult(ManifestState.VALID, manifest)
