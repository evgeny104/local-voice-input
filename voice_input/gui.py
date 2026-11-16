"""Графический интерфейс приложения (PySide6).

Состав:
  - VoiceInputWindow — окно: индикатор статуса, кнопка вкл/выкл голосового ввода,
    поле последнего текста, настройки (микрофон, модель Whisper, URL LM Studio);
  - VoiceController — связка клавиатуры (KeyboardHandler) и конвейера обработки
    с GUI: все вызовы Whisper/LLM идут в фоновом потоке, в GUI приходят
    только сигналы Qt (безопасно с любого потока);
  - Pipeline / TranscriptionLike — контракт конвейера обработки
    (реализация подключается снаружи — см. test_stage6.py и main.py).

ВАЖНО: виджеты трогает только GUI-поток. Обратные вызовы KeyboardHandler
выполняются в потоках слушателя — они лишь эмитят сигналы контроллера.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

import sounddevice as sd

from .audio_recorder import MicrophoneError
from .config import APP_NAME, WHISPER_MODELS, AppConfig, LLMConfig
from .keyboard_handler import KeyboardHandler
from .llm_processor import LLMProcessor

logger = logging.getLogger(__name__)


class AppStatus(Enum):
    """Состояния приложения, отображаемые индикатором."""

    DISABLED = "Отключено"
    IDLE = "Ожидание"
    HOLDING = "Удерживайте Space"
    RECORDING = "Идёт запись"
    TRANSCRIBING = "Распознавание речи"
    PROCESSING = "Обработка текста"
    DONE = "Готово"
    ERROR = "Ошибка"


STATUS_COLORS = {
    AppStatus.DISABLED: "#757575",
    AppStatus.IDLE: "#546e7a",
    AppStatus.HOLDING: "#ef6c00",
    AppStatus.RECORDING: "#c62828",
    AppStatus.TRANSCRIBING: "#1565c0",
    AppStatus.PROCESSING: "#1565c0",
    AppStatus.DONE: "#2e7d32",
    AppStatus.ERROR: "#c62828",
}


class TranscriptionLike(Protocol):
    """Минимальная форма результата распознавания (см. whisper_engine.Transcription)."""

    text: str
    language: str


class Pipeline(Protocol):
    """Контракт конвейера: запись -> транскрипция -> обработка текста.

    Реализации: демо-конвейер в test_stage6.py, реальный — в main.py
    (адаптер над AudioRecorder + WhisperEngine + LLMProcessor).
    """

    def start_recording(self) -> None: ...
    def stop_recording(self) -> Path | None: ...
    def transcribe(self, audio_path: Path) -> TranscriptionLike: ...
    def process_text(self, text: str) -> str: ...


@dataclass
class Transcript:
    """Простейшая реализация TranscriptionLike для демо-конвейеров."""

    text: str
    language: str = ""


class VoiceController(QObject):
    """Связывает KeyboardHandler и Pipeline с окном через сигналы Qt.

    Потоки:
      - поток слушателя клавиатуры: _on_space_pressed/_on_record_start/_on_record_stop;
      - рабочий поток «pipeline-worker»: транскрипция и обработка текста;
      - GUI-поток: слоты окна.
    """

    status_changed = Signal(AppStatus)
    text_ready = Signal(str)        # сырой текст Whisper — только показ в поле
    final_ready = Signal(str)       # итоговый текст после LLM — показ + буфер обмена
    error_occurred = Signal(str)

    def __init__(
        self,
        config: AppConfig,
        pipeline: Pipeline,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._pipeline = pipeline
        self._keyboard = KeyboardHandler(
            config.keys,
            on_record_start=self._on_record_start,
            on_record_stop=self._on_record_stop,
            on_press=self._on_space_pressed,
            on_cancel=self._on_cancel,
        )
        self._state_lock = threading.Lock()
        self._active = True        # голосовой ввод включён кнопкой
        self._processing = False   # идёт транскрипция/обработка

    def start(self) -> None:
        """Запускает слушатель клавиатуры (вызывать из GUI-потока после show())."""
        self._keyboard.start()

    def shutdown(self) -> None:
        """Останавливает слушатель (вызывать при закрытии окна)."""
        self._keyboard.stop()

    def set_active(self, active: bool) -> None:
        """Включает/отключает реакцию на Space (кнопка в окне)."""
        with self._state_lock:
            self._active = active
            busy = (not active) or self._processing
        self._keyboard.set_busy(busy)
        self.status_changed.emit(AppStatus.IDLE if active else AppStatus.DISABLED)

    def _on_space_pressed(self) -> None:
        # поток слушателя: только сигнал, ничего не блокируем
        self.status_changed.emit(AppStatus.HOLDING)

    def _on_cancel(self) -> None:
        # отпустили Space раньше времени удержания — возврат в ожидание
        self.status_changed.emit(AppStatus.IDLE)

    def _on_record_start(self) -> None:
        # поток слушателя: открытие аудиопотока занимает миллисекунды, не блокируем
        try:
            self._pipeline.start_recording()
        except MicrophoneError as exc:
            logger.warning("Не удалось начать запись: %s", exc)
            self.error_occurred.emit(str(exc))
            return
        self.status_changed.emit(AppStatus.RECORDING)

    def _on_record_stop(self) -> None:
        # поток слушателя: останавливаем запись и сразу отдаём обработку фоновому потоку
        path = self._pipeline.stop_recording()
        if path is None:
            self.status_changed.emit(AppStatus.IDLE)  # запись слишком короткая
            return
        with self._state_lock:
            self._processing = True
        self._keyboard.set_busy(True)
        self.status_changed.emit(AppStatus.TRANSCRIBING)
        worker = threading.Thread(
            target=self._process_recording, args=(path,), daemon=True, name="pipeline-worker"
        )
        worker.start()

    def _process_recording(self, path: Path) -> None:
        try:
            transcript = self._pipeline.transcribe(path)
            if not transcript.text:
                self.status_changed.emit(AppStatus.IDLE)  # речь не распознана
                return
            self.text_ready.emit(transcript.text)
            self.status_changed.emit(AppStatus.PROCESSING)
            final_text = self._pipeline.process_text(transcript.text)
            self.final_ready.emit(final_text)
            self.status_changed.emit(AppStatus.DONE)
        except Exception as exc:
            logger.exception("Ошибка обработки записи")
            self.error_occurred.emit(f"Ошибка обработки: {exc}")
        finally:
            path.unlink(missing_ok=True)  # временный WAV не должен остаться на диске
            with self._state_lock:
                self._processing = False
                busy = not self._active
            self._keyboard.set_busy(busy)


class VoiceInputWindow(QMainWindow):
    """Окно приложения: статус, вкл/выкл, текст, настройки."""

    llm_check_finished = Signal(bool, str)

    def __init__(
        self,
        controller: VoiceController,
        config: AppConfig,
        start_in_tray: bool = False,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._config = config
        self._mic_ids: list[int | None] = []
        self._quitting = False
        self._tray: QSystemTrayIcon | None = None
        self._start_in_tray = False

        self.setWindowTitle(APP_NAME)
        self._build_ui()
        self._connect_signals()
        self.resize(540, 460)
        self._setup_tray(start_in_tray)

    @property
    def start_in_tray(self) -> bool:
        """True, если окно стартует скрытым в трей (main.py не должен делать show())."""
        return self._start_in_tray

    def _setup_tray(self, start_in_tray: bool) -> None:
        self._start_in_tray = False
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("Системный трей недоступен — окно будет обычным")
            return

        self._tray = QSystemTrayIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaVolume
        ), self)
        self._tray.setToolTip(
            f"{APP_NAME} — удерживайте Space {self._config.keys.hold_seconds:g} с"
        )

        menu = QMenu()
        menu.addAction("Показать окно", self.showNormal)
        menu.addAction("Выход", self._quit_from_tray)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

        self._start_in_tray = start_in_tray
        if start_in_tray:
            self.hide()
            self._tray.showMessage(
                APP_NAME,
                f"Голосовой ввод запущен. Удерживайте Space {self._config.keys.hold_seconds:g} с.\n"
                "Окно — клик по значку, выход — через меню значка.",
                QSystemTrayIcon.MessageIcon.Information,
                5_000,
            )

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.showNormal()
            self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._quitting = True
        if self._tray is not None:
            self._tray.hide()
        QApplication.quit()

    def notify(self, title: str, message: str) -> None:
        """Всплывающее уведомление из трея (если трей доступен)."""
        if self._tray is not None:
            self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4_000)

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)

        # Индикатор статуса + кнопка вкл/выкл
        top_row = QHBoxLayout()
        self._status_label = QLabel()
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("font-weight: bold; padding: 8px;")
        top_row.addWidget(self._status_label, stretch=1)
        self._toggle_button = QPushButton("Голосовой ввод: выкл")
        self._toggle_button.setCheckable(True)
        self._toggle_button.setChecked(True)
        self._update_toggle_text(True)
        top_row.addWidget(self._toggle_button)
        root.addLayout(top_row)

        # Последний распознанный текст
        root.addWidget(QLabel("Последний текст:"))
        self._text_edit = QPlainTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setPlaceholderText("Здесь появится распознанный текст")
        root.addWidget(self._text_edit, stretch=1)

        # Настройки
        settings_box = QGroupBox("Настройки")
        form = QFormLayout(settings_box)

        self._mic_combo = QComboBox()
        self._fill_microphones()
        form.addRow("Микрофон:", self._mic_combo)

        self._model_combo = QComboBox()
        self._model_combo.addItems(WHISPER_MODELS)
        self._model_combo.setCurrentText(self._config.whisper.model_size)
        form.addRow("Модель Whisper:", self._model_combo)

        self._llm_url_edit = QLineEdit(self._config.llm.base_url)
        self._llm_check_button = QPushButton("Проверить соединение")
        llm_row = QHBoxLayout()
        llm_row.addWidget(self._llm_url_edit, stretch=1)
        llm_row.addWidget(self._llm_check_button)
        form.addRow("LM Studio:", llm_row)

        root.addWidget(settings_box)
        self.setCentralWidget(central)
        self.set_status(AppStatus.IDLE)

    def _connect_signals(self) -> None:
        controller = self._controller
        controller.status_changed.connect(self.set_status)
        controller.text_ready.connect(self.show_text)
        controller.final_ready.connect(self.show_text)
        controller.final_ready.connect(self._on_final_text)
        controller.error_occurred.connect(self.show_error)
        self._toggle_button.toggled.connect(self._on_toggle)
        self._mic_combo.currentIndexChanged.connect(self._on_mic_changed)
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        self._llm_check_button.clicked.connect(self._on_check_llm)
        self.llm_check_finished.connect(self._on_llm_check_finished)

    # ---- слоты контроллера (GUI-поток) ----

    def set_status(self, status: AppStatus) -> None:
        color = STATUS_COLORS[status]
        self._status_label.setText(f"Статус: {status.value}")
        self._status_label.setStyleSheet(
            f"color: white; background-color: {color};"
            "font-weight: bold; padding: 8px; border-radius: 4px;"
        )

    def show_text(self, text: str) -> None:
        self._text_edit.setPlainText(text)

    def _on_final_text(self, text: str) -> None:
        preview = text if len(text) <= 80 else text[:77] + "..."
        self.notify(APP_NAME, f"Текст скопирован в буфер обмена:\n{preview}")

    def show_error(self, message: str) -> None:
        self.set_status(AppStatus.ERROR)
        QMessageBox.critical(self, APP_NAME, message)

    # ---- обработчики виджетов ----

    def _on_toggle(self, checked: bool) -> None:
        self._update_toggle_text(checked)
        self._controller.set_active(checked)

    def _update_toggle_text(self, checked: bool) -> None:
        self._toggle_button.setText("Голосовой ввод: вкл" if checked else "Голосовой ввод: выкл")

    def _on_mic_changed(self, index: int) -> None:
        self._config.audio.device = self._mic_ids[index]

    def _on_model_changed(self, model_size: str) -> None:
        self._config.whisper.model_size = model_size  # применяется при перезагрузке модели

    def _on_check_llm(self) -> None:
        url = self._llm_url_edit.text().strip()
        self._config.llm.base_url = url
        self._llm_check_button.setEnabled(False)
        self._llm_check_button.setText("Проверка...")
        threading.Thread(
            target=self._check_llm_worker, args=(url,), daemon=True
        ).start()

    def _check_llm_worker(self, url: str) -> None:
        try:
            ok = LLMProcessor(LLMConfig(base_url=url)).is_available()
        except Exception:
            logger.exception("Ошибка проверки LM Studio")
            ok = False
        self.llm_check_finished.emit(ok, url)

    def _on_llm_check_finished(self, ok: bool, url: str) -> None:
        self._llm_check_button.setEnabled(True)
        self._llm_check_button.setText("Проверить соединение")
        if ok:
            QMessageBox.information(self, APP_NAME, f"LM Studio доступна:\n{url}")
        else:
            QMessageBox.warning(
                self, APP_NAME, f"LM Studio недоступна или модель не загружена:\n{url}"
            )

    # ---- прочее ----

    def _fill_microphones(self) -> None:
        self._mic_ids = [None]  # «по умолчанию»
        self._mic_combo.addItem("Микрофон по умолчанию")
        try:
            devices = sd.query_devices()
        except sd.PortAudioError:
            logger.exception("Не удалось получить список устройств")
            return
        for index, device in enumerate(devices):
            if device["max_input_channels"] > 0:
                self._mic_ids.append(index)
                self._mic_combo.addItem(f"[{index}] {device['name']}")
        if self._config.audio.device in self._mic_ids:
            self._mic_combo.setCurrentIndex(self._mic_ids.index(self._config.audio.device))

    def closeEvent(self, event) -> None:  # noqa: N802 — имя из Qt
        if self._tray is not None and not self._quitting:
            # закрытие окна — сворачивание в трей, выход только через меню значка
            event.ignore()
            self.hide()
            self._tray.showMessage(
                APP_NAME,
                "Приложение продолжает работу в трее (у часов).\n"
                "Выход — правый клик по значку -> Выход.",
                QSystemTrayIcon.MessageIcon.Information,
                4_000,
            )
            return
        self._controller.shutdown()
        super().closeEvent(event)
