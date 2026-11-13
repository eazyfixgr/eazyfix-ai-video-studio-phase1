"""Chat, asset shelf, editable inspector, and beginner-friendly scene timeline."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..models import Asset, Layer, Project
from ..renderer import render_frame


class DebouncedTextEdit(QPlainTextEdit):
    focus_lost = Signal()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.focus_lost.emit()


class ChatPanel(QWidget):
    prompt_submitted = Signal(str)
    import_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 8, 10)
        title_row = QHBoxLayout()
        title = QLabel("AI Chat")
        title.setObjectName("panelTitle")
        self.mode_badge = QLabel("LOCAL MODE")
        self.mode_badge.setObjectName("modeBadge")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.mode_badge)
        layout.addLayout(title_row)

        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setObjectName("chatHistory")
        self.history.setPlainText(
            "Καλώς ήρθες στο EazyFix AI Video Studio.\n\n"
            "Η τοπική λειτουργία δημιουργεί επεξεργάσιμα video projects χωρίς API key. "
            "Γράψε ένα prompt για να ξεκινήσεις ή επίλεξε ένα στοιχείο για άμεση επεξεργασία."
        )
        layout.addWidget(self.history, 1)

        self.input = QPlainTextEdit()
        self.input.setObjectName("chatInput")
        self.input.setPlaceholderText("Περιέγραψε το βίντεο ή ζήτησε μια αλλαγή…")
        self.input.setMaximumHeight(104)
        layout.addWidget(self.input)
        controls = QHBoxLayout()
        self.attach_button = QPushButton("＋  Προσθήκη media")
        self.attach_button.clicked.connect(self.import_requested.emit)
        self.send_button = QPushButton("Δημιουργία  ➤")
        self.send_button.setObjectName("primaryButton")
        self.send_button.clicked.connect(self._send)
        self.stop_button = QPushButton("Stop")
        self.stop_button.hide()
        self.stop_button.clicked.connect(self.cancel_requested.emit)
        self.retry_button = QPushButton("Retry")
        self.retry_button.hide()
        self.retry_button.clicked.connect(self._retry)
        controls.addWidget(self.attach_button)
        controls.addStretch(1)
        controls.addWidget(self.retry_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.send_button)
        layout.addLayout(controls)
        self._last_sent = ""

    def _send(self) -> None:
        text = self.input.toPlainText().strip()
        if not text:
            return
        self._last_sent = text
        self.retry_button.hide()
        self.input.clear()
        self.add_message("Εσύ", text)
        self.prompt_submitted.emit(text)

    def _retry(self) -> None:
        if self._last_sent:
            self.input.setPlainText(self._last_sent)
            self._send()

    def set_mode(self, name: str) -> None:
        self.mode_badge.setText(name.upper())

    def set_busy(self, busy: bool) -> None:
        self.send_button.setEnabled(not busy)
        self.stop_button.setVisible(busy)
        self.send_button.setText("Σκέφτομαι…" if busy else "Δημιουργία  ➤")

    def set_retry_available(self, available: bool) -> None:
        self.retry_button.setVisible(available)

    def add_message(self, speaker: str, text: str) -> None:
        self.history.appendPlainText(f"\n{speaker}\n{text}")
        bar = self.history.verticalScrollBar()
        bar.setValue(bar.maximum())


class AssetGallery(QWidget):
    import_requested = Signal()
    place_requested = Signal(str)
    asset_edited = Signal(str, str, str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        row = QHBoxLayout()
        title = QLabel("MEDIA LIBRARY")
        title.setObjectName("sectionLabel")
        add = QPushButton("＋ Import")
        add.clicked.connect(self.import_requested.emit)
        self.place_button = QPushButton("Place in scene")
        self.place_button.clicked.connect(self._place_selected)
        row.addWidget(title)
        row.addStretch(1)
        row.addWidget(self.place_button)
        row.addWidget(add)
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setObjectName("assetShelf")
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setFlow(QListWidget.Flow.LeftToRight)
        self.list.setWrapping(True)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setIconSize(QSize(64, 58))
        self.list.setGridSize(QSize(92, 92))
        self.list.itemDoubleClicked.connect(self._edit_selected)
        layout.addWidget(self.list)
        self._assets: list[Asset] = []

    def _place_selected(self) -> None:
        item = self.list.currentItem()
        if item:
            self.place_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def selected_image_asset_ids(self) -> list[str]:
        selected = {item.data(Qt.ItemDataRole.UserRole) for item in self.list.selectedItems()}
        return [asset.id for asset in self._assets if asset.id in selected and asset.kind == "image"]

    def set_assets(self, assets: list[Asset]) -> None:
        self._assets = assets
        self.list.clear()
        for asset in assets:
            item = QListWidgetItem(self._icon_for(asset), asset.name)
            item.setData(Qt.ItemDataRole.UserRole, asset.id)
            item.setToolTip(f"{asset.role}\n{asset.description or 'Διπλό κλικ για επεξεργασία'}")
            self.list.addItem(item)

    @staticmethod
    def _icon_for(asset: Asset) -> QIcon:
        path = Path(asset.path)
        if asset.kind == "image" and path.suffix.lower() == ".svg" and path.is_file():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                return QIcon(pixmap.scaled(72, 58, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        if asset.kind == "image" and path.is_file():
            try:
                with Image.open(path) as image:
                    image.thumbnail((96, 72))
                    preview = image.convert("RGBA")
                    data = preview.tobytes()
                    pixmap = QPixmap.fromImage(QImage(data, preview.width, preview.height, preview.width * 4, QImage.Format.Format_RGBA8888).copy())
                    return QIcon(pixmap)
            except (OSError, ValueError):
                pass
        pixmap = QPixmap(72, 56)
        pixmap.fill(QColor("#292E50"))
        return QIcon(pixmap)

    def _edit_selected(self, item: QListWidgetItem) -> None:
        asset_id = item.data(Qt.ItemDataRole.UserRole)
        asset = next((asset for asset in self._assets if asset.id == asset_id), None)
        if not asset:
            return
        dialog = AssetDetailsDialog(asset, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.asset_edited.emit(asset.id, dialog.role.text().strip() or "inspiration", dialog.description.text().strip(), dialog.use_in_video.isChecked())


class AssetDetailsDialog(QDialog):
    def __init__(self, asset: Asset, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Asset details")
        self.setMinimumWidth(340)
        form = QFormLayout(self)
        form.addRow(QLabel(f"<b>{asset.name}</b>"))
        self.role = QLineEdit(asset.role)
        self.description = QLineEdit(asset.description)
        self.use_in_video = QCheckBox("Use this file in the final video")
        self.use_in_video.setChecked(asset.use_in_video)
        form.addRow("Role", self.role)
        form.addRow("Description", self.description)
        form.addRow("", self.use_in_video)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class InspectorPanel(QWidget):
    layer_changed = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(230)
        self.setMaximumWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 12)
        title = QLabel("Inspector")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        self.summary = QLabel("Επίλεξε ένα στοιχείο στην προεπισκόπηση.")
        self.summary.setObjectName("mutedText")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.form = QFormLayout()
        layout.addLayout(self.form)
        self.text = DebouncedTextEdit()
        self.text.setMaximumHeight(94)
        self.text.setPlaceholderText("Κείμενο")
        self._text_timer = QTimer(self)
        self._text_timer.setSingleShot(True)
        self._text_timer.setInterval(450)
        self._text_timer.timeout.connect(self.flush_pending)
        self.text.focus_lost.connect(self.flush_pending)
        self.text.textChanged.connect(self._text_changed)
        self.font_size = QSpinBox()
        self.font_size.setRange(12, 180)
        self.font_size.valueChanged.connect(lambda value: self._emit(font_size=value))
        self.color_button = QPushButton("Text color")
        self.color_button.clicked.connect(self._choose_color)
        self.animation = QComboBox()
        self.animation.addItems(["fade_up", "fade", "zoom", "slide_left", "spring", "word_reveal"])
        self.animation.currentTextChanged.connect(lambda value: self._emit(animation=value))
        self.x = QDoubleSpinBox()
        self.y = QDoubleSpinBox()
        for control in (self.x, self.y):
            control.setRange(0.0, 1.0)
            control.setSingleStep(0.01)
            control.setDecimals(2)
            control.valueChanged.connect(self._position_changed)
        self.image_asset = QComboBox()
        self.image_asset.currentIndexChanged.connect(self._asset_changed)
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.05, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.valueChanged.connect(lambda value: self._emit(opacity=value))
        self._color = "#F7F8FF"
        self._layer_id = ""
        self._project: Project | None = None
        self._updating = False
        self._text_dirty = False
        self._add_row("Text", self.text)
        self._add_row("Font size", self.font_size)
        self._add_row("Color", self.color_button)
        self._add_row("Animation", self.animation)
        self._add_row("Position X", self.x)
        self._add_row("Position Y", self.y)
        self._add_row("Image asset", self.image_asset)
        self._add_row("Opacity", self.opacity)
        layout.addStretch(1)

    def _add_row(self, name: str, widget: QWidget) -> None:
        self.form.addRow(name, widget)

    def set_layer(self, project: Project, layer: Layer | None) -> None:
        self.flush_pending()
        self._updating = True
        self._text_timer.stop()
        self._project = project
        self._layer_id = layer.id if layer else ""
        if not layer:
            self.summary.setText("Επίλεξε ένα στοιχείο στην προεπισκόπηση. Σύρε κείμενο ή εικόνα για να αλλάξεις θέση.")
            for index in range(self.form.rowCount()):
                label = self.form.itemAt(index, QFormLayout.ItemRole.LabelRole)
                field = self.form.itemAt(index, QFormLayout.ItemRole.FieldRole)
                if label and label.widget():
                    label.widget().setVisible(False)
                if field and field.widget():
                    field.widget().setVisible(False)
            self._updating = False
            return
        self.summary.setText(f"{layer.role}  ·  {layer.kind}")
        visible = {"text": {"Text", "Font size", "Color", "Animation", "Position X", "Position Y", "Opacity"}, "image": {"Image asset", "Animation", "Position X", "Position Y", "Opacity"}, "mockup": {"Animation", "Position X", "Position Y", "Opacity"}, "shape": {"Position X", "Position Y", "Opacity"}}.get(layer.kind, set())
        for index in range(self.form.rowCount()):
            label_item = self.form.itemAt(index, QFormLayout.ItemRole.LabelRole)
            field_item = self.form.itemAt(index, QFormLayout.ItemRole.FieldRole)
            label = label_item.widget() if label_item else None
            field = field_item.widget() if field_item else None
            label_text = label.text() if isinstance(label, QLabel) else ""
            show = label_text in visible
            if label:
                label.setVisible(show)
            if field:
                field.setVisible(show)
        self.text.setPlainText(layer.text)
        self.font_size.setValue(layer.font_size)
        self._color = layer.color
        self.color_button.setText(layer.color)
        self.color_button.setStyleSheet(f"background:{layer.color}; color:#101321")
        self.animation.setCurrentText(layer.animation)
        self.x.setValue(layer.x)
        self.y.setValue(layer.y)
        self.opacity.setValue(layer.opacity)
        self.image_asset.clear()
        if project:
            for asset in project.assets:
                if asset.kind == "image":
                    self.image_asset.addItem(asset.name, asset.id)
        index = self.image_asset.findData(layer.asset_id)
        self.image_asset.setCurrentIndex(index)
        self._updating = False

    def _text_changed(self) -> None:
        if not self._updating:
            self._text_dirty = True
            self._text_timer.start()

    def flush_pending(self) -> None:
        if self._text_dirty:
            self._text_timer.stop()
            self._text_dirty = False
            self._emit(text=self.text.toPlainText())

    def _emit(self, **values) -> None:
        if self._layer_id and not self._updating:
            self.layer_changed.emit(self._layer_id, values)

    def _position_changed(self) -> None:
        self._emit(x=self.x.value(), y=self.y.value())

    def _asset_changed(self, index: int) -> None:
        asset_id = self.image_asset.itemData(index)
        if asset_id:
            self._emit(asset_id=asset_id)

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, "Choose text color")
        if color.isValid():
            self._color = color.name().upper()
            self.color_button.setText(self._color)
            self.color_button.setStyleSheet(f"background:{self._color}; color:#101321")
            self._emit(color=self._color)


class TimelinePanel(QWidget):
    scene_selected = Signal(int)
    duration_adjusted = Signal(int, float)
    scene_added = Signal()
    scene_duplicated = Signal(int)
    scene_deleted = Signal(int)
    scene_moved = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        heading = QHBoxLayout()
        label = QLabel("SCENES")
        label.setObjectName("sectionLabel")
        self.duration_label = QLabel("")
        self.duration_label.setObjectName("mutedText")
        heading.addWidget(label)
        heading.addStretch(1)
        heading.addWidget(self.duration_label)
        layout.addLayout(heading)
        self.list = QListWidget()
        self.list.setObjectName("sceneTimeline")
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setFlow(QListWidget.Flow.LeftToRight)
        self.list.setWrapping(False)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setIconSize(QSize(72, 84))
        self.list.setGridSize(QSize(140, 104))
        self.list.itemClicked.connect(self._selected)
        self.list.setMaximumHeight(118)
        layout.addWidget(self.list)

        controls = QHBoxLayout()
        self.add_button = QPushButton("＋ Scene")
        self.duplicate_button = QPushButton("Duplicate")
        self.up_button = QPushButton("↑")
        self.down_button = QPushButton("↓")
        self.delete_button = QPushButton("Delete")
        self.minus_button = QPushButton("− 1s")
        self.plus_button = QPushButton("＋ 1s")
        for button in (self.add_button, self.duplicate_button, self.up_button, self.down_button, self.minus_button, self.plus_button, self.delete_button):
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.add_button.clicked.connect(self.scene_added.emit)
        self.duplicate_button.clicked.connect(lambda: self.scene_duplicated.emit(self.current_index))
        self.delete_button.clicked.connect(lambda: self.scene_deleted.emit(self.current_index))
        self.up_button.clicked.connect(lambda: self.scene_moved.emit(self.current_index, max(0, self.current_index - 1)))
        self.down_button.clicked.connect(lambda: self.scene_moved.emit(self.current_index, self.current_index + 1))
        self.minus_button.clicked.connect(lambda: self.duration_adjusted.emit(self.current_index, -1.0))
        self.plus_button.clicked.connect(lambda: self.duration_adjusted.emit(self.current_index, 1.0))
        self.current_index = 0

    def _selected(self, item: QListWidgetItem) -> None:
        self.current_index = item.data(Qt.ItemDataRole.UserRole)
        self.scene_selected.emit(self.current_index)

    def set_project(self, project: Project, selected_index: int) -> None:
        self.current_index = max(0, min(selected_index, len(project.scenes) - 1))
        self.duration_label.setText(f"{project.duration:.1f}s  ·  {len(project.scenes)} scenes")
        self.list.clear()
        elapsed = 0.0
        for index, scene in enumerate(project.scenes):
            image = render_frame(project, elapsed + min(0.4, scene.duration / 3), (70, 124))
            image = image.convert("RGB")
            data = image.tobytes()
            pixmap = QPixmap.fromImage(QImage(data, image.width, image.height, image.width * 3, QImage.Format.Format_RGB888).copy())
            item = QListWidgetItem(QIcon(pixmap), f"{index + 1}. {scene.title}\n{scene.duration:.1f}s")
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setSizeHint(QSize(132, 104))
            self.list.addItem(item)
            elapsed += scene.duration
        self.list.setCurrentRow(self.current_index)
