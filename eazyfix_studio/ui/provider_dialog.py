"""AI provider settings with encrypted OS credential storage and model discovery."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..ai.config import AISettings, AISettingsError, AISettingsStore, SecureKeyStore, SecureStorageError
from ..ai.deepseek import ModelInfo
from ..ai.workers import ConnectionWorker


class ProviderSettingsDialog(QDialog):
    def __init__(self, settings: AISettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Provider Settings")
        self.setMinimumWidth(520)
        self.settings_store = AISettingsStore()
        self.key_store = SecureKeyStore()
        self.saved_settings: AISettings | None = None
        self._saved_key_available = False
        self._key_store_error = ""
        self._clear_key = False
        self._connection_worker: ConnectionWorker | None = None

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Το DeepSeek μπορεί να σχεδιάζει και να τροποποιεί το project. "
            "Τα prompts και η σύνοψη του project στέλνονται στον provider όταν χρησιμοποιείς το AI. "
            "Οι εικόνες παραμένουν τοπικές εκτός αν επιβεβαιώσεις ξεχωριστά την αποστολή τους."
        )
        intro.setWordWrap(True)
        intro.setObjectName("mutedText")
        layout.addWidget(intro)

        form = QFormLayout()
        layout.addLayout(form)
        self.provider = QComboBox()
        self.provider.addItem("Offline templates", "offline")
        self.provider.addItem("DeepSeek API", "deepseek")
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.provider)))
        form.addRow("Provider", self.provider)

        self.endpoint = QLineEdit(settings.endpoint)
        self.endpoint.setPlaceholderText("https://api.deepseek.com")
        form.addRow("API endpoint", self.endpoint)

        self.text_model = QComboBox()
        self.text_model.setEditable(True)
        self.text_model.addItems([settings.text_model, "deepseek-v4-pro", "deepseek-flash"])
        self.text_model.setCurrentText(settings.text_model)
        form.addRow("Text/planning model", self.text_model)

        self.vision_model = QComboBox()
        self.vision_model.setEditable(True)
        self.vision_model.addItems([settings.vision_model, "deepseek-flash", "deepseek-v4-pro"])
        self.vision_model.setCurrentText(settings.vision_model)
        form.addRow("Image analysis model", self.vision_model)

        key_row = QHBoxLayout()
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Saved in Windows Credential Manager" if self._key_exists() else "Paste your DeepSeek API key")
        self.api_key.textEdited.connect(self._new_key_entered)
        key_row.addWidget(self.api_key, 1)
        self.clear_key_button = QPushButton("Clear")
        self.clear_key_button.clicked.connect(self._clear_saved_key)
        key_row.addWidget(self.clear_key_button)
        form.addRow("API key", key_row)

        self.privacy = QCheckBox("I agree to send prompts and project summaries to DeepSeek when I use AI.")
        self.privacy.setChecked(settings.allow_project_context)
        form.addRow("Privacy", self.privacy)

        self.capability_label = QLabel("DeepSeek model capabilities are discovered by Test connection.")
        self.capability_label.setWordWrap(True)
        self.capability_label.setObjectName("mutedText")
        layout.addWidget(self.capability_label)

        status_row = QHBoxLayout()
        self.status = QLabel(self._key_store_error or "API keys are stored in the operating-system credential manager, not in project files.")
        self.status.setWordWrap(True)
        self.status.setObjectName("mutedText")
        self.test_button = QPushButton("Test connection")
        self.test_button.clicked.connect(self._test_connection)
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.test_button)
        layout.addLayout(status_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.provider.currentIndexChanged.connect(self._update_enabled)
        self._update_enabled()

    def _key_exists(self) -> bool:
        try:
            self._saved_key_available = bool(self.key_store.get())
        except SecureStorageError as error:
            self._key_store_error = str(error)
        return self._saved_key_available

    def _update_enabled(self) -> None:
        enabled = self.provider.currentData() == "deepseek"
        for widget in (self.endpoint, self.text_model, self.vision_model, self.api_key, self.clear_key_button, self.privacy, self.test_button):
            widget.setEnabled(enabled)

    def _new_key_entered(self, _value: str) -> None:
        self._clear_key = False

    def _clear_saved_key(self) -> None:
        self.api_key.clear()
        self._clear_key = True
        self._saved_key_available = False
        self.api_key.setPlaceholderText("API key will be removed on Save")

    def _get_test_key(self) -> str:
        entered = self.api_key.text().strip()
        return entered or self.key_store.get() or ""

    def _test_connection(self) -> None:
        try:
            api_key = self._get_test_key()
            if not api_key:
                raise SecureStorageError("Enter an API key before testing the connection.")
            endpoint = self.endpoint.text().strip()
            temporary_settings = AISettings(provider="deepseek", endpoint=endpoint)
            temporary_settings.validate()
        except (AISettingsError, SecureStorageError) as error:
            self.status.setText(str(error))
            return
        self.status.setText("Checking endpoint and discovering available models…")
        self.test_button.setEnabled(False)
        self.buttons.setEnabled(False)
        worker = ConnectionWorker(endpoint, api_key, self)
        worker.completed.connect(lambda models: self._connection_succeeded(models, worker))
        worker.failed.connect(lambda message: self._connection_failed(message, worker))
        worker.finished.connect(lambda: self._connection_finished(worker))
        self._connection_worker = worker
        worker.start()

    def _connection_succeeded(self, models: list[ModelInfo], worker: ConnectionWorker) -> None:
        ids = [model.id for model in models]
        for combo, preferred in ((self.text_model, "deepseek-v4-pro"), (self.vision_model, "deepseek-flash")):
            current = combo.currentText().strip()
            combo.clear()
            combo.addItems(ids)
            combo.setCurrentText(current if current in ids else preferred if preferred in ids else ids[0])
        capabilities = "; ".join(f"{model.id}: {', '.join(model.input_modalities)}" for model in models)
        self.capability_label.setText(f"Available models: {capabilities}")
        vision = next((model for model in models if model.id == self.vision_model.currentText().strip()), None)
        if vision and "image" not in vision.input_modalities:
            self.status.setText("Connected, but the selected image model does not accept images. Choose one marked with image input.")
        else:
            self.status.setText(f"Connection successful · {len(models)} models discovered · no model tokens were used.")

    def _connection_failed(self, message: str, worker: ConnectionWorker) -> None:
        self.status.setText(message)

    def _connection_finished(self, worker: ConnectionWorker) -> None:
        if self._connection_worker is worker:
            self._connection_worker = None
            self.buttons.setEnabled(True)
            self.test_button.setEnabled(self.provider.currentData() == "deepseek")
            worker.deleteLater()

    def _save(self) -> None:
        settings = AISettings(
            provider=str(self.provider.currentData()),
            endpoint=self.endpoint.text().strip().rstrip("/"),
            text_model=self.text_model.currentText().strip(),
            vision_model=self.vision_model.currentText().strip(),
            allow_project_context=self.privacy.isChecked(),
        )
        try:
            settings.validate()
            if settings.provider == "deepseek":
                if not settings.allow_project_context:
                    raise AISettingsError("Confirm that prompts and project summaries may be sent to DeepSeek.")
                if self.api_key.text().strip():
                    self.key_store.set(self.api_key.text())
                    self._saved_key_available = True
                elif self._clear_key:
                    self.key_store.delete()
                    self._saved_key_available = False
                elif not self._saved_key_available:
                    # Read again because credential-store availability may have changed since the dialog opened.
                    self._saved_key_available = bool(self.key_store.get())
                if not self._saved_key_available:
                    raise SecureStorageError("Add a DeepSeek API key before enabling the provider.")
            elif self._clear_key:
                self.key_store.delete()
            self.settings_store.save(settings)
        except (AISettingsError, SecureStorageError) as error:
            QMessageBox.warning(self, "AI settings not saved", str(error))
            return
        self.saved_settings = settings
        self.accept()

    def closeEvent(self, event) -> None:
        if self._connection_worker and self._connection_worker.isRunning():
            self._connection_worker.wait()
        super().closeEvent(event)
