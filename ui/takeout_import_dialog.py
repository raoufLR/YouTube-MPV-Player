"""Google Takeout local data import dialog with beginner-friendly guide."""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import tr

if TYPE_CHECKING:
    from core.takeout_parser import TakeoutInspectionResult
    from services.data_import_service import DataImportService, ImportProgress, ImportResult


class _InspectWorker(QThread):
    finished_inspection = pyqtSignal(object)
    failed_inspection = pyqtSignal(str)

    def __init__(self, service: DataImportService, path: str):
        super().__init__()
        self._service = service
        self._path = path

    def run(self):
        try:
            res = self._service.inspect(self._path)
            self.finished_inspection.emit(res)
        except Exception as exc:
            self.failed_inspection.emit(str(exc))


class _ImportWorker(QThread):
    progress_update = pyqtSignal(object)
    finished_import = pyqtSignal(object)

    def __init__(
        self,
        service: DataImportService,
        path: str,
        selections: dict[str, bool],
        overwrite: bool,
    ):
        super().__init__()
        self._service = service
        self._path = path
        self._selections = selections
        self._overwrite = overwrite
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def run(self):
        try:
            res = self._service.execute_import(
                source_path=self._path,
                selections=self._selections,
                overwrite=self._overwrite,
                progress_callback=self.progress_update.emit,
                cancel_event=self._cancel_event,
            )
            self.finished_import.emit(res)
        except Exception as exc:
            from services.data_import_service import ImportResult

            self.finished_import.emit(
                ImportResult(success=False, error_message=str(exc))
            )


