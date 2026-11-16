# Local Voice Input — состояние проекта

> Файл состояния для продолжения работы в новой сессии.
> Последнее обновление: все этапы 1–7 выполнены и проверены. Проект причёсан под git: пакет `voice_input/`, тесты в `tests/`, ТЗ в `docs/`, README. Трей, автозапуск, защита от дублей — на месте.

## Задача
Локальное приложение голосового ввода (Voice Typing): удержание Space 3 с → запись с микрофона → Whisper (локально) → обработка текста в LM Studio (OpenAI-compatible API, localhost:1234) → текст в буфер обмена. Windows, CPU-only, без облаков. Полное ТЗ: `docs/requirements.txt` (этапы 1–7).

## Статус этапов
- ✅ Этап 1 — архитектура (согласована)
- ✅ Этап 2 — зависимости установлены и проверены
- ✅ Этап 3 — запись + клавиша Space, проверен пользователем (файл записывается, фраза слышна)
- ✅ Этап 4 — запись → Whisper → текст, проверен пользователем (RU/EN точно, см. замечания ниже)
- ✅ Этап 5 — LM Studio: llm_processor.py + fallback на сырой текст, проверен пользователем (модель qwen-3b; fallback работает; «короче» не всегда убирается — особенность модели)
- ✅ Этап 6 — GUI PySide6 (gui.py): окно, статусы, кнопка вкл/выкл, настройки; проверен пользователем (исправлен баг: колбэк `_on_press` перекрывал метод `_on_press`)
- ✅ Этап 7 — сборка в main.py + clipboard.py, проверено пользователем: голосовой ввод целиком работает, текст вставляется через Ctrl+V (все 7 этапов ТЗ выполнены)

## Принятые решения (не переобсуждать без запроса)
- Whisper по умолчанию **small** (важно качество русской речи на CPU)
- PyTorch CPU-версия: `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu`
- Пробелы, печатающиеся в окно во время удержания Space — принято пользователем (LLM очистит)
- Временные WAV — в папке `temp/` в корне проекта (в .gitignore), НЕ в системном %TEMP%
- Модель Whisper грузится один раз при старте, не при каждой записи
- Автоопределение языка (language=None в transcribe)

## Замечания к этапу 4 (не баги)
- Мусор («Дуиспекраша?») на короткой/невнятной записи — норма для Whisper; при необходимости поднять `min_duration` в config.py
- Флаг языка на коротких EN-фразах определялся как ru — на текст не влияет

## Окружение
- venv: `.venv`, **Python 3.14.10**, pip 26
- Установлено: torch 2.15.0+cpu, openai-whisper 20250625, PySide6 6.12.0, sounddevice 0.5.6, soundfile 0.14.0, pynput 1.8.2, requests 2.34.2, numpy 2.5.x
- ffmpeg 9.0.2 — портативно в `%LOCALAPPDATA%\Programs\ffmpeg\bin`. ⚠️ В user PATH ffmpeg **не прописан** (проверено реестром — запись отсутствует), поэтому whisper_engine.py сам ищет ffmpeg.exe в `%LOCALAPPDATA%\Programs\ffmpeg\bin` и добавляет папку в PATH процесса (`_ensure_ffmpeg_on_path()`). Приложение больше НЕ зависит от системного PATH.
- Модель whisper small скачана в `~/.cache/whisper` (461 МБ)
- Микрофон по умолчанию: Microphone (Logi C270 HD WebCam)
- Логи приложения: `voice_input.log` (setup_logging из config.py)

## Структура (причесана под git)
- `main.py` — тонкая точка входа: `from voice_input.app import main`
- `voice_input/` — пакет приложения (все модули ниже), импорты внутри — относительные
- `voice_input/config.py` — AppConfig (AudioConfig/KeyConfig/WhisperConfig/LLMConfig), PROJECT_ROOT, setup_logging() (лог в корне проекта)
- `voice_input/audio_recorder.py` — AudioRecorder: start/stop, WAV в temp/, MicrophoneError, min_duration 0.5 с
- `voice_input/keyboard_handler.py` — KeyboardHandler: pynput-слушатель, таймер 3 с, защита от key repeat, set_busy(); опциональные on_press/on_cancel (⚠️ хранятся в `_on_press_cb`/`_on_cancel_cb` — имя `_on_press` занято методом)
- `voice_input/whisper_engine.py` — WhisperEngine: load() один раз, transcribe() → Transcription, блокировка; `_ensure_ffmpeg_on_path()` — сам ищет ffmpeg.exe
- `voice_input/llm_processor.py` — LLMProcessor: is_available() + process() с fallback на исходный текст
- `voice_input/clipboard.py` — copy_text() через QClipboard (только GUI-поток)
- `voice_input/gui.py` — AppStatus (8 состояний), VoiceController (KeyboardHandler+Pipeline через Qt-сигналы, фоновый поток), VoiceInputWindow (статусы, вкл/выкл, текст, настройки, трей: старт свёрнутым start_in_tray, закрытие->трей, уведомления; требует app.setQuitOnLastWindowClosed(False))
- `voice_input/app.py` — AppPipeline (контракт gui.Pipeline), acquire_single_instance() (мьютекс WinAPI), clean_temp_files(), main() (сборка + final_ready -> буфер)
- `tests/` — поэтапные тесты (`python -m tests.test_stageN` из корня): stage3 запись+клавиша, stage4 +Whisper, stage5 +LM Studio/fallback, stage6 GUI с демо-конвейером
- `docs/requirements.txt` — исходное ТЗ
- `README.md` — краткое описание: что нужно и как запустить
- Автозапуск: ярлык «Local Voice Input.lnk» в shell:startup -> .venv\Scripts\pythonw.exe main.py; дубль на рабочем столе (OneDrive\Desktop). Удалить ярлык = отключить автозапуск

## Договорённости по процессу
- Работаем поэтапно; каждый этап пользователь подтверждает фактическим тестом
- Пользователь: PyCharm, Windows, CPU-only, русскоязычный
- Тесты этапов запускает пользователь в терминале PyCharm (нужны физические действия: микрофон, клавиши)
