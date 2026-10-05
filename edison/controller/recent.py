"""Projects shown on the home page and in "Fichier > Projets récents" (sprint S6).

Suggested storage: ``QSettings().value("recent_projects", [])`` (a list of paths kept by Qt
in the registry on Windows), plus every ``.edison`` file of ``config.projects_dir()``.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from edison.config import PROJECT_EXTENSION, projects_dir


@dataclass
class ProjectSummary:
    """What the home page displays for a project (one card)."""

    path: str
    name: str
    saved_at: float  # timestamp, shown as "Modifié le ..."
    thumbnail: str | None  # base64 JPEG saved in the project file


def recent_projects() -> list[str]:
    """Return the recently opened project files that still exist.

    TODO(S6)
    """
    return []


def add_recent_project(path: str | Path) -> None:
    """Put a project at the top of the recent list (at most 8).

    TODO(S6)
    """


def list_projects() -> list[ProjectSummary]:
    """Return the projects for the home page, most recent first.

    TODO(S6): files of ``projects_dir()`` + ``recent_projects()``; read the name, the date
    and the thumbnail of each file (``json``), ignore the unreadable ones.
    """
    return []


def unique_project_path(name: str) -> Path:
    """Return a free file name in the default folder for a new project ("Mon projet (2).edison")."""
    safe = re.sub(r'[<>:"/\\|?*]+', "_", name).strip(" .") or "Projet"
    path = projects_dir() / f"{safe}{PROJECT_EXTENSION}"
    number = 2
    while path.exists():
        path = projects_dir() / f"{safe} ({number}){PROJECT_EXTENSION}"
        number += 1
    return path
