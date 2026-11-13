"""Interactive canvas preview with element selection and direct text dragging."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..models import Layer, Project


class PreviewCanvas(QWidget):
    layer_selected = Signal(str)
    layer_moved = Signal(str, float, float)
    drag_started = Signal(str)
    drag_finished = Signal(str)
    text_edit_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 320)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.project: Project | None = None
        self.scene_index = 0
        self.selected_layer_id = ""
        self.frame: QImage | None = None
        self._dragging = False
        self._last_point = QPoint()
        self._draw_rect = QRect()

    def set_project(self, project: Project, scene_index: int = 0) -> None:
        self.project = project
        self.scene_index = max(0, min(scene_index, len(project.scenes) - 1))
        self.update()

    def set_frame(self, image: Image.Image) -> None:
        rgb = image.convert("RGB")
        self.frame = QImage(rgb.tobytes(), rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888).copy()
        self.update()

    def set_selected_layer(self, layer_id: str) -> None:
        self.selected_layer_id = layer_id
        self.update()

    def _current_layers(self) -> list[Layer]:
        if not self.project or not self.project.scenes:
            return []
        return self.project.scenes[self.scene_index].layers

    def _layer_at(self, point: QPoint) -> Layer | None:
        if not self.project or self._draw_rect.isEmpty() or not self._draw_rect.contains(point):
            return None
        nx = (point.x() - self._draw_rect.left()) / self._draw_rect.width()
        ny = (point.y() - self._draw_rect.top()) / self._draw_rect.height()
        for layer in reversed(self._current_layers()):
            left = layer.x - layer.width / 2
            right = layer.x + layer.width / 2
            top = layer.y - layer.height / 2
            bottom = layer.y + layer.height / 2
            if left <= nx <= right and top <= ny <= bottom:
                return layer
        return None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0D1020"))
        if not self.frame or self.frame.isNull():
            painter.setPen(QColor("#AAB4D5"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Προεπισκόπηση")
            return
        bounds = self.rect().adjusted(14, 12, -14, -12)
        scaled = self.frame.size().scaled(bounds.size(), Qt.AspectRatioMode.KeepAspectRatio)
        left = bounds.left() + (bounds.width() - scaled.width()) // 2
        top = bounds.top() + (bounds.height() - scaled.height()) // 2
        self._draw_rect = QRect(left, top, scaled.width(), scaled.height())
        painter.setPen(QPen(QColor("#3B4265"), 1))
        painter.drawRoundedRect(self._draw_rect.adjusted(-2, -2, 2, 2), 8, 8)
        painter.drawImage(self._draw_rect, self.frame)

        if self.project and self.selected_layer_id:
            layer = next((item for item in self._current_layers() if item.id == self.selected_layer_id), None)
            if layer:
                sx = self._draw_rect.width()
                sy = self._draw_rect.height()
                rect = QRect(
                    round(self._draw_rect.left() + (layer.x - layer.width / 2) * sx),
                    round(self._draw_rect.top() + (layer.y - layer.height / 2) * sy),
                    round(layer.width * sx),
                    round(layer.height * sy),
                )
                painter.setPen(QPen(QColor("#49D7F5"), 2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect, 4, 4)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            layer = self._layer_at(event.position().toPoint())
            if layer:
                self.selected_layer_id = layer.id
                self.layer_selected.emit(layer.id)
                self.drag_started.emit(layer.id)
                self._dragging = True
                self._last_point = event.position().toPoint()
                self.update()
            else:
                self.selected_layer_id = ""
                self.layer_selected.emit("")
                self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self.project and self._draw_rect.width() > 0:
            point = event.position().toPoint()
            delta = point - self._last_point
            layer = next((item for item in self._current_layers() if item.id == self.selected_layer_id), None)
            if layer:
                x = max(0.03, min(0.97, layer.x + delta.x() / self._draw_rect.width()))
                y = max(0.03, min(0.97, layer.y + delta.y() / self._draw_rect.height()))
                self.layer_moved.emit(layer.id, x, y)
                self._last_point = point
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self.drag_finished.emit(self.selected_layer_id)
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        layer = self._layer_at(event.position().toPoint())
        if layer and layer.kind == "text":
            self.text_edit_requested.emit(layer.id)
        super().mouseDoubleClickEvent(event)
