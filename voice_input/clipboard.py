"""Работа с системным буфером обмена Windows.

Используем QClipboard из PySide6 (GUI-поток): на Windows setText() сразу
копирует текст в системный буфер, данные не теряются, пока приложение живёт.

Вызывать только после создания QApplication и из GUI-потока
(в приложении это слот сигнала VoiceController.final_ready).
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


def copy_text(text: str) -> None:
    """Копирует текст в буфер обмена. Пустой текст игнорируется."""
    if not text:
        return
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("copy_text вызван до создания QApplication")
    app.clipboard().setText(text)
    logger.info("Текст скопирован в буфер обмена (%d символов)", len(text))
