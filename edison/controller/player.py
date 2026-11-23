"""Real-time playback of the timeline (picture and sound).

* Pictures are rendered by a worker thread with :func:`render_frame`; only the
  latest requested time is rendered, so the interface never waits.
* Sound is mixed by :func:`mix_audio` inside the ``sounddevice`` callback.
* Both threads read a copy of the project, refreshed after every change,
  so the interface can edit the project while they read it.
* The effects pop-up can show a temporary version of the project
  (:meth:`Player.set_preview`) without changing the real one.
"""

from __future__ import annotations

import copy
import logging
import threading
import time

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QImage

from edison.config import CHANNELS, SAMPLE_RATE
from edison.render.audio_effects import audio_effects
from edison.render.renderer import MediaSources, mix_audio, preview_size, render_frame

try:
    import sounddevice
except OSError:  # PortAudio missing: playback stays silent
    sounddevice = None

logger = logging.getLogger(__name__)

SKIP_SECONDS = 5.0


class _RenderWorker(QThread):
    """Thread rendering preview pictures."""

    frame_ready = Signal(float, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._condition = threading.Condition()
        self._project = None
        self._requested: float | None = None
        self._running = True

    def set_project(self, project) -> None:
        """Use a new copy of the project for the next pictures."""
        with self._condition:
            self._project = project

    def request(self, position: float) -> None:
        """Ask for the picture at ``position`` (replaces a request not rendered yet)."""
        with self._condition:
            self._requested = position
            self._condition.notify()

    def stop(self) -> None:
        """Stop the thread and wait for it."""
        with self._condition:
            self._running = False
            self._condition.notify()
        self.wait()

    def run(self) -> None:
        sources = MediaSources()
        try:
            while True:
                with self._condition:
                    while self._running and self._requested is None:
                        self._condition.wait()
                    if not self._running:
                        return
                    position, project = self._requested, self._project
                    self._requested = None
                if project is None:
                    continue
                width, height = preview_size(project)
                try:
                    frame = render_frame(project, position, width, height, sources)
                except Exception:
                    logger.exception("Preview rendering failed at %.2f s", position)
                    continue
                image = QImage(frame.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
                self.frame_ready.emit(position, image)
        finally:
            sources.close()


class Player(QObject):
    """Playback state: position, play/pause, volume.

    Parameters
    ----------
    controller : ProjectController
        Controller of the open project.
    """

    position_changed = Signal(float)
    playing_changed = Signal(bool)
    frame_ready = Signal(QImage)
    volume_changed = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._snapshot = None  # copy of the project
        self._preview = None  # temporary project shown by the effects pop-up
        self._current = None  # what is played: the preview if any, else the copy
        self._position = 0.0
        self._playing = False
        self._volume = 1.0
        self._muted = False
        self._clock_start = 0.0
        self._position_start = 0.0
        self._audio_sample = 0
        self._stream = None
        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._tick)
        self._worker = _RenderWorker(self)
        self._worker.frame_ready.connect(self._on_frame_ready)
        self._worker.start()
        controller.project_changed.connect(self._refresh_snapshot)
        controller.project_opened.connect(self._on_project_opened)
        controller.project_closed.connect(self._on_project_closed)

    # ------------------------------------------------------------ properties
    @property
    def position(self) -> float:
        """Current time, in seconds."""
        return self._position

    @property
    def duration(self) -> float:
        """Length of the montage, in seconds."""
        return self._current.duration if self._current else 0.0

    @property
    def fps(self) -> float:
        """Frame rate of the project."""
        return self._current.fps if self._current else 30.0

    @property
    def playing(self) -> bool:
        """True during playback."""
        return self._playing

    @property
    def volume(self) -> float:
        """Playback volume, from 0 to 1."""
        return self._volume

    @property
    def muted(self) -> bool:
        """True if the sound is muted."""
        return self._muted

    # --------------------------------------------------------------- actions
    def toggle(self) -> None:
        """Play or pause."""
        if self._playing:
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        """Start playback from the current position (from the start if at the end)."""
        if self._playing or self.duration <= 0:
            return
        if self._position >= self.duration - 1e-3:
            self._position = 0.0
        self._playing = True
        self._restart_clock()
        self._start_audio()
        self._timer.start()
        self.playing_changed.emit(True)

    def pause(self) -> None:
        """Pause playback."""
        if not self._playing:
            return
        self._playing = False
        self._timer.stop()
        self._stop_audio()
        self.playing_changed.emit(False)

    def seek(self, position: float) -> None:
        """Go to ``position`` (in seconds)."""
        self._position = min(max(position, 0.0), self.duration)
        if self._playing:
            self._restart_clock()
        self.position_changed.emit(self._position)
        self._worker.request(self._position)

    def skip(self, direction: int) -> None:
        """Go back (-1) or forward (+1) by a few seconds."""
        self.seek(self._position + direction * SKIP_SECONDS)

    def step_frame(self, direction: int) -> None:
        """Go to the previous (-1) or next (+1) frame."""
        self.seek(self._position + direction / self.fps)

    def set_volume(self, volume: float) -> None:
        """Set the playback volume (0 to 1)."""
        self._volume = min(max(volume, 0.0), 1.0)
        self._muted = self._volume == 0
        self.volume_changed.emit()

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute the sound."""
        self._muted = muted
        self.volume_changed.emit()

    def set_preview(self, project) -> None:
        """Play a temporary version of the project (None goes back to the real project).

        The caller gives a copy: it is used as is, without being copied again.
        """
        self._preview = project
        self._use_current()

    def refresh(self) -> None:
        """Render the current picture again."""
        self._worker.request(self._position)

    def shutdown(self) -> None:
        """Stop playback and the render thread (when the application closes)."""
        self.pause()
        self._worker.stop()

    # -------------------------------------------------------------- internal
    def _restart_clock(self) -> None:
        self._clock_start = time.perf_counter()
        self._position_start = self._position
        self._audio_sample = int(round(self._position * SAMPLE_RATE))

    def _tick(self) -> None:
        position = self._position_start + time.perf_counter() - self._clock_start
        if position >= self.duration:
            self._position = self.duration
            self.pause()
        else:
            self._position = position
        self.position_changed.emit(self._position)
        self._worker.request(self._position)

    def _start_audio(self) -> None:
        if sounddevice is None:
            return
        try:
            self._stream = sounddevice.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
                                                    callback=self._audio_callback)
            self._stream.start()
        except Exception:  # no audio device: the picture still plays
            logger.warning("Audio output unavailable", exc_info=True)
            self._stream = None

    def _stop_audio(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                logger.warning("Cannot close the audio output", exc_info=True)
            self._stream = None

    def _audio_callback(self, outdata, frames, _time_info, _status) -> None:
        """Called by the audio thread: fill ``outdata`` with the next samples."""
        project = self._current
        start = self._audio_sample
        self._audio_sample += frames
        if project is None or self._muted:
            outdata.fill(0)
            return
        try:
            mixed = mix_audio(project, start, frames, self._controller.audio_store, self._controller.audio_effects)
            outdata[:] = mixed * self._volume
        except Exception:  # an exception would stop the audio stream
            logger.exception("Audio mixing failed")
            outdata.fill(0)

    def _refresh_snapshot(self) -> None:
        project = self._controller.project
        self._snapshot = copy.deepcopy(project) if project else None
        self._use_current()

    def _use_current(self) -> None:
        self._current = self._preview or self._snapshot
        self._worker.set_project(self._current)
        if self._current is not None and any(audio_effects(clip) for _, clip in self._current.iter_clips()):
            # Audio effects are computed in the background; until then the clip plays without them.
            threading.Thread(target=self._controller.audio_effects.prepare, args=(self._current,),
                             daemon=True).start()
        if self._position > self.duration:
            self.seek(self.duration)
        else:
            self._worker.request(self._position)

    def _on_project_opened(self) -> None:
        self.pause()
        self._refresh_snapshot()
        self.seek(0.0)

    def _on_project_closed(self) -> None:
        self.pause()
        self._snapshot = self._preview = self._current = None
        self._worker.set_project(None)
        self._position = 0.0

    def _on_frame_ready(self, _position: float, image: QImage) -> None:
        self.frame_ready.emit(image)
