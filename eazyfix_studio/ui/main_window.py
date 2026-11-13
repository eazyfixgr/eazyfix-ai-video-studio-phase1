"""Main beginner-oriented desktop workspace and project editing workflow."""

from __future__ import annotations

import copy
import os
import re
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..assistant import apply_offline_edit, create_from_prompt
from ..exporter import ExportWorker
from ..models import Asset, Layer, Project, Scene, new_id, sample_project
from ..project_io import autosave_path, import_asset, load_project, save_project
from ..renderer import render_frame
from .panels import AssetGallery, ChatPanel, InspectorPanel, TimelinePanel
from .preview import PreviewCanvas


APP_STYLE = """
QMainWindow, QWidget { background: #101321; color: #E9EBF6; font-family: 'Segoe UI'; font-size: 10pt; }
QWidget#chatHistory, QWidget#chatInput, QWidget#assetShelf, QWidget#sceneTimeline { background: #171B2D; border: 1px solid #292F49; border-radius: 10px; }
QLabel#panelTitle { font-size: 16pt; font-weight: 700; color: #F5F6FF; }
QLabel#sectionLabel { color: #939DBB; font-size: 9pt; font-weight: 700; letter-spacing: 1px; }
QLabel#mutedText { color: #A4ADC8; }
QLabel#modeBadge { color: #B8FA79; background: #243321; border-radius: 7px; padding: 4px 7px; font-size: 8pt; font-weight: 700; }
QPushButton { background: #222840; border: 1px solid #343B5C; border-radius: 8px; padding: 7px 10px; color: #E7EAF6; }
QPushButton:hover { background: #303858; border-color: #656FC0; }
QPushButton#primaryButton { background: #6657EF; border-color: #7D70FF; font-weight: 700; }
QPushButton#primaryButton:hover { background: #7768FF; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #191E31; border: 1px solid #303753; border-radius: 7px; padding: 6px; selection-background-color: #6558E8; }
QComboBox::drop-down { border: 0; }
QListWidget { outline: 0; }
QListWidget::item { padding: 3px; border-radius: 8px; }
QListWidget::item:selected { background: #30375A; border: 1px solid #7267F6; }
QSlider::groove:horizontal { height: 5px; background: #333A59; border-radius: 2px; }
QSlider::handle:horizontal { background: #54D7EF; width: 13px; margin: -5px 0; border-radius: 6px; }
QSplitter::handle { background: #252A40; width: 2px; }
QToolTip { background: #252B43; color: white; border: 1px solid #4A5274; padding: 5px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EazyFix AI Video Studio")
        self.setMinimumSize(1120, 720)
        self.resize(1540, 960)
        self.setAcceptDrops(True)
        self.setStyleSheet(APP_STYLE)
        self.project = sample_project()
        self.project_path: Path | None = None
        self.current_time = 0.0
        self.current_scene = 0
        self.selected_layer_id = ""
        self._undo_stack: list[tuple[dict, str]] = []
        self._redo_stack: list[tuple[dict, str]] = []
        self._drag_before: dict | None = None
        self._last_preview_scene = -1
        self._fullscreen_dialog: QDialog | None = None
        self._fullscreen_canvas: PreviewCanvas | None = None
        self._export_worker: ExportWorker | None = None
        self._export_dialog: QProgressDialog | None = None
        self.preview_size = 380

        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self._build_toolbar())

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.chat = ChatPanel()
        self.gallery = AssetGallery()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)
        left_layout.addWidget(self.chat, 1)
        left_layout.addWidget(self.gallery, 0)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(8, 8, 8, 8)
        center_layout.setSpacing(8)
        center_layout.addWidget(self._build_preview_toolbar())
        self.preview = PreviewCanvas()
        center_layout.addWidget(self.preview, 1)
        center_layout.addWidget(self._build_playback_controls())
        self.timeline = TimelinePanel()
        center_layout.addWidget(self.timeline, 0)

        self.inspector = InspectorPanel()
        self.inspector.hide()
        self.splitter.addWidget(left)
        self.splitter.addWidget(center)
        self.splitter.addWidget(self.inspector)
        self.splitter.setSizes([330, 900, 280])
        main.addWidget(self.splitter, 1)
        self.statusBar().showMessage("Έτοιμο · Local mode · Αποθήκευση αυτόματης ανάκτησης ενεργή")

        self.play_timer = QTimer(self)
        self.play_timer.setInterval(80)
        self.play_timer.timeout.connect(self._play_tick)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(45_000)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start()

        self._connect_signals()
        self._create_actions()
        self._refresh_project()
        self._offer_recovery()

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("appToolbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        title = QLabel("EazyFix <b>AI Video Studio</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        layout.addSpacing(14)
        for label, callback in (("New", self.new_project), ("Open", self.open_project), ("Save", self.save_current_project), ("Undo", self.undo), ("Redo", self.redo)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            layout.addWidget(button)
        layout.addStretch(1)
        self.project_name = QLabel(self.project.name)
        self.project_name.setObjectName("mutedText")
        layout.addWidget(self.project_name)
        self.inspector_toggle = QPushButton("Inspector")
        self.inspector_toggle.clicked.connect(self._toggle_inspector)
        layout.addWidget(self.inspector_toggle)
        export = QPushButton("Export MP4  ↗")
        export.setObjectName("primaryButton")
        export.clicked.connect(self.export_video)
        layout.addWidget(export)
        return bar

    def _build_preview_toolbar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 0, 4, 0)
        preview_label = QLabel("LIVE PREVIEW")
        preview_label.setObjectName("sectionLabel")
        layout.addWidget(preview_label)
        layout.addStretch(1)
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("Draft preview", 300)
        self.quality_combo.addItem("High preview", 520)
        self.quality_combo.currentIndexChanged.connect(self._quality_changed)
        layout.addWidget(self.quality_combo)
        self.ratio_combo = QComboBox()
        self.ratio_combo.addItem("Portrait  9:16", (1080, 1920))
        self.ratio_combo.addItem("Landscape  16:9", (1920, 1080))
        self.ratio_combo.addItem("Square  1:1", (1080, 1080))
        self.ratio_combo.currentIndexChanged.connect(self._ratio_changed)
        layout.addWidget(self.ratio_combo)
        self.fullscreen_button = QPushButton("⛶")
        self.fullscreen_button.setToolTip("Fullscreen preview")
        self.fullscreen_button.clicked.connect(self._show_fullscreen)
        layout.addWidget(self.fullscreen_button)
        return bar

    def _build_playback_controls(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 0, 4, 2)
        self.play_button = QPushButton("▶  Play")
        self.play_button.clicked.connect(self._toggle_play)
        layout.addWidget(self.play_button)
        self.time_label = QLabel("00:00.0 / 00:10.0")
        self.time_label.setMinimumWidth(130)
        self.time_label.setObjectName("mutedText")
        layout.addWidget(self.time_label)
        self.scrubber = QSlider(Qt.Orientation.Horizontal)
        self.scrubber.setRange(0, 1000)
        self.scrubber.valueChanged.connect(self._scrub)
        layout.addWidget(self.scrubber, 1)
        return bar

    def _connect_signals(self) -> None:
        self.chat.prompt_submitted.connect(self._handle_prompt)
        self.chat.import_requested.connect(self.import_assets)
        self.gallery.import_requested.connect(self.import_assets)
        self.gallery.place_requested.connect(self._place_asset)
        self.gallery.asset_edited.connect(self._edit_asset)
        self.inspector.layer_changed.connect(self._inspector_changed)
        self.preview.layer_selected.connect(self._select_layer)
        self.preview.layer_moved.connect(self._drag_layer)
        self.preview.drag_started.connect(self._begin_drag)
        self.preview.drag_finished.connect(self._finish_drag)
        self.preview.text_edit_requested.connect(self._edit_text_direct)
        self.timeline.scene_selected.connect(self._select_scene)
        self.timeline.duration_adjusted.connect(self._adjust_scene_duration)
        self.timeline.scene_added.connect(self._add_scene)
        self.timeline.scene_duplicated.connect(self._duplicate_scene)
        self.timeline.scene_deleted.connect(self._delete_scene)
        self.timeline.scene_moved.connect(self._move_scene)

    def _create_actions(self) -> None:
        shortcuts = (("Save project", "Ctrl+S", self.save_current_project), ("Open project", "Ctrl+O", self.open_project), ("Undo", "Ctrl+Z", self.undo), ("Redo", "Ctrl+Y", self.redo), ("Export", "Ctrl+E", self.export_video))
        for name, sequence, callback in shortcuts:
            action = QAction(name, self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(callback)
            self.addAction(action)

    def _refresh_project(self, *, rebuild_timeline: bool = True) -> None:
        self.project.validate()
        self.current_scene = max(0, min(self.current_scene, len(self.project.scenes) - 1))
        self.current_time = max(0.0, min(self.current_time, self.project.duration))
        self.project_name.setText(self.project.name)
        size = self.project.width, self.project.height
        index = next((i for i in range(self.ratio_combo.count()) if self.ratio_combo.itemData(i) == size), 0)
        self.ratio_combo.blockSignals(True)
        self.ratio_combo.setCurrentIndex(index)
        self.ratio_combo.blockSignals(False)
        self.preview.set_project(self.project, self.current_scene)
        self.preview.set_selected_layer(self.selected_layer_id)
        if rebuild_timeline:
            self.timeline.set_project(self.project, self.current_scene)
        self.gallery.set_assets(self.project.assets)
        self.inspector.set_layer(self.project, self._selected_layer())
        self._render_preview()
        self._update_time_label()

    def _selected_layer(self) -> Layer | None:
        if not self.project.scenes:
            return None
        return next((layer for layer in self.project.scenes[self.current_scene].layers if layer.id == self.selected_layer_id), None)

    def _render_preview(self) -> None:
        ratio = self.project.width / self.project.height
        if ratio >= 1:
            size = (self.preview_size, max(1, round(self.preview_size / ratio)))
        else:
            size = (max(1, round(self.preview_size * ratio)), self.preview_size)
        try:
            image = render_frame(self.project, self.current_time, size)
            self.preview.set_frame(image)
            if self._fullscreen_canvas:
                self._fullscreen_canvas.set_project(self.project, self.current_scene)
                self._fullscreen_canvas.set_frame(image)
        except Exception as error:
            self.statusBar().showMessage(f"Preview error: {error}", 6000)

    def _update_time_label(self) -> None:
        def stamp(seconds: float) -> str:
            whole = int(max(0, seconds))
            return f"{whole // 60:02d}:{whole % 60:02d}.{int((seconds % 1) * 10)}"

        self.time_label.setText(f"{stamp(self.current_time)} / {stamp(self.project.duration)}")
        self.scrubber.blockSignals(True)
        self.scrubber.setValue(round(self.current_time / max(0.1, self.project.duration) * 1000))
        self.scrubber.blockSignals(False)

    def _scene_at_time(self, seconds: float) -> int:
        cursor = 0.0
        for index, scene in enumerate(self.project.scenes):
            cursor += scene.duration
            if seconds < cursor or index == len(self.project.scenes) - 1:
                return index
        return 0

    def _scrub(self, value: int) -> None:
        self.current_time = self.project.duration * value / 1000
        if self.play_timer.isActive():
            self._play_started_at = time.monotonic() - self.current_time
        self.current_scene = self._scene_at_time(self.current_time)
        self._sync_scene_selection()
        self._render_preview()
        self._update_time_label()

    def _sync_scene_selection(self) -> None:
        if self.current_scene != self._last_preview_scene:
            self.timeline.current_index = self.current_scene
            self.timeline.list.setCurrentRow(self.current_scene)
            self._last_preview_scene = self.current_scene
            if not any(layer.id == self.selected_layer_id for layer in self.project.scenes[self.current_scene].layers):
                self.selected_layer_id = ""
                self.preview.set_selected_layer("")
                self.inspector.set_layer(self.project, None)

    def _toggle_play(self) -> None:
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.play_button.setText("▶  Play")
            return
        if self.current_time >= self.project.duration:
            self.current_time = 0.0
        self._play_started_at = time.monotonic() - self.current_time
        self.play_button.setText("Ⅱ  Pause")
        self.play_timer.start()

    def _play_tick(self) -> None:
        self.current_time = time.monotonic() - self._play_started_at
        if self.current_time >= self.project.duration:
            self.current_time = self.project.duration
            self.play_timer.stop()
            self.play_button.setText("▶  Play")
        self.current_scene = self._scene_at_time(self.current_time)
        self._sync_scene_selection()
        self._render_preview()
        self._update_time_label()

    def _quality_changed(self, index: int) -> None:
        self.preview_size = int(self.quality_combo.itemData(index) or 300)
        self._render_preview()

    def _ratio_changed(self, index: int) -> None:
        size = self.ratio_combo.itemData(index)
        if not size or (self.project.width, self.project.height) == size:
            return
        self._commit("Changed video aspect ratio", lambda: self._set_canvas(size))

    def _set_canvas(self, size: tuple[int, int]) -> None:
        self.project.width, self.project.height = size

    def _toggle_inspector(self) -> None:
        self.inspector.setVisible(not self.inspector.isVisible())

    def _show_fullscreen(self) -> None:
        if self._fullscreen_dialog:
            self._fullscreen_dialog.close()
        dialog = QDialog(self)
        dialog.setWindowTitle("EazyFix Studio — Preview (Esc to close)")
        dialog.setStyleSheet("QDialog { background: #080A13; }")
        layout = QVBoxLayout(dialog)
        canvas = PreviewCanvas(dialog)
        canvas.set_project(self.project, self.current_scene)
        layout.addWidget(canvas)
        ratio = self.project.width / self.project.height
        size = (900, round(900 / ratio)) if ratio >= 1 else (round(900 * ratio), 900)
        canvas.set_frame(render_frame(self.project, self.current_time, size))
        self._fullscreen_dialog, self._fullscreen_canvas = dialog, canvas
        dialog.finished.connect(lambda: self._clear_fullscreen(dialog))
        dialog.showFullScreen()

    def _clear_fullscreen(self, dialog: QDialog) -> None:
        if self._fullscreen_dialog is dialog:
            self._fullscreen_dialog = None
            self._fullscreen_canvas = None

    def _select_layer(self, layer_id: str) -> None:
        self.selected_layer_id = layer_id
        self.preview.set_selected_layer(layer_id)
        self.inspector.set_layer(self.project, self._selected_layer())
        if layer_id and not self.inspector.isVisible():
            self.inspector.show()
            self.splitter.setSizes([320, 870, 300])

    def _inspector_changed(self, layer_id: str, values: dict) -> None:
        target = next((layer for scene in self.project.scenes for layer in scene.layers if layer.id == layer_id), None)
        if not target:
            return
        def update() -> None:
            for key, value in values.items():
                setattr(target, key, value)
                if key == "asset_id":
                    asset = next((item for item in self.project.assets if item.id == value), None)
                    if asset:
                        asset.use_in_video = True
        self._commit("Updated a scene element", update)
        self._render_preview()

    def _begin_drag(self, layer_id: str) -> None:
        self._drag_before = copy.deepcopy(self.project.to_dict())

    def _drag_layer(self, layer_id: str, x: float, y: float) -> None:
        layer = next((layer for scene in self.project.scenes for layer in scene.layers if layer.id == layer_id), None)
        if layer:
            layer.x, layer.y = x, y
            if layer.id == self.selected_layer_id:
                self.inspector.x.blockSignals(True)
                self.inspector.y.blockSignals(True)
                self.inspector.x.setValue(x)
                self.inspector.y.setValue(y)
                self.inspector.x.blockSignals(False)
                self.inspector.y.blockSignals(False)
            self._render_preview()

    def _finish_drag(self, layer_id: str) -> None:
        if self._drag_before and self._drag_before != self.project.to_dict():
            self._push_undo(self._drag_before, "Moved an element")
            self.statusBar().showMessage("Moved element · Ctrl+Z to undo", 2500)
        self._drag_before = None

    def _edit_text_direct(self, layer_id: str) -> None:
        layer = next((layer for scene in self.project.scenes for layer in scene.layers if layer.id == layer_id), None)
        if not layer:
            return
        from PySide6.QtWidgets import QInputDialog

        text, accepted = QInputDialog.getMultiLineText(self, "Edit headline", "Text", layer.text)
        if accepted:
            self._commit(f"Updated {layer.role}", lambda: setattr(layer, "text", text))
            self._render_preview()
            self.inspector.set_layer(self.project, layer)

    def _select_scene(self, index: int) -> None:
        if not 0 <= index < len(self.project.scenes):
            return
        self.current_scene = index
        self._last_preview_scene = index
        self.current_time = sum(scene.duration for scene in self.project.scenes[:index])
        if self.play_timer.isActive():
            self._play_started_at = time.monotonic() - self.current_time
        self.selected_layer_id = ""
        self.preview.set_project(self.project, index)
        self.preview.set_selected_layer("")
        self.inspector.set_layer(self.project, None)
        self._render_preview()
        self._update_time_label()

    def _commit(self, summary: str, mutation) -> bool:
        before = copy.deepcopy(self.project.to_dict())
        try:
            mutation()
            self.project.validate()
        except Exception as error:
            self.project = Project.from_dict(before)
            self.statusBar().showMessage(f"Could not apply change: {error}", 7000)
            return False
        self._push_undo(before, summary)
        self._refresh_project(rebuild_timeline=False)
        self.statusBar().showMessage(f"{summary} · Ctrl+Z to undo", 3000)
        return True

    def _push_undo(self, snapshot: dict, summary: str) -> None:
        self._undo_stack.append((snapshot, summary))
        self._undo_stack = self._undo_stack[-50:]
        self._redo_stack.clear()

    def undo(self) -> None:
        if not self._undo_stack:
            self.statusBar().showMessage("Nothing to undo", 2000)
            return
        current = copy.deepcopy(self.project.to_dict())
        snapshot, summary = self._undo_stack.pop()
        self._redo_stack.append((current, summary))
        self.project = Project.from_dict(snapshot)
        self.selected_layer_id = ""
        self._refresh_project()
        self.statusBar().showMessage(f"Undid: {summary}", 2500)

    def redo(self) -> None:
        if not self._redo_stack:
            self.statusBar().showMessage("Nothing to redo", 2000)
            return
        current = copy.deepcopy(self.project.to_dict())
        snapshot, summary = self._redo_stack.pop()
        self._undo_stack.append((current, summary))
        self.project = Project.from_dict(snapshot)
        self.selected_layer_id = ""
        self._refresh_project()
        self.statusBar().showMessage(f"Redid: {summary}", 2500)

    def _handle_prompt(self, prompt: str) -> None:
        lower = prompt.casefold()
        if re.search(r"\b(create|make|build|δημιούργησε|δημιουργησε|φτιάξε|φτιαξε|φτιάξτε|ετοίμασε)\b", lower):
            project = create_from_prompt(prompt)
            project.assets = self.project.assets
            self.project = project
            self.project_path = None
            self.current_scene = 0
            self.current_time = 0.0
            self.selected_layer_id = ""
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._refresh_project()
            self.chat.add_message("EazyFix Studio", f"Έφτιαξα το «{project.name}» ως επεξεργάσιμο project {project.duration:.0f}s. Η τοπική λειτουργία δεν στέλνει τα αρχεία σου σε AI. Πρόσθεσε εικόνες από το Media Library και σύρε τα στοιχεία για να τα προσαρμόσεις.")
            return
        before = copy.deepcopy(self.project.to_dict())
        summary, changed = apply_offline_edit(self.project, prompt, self.selected_layer_id)
        if changed:
            self._push_undo(before, summary)
            self._refresh_project(rebuild_timeline=False)
            self.statusBar().showMessage(summary, 3500)
        self.chat.add_message("EazyFix Studio", summary)

    def _place_asset(self, asset_id: str) -> None:
        asset = next((item for item in self.project.assets if item.id == asset_id), None)
        if not asset:
            return
        if asset.kind == "audio":
            def set_music() -> None:
                self.project.music_asset_id = asset.id
                asset.use_in_video = True
            self._commit("Set background music", set_music)
            self.chat.add_message("EazyFix Studio", f"Ορίστηκε το {asset.name} ως background music. Η μίξη εφαρμόζεται στο MP4 export.")
            return
        if asset.kind != "image":
            QMessageBox.information(self, "Video clip imported", "Το αρχείο διατηρήθηκε στη βιβλιοθήκη project. Η σύνθεση video clips θα προστεθεί σε επόμενη έκδοση.")
            return
        def add_image() -> None:
            scene = self.project.scenes[self.current_scene]
            asset.use_in_video = True
            scene.layers.append(Layer(new_id(), "project_showcase", kind="image", asset_id=asset.id, x=0.5, y=0.65, width=0.82, height=0.31, animation="zoom", fit="cover"))
        if self._commit(f"Placed {asset.name}", add_image):
            layer = self.project.scenes[self.current_scene].layers[-1]
            self._select_layer(layer.id)
            self.timeline.set_project(self.project, self.current_scene)

    def _edit_asset(self, asset_id: str, role: str, description: str, use_in_video: bool) -> None:
        asset = next((item for item in self.project.assets if item.id == asset_id), None)
        if asset:
            def edit() -> None:
                asset.role, asset.description, asset.use_in_video = role, description, use_in_video
            self._commit(f"Updated asset {asset.name}", edit)

    def import_assets(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import images, music, or video",
            str(Path.home()),
            "Media files (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.svg *.mp3 *.wav *.m4a *.aac *.ogg *.mp4 *.mov *.mkv *.webm);;All files (*.*)",
        )
        if not paths:
            return
        storage = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "EazyFixAIStudio" / "ImportedMedia"
        imported: list[Asset] = []
        errors: list[str] = []
        for file_path in paths:
            path = Path(file_path)
            suffix = path.suffix.lower()
            if suffix in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
                kind, role = "audio", "background_music"
            elif suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
                kind, role = "video", "video_footage"
            else:
                kind, role = "image", "inspiration"
            asset = Asset(new_id(), path.name, str(path), kind=kind, role=role, description="", use_in_video=True)
            try:
                import_asset(path, asset, storage)
                imported.append(asset)
            except (OSError, PermissionError) as error:
                errors.append(f"{path.name}: {error}")
        if imported:
            def add_assets() -> None:
                self.project.assets.extend(imported)
                first_audio = next((item for item in imported if item.kind == "audio"), None)
                if first_audio and not self.project.music_asset_id:
                    self.project.music_asset_id = first_audio.id
            if self._commit(f"Imported {len(imported)} media file(s)", add_assets):
                self.gallery.set_assets(self.project.assets)
        if errors:
            QMessageBox.warning(self, "Some files could not be imported", "\n".join(errors))

    def _adjust_scene_duration(self, index: int, amount: float) -> None:
        if not 0 <= index < len(self.project.scenes):
            return
        scene = self.project.scenes[index]
        self._commit("Adjusted scene duration", lambda: setattr(scene, "duration", max(0.5, scene.duration + amount)))
        self.timeline.set_project(self.project, self.current_scene)

    def _add_scene(self) -> None:
        def add() -> None:
            self.project.scenes.append(Scene(new_id(), "Νέα σκηνή", 3.0, transition="fade", layers=[Layer(new_id(), "scene_headline", text="Η ΔΙΚΗ ΣΟΥ ΙΔΕΑ", y=0.42, font_size=76), Layer(new_id(), "scene_subtitle", text="Πες μας περισσότερα.", y=0.55, font_size=34, color="#C5FA72")]))
        if self._commit("Added scene", add):
            self.current_scene = len(self.project.scenes) - 1
            self.timeline.set_project(self.project, self.current_scene)
            self._select_scene(self.current_scene)

    def _duplicate_scene(self, index: int) -> None:
        if not 0 <= index < len(self.project.scenes):
            return
        duplicate = copy.deepcopy(self.project.scenes[index])
        duplicate.id = new_id()
        duplicate.title += " (copy)"
        for layer in duplicate.layers:
            layer.id = new_id()
        def add() -> None:
            self.project.scenes.insert(index + 1, duplicate)
        if self._commit("Duplicated scene", add):
            self.current_scene = index + 1
            self.timeline.set_project(self.project, self.current_scene)
            self._select_scene(self.current_scene)

    def _delete_scene(self, index: int) -> None:
        if len(self.project.scenes) <= 1:
            QMessageBox.information(self, "Keep one scene", "A project must contain at least one scene.")
            return
        if not 0 <= index < len(self.project.scenes):
            return
        def remove() -> None:
            self.project.scenes.pop(index)
            self.current_scene = min(index, len(self.project.scenes) - 1)
        if self._commit(f"Deleted {self.project.scenes[index].title}", remove):
            self.timeline.set_project(self.project, self.current_scene)
            self._select_scene(self.current_scene)

    def _move_scene(self, old: int, new: int) -> None:
        if not 0 <= old < len(self.project.scenes) or not 0 <= new < len(self.project.scenes) or old == new:
            return
        def move() -> None:
            scene = self.project.scenes.pop(old)
            self.project.scenes.insert(new, scene)
        if self._commit("Moved scene", move):
            self.current_scene = new
            self.timeline.set_project(self.project, self.current_scene)
            self._select_scene(self.current_scene)

    def new_project(self) -> None:
        self.project = sample_project()
        self.project_path = None
        self.current_scene, self.current_time = 0, 0.0
        self.selected_layer_id = ""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._refresh_project()
        self.chat.add_message("EazyFix Studio", "Άνοιξα νέο επεξεργάσιμο 10-second project. Πρόσθεσε assets ή γράψε ένα prompt για να διαλέξω offline template.")

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open EazyFix project", str(Path.home()), "EazyFix project (*.eazyproj);;JSON project (*.json)")
        if not path:
            return
        try:
            self.project = load_project(path)
            self.project_path = Path(path)
            self.current_scene, self.current_time = 0, 0.0
            self.selected_layer_id = ""
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._refresh_project()
            self.statusBar().showMessage(f"Opened {Path(path).name}", 3500)
        except Exception as error:
            QMessageBox.critical(self, "Could not open project", str(error))

    def save_current_project(self) -> None:
        self.inspector.flush_pending()
        path = self.project_path
        if path is None:
            selected, _ = QFileDialog.getSaveFileName(self, "Save project", str(Path.home() / f"{self.project.name}.eazyproj"), "EazyFix project (*.eazyproj)")
            if not selected:
                return
            path = Path(selected)
            if path.suffix.lower() != ".eazyproj":
                path = path.with_suffix(".eazyproj")
        try:
            save_project(self.project, path)
            self.project_path = path
            self.statusBar().showMessage(f"Saved editable project · {path}", 4500)
        except Exception as error:
            QMessageBox.critical(self, "Could not save project", str(error))

    def _autosave(self) -> None:
        try:
            self.inspector.flush_pending()
            save_project(self.project, autosave_path())
            self.statusBar().showMessage("Recovery copy saved", 1800)
        except Exception as error:
            self.statusBar().showMessage(f"Autosave failed: {error}", 5000)

    def _offer_recovery(self) -> None:
        recovery = autosave_path()
        if not recovery.is_file():
            return
        answer = QMessageBox.question(self, "Recover previous work?", "A recovery copy from an earlier session is available. Open it?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
        if answer == QMessageBox.StandardButton.Yes:
            try:
                self.project = load_project(recovery)
                self.project_path = None
                self.current_scene, self.current_time = 0, 0.0
                self._refresh_project()
            except Exception as error:
                QMessageBox.warning(self, "Recovery failed", str(error))
        else:
            recovery.unlink(missing_ok=True)

    def export_video(self) -> None:
        self.inspector.flush_pending()
        default_name = re.sub(r"[^\w.-]+", "_", self.project.name).strip("_.") or "EazyFix_Video"
        path, _ = QFileDialog.getSaveFileName(self, "Export MP4", str(Path.home() / f"{default_name}.mp4"), "MP4 video (*.mp4)")
        if not path:
            return
        if Path(path).suffix.lower() != ".mp4":
            path += ".mp4"
        project_copy = Project.from_dict(copy.deepcopy(self.project.to_dict()))
        worker = ExportWorker(project_copy, path, self)
        progress = QProgressDialog("Rendering video…", "Cancel", 0, 100, self)
        progress.setWindowTitle("Export MP4")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.canceled.connect(worker.cancel)
        worker.progress.connect(progress.setValue)
        worker.completed.connect(lambda result: self._export_completed(result, worker, progress))
        worker.failed.connect(lambda error: self._export_failed(error, worker, progress))
        worker.finished.connect(lambda: self._export_thread_finished(worker, progress))
        self._export_worker, self._export_dialog = worker, progress
        worker.start()

    def _export_completed(self, path: str, worker: ExportWorker, progress: QProgressDialog) -> None:
        progress.setValue(100)
        progress.close()
        self.statusBar().showMessage(f"Video exported: {path}", 6000)
        QMessageBox.information(self, "Export complete", f"Your MP4 video is ready:\n{path}")
        self._clear_export(worker, progress)

    def _export_failed(self, error: str, worker: ExportWorker, progress: QProgressDialog) -> None:
        progress.close()
        if error != "Export cancelled.":
            QMessageBox.critical(self, "Export failed", error)
        self._clear_export(worker, progress)

    def _clear_export(self, worker: ExportWorker, progress: QProgressDialog) -> None:
        if self._export_worker is not worker:
            return
        worker.deleteLater()
        progress.deleteLater()
        self._export_worker = None
        self._export_dialog = None

    def _export_thread_finished(self, worker: ExportWorker, progress: QProgressDialog) -> None:
        if self._export_worker is worker:
            progress.close()
            self._clear_export(worker, progress)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self._import_paths(paths)
        event.acceptProposedAction()

    def _import_paths(self, paths: list[str]) -> None:
        # Reuse the same import workflow as the picker without opening another dialog.
        storage = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "EazyFixAIStudio" / "ImportedMedia"
        imported: list[Asset] = []
        for file_path in paths:
            path = Path(file_path)
            suffix = path.suffix.lower()
            kind = "audio" if suffix in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"} else "video" if suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi"} else "image"
            asset = Asset(new_id(), path.name, str(path), kind, "background_music" if kind == "audio" else "video_footage" if kind == "video" else "inspiration")
            try:
                imported.append(import_asset(path, asset, storage))
            except OSError as error:
                self.statusBar().showMessage(f"Could not import {path.name}: {error}", 5000)
        if imported:
            def add() -> None:
                self.project.assets.extend(imported)
                audio = next((asset for asset in imported if asset.kind == "audio"), None)
                if audio and not self.project.music_asset_id:
                    self.project.music_asset_id = audio.id
            self._commit(f"Imported {len(imported)} media file(s)", add)

    def closeEvent(self, event) -> None:
        if self._export_worker and self._export_worker.isRunning():
            answer = QMessageBox.question(self, "Export in progress", "Cancel export and close the application?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._export_worker.cancel()
            self._export_worker.wait()
        self._autosave()
        event.accept()
