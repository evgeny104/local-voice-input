"""Запись аудио с микрофона (sounddevice + soundfile)."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from .config import AudioConfig

logger = logging.getLogger(__name__)


class MicrophoneError(RuntimeError):
    """Микрофон недоступен либо ошибка потока записи."""


class AudioRecorder:
    """Пишет моно-WAV 16 кГц блоками в фоновом аудиопотоке.

    Методы start()/stop() не блокируют вызывающий поток надолго:
    сама запись идёт в потоке обратного вызова sounddevice.
    """

    def __init__(self, config: AudioConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        """Открывает поток записи. Бросает MicrophoneError, если микрофон недоступен."""
        if self.is_recording:
            logger.warning("start() при активной записи — вызов проигнорирован")
            return
        self._frames = []
        try:
            self._stream = sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                blocksize=self._config.blocksize,
                device=self._config.device,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()
        except sd.PortAudioError as exc:
            self._stream = None
            logger.exception("Не удалось открыть микрофон")
            raise MicrophoneError(
                "Микрофон недоступен. Проверьте, что микрофон подключён и разрешён "
                "в параметрах Windows (Конфиденциальность -> Микрофон)."
            ) from exc
        logger.info("Запись начата")

    def stop(self) -> Path | None:
        """Останавливает запись и сохраняет WAV во временный файл.

        Возвращает путь к файлу или None, если запись слишком короткая/пустая.
        Удаление файла — ответственность вызывающего кода.
        """
        stream = self._stream
        if stream is None:
            logger.warning("stop() без активной записи — вызов проигнорирован")
            return None
        self._stream = None  # сначала перестаём принимать блоки
        try:
            stream.stop()
            stream.close()
        except sd.PortAudioError:
            logger.exception("Ошибка при остановке звукового потока")

        with self._lock:
            frames = self._frames
            self._frames = []

        duration = sum(len(f) for f in frames) / self._config.sample_rate
        logger.info("Запись остановлена, длительность %.2f с", duration)
        if not frames or duration < self._config.min_duration:
            logger.warning("Запись слишком короткая (%.2f с) — файл не сохранён", duration)
            return None

        data = np.concatenate(frames, axis=0)
        temp_dir = self._config.temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="voice_input_", suffix=".wav", dir=temp_dir)
        os.close(fd)
        sf.write(tmp_name, data, self._config.sample_rate, subtype="PCM_16")
        logger.info("Аудио сохранено: %s", tmp_name)
        return Path(tmp_name)

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            logger.warning("Статус звукового потока: %s", status)
        with self._lock:
            if self._stream is not None:
                self._frames.append(indata.copy())
