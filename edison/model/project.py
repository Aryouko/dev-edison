"""Project data model: ``Project -> Track -> Clip -> EffectInstance``.

The model is plain Python with no Qt dependency, so it can be unit tested,
copied to worker threads and saved as JSON (``.edison`` files).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from edison.config import DEFAULT_FPS, DEFAULT_HEIGHT, DEFAULT_WIDTH, PROJECT_FORMAT_VERSION

VIDEO = "video"
AUDIO = "audio"
EFFECT = "effect"  # kind of the tracks holding effect blocks (applied to the whole picture)


class ProjectFileError(Exception):
    """Raised when a project file cannot be read."""


def new_id() -> str:
    """Return a short random identifier."""
    return uuid.uuid4().hex[:12]


@dataclass
class Media:
    """A file imported into the project library.

    Parameters
    ----------
    id : str
        Unique identifier.
    path : str
        Absolute path of the file.
    kind : str
        ``VIDEO`` or ``AUDIO``.
    duration : float
        Duration in seconds.
    has_audio : bool
        True if the file contains an audio stream.
    width, height : int
        Picture size (videos only).
    fps : float
        Frame rate (videos only).
    imported_at : float
        Import timestamp, used to sort the library.
    """

    id: str
    path: str
    kind: str
    duration: float
    has_audio: bool = False
    width: int = 0
    height: int = 0
    fps: float = 0.0
    imported_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        """File name shown to the user."""
        return Path(self.path).name


@dataclass
class EffectInstance:
    """An effect applied to a clip, with its settings.

    Parameters
    ----------
    id : str
        Unique identifier.
    type : str
        Identifier of the effect plugin (see :mod:`edison.effects`).
    params : dict
        Values of the effect parameters.
    """

    id: str
    type: str
    params: dict = field(default_factory=dict)

    def copy(self) -> EffectInstance:
        """Independent copy with a new identifier."""
        return EffectInstance(new_id(), self.type, dict(self.params))


@dataclass
class Clip:
    """A portion of a media placed on a track.

    Parameters
    ----------
    id : str
        Unique identifier.
    media_id : str
        Identifier of the source media.
    start : float
        Position on the timeline, in seconds.
    in_point : float
        Position in the source media where the clip begins, in seconds.
    duration : float
        Length of the clip, in seconds.
    volume : float
        Gain applied to the audio (1.0 = 100 %).
    fade_in, fade_out : float
        Audio fade durations, in seconds.
    link_id : str or None
        Clips sharing the same ``link_id`` (video and its audio) move together.
    effects : list of EffectInstance
        Effects applied in order. A clip of an effect track has no media (``media_id`` is
        empty) and exactly one effect, applied to the whole picture.
    """

    id: str
    media_id: str
    start: float
    in_point: float
    duration: float
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    link_id: str | None = None
    effects: list[EffectInstance] = field(default_factory=list)

    @property
    def is_effect_block(self) -> bool:
        """True for a clip of an effect track."""
        return not self.media_id

    @property
    def end(self) -> float:
        """Timeline position where the clip ends."""
        return self.start + self.duration

    @property
    def source_end(self) -> float:
        """Position in the source media where the clip ends."""
        return self.in_point + self.duration

    def contains(self, time: float) -> bool:
        """Return True if the clip is visible/audible at ``time``."""
        return self.start <= time < self.end


@dataclass
class Track:
    """A timeline row holding clips of a single kind.

    Parameters
    ----------
    id : str
        Unique identifier.
    kind : str
        ``VIDEO``, ``AUDIO`` or ``EFFECT``.
    name : str
        Name displayed in the track header.
    clips : list of Clip
        Clips sorted by start time, never overlapping.
    """

    id: str
    kind: str
    name: str
    clips: list[Clip] = field(default_factory=list)

    @property
    def end(self) -> float:
        """End of the last clip of the track."""
        return max((clip.end for clip in self.clips), default=0.0)

    def sort(self) -> None:
        """Sort clips by start time."""
        self.clips.sort(key=lambda clip: clip.start)

    def clip_at(self, time: float) -> Clip | None:
        """Return the clip playing at ``time``, if any."""
        return next((clip for clip in self.clips if clip.contains(time)), None)


@dataclass
class Project:
    """A video editing project.

    Parameters
    ----------
    name : str
        Project name.
    width, height : int
        Output size ("identique à la source" in the export tab).
    fps : float
        Output frame rate.
    media : list of Media
        Library of imported files.
    tracks : list of Track
        Video tracks first (the top-most one is displayed in front), then audio tracks,
        then effect tracks.
    """

    name: str
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    fps: float = DEFAULT_FPS
    media: list[Media] = field(default_factory=list)
    tracks: list[Track] = field(default_factory=list)

    @classmethod
    def create(cls, name: str) -> Project:
        """Create an empty project with one video, one audio and one effect track."""
        return cls(name=name, tracks=[Track(new_id(), VIDEO, "Vidéo 1"), Track(new_id(), AUDIO, "Audio 1"),
                                      Track(new_id(), EFFECT, "Effets 1")])

    @property
    def duration(self) -> float:
        """End of the last clip of the timeline."""
        return max((track.end for track in self.tracks), default=0.0)

    def get_media(self, media_id: str) -> Media | None:
        """Return the media with this identifier."""
        return next((media for media in self.media if media.id == media_id), None)

    def get_track(self, track_id: str | None) -> Track | None:
        """Return the track with this identifier."""
        return next((track for track in self.tracks if track.id == track_id), None)

    def tracks_of(self, kind: str) -> list[Track]:
        """Return the tracks of a kind, in display order."""
        return [track for track in self.tracks if track.kind == kind]

    def iter_clips(self):
        """Yield ``(track, clip)`` for every clip of the timeline."""
        for track in self.tracks:
            for clip in track.clips:
                yield track, clip

    def find_clip(self, clip_id: str) -> tuple[Track, Clip] | None:
        """Return ``(track, clip)`` for a clip identifier."""
        return next(((track, clip) for track, clip in self.iter_clips() if clip.id == clip_id), None)

    def linked_clips(self, clip: Clip) -> list[Clip]:
        """Return the other clips linked to ``clip`` (e.g. the audio of a video)."""
        if clip.link_id is None:
            return []
        return [other for _, other in self.iter_clips() if other.link_id == clip.link_id and other.id != clip.id]

    def is_media_used(self, media_id: str) -> bool:
        """Return True if a clip of the timeline uses this media."""
        return any(clip.media_id == media_id for _, clip in self.iter_clips())

    # ----------------------------------------------------------------- state
    def timeline_state(self) -> dict:
        """Return a copy of everything the user can undo (settings and tracks)."""
        return {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "tracks": [
                {"id": t.id, "kind": t.kind, "name": t.name, "clips": [asdict(c) for c in t.clips]}
                for t in self.tracks
            ],
        }

    def restore_timeline_state(self, state: dict) -> None:
        """Restore a state returned by :meth:`timeline_state`."""
        self.width = state["width"]
        self.height = state["height"]
        self.fps = state["fps"]
        self.tracks = [
            Track(t["id"], t["kind"], t["name"], [_clip_from_dict(c) for c in t["clips"]]) for t in state["tracks"]
        ]

    def to_dict(self) -> dict:
        """Serialise the project to a JSON compatible dictionary."""
        return {
            "format": "edison",
            "version": PROJECT_FORMAT_VERSION,
            "name": self.name,
            "media": [asdict(media) for media in self.media],
            **self.timeline_state(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Project:
        """Build a project from :meth:`to_dict` output."""
        project = cls(name=data["name"], media=[_build(Media, m) for m in data.get("media", [])])
        project.restore_timeline_state(data)
        return project


def _build(cls, data: dict):
    """Instantiate a dataclass, ignoring unknown keys (forward compatibility)."""
    names = {f.name for f in fields(cls)}
    return cls(**{key: value for key, value in data.items() if key in names})


def _clip_from_dict(data: dict) -> Clip:
    clip = _build(Clip, data)
    clip.effects = [_build(EffectInstance, {**e, "params": dict(e.get("params", {}))}) for e in data.get("effects", [])]
    return clip


def save_project(project: Project, path: str | Path, thumbnail: str | None = None) -> None:
    """Write a project to a ``.edison`` file.

    Parameters
    ----------
    project : Project
        Project to save.
    path : str or Path
        Destination file.
    thumbnail : str or None
        Base64 JPEG shown on the home page.
    """
    data = project.to_dict()
    data["thumbnail"] = thumbnail
    data["saved_at"] = time.time()
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)  # never leaves a half-written project


def read_project_file(path: str | Path) -> dict:
    """Read the raw content of a ``.edison`` file.

    Raises
    ------
    ProjectFileError
        If the file is missing or is not a valid project.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProjectFileError(f"Impossible de lire le projet : {error}") from error
    if not isinstance(data, dict) or data.get("format") != "edison":
        raise ProjectFileError("Ce fichier n'est pas un projet Edison.")
    return data


def load_project(path: str | Path) -> Project:
    """Load a project from a ``.edison`` file.

    Raises
    ------
    ProjectFileError
        If the file is missing or is not a valid project.
    """
    data = read_project_file(path)
    try:
        return Project.from_dict(data)
    except (KeyError, TypeError) as error:
        raise ProjectFileError("Le fichier projet est incomplet ou corrompu.") from error
