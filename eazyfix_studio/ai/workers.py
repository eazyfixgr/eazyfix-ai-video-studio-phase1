"""Background workers for provider calls and connection checks."""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from ..models import Project
from .config import AISettings
from .deepseek import DeepSeekClient
from .planner import DeepSeekPlanner


class PlanWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, settings: AISettings, api_key: str, prompt: str, project: Project, selected_layer_id: str, conversation: list[dict[str, str]], image_asset_ids: list[str], parent=None):
        super().__init__(parent)
        self.settings = settings
        self.api_key = api_key
        self.prompt = prompt
        self.project = project
        self.selected_layer_id = selected_layer_id
        self.conversation = conversation
        self.image_asset_ids = image_asset_ids
        self._cancel_requested = threading.Event()
        self.planner = DeepSeekPlanner(settings.endpoint, api_key, settings.text_model, settings.vision_model)

    def cancel(self) -> None:
        self._cancel_requested.set()
        self.planner.cancel()

    def run(self) -> None:
        try:
            plan = self.planner.create_plan(
                self.prompt,
                self.project,
                selected_layer_id=self.selected_layer_id,
                conversation=self.conversation,
                image_asset_ids=self.image_asset_ids,
            )
            if self._cancel_requested.is_set():
                self.cancelled.emit()
            else:
                self.completed.emit(plan)
        except Exception as error:
            if self._cancel_requested.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(str(error))


class ConnectionWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, endpoint: str, api_key: str, parent=None):
        super().__init__(parent)
        self.endpoint = endpoint
        self.api_key = api_key

    def run(self) -> None:
        try:
            models = DeepSeekClient(self.endpoint, self.api_key, timeout=30).list_models()
            if not models:
                raise RuntimeError("The account returned no available models.")
            self.completed.emit(models)
        except Exception as error:
            self.failed.emit(str(error))
