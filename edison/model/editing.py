"""Timeline editing operations: pure functions on the model (no Qt).

How to write an operation
-------------------------
* It takes the project first, then its arguments: ``cut_clips(project, clip_ids, time)``.
* It checks everything BEFORE changing anything; if the edit is impossible it raises
  :class:`EditError` with a French message (shown to the user) and the project is untouched.
* It does not know about the selection, the undo history or the interface: the controller
  (``ProjectController``) calls it and makes it undoable (sprint S5).
* Each operation gets its unit test in ``tests/test_editing.py`` (no window needed).

The functions below are the operations listed in the CDC ("Trame", "Liste des outils",
menus of the clips). Implement them sprint after sprint, then remove the ``raise``.
"""

from __future__ import annotations

from edison.model.project import Clip, Media, Project, Track

EPSILON = 1e-6  # tolerance on times (floating point numbers)
MIN_CLIP_DURATION = 0.1  # seconds; a cut or a trim never creates a shorter clip


class EditError(Exception):
    """Raised when an edit is impossible. The message is shown to the user."""


# ------------------------------------------------------------------- helpers
def overlaps(track: Track, start: float, end: float, ignore=()) -> bool:
    """Return True if ``[start, end[`` collides with a clip of ``track``.

    Parameters
    ----------
    track : Track
        Track to check.
    start, end : float
        Tested interval, in seconds.
    ignore : collection of str
        Clip identifiers to ignore (e.g. the clips being moved).
    """
    return any(
        clip.id not in ignore and clip.start < end - EPSILON and clip.end > start + EPSILON for clip in track.clips
    )


# ---------------------------------------------------------------------- S3
def add_media(project: Project, media: Media, start: float, track_id: str | None = None) -> list[Clip]:
    """Place a media of the library on the timeline (drag and drop from the "Import" tab).

    TODO(S3):
        - choose the track: ``track_id`` if it has the right kind, else the first free track
          of that kind (create one if none is free);
        - refuse an occupied place with :class:`EditError` (use :func:`overlaps`);
        - a video WITH sound also creates an audio clip on an audio track; both clips get the
          same ``link_id`` (CDC "Une vidéo importée crée un clip vidéo et un clip audio liés").

    Returns
    -------
    list of Clip
        The created clips.
    """
    raise NotImplementedError("TODO(S3): add_media")


def move_clips(project: Project, clip_ids, delta: float, target_track_id: str | None = None) -> None:
    """Move clips in time; the dragged clip can change track (CDC "Manipulation des clips").

    TODO(S3): only to a track of the same kind, never before 0 s, never over another clip.
    The linked clips (same ``link_id``) move with them.
    """
    raise NotImplementedError("TODO(S3): move_clips")


def trim_clip(project: Project, clip_id: str, edge: str, delta: float) -> None:
    """Move the ``"start"`` or ``"end"`` edge of a clip ("Rogner un clip").

    TODO(S3): moving the start also moves ``in_point``; limits: the neighbouring clips,
    the length of the source media and ``MIN_CLIP_DURATION``. Trim the linked clips too.
    """
    raise NotImplementedError("TODO(S3): trim_clip")


def cut_clips(project: Project, clip_ids, time: float) -> None:
    """Cut clips in two at the cursor position (tool "Cut").

    TODO(S3): the right part is a new clip with ``in_point += time - start``; copy its
    effects (do not share the same list!); give the right parts of linked clips a new
    common ``link_id``.
    """
    raise NotImplementedError("TODO(S3): cut_clips")


def merge_clips(project: Project, track_id: str, left_id: str, right_id: str) -> None:
    """Merge two touching clips when their junction is selected (tool "Fusionner").

    TODO(S3): possible only for consecutive parts of the same media
    (``left.end == right.start`` and ``left.in_point + left.duration == right.in_point``).
    """
    raise NotImplementedError("TODO(S3): merge_clips")


def delete_clips(project: Project, clip_ids) -> None:
    """Remove clips (tool "Poubelle", menu "Supprimer")."""
    raise NotImplementedError("TODO(S3): delete_clips")


def unlink_clips(project: Project, clip_id: str) -> None:
    """Separate a video clip from its audio (menu "Séparer la piste audio et vidéo").

    TODO(S3): set ``link_id = None`` on the clip and on its linked clips.
    """
    raise NotImplementedError("TODO(S3): unlink_clips")


def duplicate_clips(project: Project, clip_ids) -> list[str]:
    """Copy clips right after themselves, at the first free place (menu "Dupliquer")."""
    raise NotImplementedError("TODO(S3): duplicate_clips")


# ---------------------------------------------------------------------- S4
def set_volume(project: Project, clip_ids, volume: float) -> None:
    """Change the volume of audio clips (menu "Volume", 0 to 2 = 0 to 200 %)."""
    raise NotImplementedError("TODO(S4): set_volume")


def set_fades(project: Project, clip_id: str, fade_in: float, fade_out: float) -> None:
    """Change the fades of an audio clip (menu "Fondu entrant / sortant").

    TODO(S4): keep ``fade_in + fade_out <= duration``.
    """
    raise NotImplementedError("TODO(S4): set_fades")


# ---------------------------------------------------------------------- S5
def add_effect(project: Project, clip_ids, effect_type: str, params: dict) -> None:
    """Apply an effect to clips (button "Appliquer" of the effects pop-up).

    TODO(S5): append an ``EffectInstance(new_id(), effect_type, dict(params))`` to each clip.
    """
    raise NotImplementedError("TODO(S5): add_effect")


def add_effect_block(project: Project, start: float, effect_type: str, params: dict) -> Clip:
    """Place an effect block on an effect track: it applies to the whole picture.

    TODO(S5): a ``Clip`` with an empty ``media_id`` and one effect, on the first free effect track.
    """
    raise NotImplementedError("TODO(S5): add_effect_block")


def update_effect(project: Project, clip_id: str, effect_id: str, params: dict) -> None:
    """Change the settings of an applied effect (menu "Effets appliqués" > modifier)."""
    raise NotImplementedError("TODO(S5): update_effect")


def remove_effect(project: Project, clip_id: str, effect_id: str) -> None:
    """Remove an applied effect (menu "Effets appliqués" > retirer)."""
    raise NotImplementedError("TODO(S5): remove_effect")
