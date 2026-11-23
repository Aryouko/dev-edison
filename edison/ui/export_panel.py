"""Export tab: output settings, progress and cancellation."""

import copy
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from edison.render.exporter import (FORMATS, QUALITIES, ExportCancelled, ExportError, ExportSettings, estimate_size,
                                    export_project)
from edison.ui import icons
from edison.ui.widgets import ComboBox
from edison.utils import format_size, format_time

RESOLUTIONS = {"source": None, "1080": 1080, "720": 720, "480": 480}
FRAME_RATES = (24, 30, 60)


class _ExportWorker(QThread):
    """Runs :func:`export_project` outside of the interface thread."""

    progress = Signal(float, object)  # fraction, remaining seconds or None
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, project, settings, store, effects, parent=None):
        super().__init__(parent)
        self._project = project
        self._settings = settings
        self._store = store
        self._effects = effects
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            export_project(self._project, self._settings, self._store,
                           on_progress=self.progress.emit, is_cancelled=lambda: self._cancel_requested,
                           effects=self._effects)
        except ExportCancelled:
            self.cancelled.emit()
        except ExportError as error:
            self.failed.emit(str(error))
        except Exception as error:  # unexpected: still report it instead of failing silently
            self.failed.emit(f"Erreur inattendue : {error}")
        else:
            self.succeeded.emit(self._settings.path)


