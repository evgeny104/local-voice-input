"""Тест Этапа 3: удержание Space 3 с → запись → сохранение WAV.

Запуск (терминал PyCharm, venv):
    python -m tests.test_stage3

Действия:
    1. Зажмите и удерживайте Space 3 секунды (в консоль напечатаются пробелы — это нормально).
    2. Дождитесь сообщения «ЗАПИСЬ ИДЁТ», скажите фразу в микрофон.
    3. Отпустите Space — файл сохранится в папке temp в корне проекта, путь будет напечатан.
    4. Проверьте файл: откройте его проигрывателем, в нём должна быть ваша фраза.

Программа завершается после одной успешной записи (или Ctrl+C).
"""

from __future__ import annotations

import logging
import threading

from voice_input.audio_recorder import AudioRecorder, MicrophoneError
from voice_input.config import AppConfig, setup_logging
from voice_input.keyboard_handler import KeyboardHandler

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    config = AppConfig()
    recorder = AudioRecorder(config.audio)
    done = threading.Event()

    def on_record_start() -> None:
        print("\n>>> ЗАПИСЬ ИДЁТ — говорите. Отпустите Space, чтобы закончить.", flush=True)
        try:
            recorder.start()
        except MicrophoneError as exc:
            print(f">>> ОШИБКА МИКРОФОНА: {exc}", flush=True)
            done.set()

    def on_record_stop() -> None:
        path = recorder.stop()
        if path is not None:
            print(f">>> Готово. Файл сохранён: {path}", flush=True)
            print(">>> Проверьте его проигрывателем — в файле должна быть ваша фраза.", flush=True)
        else:
            print(">>> Запись слишком короткая — файл не сохранён.", flush=True)
        done.set()

    handler = KeyboardHandler(config.keys, on_record_start, on_record_stop)
    handler.start()

    print("Тест Этапа 3 запущен.", flush=True)
    print("Зажмите и удерживайте Space 3 секунды, затем говорите.", flush=True)
    try:
        done.wait()
    except KeyboardInterrupt:
        print("\nПрервано пользователем (Ctrl+C).", flush=True)
    finally:
        handler.stop()
        if recorder.is_recording:
            recorder.stop()
        print("Тест завершён.", flush=True)


if __name__ == "__main__":
    main()
