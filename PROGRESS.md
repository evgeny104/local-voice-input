# Local Voice Input — состояние проекта

> Файл состояния для продолжения работы в новой сессии.
> Последнее обновление: все этапы 1–7 выполнены и проверены. Проект причёсан под git:
> пакет `voice_input/`, тесты в `tests/`, ТЗ в `docs/`, README. Трей, автозапуск,
> защита от дублей — на месте.

## Задача

Локальное приложение голосового ввода (Voice Typing): удержание Space 1,5 с → запись с микрофона →
Whisper (локально) → обработка текста в LM Studio (OpenAI-compatible API, localhost:1234) →
текст в буфер обмена. Windows, CPU-only, без облаков.
Полное ТЗ: `docs/requirements.txt` (этапы 1–7, работа поэтапно, переход после проверки этапа).

## Статус этапов

- ✅ Этап 1 — архитектура (согласована)
- ✅ Этап 2 — зависимости установлены и проверены
- ✅ Этап 3 — запись + клавиша Space, проверен пользователем (файл записывается, фраза слышна)
- ✅ Этап 4 — запись → Whisper → текст, проверен пользователем (RU/EN точно, см. замечания ниже)
- ✅ Этап 5 — LM Studio: llm_processor.py + fallback на сырой текст, проверен пользователем
  (fallback работает; «короче» не всегда убирается — особенность выбранной модели)
- ✅ Этап 6 — GUI PySide6: окно, статусы, кнопка вкл/выкл, настройки; проверен пользователем
  (исправлен баг: колбэк `_on_press` перекрывал метод `_on_press`)
- ✅ Этап 7 — сборка (`app.py` + `clipboard.py`), проверено пользователем: голосовой ввод целиком
  работает, текст вставляется через Ctrl+V (все 7 этапов ТЗ выполнены)

## Принятые решения

- Whisper по умолчанию **medium** (важно качество русской речи на CPU)
- PyTorch CPU-версия: `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu`
- Пробелы, печатающиеся в фокусированное окно во время удержания Space — известный компромисс
- Временные WAV — в папке `temp/` в корне проекта (в .gitignore), НЕ в системном %TEMP%
- Модель Whisper грузится один раз при старте, не при каждой записи
- Автоопределение языка (language=None в transcribe)

## Замечания к качеству (не баги)

- Мусор на короткой/невнятной записи — норма для Whisper; при желании поднять `min_duration`
- Флаг языка на коротких английских фразах может определяться как ru — на текст не влияет

## Окружение разработки

- Python 3.14, torch 2.15.0+cpu, openai-whisper 20250625, PySide6 6.12.0, sounddevice 0.5.6,
  soundfile 0.14.0, pynput 1.8.2, requests 2.34.2, numpy 2.5.x
- ffmpeg 9.0.2: whisper_engine сам ищет ffmpeg.exe (`%LOCALAPPDATA%\Programs\ffmpeg\bin` или PATH)
  и добавляет папку в PATH процесса — приложение не зависит от системного PATH
- Модель whisper medium скачивается в `~/.cache/whisper` (~1.5 ГБ) при первом запуске
- Логи приложения: `voice_input.log` (setup_logging из config.py, файл в корне проекта)

## Структура

- `main.py` — тонкая точка входа: `from voice_input.app import main`
- `voice_input/` — пакет приложения, импорты внутри относительные:
  - `config.py` — AppConfig (аудио, клавиша, Whisper, LM Studio), PROJECT_ROOT, setup_logging()
  - `audio_recorder.py` — запись с микрофона в WAV (sounddevice + soundfile)
  - `keyboard_handler.py` — глобальная Space: таймер 1,5 с, защита от key repeat, set_busy();
    опциональные on_press/on_cancel (⚠️ хранятся в `_on_press_cb`/`_on_cancel_cb` —
    имя `_on_press` занято методом, атрибут с таким именем его перекрыл бы — баг этапа 6)
  - `whisper_engine.py` — WhisperEngine: load() один раз, transcribe() → Transcription,
    блокировка транскрипций; `_ensure_ffmpeg_on_path()` — сам ищет ffmpeg.exe
  - `llm_processor.py` — LLMProcessor: is_available() + process() с fallback на исходный текст
  - `clipboard.py` — copy_text() через QClipboard (только GUI-поток)
  - `gui.py` — AppStatus (8 состояний), VoiceController (KeyboardHandler+Pipeline через
    Qt-сигналы, обработка в фоновом потоке), VoiceInputWindow (статусы, вкл/выкл, текст,
    настройки, трей: старт свёрнутым start_in_tray, закрытие -> трей, уведомления;
    требует app.setQuitOnLastWindowClosed(False))
  - `app.py` — AppPipeline (контракт gui.Pipeline), acquire_single_instance() (мьютекс WinAPI),
    clean_temp_files(), main() (сборка + final_ready -> буфер обмена)
- `tests/` — поэтапные тесты, запуск из корня: `python -m tests.test_stageN`
  (stage3: запись+клавиша; stage4: +Whisper; stage5: +LM Studio/fallback; stage6: GUI с демо)
- `docs/requirements.txt` — исходное ТЗ
- `README.md` — краткое описание: что нужно и как запустить

## Эксплуатация (вне репозитория)

- Автозапуск: ярлык в shell:startup -> `.venv\Scripts\pythonw.exe main.py`; дубль на рабочем столе.
  Удалить ярлык = отключить автозапуск. Папку проекта не переименовывать — пути в ярлыках.
- Защита от дубля: именованный мьютекс WinAPI (`app.acquire_single_instance`) — повторный запуск
  показывает сообщение и завершается; при смерти процесса мьютекс освобождается автоматически.

## Процесс

- Работа велась поэтапно, каждый этап подтверждался ручным тестом (микрофон, клавиши)
- Тесты этапов — самостоятельные скрипты, не pytest
