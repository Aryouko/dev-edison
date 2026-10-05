"""Playback of the montage in the render area (sprint S4 "lecteur temps réel").

The playback state (position, play/pause, volume) is ready and the controls of the
render area are connected to it. What remains (TODO(S4)):

* pictures: a worker thread (``QThread``) renders ``render_frame(copy_of_project, t, ...)``
  for the LAST requested time only, converts it to a ``QImage`` and emits it; the render
  area receives it through :attr:`Player.frame_ready`;
* clock: a ``QTimer`` (~15 ms) advances the position with ``time.perf_counter()``
  during playback, and stops at the end of the montage;
* sound: a ``sounddevice.OutputStream`` whose callback fills each block with
  ``mix_audio(copy_of_project, sample, frames, store) * volume``;
* the threads read a COPY of the project (``copy.deepcopy``) refreshed on
  ``project_changed``: the interface can then edit the project safely.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

SKIP_SECONDS = 5.0  # buttons "retour" / "en avant" of the render area


class Player(QObject):
    """Playback state: position, play/pause, volume.

    Parameters
    ----------
    controller : ProjectController
        Controller of the open project.
    """

    position_changed = Signal(float)
    playing_changed = Signal(bool)
    frame_ready = Signal(QImage)  # emitted by the render thread (TODO(S4))
    volume_changed = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._position = 0.0
        self._playing = False
        self._volume = 1.0
        self._muted = False
        controller.project_opened.connect(lambda: self.seek(0.0))
        controller.project_closed.connect(self.pause)

    # ------------------------------------------------------------ properties
    @property
    def position(self) -> float:
        """Current time (position of the cursor), in seconds."""
        return self._position

    @property
    def duration(self) -> float:
        """Length of the montage, in seconds."""
        project = self._controller.project
        return project.duration if project else 0.0

    @property
    def fps(self) -> float:
        """Frame rate of the project (used by the frame by frame keys ← / →)."""
        project = self._controller.project
        return project.fps if project else 30.0

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
        """Play or pause (button play/pause, Space key)."""
        if self._playing:
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        """Start playback from the current position."""
        # TODO(S4): start the clock timer and the audio stream, then:
        # self._playing = True; self.playing_changed.emit(True)
        self._controller.todo("Lecture de la vidéo", "S4")

    def pause(self) -> None:
        """Pause playback."""
        if self._playing:
            self._playing = False
            # TODO(S4): stop the clock timer and the audio stream.
            self.playing_changed.emit(False)

    def seek(self, position: float) -> None:
        """Go to ``position`` in seconds (ruler click, progress bar, keys)."""
        self._position = min(max(position, 0.0), self.duration)
        self.position_changed.emit(self._position)
        # TODO(S4): ask the render thread for the picture at this position.

    def skip(self, direction: int) -> None:
        """Go back (-1) or forward (+1) by ``SKIP_SECONDS``."""
        self.seek(self._position + direction * SKIP_SECONDS)

    def step_frame(self, direction: int) -> None:
        """Go to the previous (-1) or next (+1) frame."""
        self.seek(self._position + direction / self.fps)

    def set_volume(self, volume: float) -> None:
        """Set the playback volume (0 to 1)."""
        self._volume = min(max(volume, 0.0), 1.0)
        self.volume_changed.emit()

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute the sound."""
        self._muted = muted
        self.volume_changed.emit()

    def refresh(self) -> None:
        """Render the current picture again (e.g. when the full screen opens)."""
        # TODO(S4): ask the render thread for the picture at self._position.

    def shutdown(self) -> None:
        """Stop playback and the threads (the application closes)."""
        self.pause()
        # TODO(S4): stop the render thread (QThread.quit / wait).
