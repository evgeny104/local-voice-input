"""Сборка и запуск приложения: конвейер обработки и точка входа main().

Поток работы:
    python main.py
    1. Защита от повторного запуска (именованный мьютекс Windows).
    2. Логи, конфигурация, очистка остатков временных WAV прошлых запусков.
    3. Загрузка модели Whisper в память (один раз, ~10 с на CPU).
    4. Окно приложения (gui.VoiceInputWindow) + контроллер клавиатуры, трей.
    5. Голосовой ввод: удержание Space 1,5 с -> запись -> Whisper -> LM Studio
       (если сервер недоступен — сырой текст Whisper) -> буфер обмена.
    6. Вставка текста в любое приложение через Ctrl+V.

Выход — «Выход» в меню значка трея.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from .audio_recorder import AudioRecorder
from .clipboard import copy_text
from .config import APP_NAME, AppConfig, setup_logging
from .gui import VoiceController, VoiceInputWindow
from .llm_processor import LLMProcessor
from .whisper_engine import WhisperEngine

logger = logging.getLogger(__name__)

_SINGLE_INSTANCE_MUTEX = "Local\\LocalVoiceInputMutex"


def acquire_single_instance() -> bool:
    """Захватывает именованный мьютекс: True — запускаемся, False — уже запущено.

    Мьютекс живёт, пока жив процесс: при выходе/падении Windows освобождает
    его автоматически, «зависших» блокировок не бывает.
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX)
    if not mutex:
        logger.warning(
            "Не удалось проверить единственный экземпляр (ошибка %s) — запускаемся",
            ctypes.get_last_error(),
        )
        return True
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return False
    logger.debug("Мьютекс единственного экземпляра захвачен")
    return True


class AppPipeline:
    """Реальный конвейер обработки: микрофон -> Whisper -> LM Studio.

    Реализует контракт gui.Pipeline (см. tests/test_stage6.py, DemoPipeline).
    """

    def __init__(self, config: AppConfig) -> None:
        self._recorder = AudioRecorder(config.audio)
        self._engine = WhisperEngine(config.whisper)
        self._llm = LLMProcessor(config.llm)

    def load(self) -> None:
        """Загружает модель Whisper в память (вызывать один раз при старте)."""
        self._engine.load()

    def start_recording(self) -> None:
        self._recorder.start()

    def stop_recording(self) -> Path | None:
        return self._recorder.stop()

    def transcribe(self, audio_path: Path):
        return self._engine.transcribe(audio_path)

    def process_text(self, text: str) -> str:
        return self._llm.process(text)


def clean_temp_files(temp_dir: Path) -> None:
    """Удаляет временные WAV, оставшиеся от прошлых запусков (после падений)."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    for path in temp_dir.glob("voice_input_*.wav"):
        try:
            path.unlink()
            logger.info("Удалён остаточный временный файл: %s", path)
        except OSError:
            logger.warning("Не удалось удалить временный файл: %s", path)


def copy_to_clipboard(text: str) -> None:
    """Слот для final_ready: текст в буфер обмена (ошибки буфера не роняют приложение)."""
    try:
        copy_text(text)
    except Exception:
        logger.exception("Не удалось скопировать текст в буфер обмена")
        print(">>> Текст не скопирован в буфер — заберите его из окна приложения.")


def main() -> None:
    setup_logging()
    if not acquire_single_instance():
        # второй экземпляр не запускаем: модель уже в памяти у работающего
        logger.warning("Приложение уже запущено — повторный экземпляр не создан")
        app = QApplication(sys.argv)
        QMessageBox.information(
            None,
            APP_NAME,
            "Приложение уже запущено — значок в трее у часов.\n"
            "Клик по значку покажет окно, выход — через меню значка.",
        )
        sys.exit(0)

    config = AppConfig()
    clean_temp_files(config.audio.temp_dir)

    print(f"{APP_NAME}: загрузка модели Whisper '{config.whisper.model_size}'...", flush=True)
    pipeline = AppPipeline(config)
    pipeline.load()
    print("Модель загружена. Открываю окно...", flush=True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    # окно сворачивается в трей вместо закрытия — приложение живёт, пока его не выключат из трея
    app.setQuitOnLastWindowClosed(False)

    controller = VoiceController(config, pipeline)
    window = VoiceInputWindow(controller, config, start_in_tray=True)
    controller.final_ready.connect(copy_to_clipboard)
    if not window.start_in_tray:  # трей недоступен — показываем обычное окно
        window.show()
    controller.start()

    print(
        f"Приложение запущено (значок у часов). Зажмите Space {config.keys.hold_seconds:g} с,"
        " скажите фразу, отпустите —\n"
        "текст окажется в буфере обмена (Ctrl+V в любом приложении). Выход — меню значка.",
        flush=True,
    )
    exit_code = app.exec()
    controller.shutdown()
    sys.exit(exit_code)
