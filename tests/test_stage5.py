"""Тест Этапа 5: обработка текста через LM Studio + проверка fallback.

Запуск (терминал PyCharm, venv):
    python -m tests.test_stage5

Перед запуском: LM Studio → вкладка Local Server → Start Server
(модель должна быть загружена в память).

Что проверяет:
    1. Доступность LM Studio (GET /v1/models). Если сервер не запущен —
       тест сообщит об этом, пропустит п.2, но fallback (п.3) всё равно проверит.
    2. Реальную обработку: сырой текст «как из Whisper» (без пунктуации,
       со словами-паразитами) отправляется в LLM, исходник и результат
       печатаются рядом — сравните качество.
    3. Fallback: тот же текст отправляется на заведомо мёртвый порт —
       процессор обязан вернуть исходный текст без изменений.
"""

from __future__ import annotations

import logging

from voice_input.config import AppConfig, LLMConfig, setup_logging
from voice_input.llm_processor import LLMProcessor

logger = logging.getLogger(__name__)

SAMPLE_RU = (
    "ну эээ привет короче это тестовый текст распознавания речи "
    "который whisper выдал без всякой пунктуации и с ошибками"
)

SAMPLE_EN = (
    "uh hello this is a test of speech recognition text without "
    "any punctuation coming from whisper"
)

# Порт, на котором точно никто не слушает — для проверки fallback.
DEAD_URL = "http://localhost:59999/v1"


def check_live_processing() -> bool:
    """П.2: реальная обработка через запущенный LM Studio. False — сервер недоступен."""
    config = AppConfig()
    processor = LLMProcessor(config.llm)

    print("Проверка доступности LM Studio (http://localhost:1234/v1)...", flush=True)
    if not processor.is_available():
        print(
            ">>> LM Studio НЕДОСТУПНА: запустите LM Studio, загрузите модель,\n"
            ">>> вкладка Local Server -> Start Server, затем перезапустите тест.\n"
            ">>> П.2 пропущен, переход к проверке fallback (п.3).\n",
            flush=True,
        )
        return False

    print(f">>> LM Studio доступна, модель: {processor.model}\n", flush=True)
    for sample in (SAMPLE_RU, SAMPLE_EN):
        print(f"ИСХОДНИК : {sample}", flush=True)
        result = processor.process(sample)
        print(f"РЕЗУЛЬТАТ: {result}\n", flush=True)
    return True


def check_fallback() -> bool:
    """П.3: сервер мёртв — исходный текст должен вернуться без изменений."""
    print(f"Проверка fallback (мёртвый адрес {DEAD_URL})...", flush=True)
    processor = LLMProcessor(LLMConfig(base_url=DEAD_URL))
    result = processor.process(SAMPLE_RU)
    if result == SAMPLE_RU:
        print(">>> Fallback OK: исходный текст вернулся без изменений.\n", flush=True)
        return True
    print(f">>> ОШИБКА FALLBACK: текст изменён:\n{result}\n", flush=True)
    return False


def main() -> None:
    setup_logging()
    print("Тест Этапа 5: обработка текста через LM Studio\n", flush=True)

    live_ok = check_live_processing()
    fallback_ok = check_fallback()

    print("=" * 60, flush=True)
    if fallback_ok and live_ok:
        print("ИТОГ: LM Studio работает, fallback работает — этап 5 готов к подтверждению.")
    elif fallback_ok:
        print(
            "ИТОГ: fallback работает, LM Studio недоступна.\n"
            "Запустите сервер в LM Studio и повторите тест для проверки качества."
        )
    else:
        print("ИТОГ: ЕСТЬ ПРОБЛЕМЫ — см. сообщения выше и в voice_input.log.")


if __name__ == "__main__":
    main()
