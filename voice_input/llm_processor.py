"""Обработка текста через OpenAI-compatible API LM Studio.

LLM получает сырой текст Whisper и исправляет пунктуацию, очевидные ошибки
распознавания и слова-паразиты, не меняя смысл и стиль речи.

Если LM Studio не запущена или модель недоступна, process() возвращает
исходный текст без изменений (fallback по ТЗ) — голосовой ввод остаётся
работоспособным без сервера.
"""

from __future__ import annotations

import logging

import requests

from .config import LLMConfig

logger = logging.getLogger(__name__)

# Имя-заполнитель: LM Studio подставит загруженную модель независимо
# от переданного значения, поэтому точное имя не обязательно.
DEFAULT_MODEL = "local"

SYSTEM_PROMPT = (
    "Ты — редактор распознанной речи. Получаешь сырой текст от системы "
    "распознавания речи без пунктуации. Твоя задача:\n"
    "- расставить пунктуацию и заглавные буквы;\n"
    "- исправить очевидные ошибки распознавания слов;\n"
    "- убрать слова-паразиты («эээ», «ну», «короче» и подобные), только если "
    "это не меняет смысл;\n"
    "- сохранить исходный смысл и стиль речи;\n"
    "- не добавлять никакой информации от себя;\n"
    "- не превращать разговорную речь в официальный текст.\n"
    "Верни только итоговый текст без пояснений и кавычек."
)


class LLMProcessor:
    """Клиент к локальному серверу LM Studio."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._model: str | None = None

    @property
    def model(self) -> str:
        """Имя загруженной в LM Studio модели (или DEFAULT_MODEL, если неизвестно)."""
        return self._model or DEFAULT_MODEL

    def is_available(self) -> bool:
        """Быстрая проверка: сервер отвечает и в нём загружена модель."""
        try:
            response = requests.get(
                f"{self._config.base_url}/models",
                timeout=self._config.check_timeout_seconds,
            )
            if response.status_code != 200:
                logger.warning("LM Studio ответил кодом %s", response.status_code)
                return False
            models = response.json().get("data") or []
            if not models:
                logger.warning("LM Studio запущен, но модель не загружена")
                return False
            self._model = models[0].get("id") or DEFAULT_MODEL
            return True
        except requests.RequestException as exc:
            logger.warning("LM Studio недоступна: %s", exc)
            return False

    def process(self, text: str) -> str:
        """Обрабатывает текст Whisper через LLM.

        При любой ошибке соединения, таймауте или пустом ответе возвращает
        исходный текст без изменений (fallback).
        """
        text = text.strip()
        if not text:
            return text
        try:
            response = requests.post(
                f"{self._config.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    "temperature": self._config.temperature,
                    "max_tokens": self._config.max_tokens,
                },
                timeout=self._config.timeout_seconds,
            )
            response.raise_for_status()
            choices = response.json().get("choices") or []
            result = (choices[0].get("message") or {}).get("content") or ""
            result = result.strip()
            if not result:
                raise ValueError("LM Studio вернул пустой ответ")
            logger.info("LLM обработал текст (%d -> %d символов)", len(text), len(result))
            return result
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            logger.warning("LLM недоступна (%s) — возвращаю исходный текст Whisper", exc)
            return text
