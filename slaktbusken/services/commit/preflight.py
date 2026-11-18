"""Pre-flight checks before a merge commit (Requirement 27.20). Qt-free.

``Preflight.check`` returns Swedish refusals that name the file. It never
leaves anything behind: probe files are removed, and nothing else is touched.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import Callable, Iterable, NamedTuple

_MIB = 1024 * 1024
PROBE_A = ".sbk-probe-a"
PROBE_B = ".sbk-probe-b"


class DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


def lock_path_for(project_file: Path) -> Path:
    return project_file.with_name(project_file.name + ".merge.lock")


def journal_path_for(project_file: Path) -> Path:
    return project_file.with_name(project_file.name + ".merge-journal.json")


class Preflight:
    @staticmethod
    def check(
        targets: Iterable[Path],
        directory: Path,
        needed_bytes: int = 0,
        *,
        project_file: Path | None = None,
        disk_usage: Callable[[str], DiskUsage] = shutil.disk_usage,
    ) -> list[str]:
        """Return Swedish refusals (empty list: all clear).

        ``needed_bytes`` is the size of the new contents to be written.
        ``project_file`` enables the lock and pending-journal checks.
        """
        refusals: list[str] = []
        directory = Path(directory)
        target_list = [Path(t) for t in targets]

        for target in target_list:
            refusals.extend(Preflight._check_target(target))

        refusals.extend(Preflight._check_directory(directory))

        if project_file is not None:
            project_file = Path(project_file)
            lock = lock_path_for(project_file)
            if lock.exists():
                refusals.append(
                    f"Låsfilen {lock.name} finns redan. En annan sammanslagning "
                    f"pågår eller har avbrutits."
                )
            journal = journal_path_for(project_file)
            if journal.exists():
                refusals.append(
                    f"Journalfilen {journal.name} finns redan. En tidigare "
                    f"sammanslagning måste återställas först."
                )

        refusals.extend(
            Preflight._check_space(target_list, directory, needed_bytes, disk_usage)
        )
        return refusals

    @staticmethod
    def _check_target(path: Path) -> list[str]:
        name = path.name
        if not path.exists():
            return []  # absent target: directory probe covers creation
        if not path.is_file():
            return [f"{name} är inte en vanlig fil."]
        try:
            mode = os.stat(path).st_mode
        except OSError:
            return [f"Filen {name} går inte att läsa."]
        if not mode & stat.S_IWRITE:
            return [f"Filen {name} är skrivskyddad."]
        try:
            with open(path, "r+b"):
                pass
        except PermissionError:
            return [f"Filen {name} används av ett annat program."]
        except OSError:
            return [f"Filen {name} går inte att skriva till."]
        return []

    @staticmethod
    def _check_directory(directory: Path) -> list[str]:
        name = directory.name or str(directory)
        a, b = directory / PROBE_A, directory / PROBE_B
        msg = f"Mappen {name} tillåter inte att temporära filer skapas."
        try:
            a.write_bytes(b"a")
            b.write_bytes(b"b")
            os.replace(a, b)
            os.remove(b)
            return []
        except OSError:
            return [msg]
        finally:
            for p in (a, b):
                try:
                    os.remove(p)
                except OSError:
                    pass

    @staticmethod
    def _check_space(
        targets: list[Path],
        directory: Path,
        needed_bytes: int,
        disk_usage: Callable[[str], DiskUsage],
    ) -> list[str]:
        existing = 0
        for t in targets:
            try:
                existing += t.stat().st_size
            except OSError:
                pass
        required = 2 * (existing + max(needed_bytes, 0)) + _MIB
        try:
            free = disk_usage(str(directory)).free
        except OSError:
            return [f"Det går inte att kontrollera ledigt utrymme i mappen {directory.name}."]
        if free < required:
            return [
                f"Det finns inte tillräckligt med ledigt diskutrymme för "
                f"{', '.join(t.name for t in targets) or directory.name} "
                f"(behöver ungefär {required // _MIB + 1} MiB)."
            ]
        return []
