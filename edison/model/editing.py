"""Timeline editing operations (pure functions on the model, no Qt).

Each function either applies its whole change or raises :class:`EditError`
before touching the project, so the controller can wrap it in an undoable
command.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from edison.effects.audio import FADE
from edison.model.project import AUDIO, EFFECT, VIDEO, Clip, EffectInstance, Media, Project, Track, new_id

EPSILON = 1e-6
MIN_CLIP_DURATION = 0.1
JOIN_TOLERANCE = 1e-3
DEFAULT_EFFECT_BLOCK_DURATION = 3.0
TRACK_PREFIXES = {VIDEO: "Vidéo", AUDIO: "Audio", EFFECT: "Effets"}


class EditError(Exception):
    """Raised when an edit is impossible. The message is shown to the user."""


# --------------------------------------------------------------------- helpers
def overlaps(track: Track, start: float, end: float, ignore=()) -> bool:
    """Return True if ``[start, end[`` collides with a clip of ``track``.

    Parameters
    ----------
    track : Track
        Track to check.
    start, end : float
        Tested interval, in seconds.
    ignore : collection of str
        Clip identifiers to ignore (clips being moved).
    """
    return any(
        clip.id not in ignore and clip.start < end - EPSILON and clip.end > start + EPSILON for clip in track.clips
    )


def expand_links(project: Project, clip_ids) -> set[str]:
    """Add the clips linked to ``clip_ids`` (a video and its audio are selected together)."""
    ids = set(clip_ids)
    links = {clip.link_id for _, clip in project.iter_clips() if clip.id in ids and clip.link_id}
    ids.update(clip.id for _, clip in project.iter_clips() if clip.link_id in links)
    return ids


def clips_at(project: Project, time: float) -> set[str]:
    """Return the identifiers of every clip playing at ``time``."""
    return {clip.id for _, clip in project.iter_clips() if clip.contains(time)}


def snap_points(project: Project, exclude_ids=()) -> list[float]:
    """Return the times a dragged edge can snap to (clip edges and 0)."""
    points = [0.0]
    for _, clip in project.iter_clips():
        if clip.id not in exclude_ids:
            points.extend((clip.start, clip.end))
    return points


def _group(project: Project, clip_ids) -> list[tuple[Track, Clip]]:
    return [(track, clip) for track, clip in project.iter_clips() if clip.id in clip_ids]


# ---------------------------------------------------------------------- tracks
def add_track(project: Project, kind: str) -> Track:
    """Add an empty track.

    New video tracks are added on top (displayed in front), audio tracks after the
    other audio tracks, effect tracks at the bottom.
    """
    numbers = [int(t.name.split()[-1]) for t in project.tracks_of(kind) if t.name.split()[-1].isdigit()]
    track = Track(new_id(), kind, f"{TRACK_PREFIXES[kind]} {max(numbers, default=0) + 1}")
    if kind == VIDEO:
        project.tracks.insert(0, track)
    elif kind == AUDIO:
        first_effect = next((i for i, t in enumerate(project.tracks) if t.kind == EFFECT), len(project.tracks))
        project.tracks.insert(first_effect, track)
    else:
        project.tracks.append(track)
    return track


def remove_track(project: Project, track_id: str) -> None:
    """Remove an empty track (at least one track of each kind is kept)."""
    track = project.get_track(track_id)
    if track is None:
        return
    if track.clips:
        raise EditError("La piste doit être vide pour être supprimée.")
    if len(project.tracks_of(track.kind)) <= 1:
        raise EditError("Le projet doit garder au moins une piste de ce type.")
    project.tracks.remove(track)


# ----------------------------------------------------------------- add a media
@dataclass
class AddPlan:
    """Where the clips of a media would be placed on the timeline.

    Attributes
    ----------
    valid : bool
        False if the location is already occupied.
    main_track_id : str or None
        Track receiving the main clip (None: a new track will be created).
    audio_track_id : str or None
        Track receiving the linked audio clip (None: a new track will be created).
    needs_audio : bool
        True for a video containing sound (a linked audio clip is created).
    """

    valid: bool
    main_track_id: str | None
    audio_track_id: str | None
    needs_audio: bool


def plan_add_media(project: Project, media: Media, start: float, hovered_track_id: str | None = None) -> AddPlan:
    """Compute where a media dropped at ``start`` would go, without changing anything.

    Dropped on a track of the right kind, the media goes on that track (if it is free).
    Otherwise it goes on the first free track of its kind, or on a new track.
    """
    end = start + media.duration
    hovered = project.get_track(hovered_track_id)
    if hovered is not None and hovered.kind == media.kind:
        main = hovered
        valid = not overlaps(hovered, start, end)
    else:
        main = next((t for t in project.tracks_of(media.kind) if not overlaps(t, start, end)), None)
        valid = True
    valid = valid and start >= 0
    needs_audio = media.kind == VIDEO and media.has_audio
    audio = None
    if needs_audio:
        audio = next((t for t in project.tracks_of(AUDIO) if not overlaps(t, start, end)), None)
    return AddPlan(valid, main.id if main else None, audio.id if audio else None, needs_audio)


def add_media(project: Project, media: Media, start: float, hovered_track_id: str | None = None) -> list[Clip]:
    """Place a media on the timeline.

    A video with sound creates a video clip and a linked audio clip.

    Returns
    -------
    list of Clip
        The created clips.
    """
    plan = plan_add_media(project, media, start, hovered_track_id)
    if not plan.valid:
        raise EditError("Cet emplacement est déjà occupé par un autre clip.")
    main_track = project.get_track(plan.main_track_id) or add_track(project, media.kind)
    clip = Clip(new_id(), media.id, start, 0.0, media.duration)
    main_track.clips.append(clip)
    main_track.sort()
    clips = [clip]
    if plan.needs_audio:
        audio_track = project.get_track(plan.audio_track_id) or add_track(project, AUDIO)
        clip.link_id = new_id()
        audio_clip = Clip(new_id(), media.id, start, 0.0, media.duration, link_id=clip.link_id)
        audio_track.clips.append(audio_clip)
        audio_track.sort()
        clips.append(audio_clip)
    return clips


def append_position(project: Project, media: Media) -> float:
    """Return the end of the first track able to receive ``media`` (used by double-click)."""
    track = next(iter(project.tracks_of(media.kind)), None)
    return track.end if track else 0.0


# ------------------------------------------------------------------------ move
def _plan_move(project, clip_ids, delta, dragged_id, target_track_id):
    """Return ``[(clip, old_track, new_track, new_start)]`` or None if the move collides."""
    ids = set(clip_ids)
    target = project.get_track(target_track_id)
    placements = []
    for track, clip in _group(project, ids):
        new_track = target if clip.id == dragged_id and target is not None and target.kind == track.kind else track
        placements.append((clip, track, new_track, clip.start + delta))
    if not placements:
        return None
    for index, (clip, _, new_track, start) in enumerate(placements):
        end = start + clip.duration
        if start < -EPSILON or overlaps(new_track, start, end, ignore=ids):
            return None
        for other, _, other_track, other_start in placements[index + 1:]:
            if other_track is new_track and other_start < end - EPSILON and other_start + other.duration > start + EPSILON:
                return None
    return placements


def can_move(project: Project, clip_ids, delta: float, dragged_id: str | None = None,
             target_track_id: str | None = None) -> bool:
    """Return True if :func:`move_clips` would succeed."""
    return _plan_move(project, clip_ids, delta, dragged_id, target_track_id) is not None


def move_clips(project: Project, clip_ids, delta: float, dragged_id: str | None = None,
               target_track_id: str | None = None) -> None:
    """Shift clips in time; the dragged clip can also change track (same kind only).

    Parameters
    ----------
    project : Project
        Edited project.
    clip_ids : collection of str
        Moved clips.
    delta : float
        Time offset, in seconds.
    dragged_id : str or None
        Clip under the mouse, the only one allowed to change track.
    target_track_id : str or None
        New track of the dragged clip.
    """
    placements = _plan_move(project, clip_ids, delta, dragged_id, target_track_id)
    if placements is None:
        raise EditError("Impossible de déplacer ici : l'emplacement est déjà occupé.")
    for clip, old_track, new_track, start in placements:
        clip.start = max(0.0, start)
        if new_track is not old_track:
            old_track.clips.remove(clip)
            new_track.clips.append(clip)
    for track in project.tracks:
        track.sort()


# ------------------------------------------------------------------------ trim
def _neighbours(track: Track, clip: Clip) -> tuple[float, float]:
    previous_end = max((c.end for c in track.clips if c is not clip and c.end <= clip.start + EPSILON), default=0.0)
    next_start = min((c.start for c in track.clips if c is not clip and c.start >= clip.end - EPSILON), default=math.inf)
    return previous_end, next_start


def trim_bounds(project: Project, clip_id: str, edge: str) -> tuple[float, float]:
    """Return the allowed ``(min, max)`` offset of a clip edge.

    The limits come from the neighbouring clips, the length of the source media
    and the minimum clip duration. Linked clips are trimmed together, so their
    limits are combined.

    Parameters
    ----------
    edge : str
        ``"start"`` or ``"end"``.
    """
    found = project.find_clip(clip_id)
    if found is None:
        return 0.0, 0.0
    group = [found] + [project.find_clip(c.id) for c in project.linked_clips(found[1])]
    low, high = -math.inf, math.inf
    for track, clip in group:
        media = project.get_media(clip.media_id)
        if clip.is_effect_block:  # an effect block has no source: only its neighbours limit it
            media_duration, in_point = math.inf, math.inf
        else:
            media_duration = media.duration if media else clip.source_end
            in_point = clip.in_point
        previous_end, next_start = _neighbours(track, clip)
        if edge == "start":
            low = max(low, -in_point, previous_end - clip.start)
            high = min(high, clip.duration - MIN_CLIP_DURATION)
        else:
            low = max(low, MIN_CLIP_DURATION - clip.duration)
            high = min(high, media_duration - clip.source_end, next_start - clip.end)
    return (low, high) if low <= high else (0.0, 0.0)


def trim_clip(project: Project, clip_id: str, edge: str, delta: float) -> float:
    """Move the start or end edge of a clip (and of its linked clips).

    Returns
    -------
    float
        The offset actually applied (clamped by :func:`trim_bounds`).
    """
    low, high = trim_bounds(project, clip_id, edge)
    delta = min(max(delta, low), high)
    found = project.find_clip(clip_id)
    if found is None or abs(delta) < EPSILON:
        return 0.0
    for track, clip in [found] + [project.find_clip(c.id) for c in project.linked_clips(found[1])]:
        if edge == "start":
            clip.start += delta
            clip.in_point += delta
            clip.duration -= delta
        else:
            clip.duration += delta
        _clamp_fades(clip)
        track.sort()
    return delta


# ------------------------------------------------------------------ cut, merge
def cut_clips(project: Project, clip_ids, time: float) -> int:
    """Cut clips in two at ``time``.

    Returns
    -------
    int
        Number of clips cut.
    """
    targets = [
        (track, clip) for track, clip in _group(project, clip_ids)
        if clip.start + MIN_CLIP_DURATION <= time <= clip.end - MIN_CLIP_DURATION
    ]
    if not targets:
        raise EditError("Placez le curseur à l'intérieur du clip à couper.")
    new_links: dict[str, str] = {}
    for track, clip in targets:
        offset = time - clip.start
        right = replace(clip, id=new_id(), start=time, in_point=clip.in_point + offset,
                        duration=clip.duration - offset, fade_in=0.0, effects=_copy_effects(clip))
        if clip.link_id:
            right.link_id = new_links.setdefault(clip.link_id, new_id())
        clip.duration = offset
        clip.fade_out = 0.0
        _clamp_fades(clip)
        _clamp_fades(right)
        track.clips.append(right)
        track.sort()
    return len(targets)


def can_merge(left: Clip, right: Clip) -> bool:
    """Return True if two touching clips are consecutive parts of the same media, with the same effects."""
    return (
        left.media_id == right.media_id
        and abs(left.end - right.start) < JOIN_TOLERANCE
        and abs(left.source_end - right.in_point) < JOIN_TOLERANCE
        and _effect_settings(left) == _effect_settings(right)
    )


def _effect_settings(clip: Clip) -> list:
    return [(effect.type, effect.params) for effect in clip.effects]


def _copy_effects(clip: Clip) -> list[EffectInstance]:
    return [effect.copy() for effect in clip.effects]


def merge_clips(project: Project, track_id: str, left_id: str, right_id: str) -> None:
    """Merge two touching clips back into one (and their linked clips)."""
    track = project.get_track(track_id)
    left = next((c for c in track.clips if c.id == left_id), None) if track else None
    right = next((c for c in track.clips if c.id == right_id), None) if track else None
    if left is None or right is None or not can_merge(left, right):
        raise EditError("Seuls deux morceaux consécutifs d'un même média, avec les mêmes effets, "
                        "peuvent être fusionnés (par exemple après une coupe).")
    pairs = [(track, left, right)]
    for linked_left in project.linked_clips(left):
        linked_track, _ = project.find_clip(linked_left.id)
        linked_right = next(
            (c for c in linked_track.clips if right.link_id and c.link_id == right.link_id and can_merge(linked_left, c)),
            None,
        )
        if linked_right is not None:
            pairs.append((linked_track, linked_left, linked_right))
    for pair_track, pair_left, pair_right in pairs:
        pair_left.duration = pair_right.end - pair_left.start
        pair_left.fade_out = pair_right.fade_out
        pair_track.clips.remove(pair_right)


# -------------------------------------------------------------- other actions
def delete_clips(project: Project, clip_ids) -> None:
    """Remove clips from the timeline."""
    for track in project.tracks:
        track.clips = [clip for clip in track.clips if clip.id not in clip_ids]


def unlink_clips(project: Project, clip_id: str) -> None:
    """Separate a video clip from its audio so they can be edited independently."""
    found = project.find_clip(clip_id)
    if found is None:
        return
    for clip in [found[1]] + project.linked_clips(found[1]):
        clip.link_id = None


def duplicate_clips(project: Project, clip_ids) -> list[str]:
    """Copy clips right after the group, at the first free place on their tracks.

    Returns
    -------
    list of str
        Identifiers of the copies.
    """
    group = _group(project, clip_ids)
    if not group:
        return []
    first = min(clip.start for _, clip in group)
    position = max(clip.end for _, clip in group)
    while True:  # push the copies later until every track has room for them
        needed = None
        for track, clip in group:
            start = position + clip.start - first
            for other in track.clips:
                if other.start < start + clip.duration - EPSILON and other.end > start + EPSILON:
                    candidate = other.end - (clip.start - first)
                    needed = candidate if needed is None else max(needed, candidate)
        if needed is None:
            break
        position = needed
    new_links: dict[str, str] = {}
    copies = []
    for track, clip in group:
        link_id = new_links.setdefault(clip.link_id, new_id()) if clip.link_id else None
        copy = replace(clip, id=new_id(), start=position + clip.start - first, link_id=link_id,
                       effects=_copy_effects(clip))
        track.clips.append(copy)
        track.sort()
        copies.append(copy.id)
    return copies


def set_volume(project: Project, clip_ids, volume: float) -> None:
    """Set the volume (0 to 2, i.e. 0 to 200 %) of clips."""
    for _, clip in _group(project, clip_ids):
        clip.volume = min(max(volume, 0.0), 2.0)


def set_fades(project: Project, clip_id: str, fade_in: float, fade_out: float) -> None:
    """Set the fade in / fade out durations of a clip."""
    found = project.find_clip(clip_id)
    if found is None:
        return
    clip = found[1]
    clip.fade_in, clip.fade_out = max(fade_in, 0.0), max(fade_out, 0.0)
    _clamp_fades(clip)


def _clamp_fades(clip: Clip) -> None:
    """Keep fades inside the clip (fade in + fade out <= duration)."""
    total = clip.fade_in + clip.fade_out
    if total > clip.duration > 0:
        scale = clip.duration / total
        clip.fade_in *= scale
        clip.fade_out *= scale


# --------------------------------------------------------------------- effects
def add_effect(project: Project, clip_ids, effect_type: str, params: dict) -> None:
    """Apply an effect to clips.

    The fade in / fade out is stored in the ``fade_in`` / ``fade_out`` of the clips
    (the mixer and the waveform use them) instead of their effect list.
    """
    group = _group(project, clip_ids)
    if not group:
        raise EditError("Sélectionnez d'abord le clip auquel appliquer l'effet.")
    for _, clip in group:
        if effect_type == FADE:
            set_fades(project, clip.id, params.get("fade_in", 0.0), params.get("fade_out", 0.0))
        else:
            clip.effects.append(EffectInstance(new_id(), effect_type, dict(params)))


def add_effect_block(project: Project, start: float, effect_type: str, params: dict,
                     duration: float = DEFAULT_EFFECT_BLOCK_DURATION) -> Clip:
    """Place an effect block on an effect track: the effect applies to the whole picture.

    The block goes on the first effect track free at ``start`` (a new track if needed).

    Returns
    -------
    Clip
        The created block.
    """
    start = max(0.0, start)
    track = next((t for t in project.tracks_of(EFFECT) if not overlaps(t, start, start + duration)), None)
    if track is None:
        track = add_track(project, EFFECT)
    clip = Clip(new_id(), "", start, 0.0, duration, effects=[EffectInstance(new_id(), effect_type, dict(params))])
    track.clips.append(clip)
    track.sort()
    return clip


def _find_effect(project: Project, clip_id: str, effect_id: str) -> EffectInstance:
    found = project.find_clip(clip_id)
    effect = next((e for e in found[1].effects if e.id == effect_id), None) if found else None
    if effect is None:
        raise EditError("Cet effet n'existe plus.")
    return effect


def update_effect(project: Project, clip_id: str, effect_id: str, params: dict) -> None:
    """Change the settings of an applied effect."""
    _find_effect(project, clip_id, effect_id).params = dict(params)


def remove_effect(project: Project, clip_id: str, effect_id: str) -> None:
    """Remove an effect from a clip (an effect block is removed with its effect)."""
    effect = _find_effect(project, clip_id, effect_id)
    track, clip = project.find_clip(clip_id)
    clip.effects.remove(effect)
    if clip.is_effect_block and not clip.effects:
        track.clips.remove(clip)
