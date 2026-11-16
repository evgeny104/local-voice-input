"""Распознавание речи локальной моделью Whisper.

Модель загружается в память один раз (load()) и переиспользуется
для всех записей — повторная загрузка при каждой записи недопустима.
Транскрипции сериализованы блокировкой: одновременно выполняется не более одной.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

import whisper

from .config import WHISPER_MODELS, WhisperConfig

logger = logging.getLogger(__name__)


def _ensure_ffmpeg_on_path() -> None:
    """Добавляет папку с ffmpeg.exe в PATH процесса, если ffmpeg не находится.

    Whisper вызывает ffmpeg как внешний процесс; портативная установка ffmpeg
    часто отсутствует в PATH процесса (PyCharm/терминал запущены до изменения
    PATH пользователя), и subprocess падает с FileNotFoundError (WinError 2).
    """
    if shutil.which("ffmpeg"):
        return
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ffmpeg" / "bin",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ffmpeg" / "bin",
    ]
    for candidate in candidates:
        if (candidate / "ffmpeg.exe").is_file():
            os.environ["PATH"] = str(candidate) + os.pathsep + os.environ.get("PATH", "")
            logger.info("ffmpeg найден: %s — папка добавлена в PATH процесса", candidate)
            return
    logger.warning(
        "ffmpeg не найден ни в PATH, ни в известных папках — транскрипция будет "
        "падать. Установите ffmpeg либо добавьте его bin-папку в PATH."
    )


@dataclass
class Transcription:
    """Результат распознавания одной записи."""

    text: str
    language: str  # код языка, определённый Whisper (ru, en, ...)


class WhisperEngine:
    """Обёртка над локальной моделью openai-whisper."""

    def __init__(self, config: WhisperConfig) -> None:
        if config.model_size not in WHISPER_MODELS:
            raise ValueError(
                f"Неизвестный размер модели '{config.model_size}'. "
                f"Допустимые значения: {', '.join(WHISPER_MODELS)}"
            )
        self._config = config
        self._model: whisper.Whisper | None = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Загружает модель в память.

        При первом запуске веса скачиваются автоматически
        (~460 МБ для small) в кэш пользователя ~/.cache/whisper.
        """
        _ensure_ffmpeg_on_path()
        with self._lock:
            if self._model is not None:
                return
            logger.info(
                "Загрузка модели Whisper '%s' (device=%s)...",
                self._config.model_size,
                self._config.device,
            )
            self._model = whisper.load_model(
                self._config.model_size, device=self._config.device
            )
            logger.info("Модель Whisper загружена")

    def unload(self) -> None:
        with self._lock:
            self._model = None
            logger.info("Модель Whisper выгружена из памяти")

    def transcribe(self, audio_path: Path, language: str | None = None) -> Transcription:
        """Преобразует WAV-файл в текст.

        language=None — автоматическое определение языка (русский/английский и др.).
        """
        if self._model is None:
            self.load()
        logger.info("Транскрипция файла: %s", audio_path)
        with self._lock:
            result = self._model.transcribe(
                str(audio_path),
                language=language,
                fp16=self._config.fp16,
            )
        text = (result.get("text") or "").strip()
        detected = result.get("language") or language or ""
        logger.info(
            "Транскрипция завершена (язык=%s, символов=%d)", detected, len(text)
        )
        return Transcription(text=text, language=detected)
