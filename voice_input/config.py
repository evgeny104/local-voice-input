"""Настройки приложения: модель Whisper, LM Studio, микрофон, клавиша."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "Local Voice Input"

# Корень проекта: config.py лежит в voice_input/, проект — на уровень выше
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = PROJECT_ROOT / "voice_input.log"

# Допустимые размеры модели Whisper (качество и требования к CPU растут слева направо).
WHISPER_MODELS: tuple[str, ...] = ("tiny", "base", "small", "medium", "large")


@dataclass
class AudioConfig:
    """Параметры записи с микрофона."""

    sample_rate: int = 16_000      # Whisper обучен на 16 кГц
    channels: int = 1              # моно
    blocksize: int = 1_024         # ~64 мс на блок при 16 кГц
    device: int | None = None      # None — микрофон по умолчанию
    min_duration: float = 0.5      # записи короче отбрасываются, секунды
    # Папка для временных WAV — в корне проекта (попадает в .gitignore).
    temp_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "temp")


@dataclass
class KeyConfig:
    """Параметры триггерной клавиши."""

    hold_seconds: float = 1      # удержание Space до старта записи


@dataclass
class WhisperConfig:
    """Параметры локальной модели Whisper."""

    model_size: str = "medium"     # по умолчанию medium (CPU, важно качество русской речи)
    device: str = "cpu"
    fp16: bool = False             # на CPU обязательно False


@dataclass
class LLMConfig:
    """Параметры подключения к локальному серверу LM Studio."""

    base_url: str = "http://localhost:1234/v1"
    temperature: float = 0.2       # низкая температура — правим текст, не сочиняем
    max_tokens: int = 2_000
    timeout_seconds: float = 90.0
    check_timeout_seconds: float = 2.0   # таймаут быстрой проверки доступности


@dataclass
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    keys: KeyConfig = field(default_factory=KeyConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


def setup_logging(level: int = logging.INFO) -> None:
    """Настраивает логи: файл voice_input.log + консоль. Безопасен к повторному вызову."""
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)

    root.addHandler(file_handler)
    root.addHandler(console)
