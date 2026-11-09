---
name: disk-cleaner
description: >-
  Умный помощник для анализа дискового пространства Windows, поиска системного и
  браузерного мусора, кэшей разработчика, тяжёлых папок/файлов, забытых загрузок
  (Downloads), 100% дубликатов по SHA-256 и безопасной очистки (Dry-Run превью +
  отправка в Корзину или полное удаление) с интерактивным Generative UI дашбордом.
  Активируй этот скилл, когда пользователь просит проанализировать диск, проверить
  свободное место, найти мусор/дубликаты или почистить компьютер.
---

# 🧹 Antigravity Disk Cleaner Skill

Этот скилл управляет анализом дискового пространства и безопасной очисткой системы Windows с помощью MCP-сервера `disk-cleaner-mcp` и ядра [disk_cleaner_core.py](./scripts/disk_cleaner_core.py).

## 1. Доступные инструменты

### Через MCP-сервер (`disk-cleaner-mcp`)
Если плагин активен, используй его инструменты напрямую:
- `disk_overview_and_junk` — сводка по всем локальным дискам и полное сканирование категорий мусора.
- `analyze_disk_space` — топ тяжёлых папок, самые крупные файлы (`> 20 МБ`), старые/крупные файлы в `Downloads` и поиск 100% дубликатов по `SHA-256`.
- `clean_disk_junk` — очистка категорий (`target_ids`) или конкретных файлов (`custom_paths`) с параметрами `dry_run` (`true`/`false`) и `mode` (`"recycle"` / `"permanent"`).
- `generate_disk_dashboard` — генерация полного интерактивного HTML-дашборда и компактного виджета `<agent-embed>`.

### Через прямой вызов CLI-движка (работает всегда)
Если MCP-сервер ещё не загружен или нужен прямой запуск из терминала:

```powershell
# 1. Полное сканирование + генерация интерактивного дашборда и компактного виджета
python "skills/disk-cleaner/scripts/disk_cleaner_core.py" --scan --html-out "ui/disk_cleaner_dashboard.html" --compact-out "ui/disk_cleaner_compact.html"

# 2. Dry-Run проверка перед очисткой (ничего не удаляет, проверяет занятые процессами файлы)
python "skills/disk-cleaner/scripts/disk_cleaner_core.py" --clean-ids "user_temp,win_temp,chrome_cache,edge_cache,crash_dumps,wer_reports,thumb_cache,dev_pkg_cache,recycle_bin" --dry-run

# 3. Безопасная очистка с отправкой в Корзину Windows (рекомендуется по умолчанию)
python "skills/disk-cleaner/scripts/disk_cleaner_core.py" --clean-ids "user_temp,chrome_cache" --execute --mode recycle

# 4. Полное удаление без Корзины (только по явному запросу пользователя)
python "skills/disk-cleaner/scripts/disk_cleaner_core.py" --clean-ids "user_temp,recycle_bin" --execute --mode permanent

# 5. Запуск живого веб-сервера дашборда с кнопками очистки в 1 клик
python "skills/disk-cleaner/scripts/disk_cleaner_core.py" --serve --port 8765
```

---

## 2. Категории мусора (`target_ids`)

| ID категории | Описание | Безопасность |
| :--- | :--- | :--- |
| `recycle_bin` | Корзина Windows на всех локальных дисках | `safe` |
| `user_temp` | Временные файлы пользователя (`%TEMP%`) | `safe` |
| `win_temp` | Системные временные файлы (`C:\Windows\Temp`) | `safe` |
| `crash_dumps` | Дампы падений приложений (`CrashDumps`, `Minidump`, `D3DSCache`) | `safe` |
| `wer_reports` | Отчёты об ошибках Windows (`WER`) | `safe` |
| `thumb_cache` | Кэш эскизов Проводника (`thumbcache_*.db`) | `safe` |
| `win_update_cache` | Кэш скачанных обновлений (`SoftwareDistribution\Download`) | `safe` |
| `chrome_cache` | Кэш Google Chrome (без паролей, куки и истории) | `safe` |
| `edge_cache` | Кэш Microsoft Edge (без паролей и сессий) | `safe` |
| `yandex_cache` | Кэш Яндекс.Браузера | `safe` |
| `brave_cache` | Кэш Brave Browser | `safe` |
| `firefox_cache` | Кэш профилей Mozilla Firefox (`cache2`) | `safe` |
| `dev_pkg_cache` | Кэши пакетных менеджеров (`pip`, `npm`, `uv`) | `safe` |
| `scratch_logs` | Разросшиеся `.log` файлы в проектах | `review` |

---

## 3. Стандартный сценарий работы (Workflow)

1. **Анализ и визуализация**:
   - Запусти `generate_disk_dashboard` (или скрипт с `--scan --html-out ... --compact-out ...`).
   - Встрой компактный виджет в ответ с помощью `<agent-embed src="file:///<path>/disk_cleaner_compact.html"></agent-embed>` и дай ссылку на полный интерактивный дашборд.
2. **Dry-Run превью**:
   - Перед любой реальной очисткой сначала покажи результаты `dry_run=True` (сколько мегабайт/гигабайт готово к удалению, а сколько файлов сейчас открыто активными программами и будет безопасно пропущено).
3. **Безопасное удаление (Корзина по умолчанию)**:
   - По умолчанию используй `--mode recycle` (`mode="recycle"`), чтобы все очищаемые файлы отправлялись в Корзину Windows и пользователь мог восстановить любой файл при необходимости.
   - Используй `--mode permanent` только когда пользователь явно просит удалить файлы безвозвратно или очистить саму Корзину (`recycle_bin`).
