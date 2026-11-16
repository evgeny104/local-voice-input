"""Глобальная обработка клавиши Space (pynput).

Работает системно — окно приложения может быть не в фокусе.
Логика:
  - нажатие Space запускает таймер на hold_seconds (on_press — статус «удерживайте»);
  - отпускание раньше времени — запись не начинается (on_cancel — возврат в «ожидание»);
  - удержание hold_seconds — срабатывает on_record_start();
  - отпускание во время записи — on_record_stop();
  - автоповтор клавиши (key repeat) подавлен;
  - пока установлен флаг busy (идёт распознавание/обработка), клавиша игнорируется.

ВАЖНО: обратные вызовы выполняются в потоках слушателя/таймера,
поэтому они не должны блокироваться и не должны трогать GUI напрямую.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from pynput import keyboard
from pynput.keyboard import Key

from .config import KeyConfig

logger = logging.getLogger(__name__)


class KeyboardHandler:
    """Отслеживает удержание Space и сообщает о старте/стопе записи."""

    def __init__(
        self,
        config: KeyConfig,
        on_record_start: Callable[[], None],
        on_record_stop: Callable[[], None],
        on_press: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self._config = config
        self._on_record_start = on_record_start
        self._on_record_stop = on_record_stop
        self._on_press_cb = on_press        # нажали Space, идёт отсчёт удержания
        self._on_cancel_cb = on_cancel      # отпустили раньше времени

        self._listener: keyboard.Listener | None = None
        self._hold_timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._pressed = False    # Space сейчас зажата (защита от key repeat)
        self._recording = False  # идёт запись
        self._busy = False       # идёт обработка результата

    @property
    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, value: bool) -> None:
        """Блокирует/разблокирует реакцию на Space (используется во время обработки)."""
        with self._lock:
            self._busy = value

    def start(self) -> None:
        """Запускает фоновый слушатель клавиатуры."""
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()
        logger.info("Слушатель клавиатуры запущен")

    def stop(self) -> None:
        """Останавливает слушатель и таймер. Вызывать при завершении приложения."""
        with self._lock:
            timer = self._hold_timer
            self._hold_timer = None
        if timer is not None:
            timer.cancel()
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        logger.info("Слушатель клавиатуры остановлен")

    def _on_press(self, key) -> None:
        if key != Key.space:
            return
        with self._lock:
            if self._busy or self._pressed:
                return
            self._pressed = True
            self._hold_timer = threading.Timer(
                self._config.hold_seconds, self._on_hold_elapsed
            )
            self._hold_timer.daemon = True
            self._hold_timer.start()
        logger.info("Space нажата — ждём удержания %.1f с", self._config.hold_seconds)
        if self._on_press_cb is not None:
            try:
                self._on_press_cb()
            except Exception:
                logger.exception("Ошибка в on_press")

    def _on_hold_elapsed(self) -> None:
        with self._lock:
            if not self._pressed or self._busy:
                return
            self._recording = True
        logger.info("Space удержана %.1f с — начинаем запись", self._config.hold_seconds)
        try:
            self._on_record_start()
        except Exception:
            logger.exception("Ошибка в on_record_start")
            with self._lock:
                self._recording = False
                self._pressed = False

    def _on_release(self, key) -> None:
        if key != Key.space:
            return
        with self._lock:
            if not self._pressed:
                return
            self._pressed = False
            timer = self._hold_timer
            self._hold_timer = None
            was_recording = self._recording
            self._recording = False
        if timer is not None:
            timer.cancel()
        if was_recording:
            logger.info("Space отпущена — останавливаем запись")
            try:
                self._on_record_stop()
            except Exception:
                logger.exception("Ошибка в on_record_stop")
        elif self._on_cancel_cb is not None:
            try:
                self._on_cancel_cb()
            except Exception:
                logger.exception("Ошибка в on_cancel")
