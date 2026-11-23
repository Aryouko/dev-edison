"""Projects shown on the home page and in the "Projets récents" menu."""

import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QFile, QSettings

from edison.config import PROJECT_EXTENSION, projects_dir
from edison.model.project import ProjectFileError, read_project_file

MAX_RECENT = 8
_RECENT_KEY = "recent_projects"


@dataclass
class ProjectSummary:
    """What the home page displays for a project."""

    path: str
    name: str
    saved_at: float
    thumbnail: str | None


def recent_projects() -> list[str]:
    """Return the recently opened project files that still exist."""
    value = QSettings().value(_RECENT_KEY, [])
    paths = [value] if isinstance(value, str) else list(value or [])
    return [path for path in paths if Path(path).exists()]


def add_recent_project(path: str | Path) -> None:
    """Put a project at the top of the recent list."""
    path = str(Path(path).resolve())
    paths = [path] + [p for p in recent_projects() if p != path]
    QSettings().setValue(_RECENT_KEY, paths[:MAX_RECENT])


def list_projects() -> list[ProjectSummary]:
    """Return the projects of the default folder and the recent ones, most recent first."""
    paths = {str(p.resolve()) for p in projects_dir().glob(f"*{PROJECT_EXTENSION}")}
    paths.update(recent_projects())
    summaries = []
    for path in paths:
        try:
            data = read_project_file(path)
        except ProjectFileError:
            continue
        summaries.append(ProjectSummary(path, data.get("name", Path(path).stem),
                                        data.get("saved_at") or Path(path).stat().st_mtime, data.get("thumbnail")))
    return sorted(summaries, key=lambda summary: summary.saved_at, reverse=True)


def unique_project_path(name: str) -> Path:
    """Return a free file name in the default folder for a new project."""
    safe = re.sub(r'[<>:"/\\|?*]+', "_", name).strip(" .") or "Projet"
    path = projects_dir() / f"{safe}{PROJECT_EXTENSION}"
    number = 2
    while path.exists():
        path = projects_dir() / f"{safe} ({number}){PROJECT_EXTENSION}"
        number += 1
    return path


def delete_project(path: str | Path) -> None:
    """Move a project file to the recycle bin and forget it (the imported media are kept).

    Raises
    ------
    OSError
        If the file cannot be moved.
    """
    path = str(Path(path).resolve())
    if Path(path).exists() and not QFile.moveToTrash(path):
        raise OSError("Le fichier n'a pas pu être placé dans la corbeille.")
    QSettings().setValue(_RECENT_KEY, [p for p in recent_projects() if p != path])
