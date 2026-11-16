# Local Voice Input

Локальный голосовой ввод для Windows: удерживаете Space 3 с, говорите —
текст оказывается в буфере обмена и вставляется через Ctrl+V.
Распознавание — Whisper на CPU, обработка текста — LM Studio. Без облаков.

## Что нужно

- Windows 10/11, микрофон, Python 3.11+
- ffmpeg (Whisper читает им WAV; подойдёт портативная сборка)
- LM Studio с запущенным сервером — опционально (иначе сырой текст Whisper)

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```


Модель Whisper (small, ~460 МБ) скачается при первом запуске автоматически.

## Запуск

```bash
python main.py
```

Приложение сидит в трее у часов. Зажмите Space 3 с → скажите фразу → отпустите.
После «Готово» вставьте текст через Ctrl+V. Выход — правый клик по значку трея.

## Структура

```
main.py            точка входа
voice_input/       пакет приложения (запись, клавиша, Whisper, LLM, GUI, трей)
tests/             поэтапные тесты: python -m tests.test_stage4
docs/requirements.txt   исходное ТЗ
PROGRESS.md        дневник разработки
```
