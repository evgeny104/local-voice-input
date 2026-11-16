"""Тест Этапа 4: запись → распознавание Whisper → текст в консоль.

Запуск (терминал PyCharm, venv):
    python -m tests.test_stage4

Что происходит:
    1. При первом запуске скачивается модель Whisper small (~460 МБ) — подождите,
       прогресс скачивания отображается в терминале.
    2. Зажмите Space 3 с, скажите фразу, отпустите Space.
    3. Распознанный текст появится в консоли; WAV-файл удалится автоматически.
    4. Язык определяется автоматически — попробуйте фразы на русском и английском,
       запись можно повторять сколько угодно раз.

Выход — Ctrl+C.
"""

from __future__ import annotations

import logging
import threading

from voice_input.audio_recorder import AudioRecorder, MicrophoneError
from voice_input.config import AppConfig, setup_logging
from voice_input.keyboard_handler import KeyboardHandler
from voice_input.whisper_engine import WhisperEngine

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    config = AppConfig()
    recorder = AudioRecorder(config.audio)
    engine = WhisperEngine(config.whisper)

    print("Загрузка модели Whisper (small)...", flush=True)
    engine.load()
    print("Модель загружена.\n", flush=True)

    handler: KeyboardHandler | None = None

    def on_record_start() -> None:
        print(">>> ЗАПИСЬ ИДЁТ — говорите. Отпустите Space, чтобы закончить.", flush=True)
        try:
            recorder.start()
        except MicrophoneError as exc:
            print(f">>> ОШИБКА МИКРОФОНА: {exc}", flush=True)

    def on_record_stop() -> None:
        path = recorder.stop()
        if path is None:
            print(">>> Запись слишком короткая — попробуйте ещё раз.", flush=True)
            return
        if handler is not None:
            handler.set_busy(True)
        print(">>> РАСПОЗНАВАНИЕ РЕЧИ — на CPU это занимает несколько секунд...", flush=True)

        def work() -> None:
            try:
                result = engine.transcribe(path)
                if result.text:
                    print(
                        f"\n>>> РАСПОЗНАНО (язык: {result.language}):\n{result.text}\n",
                        flush=True,
                    )
                else:
                    print(">>> Речь не распознана (пустой результат).", flush=True)
            except Exception as exc:
                logger.exception("Ошибка транскрипции")
                print(f">>> ОШИБКА РАСПОЗНАВАНИЯ: {exc}", flush=True)
            finally:
                path.unlink(missing_ok=True)
                if handler is not None:
                    handler.set_busy(False)
                print(">>> Готово. Следующая фраза — снова зажмите Space. Выход: Ctrl+C.\n", flush=True)

        threading.Thread(target=work, daemon=True, name="whisper-worker").start()

    handler = KeyboardHandler(config.keys, on_record_start, on_record_stop)
    handler.start()

    print(
        "Тест Этапа 4 запущен. Зажмите и удерживайте Space 3 секунды, затем говорите.",
        flush=True,
    )
    try:
        while True:
            threading.Event().wait(3600)  # спим, пока пользователь не нажмёт Ctrl+C
    except KeyboardInterrupt:
        print("\nПрервано пользователем (Ctrl+C).", flush=True)
    finally:
        handler.stop()
        if recorder.is_recording:
            recorder.stop()
        print("Тест завершён.", flush=True)


if __name__ == "__main__":
    main()
