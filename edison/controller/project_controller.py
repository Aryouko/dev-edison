
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
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QUndoStack

from edison.media.audio import AudioStore
from edison.media.probe import UnsupportedMediaError, is_supported, probe_media, video_thumbnail
from edison.model import editing
from edison.model.editing import EditError
from edison.model.project import Project

logger = logging.getLogger(__name__)


class _ImportSignals(QObject):
    """Signals of an import task (a QRunnable is not a QObject and cannot have signals)."""

    imported = Signal(int, object, object)  # batch number, Media, thumbnail (numpy array or None)
    failed = Signal(int, str, str)  # batch number, file name, reason
    finished = Signal(int, object)  # batch number, the task itself


class _ImportTask(QRunnable):
    """Analyse one file in a worker thread: ``probe_media`` then ``video_thumbnail``.

    The results go back to the main thread through the signals (queued connections).
    """

    def __init__(self, batch: int, path: str, audio_store: AudioStore | None = None):
        super().__init__()
        self.batch = batch
        self.path = path
        self.signals = _ImportSignals()
        self.audio_store = audio_store

    def run(self) -> None:
        name = Path(self.path).name
        try:
            media = probe_media(self.path)
            thumbnail = video_thumbnail(media)
            if media.has_audio:
                self.audio_store.load(media)
            # TODO(S4): self.audio_store.load(media) when the media has sound.
        except UnsupportedMediaError as error:
            self.signals.failed.emit(self.batch, name, str(error))
        except Exception:  # noqa: BLE001 - a worker thread must never crash the application
            logger.exception("Import failed: %s", self.path)
            self.signals.failed.emit(self.batch, name, "Erreur inattendue pendant l'analyse.")
        else:
            self.signals.imported.emit(self.batch, media, thumbnail)
        finally:
            self.signals.finished.emit(self.batch, self)



class _ImportBatch:
    """Files given to one call of ``import_files``: errors are shown together at the end."""

    def __init__(self, project: Project, remaining: int, errors: list):
        self.project = project
        self.remaining = remaining
        self.errors = errors
        self.imported = 0


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
        self._thread_pool = QThreadPool.globalInstance()
        self._import_batches: dict[int, _ImportBatch] = {}
        self._import_tasks: set[_ImportTask] = set()  # keeps the tasks (and their signals) alive
        self._next_batch = 0

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

        Refused extensions are reported at once; the other files are analysed in worker
        threads (``QThreadPool``), so the interface does not freeze. Each result comes back in
        the main thread (:meth:`_on_media_imported`); the errors of the whole selection are
        shown together with ``import_errors`` when the last file is done.
        """
        if self.project is None or not paths:
            return
        errors = []
        accepted = []
        for path in paths:
            if is_supported(path):
                accepted.append(str(path))
            else:
                errors.append((Path(path).name, "Format non pris en charge."))
        if not accepted:
            self.import_errors.emit(errors)
            return

        batch = self._next_batch
        self._next_batch += 1
        self._import_batches[batch] = _ImportBatch(self.project, len(accepted), errors)
        self.message.emit(f"Import de {len(accepted)} fichier(s)...")
        for path in accepted:
            task = _ImportTask(batch, path, self.audio_store)
            task.setAutoDelete(False)  # Python keeps the task until ``finished``
            task.signals.imported.connect(self._on_media_imported)
            task.signals.failed.connect(self._on_import_failed)
            task.signals.finished.connect(self._on_import_task_finished)
            self._import_tasks.add(task)
            self._thread_pool.start(task)

    @property
    def is_importing(self) -> bool:
        """True while files are being analysed."""
        return bool(self._import_batches)

    @Slot(int, object, object)
    def _on_media_imported(self, batch: int, media, thumbnail) -> None:
        current = self._import_batches.get(batch)
        if current is None or current.project is not self.project:
            return  # the project was closed during the import
        self.project.media.append(media)
        if thumbnail is not None:
            self.previews[media.id] = thumbnail
        current.imported += 1
        self.media_changed.emit()

    @Slot(int, str, str)
    def _on_import_failed(self, batch: int, name: str, reason: str) -> None:
        current = self._import_batches.get(batch)
        if current is not None:
            current.errors.append((name, reason))

    @Slot(int, object)
    def _on_import_task_finished(self, batch: int, task) -> None:
        self._import_tasks.discard(task)
        current = self._import_batches.get(batch)
        if current is None:
            return
        current.remaining -= 1
        if current.remaining > 0:
            return
        del self._import_batches[batch]
        if current.project is not self.project:
            return
        if current.imported:
            self.message.emit(f"{current.imported} média(s) importé(s).")
        if current.errors:
            self.import_errors.emit(current.errors)

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
