"""Export tab (CDC "Onglet Export"): output settings, progress and cancellation.

Ready: every field of the CDC, the "Parcourir" dialog, the size estimate, the
progress area (hidden). To do (S6): run :func:`edison.render.exporter.export_project`
in a ``QThread`` when "Exporter" is clicked (see :meth:`ExportPanel._start_export`).
"""

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from edison.render.exporter import FORMATS, QUALITIES, ExportSettings, estimate_size
from edison.ui import icons
from edison.ui.widgets import ComboBox
from edison.utils import format_size, format_time

RESOLUTIONS = {"source": None, "1080": 1080, "720": 720, "480": 480}  # None = size of the project
FRAME_RATES = (24, 30, 60)


class ExportPanel(QWidget):
    """Export tab."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller

        title = QLabel("EXPORTER LA VIDÉO")
        title.setObjectName("SectionLabel")
        file_label = QLabel("Nom et emplacement du fichier")
        file_label.setObjectName("Muted")
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
        self._fps.setCurrentIndex(FRAME_RATES.index(30))
        self._quality = ComboBox()
        for key, quality in QUALITIES.items():
            self._quality.addItem(quality.label, key)
        self._quality.setCurrentIndex(1)
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

        # Progress area, shown during the export (CDC "Pendant l'export")
        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._remaining = QLabel()
        self._remaining.setObjectName("Muted")
        self._cancel_button = QPushButton("Annuler")
        # TODO(S6): self._cancel_button.clicked.connect(...) -> ask the export thread to stop.
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
        for item in (title, file_label, path_row, form, self._estimate, self._export_button, self._progress_box):
            if isinstance(item, QWidget):
                layout.addWidget(item)
            else:
                layout.addLayout(item)
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
        controller.project_changed.connect(self._fill_resolutions)

    # ------------------------------------------------------------- settings
    def _on_project_opened(self) -> None:
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation) or str(Path.home())
        extension = FORMATS[self._format.currentData()].extension
        self._path.setText(str(Path(folder) / f"{self._controller.project.name}{extension}"))
        self._fill_resolutions()

    def _fill_resolutions(self) -> None:
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

    def _on_format_changed(self) -> None:
        export_format = FORMATS[self._format.currentData()]
        if self._path.text().strip():
            self._path.setText(str(Path(self._path.text().strip()).with_suffix(export_format.extension)))
        for combo in (self._resolution, self._fps):  # no picture in an audio file
            combo.setEnabled(not export_format.audio_only)
        self._update_estimate()

    def settings(self) -> ExportSettings:
        """Return the choices of the tab."""
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
        size = estimate_size(self.settings(), project.duration)
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
        """Button "Exporter".

        TODO(S6):
            * check the timeline is not empty and a file name is given; ask before replacing a file;
            * create a ``QThread`` subclass whose ``run()`` calls
              ``export_project(copy.deepcopy(project), self.settings(), store, on_progress, is_cancelled)``
              and emits signals (progress, succeeded, failed, cancelled) -> the interface stays usable;
            * show ``self._progress_box`` and call :meth:`_show_progress` on each progress signal;
            * at the end: message with an "Ouvrir le dossier" button
              (``QDesktopServices.openUrl(QUrl.fromLocalFile(folder))``), or the error message.
        """
        self._controller.todo("Export de la vidéo", "S6")

    def _show_progress(self, fraction: float, remaining: float | None) -> None:
        """Update the progress area (percentage and estimated remaining time)."""
        self._progress.setValue(int(fraction * 1000))
        self._progress.setFormat(f"{fraction * 100:.0f} %")
        if remaining is not None:
            self._remaining.setText(f"Temps restant estimé : {format_time(remaining, precise=False)}")
