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
    "Ты редактор распознанной речи. На вход получаешь сырой текст без пунктуации "
    "от системы распознавания речи. Верни только исправленный текст — без пояснений, "
    "без кавычек, без слов «выход»/«ответ».\n"
    "Что делать:\n"
    "1. Расставь пунктуацию и заглавные буквы.\n"
    "2. Исправь очевидные ошибки распознавания слов.\n"
    "3. Удали слова-паразиты (эээ, ну, короче, типа и т.п.), только если смысл не меняется.\n"
    "4. Сохрани смысл и разговорный стиль, ничего не добавляй от себя.\n"
    "\n"
    "Примеры:\n"
    "Вход: ну эээ привет как дела\n"
    "Выход: Привет, как дела?\n"
    "Вход: завтра в десять утра встреча с ивановым обсудить итоги квартала\n"
    "Выход: Завтра в десять утра встреча с Ивановым, обсудить итоги квартала.\n"
    "Вход: hello world this is a test\n"
    "Выход: Hello world, this is a test."
)


def _extract_answer(message: dict) -> str:
    """Достаёт итоговый текст из ответа модели.

    Обычные модели пишут ответ в content. Reasoning-модели (Qwen3 и т.п.) могут
    оставить content пустым и положить всё в reasoning_content — тогда ищем
    финальный ответ: после маркера либо в последнем абзаце рассуждения.
    """
    content = (message.get("content") or "").strip()
    if content:
        return content
    reasoning = (message.get("reasoning_content") or "").strip()
    if not reasoning:
        return ""
    for marker in ("**Final Answer:**", "Final Answer:", "Answer:", "Ответ:"):
        if marker in reasoning:
            tail = reasoning.split(marker)[-1].strip()
            if tail:
                return tail
    paragraphs = [p.strip() for p in reasoning.split("\n\n") if p.strip()]
    return paragraphs[-1] if paragraphs else ""


def _clean_llm_output(result: str) -> str:
    """Убирает типичные обёртки ответа: код-блоки, кавычки, служебные слова.

    Маленькие модели часто игнорируют «без пояснений» и возвращают
    «Выход: ...» в кавычках — зачистим это до чистого текста.
    """
    result = result.strip()
    if result.startswith("```") and result.endswith("```"):
        result = result.strip("`").strip()
    for opening, closing in (("«", "»"), ('"', '"'), ("'", "'")):
        if len(result) > 1 and result[0] == opening and result[-1] == closing:
            result = result[1:-1].strip()
    for label in ("Выход:", "Ответ:", "Результат:", "Итог:", "Итоговый текст:"):
        if result.lower().startswith(label.lower()):
            result = result[len(label):].strip()
    return result


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
                    # для Qwen3 и подобных: пытаемся отключить «размышления»;
                    # шаблоны, которые флаг не знают, просто его игнорируют
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=self._config.timeout_seconds,
            )
            response.raise_for_status()
            message = (response.json().get("choices") or [{}])[0].get("message") or {}
            result = _clean_llm_output(_extract_answer(message))
            if not result:
                raise ValueError("LM Studio вернул пустой ответ")
            logger.info("LLM обработал текст (%d -> %d символов)", len(text), len(result))
            return result
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            logger.warning("LLM недоступна (%s) — возвращаю исходный текст Whisper", exc)
            return text
