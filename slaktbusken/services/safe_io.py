"""Safety guards for data that originates from a project file.

A ``.slakt`` project is user data and may be shared between people, so any URL
or file path it carries must be treated as untrusted. Two classes of risk this
module guards against:

* **Untrusted URL schemes.** A stored "direct link" opened with the OS handler
  (``QDesktopServices.openUrl``) acts on whatever scheme it is given — ``file:``,
  ``javascript:``, or an application-registered protocol — not just a web page.
  :func:`is_safe_external_url` restricts opening to an explicit allow-list of
  web/mail schemes.

* **Path traversal / escape.** A media or data file referenced by a project is
  resolved relative to the project folder. An absolute path or a ``..`` sequence
  stored in the project resolves *outside* that folder, so "open this photo"
  could touch or launch an arbitrary file on disk. :func:`resolve_within`
  resolves a candidate against a root and returns it only when it stays inside
  that root.

Both functions are pure (no Qt, no I/O beyond path resolution) and defensive:
they never raise on malformed input, they return a sentinel (``False`` /
``None``) instead, so callers can treat "unsafe" and "could not be determined"
identically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# Schemes we are willing to hand to the OS default handler for a stored link.
# Deliberately excludes ``file``, ``javascript``, ``data`` and any
# application-registered protocol: those can read local files or execute code
# rather than open a web page. Lower-cased for case-insensitive comparison.
_ALLOWED_URL_SCHEMES = frozenset({"http", "https", "mailto"})


def is_safe_external_url(url: Optional[str]) -> bool:
    """Return ``True`` when *url* is safe to open with the OS default handler.

    A URL is considered safe only when its scheme is one of ``http``,
    ``https`` or ``mailto`` (case-insensitive). Everything else — an empty or
    whitespace-only value, a scheme-less value (which the OS may interpret as a
    local path), ``file:``, ``javascript:``, ``data:``, or any custom protocol —
    is rejected. Parsing failures are treated as unsafe rather than raised.

    Args:
        url: The raw URL string from project data, or ``None``.

    Returns:
        ``True`` only for an allow-listed web/mail scheme; ``False`` otherwise.
    """
    if not url or not url.strip():
        return False
    try:
        scheme = urlparse(url.strip()).scheme.lower()
    except (ValueError, TypeError):
        return False
    return scheme in _ALLOWED_URL_SCHEMES


def resolve_within(root: Path, candidate: str) -> Optional[Path]:
    """Resolve *candidate* against *root* and return it only if it stays inside.

    ``candidate`` is a path from project data (typically a media or data file
    reference). It is joined onto ``root`` and fully resolved (following ``..``
    segments and, where present, symlinks). The resolved path is returned only
    when it is ``root`` itself or a descendant of ``root``; an absolute
    ``candidate`` or one that climbs out of ``root`` with ``..`` yields ``None``.

    This is a containment check, not an existence check: the returned path need
    not exist on disk (the caller decides what to do when it does not). Malformed
    input never raises — it returns ``None``.

    Args:
        root: The directory a project-referenced path must stay within
            (e.g. the project folder or its media sub-folder).
        candidate: The stored relative path to resolve.

    Returns:
        The resolved absolute :class:`~pathlib.Path` when contained in ``root``,
        otherwise ``None``.
    """
    if not candidate or not str(candidate).strip():
        return None
    try:
        root_resolved = Path(root).resolve()
        # ``root / candidate`` keeps an absolute ``candidate`` absolute (so an
        # absolute project path is caught by the containment test below rather
        # than silently accepted).
        combined = (root_resolved / candidate).resolve()
    except (ValueError, OSError, RuntimeError):
        return None

    if combined == root_resolved:
        return combined
    if root_resolved in combined.parents:
        return combined
    return None