class TakeoutGuideDialog(QDialog):
    """Simple, friendly step-by-step beginner guide for Google Takeout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("How to get your Google Takeout data"))
        self.setFixedSize(540, 480)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(tr("💡 Google Takeout — Simple Beginner Guide"))
        title.setObjectName("takeoutTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            tr(
                "Google Takeout is an official, free tool by Google that lets you "
                "download a complete copy of your YouTube data safely to your computer."
            )
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("takeoutSubtitle")
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        steps = [
            (
                tr("1. Go to Google Takeout"),
                tr(
                    "Open your browser and visit: takeout.google.com\n"
                    "(Sign in with your Google / YouTube account if asked)."
                ),
            ),
            (
                tr("2. Deselect All Products"),
                tr(
                    "At the top of the list, click 'Deselect all'. You only need "
                    "your YouTube data."
                ),
            ),
            (
                tr("3. Check 'YouTube and YouTube Music'"),
                tr(
                    "Scroll down and check only the box for 'YouTube and YouTube Music'.\n"
                    "Optional: Click 'Multiple formats' to confirm JSON is selected."
                ),
            ),
            (
                tr("4. Create Export"),
                tr(
                    "Scroll to the bottom and click 'Next step', then click "
                    "'Create export'."
                ),
            ),
            (
                tr("5. Download & Import"),
                tr(
                    "Google will generate a .zip archive (usually ready within minutes). "
                    "Download the .zip file to your computer, and select it right here "
                    "in this app!"
                ),
            ),
        ]

        for step_title, step_desc in steps:
            card = QFrame()
            card.setObjectName("takeoutCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 10, 10, 10)
            card_layout.setSpacing(4)

            st = QLabel(step_title)
            st.setObjectName("takeoutStepTitle")
            card_layout.addWidget(st)

            sd = QLabel(step_desc)
            sd.setWordWrap(True)
            sd.setObjectName("takeoutStepText")
            card_layout.addWidget(sd)

            content_layout.addWidget(card)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close_btn = QPushButton(tr("Got it!"))
        close_btn.setObjectName("primaryButton")
        close_btn.setFixedHeight(36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class TakeoutImportDialog(QDialog):
    """Main dialog to inspect, configure, and execute Takeout data import."""

    def __init__(self, data_import_service: DataImportService, parent=None):
        super().__init__(parent)
        self._service = data_import_service
        self._inspect_worker: _InspectWorker | None = None
        self._import_worker: _ImportWorker | None = None
        self._selected_path = ""
        self._inspection_result: TakeoutInspectionResult | None = None
        self._closing = False

        self.setWindowTitle(tr("Import Google Takeout Archive"))
        self.setFixedSize(580, 560)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel(tr("Import YouTube Data from Google Takeout"))
        title.setObjectName("takeoutTitle")
        title_box.addWidget(title)

        subtitle = QLabel(
            tr("Import your playlists, liked videos, history and subscriptions locally.")
        )
        subtitle.setObjectName("takeoutSubtitle")
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)

        guide_btn = QPushButton(tr("💡 Beginner Guide"))
        guide_btn.setObjectName("takeoutSecondaryButton")
        guide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        guide_btn.clicked.connect(self._show_guide)
        header_layout.addWidget(guide_btn)
        layout.addLayout(header_layout)

        # File Selection Card
        sel_card = QFrame()
        sel_card.setObjectName("takeoutCard")
        sel_layout = QVBoxLayout(sel_card)
        sel_layout.setContentsMargins(12, 12, 12, 12)
        sel_layout.setSpacing(8)

        sel_label = QLabel(tr("Select Takeout ZIP file or extracted folder:"))
        sel_label.setObjectName("takeoutSectionTitle")
        sel_layout.addWidget(sel_label)

        file_row = QHBoxLayout()
        self._path_label = QLabel(tr("No archive selected"))
        self._path_label.setObjectName("takeoutPath")
        file_row.addWidget(self._path_label, 1)

        browse_zip_btn = QPushButton(tr("Browse ZIP..."))
        browse_zip_btn.setObjectName("takeoutSecondaryButton")
        browse_zip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_zip_btn.clicked.connect(self._browse_zip)
        file_row.addWidget(browse_zip_btn)

        browse_dir_btn = QPushButton(tr("Browse Folder..."))
        browse_dir_btn.setObjectName("takeoutSecondaryButton")
        browse_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_dir_btn.clicked.connect(self._browse_folder)
        file_row.addWidget(browse_dir_btn)

        sel_layout.addLayout(file_row)
        layout.addWidget(sel_card)

        # Items Card (Found data)
        self._items_card = QFrame()
        self._items_card.setObjectName("takeoutCard")
        items_layout = QVBoxLayout(self._items_card)
        items_layout.setContentsMargins(12, 12, 12, 12)
        items_layout.setSpacing(6)

        items_title = QLabel(tr("Data detected in archive:"))
        items_title.setObjectName("takeoutSectionTitle")
        items_layout.addWidget(items_title)

        self._check_likes = QCheckBox(tr("Liked Videos (0 found)"))
        self._check_likes.setChecked(True)
        items_layout.addWidget(self._check_likes)

        self._check_watch_later = QCheckBox(tr("Watch Later (0 found)"))
        self._check_watch_later.setChecked(True)
        items_layout.addWidget(self._check_watch_later)

        self._check_playlists = QCheckBox(tr("Playlists (0 found)"))
        self._check_playlists.setChecked(True)
        items_layout.addWidget(self._check_playlists)

        self._check_history = QCheckBox(tr("Watch History (0 found)"))
        self._check_history.setChecked(True)
        items_layout.addWidget(self._check_history)

        self._check_subs = QCheckBox(tr("Subscriptions (0 found)"))
        self._check_subs.setChecked(True)
        items_layout.addWidget(self._check_subs)

        self._items_card.setEnabled(False)
        layout.addWidget(self._items_card)

        # Conflict resolution
        conflict_card = QFrame()
        conflict_card.setObjectName("takeoutCard")
        conflict_layout = QVBoxLayout(conflict_card)
        conflict_layout.setContentsMargins(12, 12, 12, 12)
        conflict_layout.setSpacing(6)

        conflict_title = QLabel(tr("Collision Resolution:"))
        conflict_title.setObjectName("takeoutSectionTitle")
        conflict_layout.addWidget(conflict_title)

        self._btn_group = QButtonGroup(self)
        self._radio_skip = QRadioButton(
            tr("Skip duplicates (Keep current local data) [Recommended]")
        )
        self._radio_skip.setChecked(True)
        self._btn_group.addButton(self._radio_skip)
        conflict_layout.addWidget(self._radio_skip)

        self._radio_overwrite = QRadioButton(
            tr("Overwrite existing items with Takeout data")
        )
        self._btn_group.addButton(self._radio_overwrite)
        conflict_layout.addWidget(self._radio_overwrite)

        layout.addWidget(conflict_card)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setObjectName("takeoutStatus")
        self._status_label.hide()
        layout.addWidget(self._status_label)

        # Actions
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._cancel_btn = QPushButton(tr("Cancel"))
        self._cancel_btn.setObjectName("takeoutSecondaryButton")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)

        self._import_btn = QPushButton(tr("Start Import"))
        self._import_btn.setObjectName("primaryButton")
        self._import_btn.setFixedHeight(34)
        self._import_btn.setEnabled(False)
        self._import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_btn.clicked.connect(self._start_import)
        btn_layout.addWidget(self._import_btn)

        layout.addLayout(btn_layout)

    def _show_guide(self):
        dlg = TakeoutGuideDialog(self)
        dlg.exec()

    def _browse_zip(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Select Google Takeout ZIP archive"),
            "",
            "ZIP Archives (*.zip);;All Files (*.*)",
        )
        if path:
            self._analyze_path(path)

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(
            self,
            tr("Select extracted Takeout folder"),
            "",
        )
        if path:
            self._analyze_path(path)

    def _analyze_path(self, path: str):
        self._selected_path = path
        self._path_label.setText(os.path.basename(path))
        self._status_label.setText(tr("Analyzing archive contents..."))
        self._status_label.show()
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_bar.show()
        self._import_btn.setEnabled(False)

        self._inspect_worker = _InspectWorker(self._service, path)
        self._inspect_worker.finished_inspection.connect(self._on_inspection_finished)
        self._inspect_worker.failed_inspection.connect(self._on_inspection_failed)
        self._inspect_worker.start()

    def _on_inspection_finished(self, res: TakeoutInspectionResult):
        if self._closing:
            return
        self._inspection_result = res
        self._progress_bar.hide()
        self._status_label.hide()
        self._items_card.setEnabled(True)

        self._check_likes.setText(
            tr("Liked Videos ({count} found)").format(count=res.likes_count)
        )
        self._check_likes.setChecked(res.has_likes)

        self._check_watch_later.setText(
            tr("Watch Later ({count} found)").format(count=res.watch_later_count)
        )
        self._check_watch_later.setChecked(res.has_watch_later)

        total_pl_vids = sum(count for _, count in res.playlists)
        self._check_playlists.setText(
            tr("Playlists ({playlists} playlists with {videos} videos)").format(
                playlists=len(res.playlists), videos=total_pl_vids
            )
        )
        self._check_playlists.setChecked(bool(res.playlists))

        self._check_history.setText(
            tr("Watch History ({count} items found)").format(count=res.history_count)
        )
        self._check_history.setChecked(res.has_history)

        self._check_subs.setText(
            tr("Subscriptions ({count} channels)").format(
                count=res.subscriptions_count
            )
        )
        self._check_subs.setChecked(res.has_subscriptions)

        if res.total_items > 0:
            self._import_btn.setEnabled(True)
        else:
            QMessageBox.information(
                self,
                tr("No Data Found"),
                tr(
                    "No YouTube playlists, watch history, or liked videos were found "
                    "in this file.\nPlease make sure you selected the Takeout archive "
                    "containing YouTube data."
                ),
            )

    def _on_inspection_failed(self, error: str):
        self._progress_bar.hide()
        self._status_label.hide()
        QMessageBox.warning(
            self,
            tr("Inspection Error"),
            tr("Failed to read archive: {error}").format(error=error),
        )

    def _start_import(self):
        if not self._selected_path:
            return

        selections = {
            "likes": self._check_likes.isChecked(),
            "watch_later": self._check_watch_later.isChecked(),
            "playlists": self._check_playlists.isChecked(),
            "history": self._check_history.isChecked(),
            "subscriptions": self._check_subs.isChecked(),
        }

        overwrite = self._radio_overwrite.isChecked()

        self._items_card.setEnabled(False)
        self._import_btn.setEnabled(False)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._status_label.setText(tr("Starting import..."))
        self._status_label.show()

        self._import_worker = _ImportWorker(
            self._service,
            self._selected_path,
            selections,
            overwrite,
        )
        self._import_worker.progress_update.connect(self._on_progress_update)
        self._import_worker.finished_import.connect(self._on_import_finished)
        self._import_worker.start()

    def _on_progress_update(self, progress: ImportProgress):
        if self._closing:
            return
        self._progress_bar.setValue(int(progress.percent))
        self._status_label.setText(progress.stage)

    def _on_import_finished(self, res: ImportResult):
        if self._closing:
            return
        self._progress_bar.hide()
        self._status_label.hide()

        if res.success:
            msg = "\n".join(
                [
                    tr("Import completed successfully!"),
                    "",
                    tr("• Watch History items added: {count}").format(
                        count=res.imported_history
                    ),
                    tr("• Liked Videos added: {count}").format(
                        count=res.imported_likes
                    ),
                    tr("• Watch Later videos added: {count}").format(
                        count=res.imported_watch_later
                    ),
                    tr("• Custom Playlists added: {count}").format(
                        count=res.imported_playlists
                    ),
                    tr("• Subscriptions saved: {count}").format(
                        count=res.imported_subscriptions
                    ),
                ]
            )
            QMessageBox.information(self, tr("Import Succeeded"), msg)
            self.accept()
        else:
            QMessageBox.warning(
                self,
                tr("Import Result"),
                tr("Import could not complete:\n{error}").format(
                    error=res.error_message
                ),
            )
            self._items_card.setEnabled(True)
            self._import_btn.setEnabled(True)

    def _stop_running_workers(self, timeout_ms: int = 5000) -> bool:
        """Cancel and join workers before the dialog can be destroyed.

        A ``QThread`` still running when its Python owner is collected makes
        Qt abort the process, so closing the window mid-import has to wait
        for the worker to stop.
        """
        stopped = True
        for worker in (self._inspect_worker, self._import_worker):
            if worker is None or not worker.isRunning():
                continue
            cancel = getattr(worker, "cancel", None)
            if cancel is not None:
                cancel()
            if not worker.wait(timeout_ms):
                stopped = False
        return stopped

    def reject(self):
        if not self._stop_running_workers():
            self._status_label.setText(tr("Finishing the current operation..."))
            self._status_label.show()
            return
        self._closing = True
        super().reject()

    def closeEvent(self, event):
        if not self._stop_running_workers():
            self._status_label.setText(tr("Finishing the current operation..."))
            self._status_label.show()
            event.ignore()
            return
        self._closing = True
        super().closeEvent(event)

    def _on_cancel(self):
        self._status_label.setText(tr("Cancelling import..."))
        self._status_label.show()
        self.reject()
