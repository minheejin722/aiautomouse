from __future__ import annotations

import json
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.gui.capture import RegionCaptureDialog
from aiautomouse.services.desktop import DesktopAutomationService


class TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class BackgroundTask(QObject):
    def __init__(self, func, *args, **kwargs) -> None:
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = TaskSignals()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            result = self.func(*self.args, **self.kwargs)
        except Exception as exc:  # pragma: no cover - UI flow
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(result)


class SnippetsTab(QWidget):
    changed = Signal()

    def __init__(self, service: DesktopAutomationService, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.current_name: str | None = None
        self.list_widget = QListWidget()
        self.name_edit = QLineEdit()
        self.editor = QPlainTextEdit()
        self.status_label = QLabel()
        self._build()
        self.refresh()

    def _build(self) -> None:
        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Saved snippets"))
        left_layout.addWidget(self.list_widget)
        left_buttons = QHBoxLayout()
        for label, handler in (
            ("Refresh", self.refresh),
            ("New", self.new_snippet),
            ("Delete", self.delete_snippet),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            left_buttons.addWidget(button)
        left_layout.addLayout(left_buttons)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        form = QFormLayout()
        form.addRow("Snippet ID", self.name_edit)
        right_layout.addLayout(form)
        right_layout.addWidget(self.editor)
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_snippet)
        right_layout.addWidget(save_button)
        right_layout.addWidget(self.status_label)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        self.list_widget.currentTextChanged.connect(self.load_selected)

    def refresh(self) -> None:
        entries = self.service.workspace.snippets.list_entries()
        current = self.current_name
        self.list_widget.clear()
        for entry in entries:
            self.list_widget.addItem(entry.name)
        if current:
            matches = self.list_widget.findItems(current, Qt.MatchExactly)
            if matches:
                self.list_widget.setCurrentItem(matches[0])

    def new_snippet(self) -> None:
        self.current_name = None
        self.name_edit.clear()
        self.editor.clear()
        self.status_label.setText("New snippet")

    def load_selected(self, name: str) -> None:
        if not name:
            return
        self.current_name = name
        self.name_edit.setText(name)
        self.editor.setPlainText(self.service.workspace.snippets.read(name))
        self.status_label.setText(f"Loaded {name}")

    def save_snippet(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self._error("Snippet ID is required")
            return
        self.service.workspace.snippets.save(name, self.editor.toPlainText())
        self.current_name = name
        self.status_label.setText(f"Saved {name}")
        self.refresh()
        self.changed.emit()

    def delete_snippet(self) -> None:
        if not self.current_name:
            return
        self.service.workspace.snippets.delete(self.current_name)
        self.new_snippet()
        self.refresh()
        self.changed.emit()

    def _error(self, message: str) -> None:
        QMessageBox.critical(self, "Snippets", message)


class TemplatesTab(QWidget):
    changed = Signal()

    def __init__(self, service: DesktopAutomationService, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.current_path: Path | None = None
        self.list_widget = QListWidget()
        self.preview = QLabel("No template selected")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(260)
        self.path_label = QLabel()
        self._build()
        self.refresh()

    def _build(self) -> None:
        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Image templates"))
        left_layout.addWidget(self.list_widget)
        left_buttons = QHBoxLayout()
        for label, handler in (
            ("Refresh", self.refresh),
            ("Import", self.import_template),
            ("Capture", self.capture_template),
            ("Delete", self.delete_template),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            left_buttons.addWidget(button)
        left_layout.addLayout(left_buttons)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.preview)
        right_layout.addWidget(self.path_label)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        self.list_widget.currentTextChanged.connect(self.load_selected)

    def refresh(self) -> None:
        entries = self.service.workspace.templates.list_entries()
        current = self.current_path.name if self.current_path else None
        self.list_widget.clear()
        for entry in entries:
            self.list_widget.addItem(entry.path.name)
        if current:
            matches = self.list_widget.findItems(current, Qt.MatchExactly)
            if matches:
                self.list_widget.setCurrentItem(matches[0])

    def load_selected(self, filename: str) -> None:
        if not filename:
            return
        self.current_path = self.service.workspace.templates.root / filename
        pixmap = QPixmap(str(self.current_path))
        self.preview.setPixmap(pixmap.scaled(420, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.path_label.setText(str(self.current_path))

    def import_template(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self,
            "Import template",
            str(Path.cwd()),
            "Images (*.png *.jpg *.jpeg *.bmp)",
        )
        if not source:
            return
        name, ok = QInputDialog.getText(self, "Template Name", "Saved template name:")
        if not ok or not name.strip():
            return
        self.service.workspace.templates.import_file(source, name.strip())
        self.refresh()
        self.changed.emit()

    def capture_template(self) -> None:
        name, ok = QInputDialog.getText(self, "Capture Template", "Saved template name:")
        if not ok or not name.strip():
            return
        dialog = RegionCaptureDialog(
            screen_capture=self.service.automation_app.screen_capture,
            window_manager=self.service.automation_app.window_manager,
            parent=self,
        )
        if dialog.exec() and dialog.image_bytes:
            self.service.workspace.templates.save_bytes(name.strip(), dialog.image_bytes)
            self.refresh()
            self.changed.emit()

    def delete_template(self) -> None:
        if self.current_path is None:
            return
        self.service.workspace.templates.delete(self.current_path.name)
        self.current_path = None
        self.preview.setText("No template selected")
        self.path_label.clear()
        self.refresh()
        self.changed.emit()


class MacrosTab(QWidget):
    changed = Signal()

    def __init__(self, service: DesktopAutomationService, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.current_path: Path | None = None
        self.list_widget = QListWidget()
        self.editor = QPlainTextEdit()
        self.file_name_edit = QLineEdit()
        self.hotkey_edit = QLineEdit()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["dry-run", "execute"])
        self.format_combo = QComboBox()
        self.format_combo.addItems([".json", ".yaml"])
        self.status_label = QLabel()
        self._build()
        self.refresh()

    def _build(self) -> None:
        splitter = QSplitter()

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Macros"))
        left_layout.addWidget(self.list_widget)
        left_buttons = QHBoxLayout()
        for label, handler in (
            ("Refresh", self.refresh),
            ("New", self.new_macro),
            ("Delete", self.delete_macro),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            left_buttons.addWidget(button)
        left_layout.addLayout(left_buttons)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        form = QFormLayout()
        form.addRow("File name", self.file_name_edit)
        form.addRow("Hotkey", self.hotkey_edit)
        form.addRow("Hotkey mode", self.mode_combo)
        form.addRow("Save format", self.format_combo)
        right_layout.addLayout(form)
        right_layout.addWidget(self.editor)
        actions = QHBoxLayout()
        for label, handler in (
            ("Generate From Text", self.generate_from_text),
            ("Validate", self.validate_macro),
            ("Save", self.save_macro),
            ("Register Hotkey", self.register_hotkey),
            ("Unregister Hotkey", self.unregister_hotkey),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        right_layout.addLayout(actions)
        right_layout.addWidget(self.status_label)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        self.list_widget.currentTextChanged.connect(self.load_selected)

    def refresh(self) -> None:
        entries = self.service.workspace.macros.list_entries()
        current = self.current_path.name if self.current_path else None
        self.list_widget.clear()
        for entry in entries:
            self.list_widget.addItem(entry.path.name)
        if current:
            matches = self.list_widget.findItems(current, Qt.MatchExactly)
            if matches:
                self.list_widget.setCurrentItem(matches[0])

    def new_macro(self) -> None:
        self.current_path = None
        self.file_name_edit.clear()
        self.hotkey_edit.clear()
        self.mode_combo.setCurrentText(self.service.settings.ui.default_macro_mode)
        self.format_combo.setCurrentText(".json")
        self.editor.setPlainText(
            json.dumps(
                {
                    "schema_version": "2.0",
                    "name": "new_macro",
                    "steps": [
                        {"type": "focus_window", "id": "focus_app", "title_contains": "Chrome"}
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        self.status_label.setText("New macro")

    def load_selected(self, filename: str) -> None:
        if not filename:
            return
        self.current_path = self.service.workspace.macros.root / filename
        self.file_name_edit.setText(self.current_path.name)
        self.format_combo.setCurrentText(self.current_path.suffix.lower())
        self.editor.setPlainText(self.service.workspace.macros.read_text(self.current_path))
        binding = self.service.get_macro_hotkey(self.current_path)
        self.hotkey_edit.setText(binding.hotkey if binding else "")
        self.mode_combo.setCurrentText(binding.mode if binding else self.service.settings.ui.default_macro_mode)
        self.status_label.setText(f"Loaded {self.current_path.name}")

    def validate_macro(self) -> None:
        try:
            suffix = self._current_suffix()
            macro = self.service.workspace.macros.validate_text(self.editor.toPlainText(), suffix)
        except Exception as exc:
            self._error(str(exc))
            return
        self.status_label.setText(f"Valid schema {macro['schema_version']} macro")

    def save_macro(self) -> None:
        name = self.file_name_edit.text().strip()
        if not name:
            self._error("Macro file name is required")
            return
        suffix = self._current_suffix()
        try:
            self.service.workspace.macros.validate_text(self.editor.toPlainText(), suffix)
            path = self.service.workspace.macros.save_text(name, self.editor.toPlainText(), extension=suffix)
        except Exception as exc:
            self._error(str(exc))
            return
        self.current_path = path
        self.file_name_edit.setText(path.name)
        self.status_label.setText(f"Saved {path.name}")
        self.refresh()
        self.changed.emit()

    def delete_macro(self) -> None:
        if self.current_path is None:
            return
        self.service.unregister_hotkey(self.current_path)
        self.service.workspace.macros.delete(self.current_path)
        self.current_path = None
        self.file_name_edit.clear()
        self.hotkey_edit.clear()
        self.editor.clear()
        self.refresh()
        self.changed.emit()

    def register_hotkey(self) -> None:
        if self.current_path is None:
            self.save_macro()
        if self.current_path is None:
            return
        hotkey = self.hotkey_edit.text().strip()
        if not hotkey:
            self._error("Hotkey is required")
            return
        self.service.register_hotkey(self.current_path, hotkey, self.mode_combo.currentText())
        self.status_label.setText(f"Registered {hotkey}")

    def unregister_hotkey(self) -> None:
        if self.current_path is None:
            return
        self.service.unregister_hotkey(self.current_path)
        self.hotkey_edit.clear()
        self.status_label.setText("Hotkey removed")

    def generate_from_text(self) -> None:
        prompt, ok = QInputDialog.getMultiLineText(
            self,
            "Generate Macro JSON",
            "Describe the macro in natural language:",
        )
        if not ok or not prompt.strip():
            return
        try:
            requested_name = self.file_name_edit.text().strip()
            if requested_name:
                requested_name = Path(requested_name).stem
            result = self.service.authoring.convert_text(
                prompt,
                macro_name=requested_name or None,
                hotkey=self.hotkey_edit.text().strip() or None,
            )
        except Exception as exc:
            self._error(str(exc))
            return
        self.editor.setPlainText(json.dumps(result.macro_json, indent=2, ensure_ascii=False))
        self.format_combo.setCurrentText(".json")
        if not self.file_name_edit.text().strip():
            self.file_name_edit.setText(f"{result.macro_json['name']}.json")
        if result.macro_json.get("hotkey"):
            self.hotkey_edit.setText(str(result.macro_json["hotkey"]))
        self.status_label.setText(
            f"Generated macro. Recommended adapter: {result.target_adapter_recommendation.adapter}"
        )
        QMessageBox.information(
            self,
            "Macro Diagnostics",
            self._format_authoring_result(result),
        )

    def _format_authoring_result(self, result) -> str:
        lines = [
            f"Recommended adapter: {result.target_adapter_recommendation.adapter}",
            f"Rationale: {result.target_adapter_recommendation.rationale}",
            "",
            "Warnings:",
        ]
        if result.ambiguous_step_warnings:
            for warning in result.ambiguous_step_warnings:
                lines.append(f"- {warning.message}")
                if warning.assumption:
                    lines.append(f"  Assumption: {warning.assumption}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("Suggested fallbacks:")
        if result.suggested_fallback_strategies:
            for fallback in result.suggested_fallback_strategies:
                lines.append(f"- {fallback.message}")
                if fallback.rationale:
                    lines.append(f"  Why: {fallback.rationale}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("Required resources:")
        if result.required_resources_checklist:
            for item in result.required_resources_checklist:
                status = "present" if item.exists else "missing"
                lines.append(f"- {item.resource_type}:{item.resource_id} [{status}]")
                if item.note:
                    lines.append(f"  Note: {item.note}")
        else:
            lines.append("- None")
        return "\n".join(lines)

    def _current_suffix(self) -> str:
        if self.current_path is not None:
            return self.current_path.suffix.lower()
        return self.format_combo.currentText()

    def _error(self, message: str) -> None:
        QMessageBox.critical(self, "Macros", message)


class RunLogsTab(QWidget):
    def __init__(self, service: DesktopAutomationService, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.current_run_path: Path | None = None
        self._tasks: list[BackgroundTask] = []
        self.macro_combo = QComboBox()
        self.runs_table = QTableWidget(0, 6)
        self.runs_table.setHorizontalHeaderLabels(["Run ID", "Macro", "Status", "Mode", "Started", "Failed Step"])
        self.runs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.screenshot_preview = QLabel("No screenshot")
        self.screenshot_preview.setAlignment(Qt.AlignCenter)
        self.screenshot_preview.setMinimumHeight(220)
        self.status_label = QLabel()
        self._build()
        self.refresh_macros()
        self.refresh_runs()

    def _build(self) -> None:
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Macro"))
        toolbar.addWidget(self.macro_combo, stretch=1)
        for label, handler in (
            ("Refresh Macros", self.refresh_macros),
            ("Dry Run", lambda: self.run_selected("dry-run")),
            ("Execute", lambda: self.run_selected("execute")),
            ("Refresh Runs", self.refresh_runs),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            toolbar.addWidget(button)

        splitter = QSplitter(Qt.Vertical)
        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.addWidget(self.runs_table)
        lower = QWidget()
        lower_layout = QHBoxLayout(lower)
        lower_layout.addWidget(self.log_view, stretch=2)
        lower_layout.addWidget(self.screenshot_preview, stretch=1)
        splitter.addWidget(upper)
        splitter.addWidget(lower)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(splitter)
        layout.addWidget(self.status_label)
        self.runs_table.itemSelectionChanged.connect(self.load_selected_run)

    def refresh_macros(self) -> None:
        current = self.macro_combo.currentText()
        self.macro_combo.clear()
        for entry in self.service.workspace.macros.list_entries():
            self.macro_combo.addItem(str(entry.path), userData=entry.path)
        index = self.macro_combo.findText(current)
        if index >= 0:
            self.macro_combo.setCurrentIndex(index)

    def refresh_runs(self) -> None:
        runs = self.service.workspace.runs.list_runs(limit=self.service.settings.ui.recent_runs_limit)
        self.runs_table.setRowCount(len(runs))
        for row, run in enumerate(runs):
            values = [run.run_id, run.macro_name, run.status, run.mode, run.started_at or "", run.failed_step_id or ""]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, run.path)
                self.runs_table.setItem(row, column, item)

    def run_selected(self, mode: str) -> None:
        macro_path = self.macro_combo.currentData()
        if not macro_path:
            return
        self.status_label.setText(f"Running {Path(macro_path).name} in {mode} mode...")
        task = BackgroundTask(self.service.run_macro, macro_path, mode)
        task.signals.finished.connect(lambda result, task=task: self._run_finished(result, task))
        task.signals.failed.connect(lambda message, task=task: self._run_failed(message, task))
        self._tasks.append(task)
        task.start()

    def _run_finished(self, result, task: BackgroundTask) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        self.status_label.setText(f"Run finished with status {result.status.value}")
        self.refresh_runs()

    def _run_failed(self, message: str, task: BackgroundTask) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        QMessageBox.critical(self, "Run Macro", message)
        self.status_label.setText(message)

    def load_selected_run(self) -> None:
        items = self.runs_table.selectedItems()
        if not items:
            return
        run_path = items[0].data(Qt.UserRole)
        if not run_path:
            return
        self.current_run_path = Path(run_path)
        self.log_view.setPlainText(self.service.workspace.runs.read_events_text(run_path))
        screenshots = sorted((self.current_run_path / "screenshots").glob("*"))
        if screenshots:
            pixmap = QPixmap(str(screenshots[-1]))
            self.screenshot_preview.setPixmap(pixmap.scaled(420, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.screenshot_preview.setText("No screenshot")


class SettingsTab(QWidget):
    changed = Signal()

    def __init__(self, service: DesktopAutomationService, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.cdp_url = QLineEdit()
        self.emergency_hotkey = QLineEdit()
        self.capture_backend = QComboBox()
        self.capture_backend.addItems(["mss", "dxcam"])
        self.ocr_backends = QLineEdit()
        self.tesseract_cmd = QLineEdit()
        self.recent_runs_limit = QLineEdit()
        self.overlay_enabled = QCheckBox("Enable overlay artifacts / debug")
        self.auto_start_hotkeys = QCheckBox("Auto-start hotkey service")
        self.hotkey_service_button = QPushButton()
        self.status_label = QLabel()
        self._build()
        self.load_from_settings()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("CDP URL", self.cdp_url)
        form.addRow("Emergency Hotkey", self.emergency_hotkey)
        form.addRow("Capture Backend", self.capture_backend)
        form.addRow("OCR Backends", self.ocr_backends)
        form.addRow("Tesseract Path", self.tesseract_cmd)
        form.addRow("Recent Runs Limit", self.recent_runs_limit)
        form.addRow("", self.overlay_enabled)
        form.addRow("", self.auto_start_hotkeys)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        save_button = QPushButton("Save Settings")
        save_button.clicked.connect(self.save_settings)
        buttons.addWidget(save_button)
        self.hotkey_service_button.clicked.connect(self.toggle_hotkeys)
        buttons.addWidget(self.hotkey_service_button)
        layout.addLayout(buttons)
        layout.addWidget(QLabel("Schema"))
        layout.addWidget(QLabel(str(self.service.settings.paths.schema_path)))
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    def load_from_settings(self) -> None:
        settings = self.service.settings
        self.cdp_url.setText(settings.cdp.url)
        self.emergency_hotkey.setText(settings.emergency_stop_hotkey)
        self.capture_backend.setCurrentText(settings.capture.backend)
        self.ocr_backends.setText(",".join(settings.ocr.backends))
        self.tesseract_cmd.setText(settings.ocr.tesseract_cmd or "")
        self.recent_runs_limit.setText(str(settings.ui.recent_runs_limit))
        self.overlay_enabled.setChecked(settings.overlay.enabled)
        self.auto_start_hotkeys.setChecked(settings.ui.auto_start_hotkeys)
        self._update_hotkey_button()

    def save_settings(self) -> None:
        settings = AppSettings.from_dict(self.service.settings.model_dump(mode="python"))
        settings.cdp.url = self.cdp_url.text().strip()
        settings.emergency_stop_hotkey = self.emergency_hotkey.text().strip()
        settings.capture.backend = self.capture_backend.currentText()
        settings.ocr.backends = [item.strip() for item in self.ocr_backends.text().split(",") if item.strip()]
        settings.ocr.tesseract_cmd = self.tesseract_cmd.text().strip() or None
        settings.ui.recent_runs_limit = max(1, int(self.recent_runs_limit.text().strip() or "50"))
        settings.overlay.enabled = self.overlay_enabled.isChecked()
        settings.ui.auto_start_hotkeys = self.auto_start_hotkeys.isChecked()
        self.service.save_settings(settings)
        self.status_label.setText("Settings saved")
        self._update_hotkey_button()
        self.changed.emit()

    def toggle_hotkeys(self) -> None:
        if self.service.hotkeys.is_running():
            self.service.hotkeys.stop()
            self.status_label.setText("Hotkey service stopped")
        else:
            self.service.hotkeys.start()
            self.status_label.setText("Hotkey service started")
        self._update_hotkey_button()

    def _update_hotkey_button(self) -> None:
        self.hotkey_service_button.setText("Stop Hotkeys" if self.service.hotkeys.is_running() else "Start Hotkeys")


class MainWindow(QMainWindow):
    def __init__(self, service: DesktopAutomationService) -> None:
        super().__init__()
        self.service = service
        self.setWindowTitle("AIAutoMouse MVP")
        self.resize(1400, 900)
        self.tabs = QTabWidget()
        self.snippets_tab = SnippetsTab(service)
        self.templates_tab = TemplatesTab(service)
        self.macros_tab = MacrosTab(service)
        self.run_logs_tab = RunLogsTab(service)
        self.settings_tab = SettingsTab(service)
        self.tabs.addTab(self.snippets_tab, "Snippets")
        self.tabs.addTab(self.templates_tab, "Templates")
        self.tabs.addTab(self.macros_tab, "Macros")
        self.tabs.addTab(self.run_logs_tab, "Run / Logs")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.setCentralWidget(self.tabs)
        self.snippets_tab.changed.connect(self._refresh_dependents)
        self.templates_tab.changed.connect(self._refresh_dependents)
        self.macros_tab.changed.connect(self._refresh_dependents)
        self.settings_tab.changed.connect(self._refresh_dependents)
        if self.service.settings.ui.auto_start_hotkeys:
            self.service.hotkeys.start()
            self.settings_tab.load_from_settings()

    def closeEvent(self, event) -> None:
        self.service.shutdown()
        super().closeEvent(event)

    def _refresh_dependents(self) -> None:
        self.run_logs_tab.refresh_macros()
        self.run_logs_tab.refresh_runs()
        self.snippets_tab.refresh()
        self.templates_tab.refresh()
        self.macros_tab.refresh()
