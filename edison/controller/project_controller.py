"""Project controller: owns the open project, the selection and the undo history.

Every timeline change goes through :meth:`ProjectController._edit`, which runs a
pure function of :mod:`edison.model.editing` and pushes an undoable command.
The views listen to the signals of this class (Observer pattern).
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QBuffer, QIODevice, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage, QUndoCommand, QUndoStack

from edison.config import WAVEFORM_RATE
from edison.controller.recent import add_recent_project, unique_project_path
from edison.media.audio import AudioStore, waveform_peaks
from edison.media.probe import UnsupportedMediaError, is_supported, probe_media, video_thumbnail
from edison.model import editing
from edison.model.editing import EditError
from edison.model.project import VIDEO, Media, Project, load_project, save_project
from edison.render.audio_effects import AudioEffectCache
from edison.render.renderer import MediaSources, render_frame
from edison.utils import fit_size

logger = logging.getLogger(__name__)

THUMBNAIL_BINS = 120  # waveform drawn on the library tile of an audio file


class _SnapshotCommand(QUndoCommand):
    """Undoable command storing the timeline before and after an edit."""

    def __init__(self, controller: ProjectController, text: str, before: dict, after: dict):
        super().__init__(text)
        self._controller = controller
        self._before = before
        self._after = after

    def undo(self):
        self._controller._restore(self._before)

    def redo(self):
        self._controller._restore(self._after)


class _ImportSignals(QObject):
    finished = Signal(object, object, object, object)  # task, media, preview, waveform
    failed = Signal(object, str)  # task, reason


class _ImportTask(QRunnable):
    """Background import: read the file, decode its audio, make its thumbnail."""

    def __init__(self, generation: int, path: str, media: Media | None, store: AudioStore):
        super().__init__()
        self.setAutoDelete(False)  # kept alive by the controller until its result is handled
        self.signals = _ImportSignals()
        self.generation = generation
        self.path = path
        self.reload = media is not None  # the media is already known when a saved project is reopened
        self._media = media
        self._store = store

    def run(self):
        try:
            media = self._media or probe_media(self.path)
            samples = self._store.load(media) if media.has_audio else None
            if media.kind == VIDEO:
                preview = video_thumbnail(media)
            else:
                preview = waveform_peaks(samples, THUMBNAIL_BINS)
            waveform = None
            if samples is not None:
                waveform = waveform_peaks(samples, max(1, int(media.duration * WAVEFORM_RATE)))
        except UnsupportedMediaError as error:
            self.signals.failed.emit(self, str(error))
            return
        except Exception as error:  # FFmpeg can fail in many ways on broken files
            logger.exception("Import of %s failed", self.path)
            self.signals.failed.emit(self, f"Fichier illisible ({error}).")
            return
        self.signals.finished.emit(self, media, preview, waveform)


class ProjectController(QObject):
    """Open project, media library, selection and editing actions."""

    project_opened = Signal()
    project_closed = Signal()
    project_renamed = Signal()
    project_changed = Signal()  # timeline content or media changed
    media_changed = Signal()  # library content or thumbnails changed
    selection_changed = Signal()
    dirty_changed = Signal()
    import_progress = Signal(int)  # number of imports in progress
    import_errors = Signal(list)  # list of (file name, reason)
    missing_media = Signal(list)  # names of files not found when opening
    message = Signal(str)  # short information for the user

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.path: Path | None = None
        self.last_saved: datetime | None = None
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(lambda _clean: self.dirty_changed.emit())
        self.audio_store = AudioStore()
        self.previews: dict[str, np.ndarray] = {}  # thumbnail (video) or waveform peaks (audio)
        self.waveforms: dict[str, np.ndarray] = {}  # WAVEFORM_RATE peaks per second of each media with sound
        self.audio_effects = AudioEffectCache(self.audio_store)
        self.missing: set[str] = set()
        self.selected_clips: set[str] = set()
        self.selected_junction: tuple[str, str, str] | None = None  # track, left clip, right clip
        self._extra_dirty = False  # changes outside the undo history (import, rename)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._tasks: set[_ImportTask] = set()
        self._generation = 0  # results of imports started for a previous project are ignored
        self._errors: list[tuple[str, str]] = []

    # ================================================================ state
    @property
    def is_dirty(self) -> bool:
        """True if the project has unsaved changes."""
        return self.project is not None and (self._extra_dirty or not self.undo_stack.isClean())

    @property
    def pending_imports(self) -> int:
        """Number of imports in progress."""
        return len(self._tasks)

    def _mark_dirty(self) -> None:
        self._extra_dirty = True
        self.dirty_changed.emit()

    # ======================================================== project files
    def create_project(self, name: str) -> None:
        """Create a project in the default folder and open it."""
        self._open(Project.create(name.strip()), unique_project_path(name))
        self.save()

    def open_project(self, path: str | Path) -> None:
        """Open a ``.edison`` file.

        Raises
        ------
        ProjectFileError
            If the file is not a valid project.
        """
        project = load_project(path)
        self._open(project, Path(path))
        self.last_saved = datetime.fromtimestamp(Path(path).stat().st_mtime)
        self.dirty_changed.emit()
        missing = [media.name for media in project.media if media.id in self.missing]
        if missing:
            self.missing_media.emit(missing)

    def _open(self, project: Project, path: Path) -> None:
        self.close_project()
        self.project, self.path = project, path
        for media in project.media:
            if os.path.exists(media.path):
                self._start_import(media.path, media)
            else:
                self.missing.add(media.id)
        add_recent_project(path)
        self.project_opened.emit()
        self.project_changed.emit()
        self.media_changed.emit()
        self.selection_changed.emit()

    def close_project(self) -> None:
        """Close the current project (without saving)."""
        if self.project is None:
            return
        self._generation += 1
        self.project = self.path = self.last_saved = None
        self.undo_stack.clear()
        self._extra_dirty = False
        self.audio_store.clear()
        self.audio_effects.clear()
        self.previews.clear()
        self.waveforms.clear()
        self.missing.clear()
        self.selected_clips.clear()
        self.selected_junction = None
        self._errors.clear()
        self.project_closed.emit()
        self.dirty_changed.emit()

    def save(self, path: str | Path | None = None) -> None:
        """Save the project (to ``path`` for "Enregistrer sous").

        Raises
        ------
        OSError
            If the file cannot be written.
        """
        target = Path(path) if path else self.path
        save_project(self.project, target, thumbnail=self._thumbnail())
        self.path = target
        self.last_saved = datetime.now()
        self._extra_dirty = False
        self.undo_stack.setClean()
        add_recent_project(target)
        self.dirty_changed.emit()

    def rename(self, name: str) -> None:
        """Rename the project."""
        name = name.strip()
        if self.project is None or not name or name == self.project.name:
            return
        self.project.name = name
        self._mark_dirty()
        self.project_renamed.emit()

    def _thumbnail(self) -> str | None:
        """Base64 JPEG of the first picture of the montage, shown on the home page."""
        video_clips = [clip for track in self.project.tracks_of(VIDEO) for clip in track.clips]
        if not video_clips:
            return None
        width, height = fit_size(self.project.width, self.project.height, 320, 180)
        sources = MediaSources()
        try:
            frame = render_frame(self.project, min(c.start for c in video_clips), width, height, sources)
        finally:
            sources.close()
        image = QImage(frame.data, width, height, 3 * width, QImage.Format.Format_RGB888)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "JPG", 80)
        return base64.b64encode(bytes(buffer.data())).decode("ascii")

    # ======================================================== media library
    def import_files(self, paths: list[str]) -> None:
        """Import files in the background. Refused files are reported with :attr:`import_errors`."""
        if self.project is None:
            return
        known = {os.path.normcase(media.path) for media in self.project.media}
        for path in paths:
            name = Path(path).name
            if not is_supported(path):
                self._errors.append((name, "Format non pris en charge."))
            elif os.path.normcase(str(Path(path).resolve())) in known:
                self.message.emit(f"« {name} » est déjà dans le projet.")
            else:
                self._start_import(path)
        self._report_errors()

    def _start_import(self, path: str, media: Media | None = None) -> None:
        task = _ImportTask(self._generation, path, media, self.audio_store)
        # Bound methods of this QObject: the slots run in the main thread (queued connection).
        task.signals.finished.connect(self._on_import_finished)
        task.signals.failed.connect(self._on_import_failed)
        self._tasks.add(task)
        self._pool.start(task)
        self.import_progress.emit(len(self._tasks))

    def _on_import_finished(self, task, media, preview, waveform) -> None:
        self._tasks.discard(task)
        self.import_progress.emit(len(self._tasks))
        if task.generation != self._generation:
            return
        if not task.reload:
            if media.kind == VIDEO and not any(m.kind == VIDEO for m in self.project.media):
                # The first video gives its size and frame rate to the project.
                self.project.width, self.project.height = media.width - media.width % 2, media.height - media.height % 2
                self.project.fps = media.fps or self.project.fps
            self.project.media.append(media)
            self._mark_dirty()
        self.previews[media.id] = preview
        if waveform is not None:
            self.waveforms[media.id] = waveform
        self.media_changed.emit()
        self.project_changed.emit()
        self._report_errors()

    def _on_import_failed(self, task, reason) -> None:
        self._tasks.discard(task)
        self.import_progress.emit(len(self._tasks))
        if task.generation == self._generation:
            self._errors.append((Path(task.path).name, reason))
            self._report_errors()

    def _report_errors(self) -> None:
        if self._errors and not self._tasks:
            errors, self._errors = self._errors, []
            self.import_errors.emit(errors)

    def remove_media(self, media_id: str) -> None:
        """Remove a media from the library (only if no clip uses it)."""
        if self.project is None:
            return
        if self.project.is_media_used(media_id):
            self.message.emit("Ce média est utilisé dans la trame : supprimez d'abord ses clips.")
            return
        self.project.media = [media for media in self.project.media if media.id != media_id]
        self.previews.pop(media_id, None)
        self.waveforms.pop(media_id, None)
        self.audio_store.discard(media_id)
        self._mark_dirty()
        self.media_changed.emit()
        self.project_changed.emit()

    # ============================================================== editing
    def _edit(self, text: str, operation, *args):
        """Run an editing function as an undoable command.

        Parameters
        ----------
        text : str
            Name of the action (shown in the undo button tooltip).
        operation : callable
            Function of :mod:`edison.model.editing` taking the project first.

        Returns
        -------
        object
            Result of ``operation``, or None if it raised :class:`EditError`.
        """
        if self.project is None:
            return None
        before = self.project.timeline_state()
        try:
            result = operation(self.project, *args)
        except EditError as error:
            self.message.emit(str(error))
            return None
        after = self.project.timeline_state()
        if after != before:
            self.undo_stack.push(_SnapshotCommand(self, text, before, after))
        return result

    def _restore(self, state: dict) -> None:
        """Called by undo/redo: restore a timeline state and refresh the views."""
        self.project.restore_timeline_state(state)
        existing = {clip.id for _, clip in self.project.iter_clips()}
        self.selected_clips &= existing
        if self.selected_junction and not {self.selected_junction[1], self.selected_junction[2]} <= existing:
            self.selected_junction = None
        self.project_changed.emit()
        self.selection_changed.emit()

    def add_media_clip(self, media_id: str, start: float, track_id: str | None = None) -> None:
        """Place a media of the library on the timeline."""
        media = self.project.get_media(media_id) if self.project else None
        if media is None:
            return
        clips = self._edit("Ajouter un clip", editing.add_media, media, max(0.0, start), track_id)
        if clips:
            self.select_clips([clip.id for clip in clips])

    def append_media(self, media_id: str) -> None:
        """Add a media at the end of the timeline (double-click in the library)."""
        media = self.project.get_media(media_id) if self.project else None
        if media is not None:
            self.add_media_clip(media_id, editing.append_position(self.project, media))

    def move_clips(self, clip_ids, delta: float, dragged_id: str, target_track_id: str) -> None:
        """Move clips (drag and drop in the timeline)."""
        self._edit("Déplacer", editing.move_clips, set(clip_ids), delta, dragged_id, target_track_id)

    def trim_clip(self, clip_id: str, edge: str, delta: float) -> None:
        """Move an edge of a clip."""
        self._edit("Rogner", editing.trim_clip, clip_id, edge, delta)

    def cut(self, time: float) -> None:
        """Cut the selected clips at ``time`` (every clip under the cursor if nothing is selected)."""
        if self.project is None:
            return
        clip_ids = self.selected_clips or editing.clips_at(self.project, time)
        self._edit("Couper", editing.cut_clips, editing.expand_links(self.project, clip_ids), time)

    def can_cut(self, time: float) -> bool:
        """Return True if :meth:`cut` would cut at least one clip."""
        if self.project is None:
            return False
        clip_ids = self.selected_clips or editing.clips_at(self.project, time)
        return any(
            clip.start + editing.MIN_CLIP_DURATION <= time <= clip.end - editing.MIN_CLIP_DURATION
            for _, clip in self.project.iter_clips() if clip.id in clip_ids
        )

    def delete_selection(self) -> None:
        """Delete the selected clips."""
        if self.selected_clips:
            self._edit("Supprimer", editing.delete_clips, set(self.selected_clips))
            self.clear_selection()

    def can_merge(self) -> bool:
        """Return True if the selected junction can be merged."""
        if self.project is None or self.selected_junction is None:
            return False
        track_id, left_id, right_id = self.selected_junction
        track = self.project.get_track(track_id)
        clips = {clip.id: clip for clip in track.clips} if track else {}
        return left_id in clips and right_id in clips and editing.can_merge(clips[left_id], clips[right_id])

    def merge_selected_junction(self) -> None:
        """Merge the two clips on each side of the selected junction."""
        if self.selected_junction is None:
            self.message.emit("Cliquez d'abord sur la jonction entre deux clips collés.")
            return
        track_id, left_id, right_id = self.selected_junction
        self._edit("Fusionner", editing.merge_clips, track_id, left_id, right_id)
        if self.project.find_clip(right_id) is None:
            self.select_clips([left_id])

    def unlink_clip(self, clip_id: str) -> None:
        """Separate the audio and the video of a clip."""
        self._edit("Séparer l'audio et la vidéo", editing.unlink_clips, clip_id)
        self.select_clips([clip_id])

    def duplicate_clips(self, clip_ids) -> None:
        """Duplicate clips after themselves."""
        copies = self._edit("Dupliquer", editing.duplicate_clips, editing.expand_links(self.project, clip_ids))
        if copies:
            self.select_clips(copies)

    def set_volume(self, clip_ids, volume: float) -> None:
        """Change the volume of clips."""
        self._edit("Volume", editing.set_volume, set(clip_ids), volume)

    def set_fades(self, clip_id: str, fade_in: float, fade_out: float) -> None:
        """Change the fades of a clip."""
        self._edit("Fondu", editing.set_fades, clip_id, fade_in, fade_out)

    # -------------------------------------------------------------- effects
    def add_effect(self, clip_ids, effect_type: str, params: dict) -> None:
        """Apply an effect to clips."""
        self._edit("Ajouter un effet", editing.add_effect, set(clip_ids), effect_type, params)

    def add_effect_block(self, start: float, effect_type: str, params: dict) -> None:
        """Place an effect block on an effect track (the effect applies to the whole picture)."""
        block = self._edit("Ajouter un effet", editing.add_effect_block, start, effect_type, params)
        if block is not None:
            self.select_clips([block.id])

    def update_effect(self, clip_id: str, effect_id: str, params: dict) -> None:
        """Change the settings of an applied effect."""
        self._edit("Modifier l'effet", editing.update_effect, clip_id, effect_id, params)

    def remove_effect(self, clip_id: str, effect_id: str) -> None:
        """Remove an applied effect."""
        self._edit("Retirer l'effet", editing.remove_effect, clip_id, effect_id)

    def add_track(self, kind: str) -> None:
        """Add an empty track."""
        self._edit("Ajouter une piste", editing.add_track, kind)

    def remove_track(self, track_id: str) -> None:
        """Remove an empty track."""
        self._edit("Supprimer la piste", editing.remove_track, track_id)

    # ============================================================ selection
    def select_clips(self, clip_ids, toggle: bool = False) -> None:
        """Select clips (their linked clips are selected with them)."""
        if self.project is None:
            return
        clip_ids = editing.expand_links(self.project, clip_ids)
        if toggle:
            already = clip_ids <= self.selected_clips
            self.selected_clips = self.selected_clips - clip_ids if already else self.selected_clips | clip_ids
        else:
            self.selected_clips = clip_ids
        self.selected_junction = None
        self.selection_changed.emit()

    def select_junction(self, track_id: str, left_id: str, right_id: str) -> None:
        """Select the junction between two touching clips (for the merge tool)."""
        self.selected_clips = set()
        self.selected_junction = (track_id, left_id, right_id)
        self.selection_changed.emit()

    def clear_selection(self) -> None:
        """Deselect everything."""
        if self.selected_clips or self.selected_junction:
            self.selected_clips = set()
            self.selected_junction = None
            self.selection_changed.emit()
