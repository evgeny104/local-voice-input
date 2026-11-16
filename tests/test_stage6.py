"""Тест Этапа 6: графический интерфейс (демо, без Whisper и LM Studio).

Запуск (терминал PyCharm, venv):
    python -m tests.test_stage6

Откроется окно приложения. Демо-конвейер имитирует работу: запись ничего
не пишет, «распознавание» и «обработка» длятся ~2 с каждый и возвращают
заготовленный текст. Реальные Whisper и LM Studio подключатся на этапе 7.

Проверьте:
    1. Статус «Ожидание». Зажмите Space: появится «Удерживайте Space»,
       через 3 с — «Идёт запись»; отпустите — «Распознавание речи»,
       затем «Обработка текста», затем «Готово», а в поле появится текст.
       Клавиша работает даже когда окно не в фокусе — переключитесь
       в другой редактор и повторите.
    2. Короткое нажатие Space (меньше 3 с) ничего не запускает
       (статус мигнёт и вернётся в «Ожидание»).
    3. Пока идёт «Распознавание/Обработка», нажатия Space игнорируются.
    4. Кнопка «Голосовой ввод»: выкл — статус «Отключено», Space не работает;
       вкл — снова «Ожидание».
    5. Настройки: список микрофонов, выбор модели Whisper, поле URL LM Studio,
       кнопка «Проверить соединение» (сервер запущен — «доступна»).
    6. Закрытие окна завершает приложение без зависаний.

Выход — закрыть окно.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from voice_input.config import AppConfig, setup_logging
from voice_input.gui import Transcript, VoiceController, VoiceInputWindow

logger = logging.getLogger(__name__)

DEMO_RAW = "это демо текст распознавания который whisper выдал без пунктуации"
DEMO_FINAL = "Это демо-текст распознавания, который Whisper выдал без пунктуации."


class DemoPipeline:
    """Имитация конвейера: ничего не записывает, отвечает с задержкой."""

    def start_recording(self) -> None:
        time.sleep(0.05)  # имитация открытия аудиопотока

    def stop_recording(self) -> Path:
        time.sleep(0.05)
        return Path("temp/demo_record.wav")  # файла нет — контроллер удалит его missing_ok

    def transcribe(self, audio_path: Path) -> Transcript:
        logger.info("Демо: имитация распознавания (%s)", audio_path)
        time.sleep(2.0)
        return Transcript(text=DEMO_RAW, language="ru")

    def process_text(self, text: str) -> str:
        logger.info("Демо: имитация обработки LLM")
        time.sleep(2.0)
        return DEMO_FINAL


def main() -> None:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Local Voice Input — тест этапа 6")

    config = AppConfig()
    controller = VoiceController(config, DemoPipeline())
    window = VoiceInputWindow(controller, config)
    window.show()
    controller.start()

    logger.info("Окно теста этапа 6 открыто")
    exit_code = app.exec()
    controller.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
