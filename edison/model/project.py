"""Project data model: ``Project -> Track -> Clip -> EffectInstance``.

The classes and their fields are defined; add fields here when a feature
needs to save something in the project (and update the JSON functions below).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from edison.config import DEFAULT_FPS, DEFAULT_HEIGHT, DEFAULT_WIDTH

VIDEO = "video"
AUDIO = "audio"
EFFECT = "effect"  # kind of the tracks holding effect blocks (CDC "Plusieurs types de timeline")


class ProjectFileError(Exception):
    """Raised when a project file cannot be read. The message is shown to the user."""


def new_id() -> str:
    """Return a short random identifier."""
    return uuid.uuid4().hex[:12]


@dataclass
class Media:
    """A file imported into the project library (tab "Import").

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
        True if the file contains sound (a video with sound gives a linked audio clip).
    width, height : int
        Picture size (videos only).
    fps : float
        Frame rate (videos only).
    imported_at : float
        Import timestamp, used by the sort "Imports les plus récents en premier".
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
    """An effect applied to a clip, with its settings (sprint S5).

    Parameters
    ----------
    id : str
        Unique identifier.
    type : str
        ``type_id`` of the effect plugin (see :mod:`edison.effects`).
    params : dict
        Values of the effect parameters.
    """

    id: str
    type: str
    params: dict = field(default_factory=dict)


@dataclass
class Clip:
    """A portion of a media placed on a track.

    Parameters
    ----------
    id : str
        Unique identifier.
    media_id : str
        Source media. Empty for a block of an effect track (it has no media).
    start : float
        Position on the timeline, in seconds.
    in_point : float
        Position in the source media where the clip begins, in seconds (changed by a cut or a trim).
    duration : float
        Length of the clip, in seconds.
    volume : float
        Audio gain (1.0 = 100 %), CDC "Volume".
    fade_in, fade_out : float
        Audio fade durations in seconds, CDC "Fondu entrant / sortant".
    link_id : str or None
        A video and its audio share a ``link_id``: they move together until separated.
    effects : list of EffectInstance
        Effects applied in order.
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
    def end(self) -> float:
        """Timeline position where the clip ends."""
        return self.start + self.duration

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
        Name displayed in the track header ("Vidéo 1"...).
    clips : list of Clip
        Clips sorted by start time; they must never overlap.
    """

    id: str
    kind: str
    name: str
    clips: list[Clip] = field(default_factory=list)

    @property
    def end(self) -> float:
        """End of the last clip of the track."""
        return max((clip.end for clip in self.clips), default=0.0)

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
        Output size (the "Source" resolution of the export tab).
    fps : float
        Output frame rate.
    media : list of Media
        Library of imported files.
    tracks : list of Track
        Display order: video tracks (the top-most one is in front), audio tracks, effect tracks.
    """

    name: str
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    fps: float = DEFAULT_FPS
    media: list[Media] = field(default_factory=list)
    tracks: list[Track] = field(default_factory=list)

    @classmethod
    def create(cls, name: str) -> Project:
        """Create an empty project with one track of each kind."""
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

    # ------------------------------------------------------------- JSON (S6)
    def to_dict(self) -> dict:
        """Serialise the project to a JSON compatible dictionary.

        TODO(S6) "Sauvegarde et chargement .edison":
            - ``dataclasses.asdict`` converts the nested dataclasses to dictionaries;
            - add ``"format": "edison"`` and ``"version": PROJECT_FORMAT_VERSION`` (config.py)
              so that :func:`load_project` can recognise the file.
        """
        raise NotImplementedError("TODO(S6): Project.to_dict")

    @classmethod
    def from_dict(cls, data: dict) -> Project:
        """Build a project from :meth:`to_dict` output.

        TODO(S6): rebuild the dataclasses (Media, Track, Clip, EffectInstance) from the
        dictionaries. Ignore unknown keys, so that an older Edison can open a newer file.
        """
        raise NotImplementedError("TODO(S6): Project.from_dict")


def save_project(project: Project, path: str | Path, thumbnail: str | None = None) -> None:
    """Write a project to a ``.edison`` file (JSON).

    Parameters
    ----------
    project : Project
        Project to save.
    path : str or Path
        Destination file.
    thumbnail : str or None
        Base64 JPEG shown on the project card of the home page.

    TODO(S6): ``json.dumps(project.to_dict(), ensure_ascii=False, indent=2)``. Write to a
    temporary file, then ``os.replace`` it: a crash never leaves a half-written project.
    """
    raise NotImplementedError("TODO(S6): save_project")


def load_project(path: str | Path) -> Project:
    """Load a project from a ``.edison`` file.

    Raises
    ------
    ProjectFileError
        If the file is missing, is not JSON or is not an Edison project.

    TODO(S6): read the JSON, check ``data["format"] == "edison"``, then ``Project.from_dict``.
    """
    raise NotImplementedError("TODO(S6): load_project")