class ExportPanel(QWidget):
    """Export tab."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._worker: _ExportWorker | None = None

        title = QLabel("EXPORTER LA VIDÉO")
        title.setObjectName("SectionLabel")

        self._path = QLineEdit()
        self._path.setPlaceholderText("Nom et emplacement du fichier")
        browse = QPushButton("Parcourir…")
        browse.setIcon(icons.icon("folder", size=16))
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self._path, 1)
        path_row.addWidget(browse)

        self._format = ComboBox()
        for key, export_format in FORMATS.items():
            self._format.addItem(export_format.label, key)
        self._resolution = ComboBox()
        self._fps = ComboBox()
        for fps in FRAME_RATES:
            self._fps.addItem(f"{fps} images/s", fps)
        self._quality = ComboBox()
        for key, quality in QUALITIES.items():
            self._quality.addItem(quality.label, key)
        self._quality.setCurrentIndex(1)

        file_label = QLabel("Nom et emplacement du fichier")
        file_label.setObjectName("Muted")
        form = QFormLayout()
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow("Format", self._format)
        form.addRow("Résolution", self._resolution)
        form.addRow("Images/s", self._fps)
        form.addRow("Qualité", self._quality)

        self._estimate = QLabel()
        self._estimate.setObjectName("Muted")
        self._estimate.setWordWrap(True)

        self._export_button = QPushButton("Exporter")
        self._export_button.setObjectName("Primary")
        self._export_button.setIcon(icons.icon("export", size=18))
        self._export_button.setMinimumHeight(40)
        self._export_button.clicked.connect(self._start_export)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._remaining = QLabel()
        self._remaining.setObjectName("Muted")
        self._cancel_button = QPushButton("Annuler")
        self._cancel_button.clicked.connect(self._cancel_export)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self._remaining, 1)
        progress_row.addWidget(self._cancel_button)
        self._progress_box = QWidget()
        progress_layout = QVBoxLayout(self._progress_box)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.addWidget(self._progress)
        progress_layout.addLayout(progress_row)
        self._progress_box.hide()

        content = QWidget()
        content.setObjectName("Transparent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 6, 8, 0)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(file_label)
        layout.addLayout(path_row)
        layout.addLayout(form)
        layout.addWidget(self._estimate)
        layout.addWidget(self._export_button)
        layout.addWidget(self._progress_box)
        layout.addStretch()
        scroll = QScrollArea()  # keeps every field readable when the window is small
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._format.currentIndexChanged.connect(self._on_format_changed)
        for combo in (self._resolution, self._fps, self._quality):
            combo.currentIndexChanged.connect(self._update_estimate)
        controller.project_opened.connect(self._on_project_opened)
        controller.project_changed.connect(self._on_project_changed)
        controller.project_renamed.connect(self._reset_path)

    # ------------------------------------------------------------- settings
    def _on_project_opened(self) -> None:
        project = self._controller.project
        nearest = min(FRAME_RATES, key=lambda fps: abs(fps - project.fps))
        self._fps.setCurrentIndex(FRAME_RATES.index(nearest))
        self._reset_path()
        self._on_project_changed()

    def _on_project_changed(self) -> None:
        project = self._controller.project
        if project is None:
            return
        current = self._resolution.currentData() or "source"
        self._resolution.blockSignals(True)
        self._resolution.clear()
        for key, height in RESOLUTIONS.items():
            label = f"Source ({project.width} × {project.height})" if height is None else f"{height}p"
            self._resolution.addItem(label, key)
        self._resolution.setCurrentIndex(max(0, self._resolution.findData(current)))
        self._resolution.blockSignals(False)
        self._update_estimate()

    def _reset_path(self) -> None:
        project = self._controller.project
        if project is None:
            return
        folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation) or Path.home())
        self._path.setText(str(folder / f"{project.name}{FORMATS[self._format.currentData()].extension}"))

    def _on_format_changed(self) -> None:
        export_format = FORMATS[self._format.currentData()]
        text = self._path.text().strip()
        if text:
            self._path.setText(str(Path(text).with_suffix(export_format.extension)))
        for combo in (self._resolution, self._fps):
            combo.setEnabled(not export_format.audio_only)
        self._update_estimate()

    def _settings(self) -> ExportSettings:
        project = self._controller.project
        height = RESOLUTIONS[self._resolution.currentData() or "source"]
        if height is None:
            width, height = project.width, project.height
        else:
            width = int(round(height * project.width / project.height / 2)) * 2
        return ExportSettings(path=self._path.text().strip(), format=self._format.currentData(), width=width,
                              height=height, fps=self._fps.currentData(), quality=self._quality.currentData())

    def _update_estimate(self) -> None:
        project = self._controller.project
        if project is None:
            return
        if project.duration <= 0:
            self._estimate.setText("La trame est vide : ajoutez des clips pour pouvoir exporter.")
            return
        size = estimate_size(self._settings(), project.duration)
        self._estimate.setText(f"Durée : {format_time(project.duration, precise=False)}   •   "
                               f"Taille estimée : ≈ {format_size(size)}")

    def _browse(self) -> None:
        export_format = FORMATS[self._format.currentData()]
        path, _ = QFileDialog.getSaveFileName(self, "Exporter sous", self._path.text(),
                                              f"{export_format.label} (*{export_format.extension})")
        if path:
            self._path.setText(str(Path(path).with_suffix(export_format.extension)))

    # --------------------------------------------------------------- export
    def _start_export(self) -> None:
        project = self._controller.project
        settings = self._settings()
        if project.duration <= 0:
            QMessageBox.warning(self, "Export impossible", "La trame est vide : ajoutez au moins un clip.")
            return
        if not settings.path:
            QMessageBox.warning(self, "Export impossible", "Choisissez le nom et l'emplacement du fichier.")
            return
        settings.path = str(Path(settings.path).with_suffix(FORMATS[settings.format].extension))
        self._path.setText(settings.path)
        if Path(settings.path).exists():
            answer = QMessageBox.question(self, "Fichier existant",
                                          f"« {Path(settings.path).name} » existe déjà. Voulez-vous le remplacer ?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._worker = _ExportWorker(copy.deepcopy(project), settings, self._controller.audio_store,
                                     self._controller.audio_effects, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished.connect(self._on_worker_finished)
        self._progress.setValue(0)
        self._progress.setFormat("0 %")
        self._remaining.setText("Préparation…")
        self._cancel_button.setEnabled(True)
        self._progress_box.show()
        self._export_button.setEnabled(False)
        self._worker.start()

    @property
    def is_exporting(self) -> bool:
        """True while an export is running."""
        return self._worker is not None

    def _cancel_export(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._cancel_button.setEnabled(False)
            self._remaining.setText("Annulation…")

    def _on_progress(self, fraction: float, remaining) -> None:
        self._progress.setValue(int(fraction * 1000))
        self._progress.setFormat(f"{fraction * 100:.0f} %")
        if remaining is not None:
            self._remaining.setText(f"Temps restant estimé : {format_time(remaining, precise=False)}")

    def _on_succeeded(self, path: str) -> None:
        box = QMessageBox(QMessageBox.Icon.Information, "Export terminé",
                          f"La vidéo a été exportée :\n{path}", parent=self)
        open_folder = box.addButton("Ouvrir le dossier", QMessageBox.ButtonRole.ActionRole)
        box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is open_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Échec de l'export", message)

    def _on_cancelled(self) -> None:
        self._remaining.setText("Export annulé.")

    def _on_worker_finished(self) -> None:
        self._worker.deleteLater()
        self._worker = None
        self._export_button.setEnabled(True)
        self._cancel_button.setEnabled(False)
        if self._remaining.text() != "Export annulé.":
            self._progress_box.hide()

    def cancel_and_wait(self) -> None:
        """Stop a running export (the application is closing)."""
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait()

