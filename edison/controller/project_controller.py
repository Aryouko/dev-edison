"""Project controller: open project, media library, selection, editing actions.

Signals (Observer pattern of the CDC): the views connect to them and refresh.
* ``project_changed``  -> the timeline content changed (repaint the timeline, render again);
* ``media_changed``    -> the library changed (rebuild the "Import" tab);
* ``selection_changed``-> the selection changed;
* ``message``          -> short text shown at the bottom of the window.

Every timeline change goes through :meth:`ProjectController._edit`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoStack

from edison.media.audio import AudioStore
from edison.model import editing
from edison.model.editing import EditError
from edison.model.project import Project

logger = logging.getLogger(__name__)


class ProjectController(QObject):
    """Open project, media library, selection and editing actions."""

    project_opened = Signal()
    project_closed = Signal()
    project_renamed = Signal()
    project_changed = Signal()
    media_changed = Signal()
    selection_changed = Signal()
    dirty_changed = Signal()
    import_errors = Signal(list)  # list of (file name, reason): shown with the accepted formats
    message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.path: Path | None = None  # .edison file of the project (None until saved)
        self.undo_stack = QUndoStack(self)  # TODO(S5): filled by _edit (Undo/Redo)
        self.undo_stack.cleanChanged.connect(lambda _clean: self.dirty_changed.emit())
        self.audio_store = AudioStore()
        self.previews: dict[str, np.ndarray] = {}  # media id -> thumbnail shown in the "Import" tab
        self.selected_clips: set[str] = set()
        self.selected_junction: tuple[str, str, str] | None = None  # (track id, left clip id, right clip id)

    # ================================================================ helpers
    def todo(self, feature: str, sprint: str) -> None:
        """Tell the user that a feature is not developed yet.

        Remove the call when the feature is implemented. ``git grep "todo("`` lists them.
        """
        logger.info("Not implemented yet (%s): %s", sprint, feature)
        self.message.emit(f"« {feature} » : à implémenter (sprint {sprint}).")

    @property
    def is_dirty(self) -> bool:
        """True if the project has unsaved changes (asks for confirmation before closing)."""
        # TODO(S6): also True after an import or a rename (changes outside the undo history).
        return self.project is not None and not self.undo_stack.isClean()

    # ========================================================= project files
    def create_project(self, name: str) -> None:
        """Create a project and open it (home page card "+").

        TODO(S6): give it a file in ``config.projects_dir()`` (see ``recent.unique_project_path``)
        and save it right away, so that "Enregistrer" always knows where to write.
        """
        self.close_project()
        self.project = Project.create(name.strip())
        self.project_opened.emit()
        self.project_changed.emit()
        self.media_changed.emit()

    def open_project(self, path: str | Path) -> None:
        """Open a ``.edison`` file ("Ouvrir un projet", card of the home page, "Projets récents").

        TODO(S6): ``load_project(path)`` (raises ProjectFileError), then the same steps as
        :meth:`create_project`; decode again the media of the project in the background.
        """
        self.todo("Ouvrir un projet", "S6")

    def save(self, path: str | Path | None = None) -> None:
        """Save the project ("Enregistrer", or "Enregistrer sous" with ``path``).

        TODO(S6): ``save_project(self.project, path or self.path)``, then
        ``self.undo_stack.setClean()`` (no more unsaved changes) and ``add_recent_project``.
        """
        self.todo("Enregistrer le projet", "S6")

    def rename(self, name: str) -> None:
        """Rename the project ("Renommer le projet", Ctrl+R).

        TODO(S3): change ``self.project.name`` and emit ``project_renamed`` (the header shows the name).
        """
        self.todo("Renommer le projet", "S3")

    def close_project(self) -> None:
        """Close the current project (without saving)."""
        if self.project is None:
            return
        self.project = self.path = None
        self.undo_stack.clear()
        self.previews.clear()
        self.selected_clips.clear()
        self.selected_junction = None
        # TODO(S4): self.audio_store.clear()
        self.project_closed.emit()
        self.dirty_changed.emit()

    # ========================================================= media library
    def import_files(self, paths: list[str]) -> None:
        """Import files into the library ("+" tile, or files dropped from the explorer).

        TODO(S2) "Import fonctionnel":
            * refused extension (``probe.is_supported``) -> add ``(name, reason)`` to a list and
              emit ``import_errors`` at the end: the "Import" tab shows them with the accepted formats;
            * otherwise, in a worker thread (``QThreadPool`` + ``QRunnable``, the interface must not
              freeze): ``probe_media(path)``, the thumbnail (``video_thumbnail``) and, later, the
              audio decoding (``audio_store.load``, S4);
            * back in the main thread (connect the signals of the task to methods of this class):
              ``self.project.media.append(media)``, ``self.previews[media.id] = thumbnail``,
              then emit ``media_changed``.
        """
        self.todo("Import des médias", "S2")

    def remove_media(self, media_id: str) -> None:
        """Remove a media from the library (refused if a clip of the timeline uses it)."""
        self.todo("Retirer un média", "S3")

    # ================================================================ editing
    def _edit(self, text: str, operation, *args):
        """Run an editing function of :mod:`edison.model.editing` on the project.

        Parameters
        ----------
        text : str
            Name of the action (will be shown in the tooltip of the "Annuler" button).
        operation : callable
            Editing function taking the project first.

        Returns
        -------
        object
            Result of ``operation``, or None if the edit was refused.

        TODO(S5) "Undo/Redo: Command pattern via QUndoStack": store
        ``before`` = a copy of the tracks before the operation and ``after`` = after it, then
        ``self.undo_stack.push(command)`` with a ``QUndoCommand`` whose ``undo()`` restores
        ``before`` and ``redo()`` restores ``after`` (and emits ``project_changed``).
        """
        if self.project is None:
            return None
        try:
            result = operation(self.project, *args)
        except EditError as error:  # refused edit: explain why
            self.message.emit(str(error))
            return None
        except NotImplementedError as error:  # function of editing.py still to write
            self.message.emit(f"À implémenter : {error}")
            return None
        self.project_changed.emit()
        return result

    def add_media_clip(self, media_id: str, start: float, track_id: str | None = None) -> None:
        """Place a media on the timeline (drop from the "Import" tab, double-click on a tile)."""
        media = self.project.get_media(media_id) if self.project else None
        if media is not None:
            self._edit("Ajouter un clip", editing.add_media, media, start, track_id)

    def move_clips(self, clip_ids, delta: float, target_track_id: str | None = None) -> None:
        """Move clips (drag and drop in the timeline)."""
        self._edit("Déplacer", editing.move_clips, set(clip_ids), delta, target_track_id)

    def trim_clip(self, clip_id: str, edge: str, delta: float) -> None:
        """Move an edge of a clip."""
        self._edit("Rogner", editing.trim_clip, clip_id, edge, delta)

    def cut(self, time: float) -> None:
        """Tool "Cut": cut the selected clips at the cursor position."""
        self._edit("Couper", editing.cut_clips, set(self.selected_clips), time)

    def delete_selection(self) -> None:
        """Tool "Poubelle": delete the selected clips."""
        if self.selected_clips:
            self._edit("Supprimer", editing.delete_clips, set(self.selected_clips))
            self.clear_selection()

    def merge_selected_junction(self) -> None:
        """Tool "Fusionner": merge the two clips on each side of the selected junction."""
        if self.selected_junction is None:
            self.message.emit("Cliquez d'abord sur la jonction entre deux clips collés.")
            return
        self._edit("Fusionner", editing.merge_clips, *self.selected_junction)

    def unlink_clip(self, clip_id: str) -> None:
        """Menu "Séparer la piste audio et vidéo"."""
        self._edit("Séparer l'audio et la vidéo", editing.unlink_clips, clip_id)

    def duplicate_clips(self, clip_ids) -> None:
        """Menu "Dupliquer"."""
        self._edit("Dupliquer", editing.duplicate_clips, set(clip_ids))

    def set_volume(self, clip_ids, volume: float) -> None:
        """Menu "Volume"."""
        self._edit("Volume", editing.set_volume, set(clip_ids), volume)

    def set_fades(self, clip_id: str, fade_in: float, fade_out: float) -> None:
        """Menu "Fondu entrant / sortant"."""
        self._edit("Fondu", editing.set_fades, clip_id, fade_in, fade_out)

    def add_effect(self, clip_ids, effect_type: str, params: dict) -> None:
        """Button "Appliquer" of the effects pop-up."""
        self._edit("Ajouter un effet", editing.add_effect, set(clip_ids), effect_type, params)

    # ============================================================== selection
    def select_clips(self, clip_ids, toggle: bool = False) -> None:
        """Select clips (``toggle``: Ctrl + click adds or removes them).

        TODO(S3): also select the linked clips (same ``link_id``), they move together.
        """
        clip_ids = set(clip_ids)
        self.selected_clips = self.selected_clips ^ clip_ids if toggle else clip_ids
        self.selected_junction = None
        self.selection_changed.emit()

    def select_junction(self, track_id: str, left_id: str, right_id: str) -> None:
        """Select the junction between two touching clips (needed by the tool "Fusionner")."""
        self.selected_clips = set()
        self.selected_junction = (track_id, left_id, right_id)
        self.selection_changed.emit()

    def clear_selection(self) -> None:
        """Deselect everything (click on an empty place)."""
        if self.selected_clips or self.selected_junction:
            self.selected_clips = set()
            self.selected_junction = None
            self.selection_changed.emit()
