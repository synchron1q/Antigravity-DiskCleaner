# 🧹 Antigravity Disk Cleaner

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg?logo=windows)](https://microsoft.com/windows)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python)](https://python.org)
[![Antigravity: Skill & Plugin](https://img.shields.io/badge/Antigravity-Skill%20%26%20Plugin-7928CA.svg)](https://github.com/synchron1q/Antigravity-DiskCleaner)
[![Protocol: MCP Stdio](https://img.shields.io/badge/Protocol-MCP%20JSON--RPC%202.0-00A67E.svg)](mcp_config.json)

**Интеллектуальный помощник для глубокого анализа дискового пространства Windows, поиска системного и браузерного мусора, кэшей разработки, дубликатов по SHA-256 и безопасной очистки с интерактивным Generative UI дашбордом.**

[💬 English FAQ](#-quick-faq-frequently-asked-questions) • [О проекте](#-о-проекте) • [Результаты очистки](#-реальные-показатели-очистки-кейс) • [Архитектура безопасности](#-архитектура-безопасности-и-guardrails) • [Инструменты MCP](#-инструменты-mcp-сервера) • [Быстрый старт](#-быстрый-старт)

</div>

---

## 💬 Quick FAQ (Frequently Asked Questions)

> **Fast Answers:** [What is this?](#1-what-is-antigravity-disk-cleaner) • [Safety & Guardrails](#2-how-does-it-guarantee-safety-and-prevent-data-loss) • [19.2 GB Benchmark](#3-how-did-it-free-1918-gb-in-a-real-run) • [Admin / UAC](#4-does-it-require-administrator-privileges) • [Standalone Usage](#5-can-it-be-used-without-google-antigravity) • [Duplicates](#6-how-does-duplicate-detection-work)

### 1. What is Antigravity Disk Cleaner?
**Antigravity Disk Cleaner** is an intelligent Windows storage analyzer and safe cleaner skill/plugin tailored for **Google Antigravity**. Powered by the **Model Context Protocol (MCP)**, it gives AI coding assistants native tools to discover disk hogs, inspect system/browser caches, locate 100% SHA-256 duplicate files, and present interactive Generative UI dashboards directly within the chat interface — with **zero external pip dependencies** (built purely on the native Windows Win32 API).

### 2. How does it guarantee safety and prevent data loss?
Data safety is governed by three strict layers of protection:
1. **Dry-Run First Principle**: The agent always simulates operations first. In-use locked files (e.g., active browser cache files, database logs) are safely detected and skipped without throwing fatal exceptions.
2. **Windows Recycle Bin by default (`SHFileOperationW`)**: Cleaned files are moved to the Windows Recycle Bin with undo flags enabled (`FOF_ALLOWUNDO`). Any removed file can be restored with a single click. Permanent deletion is only executed when explicitly commanded by the user.
3. **Protected Paths Blacklist**: Operations inside `C:\Windows\System32`, `SysWOW64`, `WinSxS`, development environments (**Visual Studio**, **.NET SDK**, **VS Code**), and user projects/courseworks are strictly blocked.

### 3. How did it free +19.18 GB in a real run?
In a stress test on a production Windows system SSD (Drive C:), the cleaner boosted free space from **22.70 GB (10.2%)** to **41.88 GB (18.8%)** — freeing **19.18 GB** in total:
- **12.40 GB**: Windows update caches (`SoftwareDistribution`), crash dumps, WER error reports, and user temp files.
- **3.40 GB**: Orphaned game caches, replay clips, and mod files (BeamNG.drive).
- **1.90 GB**: Steam client cache and temp package data.
- **0.70 GB**: Minecraft and launcher runtime data (`.minecraft`, `.tlauncher`).
- **0.58 GB**: Cloud cache (Google DriveFS) and user-level AppData residues.
- *(An additional **+6.88 GB** is packaged into an automated UAC script for elevated app uninstallation, bringing total potential recovery to **+26.0 GB**).*

### 4. Does it require Administrator privileges?
**No, not for everyday cleaning.** User temp files (`%TEMP%`), browser caches (Chrome, Edge, Firefox, Brave), developer package caches (`pip`, `npm`, `uv`), and Recycle Bin management run under standard user rights without elevation. For system-wide software uninstallation (`C:\Program Files`), the project supplies `Uninstall-ApprovedApps.bat`, which requests standard Windows UAC elevation only when removing those specific apps.

### 5. Can it be used without Google Antigravity?
**Yes.** The core engine (`skills/disk-cleaner/scripts/disk_cleaner_core.py`) is completely self-contained:
- **CLI scan & report:** `python skills/disk-cleaner/scripts/disk_cleaner_core.py --scan --html-out ui/dashboard.html`
- **Safe cleanup:** `python skills/disk-cleaner/scripts/disk_cleaner_core.py --clean-ids "user_temp,chrome_cache" --execute --mode recycle`
- **Local Web Dashboard:** run `scripts/Start-DiskCleaner.bat` or `python skills/disk-cleaner/scripts/disk_cleaner_core.py --serve --port 8765` to open the interactive UI in any browser.

### 6. How does duplicate detection work?
It utilizes a high-performance multi-phase pipeline:
1. Filters files by minimum file size threshold (e.g., `> 20 MB`).
2. Groups candidates by exact byte size.
3. Reads header chunks to eliminate false candidates.
4. Computes full **SHA-256 cryptographic hashes** only on matching collisions.  
This guarantees **100% duplicate accuracy** with zero false matches.

---

## 🎯 О проекте

**Antigravity Disk Cleaner** — это официальный плагин/скилл для **Google Antigravity**, разработанный для безопасного и прозрачного освобождения места на Windows-системах. Он совмещает мощное нативное ядро на Python (без тяжелых внешних pip-зависимостей, на чистом Win32 API), протокол **Model Context Protocol (MCP)** для бесшовного управления через ИИ-агентов и интерактивный **Generative UI дашборд** прямо внутри чата.

---

## 🏆 Реальные показатели очистки (Кейс)

В ходе боевого стресс-теста на системном диске **C:** плагин показал следующие результаты:

| Показатель | До очистки | После 1-го этапа | После 2-го этапа | Суммарно освобождено |
| :--- | :---: | :---: | :---: | :---: |
| **Свободное место на C:** | **22.70 ГБ** (10.2%) | **35.20 ГБ** (15.8%) | **41.88 ГБ** (18.8%) | **+19.18 ГБ** 🎉 |
| **Потенциал с UAC-скриптом** | — | — | **~48.70 ГБ** (21.9%) | **до +26.0 ГБ** |

### 🗂️ Детализация очищенных категорий

```text
[+19.18 ГБ] УСПЕШНО ОСВОБОЖДЕНО:
 ├── 12.40 ГБ — Системные кэши Windows (SoftwareDistribution, Windows Error Reporting, CrashDumps, TEMP)
 ├──  3.40 ГБ — Игровой мусор и кэши (BeamNG.drive моды, видеоповторы, кэш физики)
 ├──  1.90 ГБ — Клиент и кэш Steam (Program Files (x86)\Steam)
 ├──  0.70 ГБ — TLauncher & Minecraft (.minecraft, .tlauncher)
 ├──  0.35 ГБ — Пользовательские кэши AppData (AutoCAD, 1C, OBS Studio, Paint.NET)
 └──  0.23 ГБ — Кэш облачного хранилища Google Drive (DriveFS)

[ +6.88 ГБ] ГОТОВО К УДАЛЕНИЮ ЧЕРЕЗ UAC (Uninstall-ApprovedApps.bat):
 ├──  3.65 ГБ — Autodesk AutoCAD 2026 (Program Files + ProgramData)
 ├──  1.01 ГБ — 1C:Предприятие 8 (Тонкие клиенты x64 и x86)
 ├──  0.83 ГБ — Android SDK & OpenJDK
 ├──  0.61 ГБ — Paint.NET
 ├──  0.46 ГБ — OBS Studio
 └──  0.31 ГБ — Microsoft SQL Server LocalDB
```

---

## 🛡️ Архитектура безопасности и Guardrails

Безопасность пользовательских данных — главный приоритет плагина.

```mermaid
flowchart TD
    Scan["1. Сканирование дисков и категорий"] --> DryRun["2. Симуляция Dry-Run"]
    DryRun --> OpenLock{"Файлы заняты активными процессами?"}
    OpenLock -- Да --> Skip["Пропустить без падения ошибки"]
    OpenLock -- Нет --> Protect{"Файл в защищённом каталоге?"}
    Protect -- "Да (System32, WinSxS, Профиль)" --> Block["Заблокировать удаление"]
    Protect -- Нет --> Action{"Режим удаления"}
    Action -- "По умолчанию (Рекомендуется)" --> Recycle["Отправка в Корзину Windows (SHFileOperationW)"]
    Action -- "По прямому запросу" --> Perm["Полное удаление (Permanent)"]
```

1. **Dry-Run First (Предпросмотр)**: Перед любой реальной очисткой формируется полная калькуляция объёмов и проверка занятости файлов процессами (заблокированные файлы браузеров или баз данных безопасно пропускаются).
2. **Корзина Windows по умолчанию (`SHFileOperationW`)**: Удаляемые файлы не затираются намертво, а перемещаются в Корзину Windows (`FOF_ALLOWUNDO`), откуда их можно восстановить за 1 клик.
3. **Белый список неприкосновенности (Zero False-Positive)**:
   - Среды разработки: **Visual Studio 2022**, **.NET SDK**, **VS Code**, **Google Antigravity**.
   - Офисные пакеты: **Microsoft Office**.
   - Пользовательские медиа: скриншоты (`Pictures\Screenshots`, Lightshot), рабочие архивы и проекты.
   - Защита системных директорий: жесткий запрет на операции в `System32`, `SysWOW64`, `WinSxS`.

---

## ⚡ Инструменты MCP-сервера

Плагин реализует официальный протокол **Model Context Protocol (JSON-RPC 2.0)** через `stdio`, что позволяет ИИ-агентам вызывать инструменты в нативном цикле рассуждений:

| Инструмент MCP | Описание | Параметры |
| :--- | :--- | :--- |
| `disk_overview_and_junk` | Сводка по всем дискам и быстрый аудит категорий мусора | `{}` |
| `analyze_disk_space` | Глубокий анализ: гигантские папки, топ файлов, забытые Downloads, дубликаты | `target_path`, `min_large_mb`, `old_days` |
| `clean_disk_junk` | Безопасная очистка категорий или путей в режимах Dry-Run/Recycle/Permanent | `target_ids`, `custom_paths`, `dry_run`, `mode` |
| `generate_disk_dashboard` | Генерация интерактивного HTML-дашборда и компактного виджета | `output_path`, `compact_path` |

---

## 📊 Интерактивный Generative UI

Плагин включает два уровня визуализации:
1. **Компактный виджет для чата (`ui/disk_cleaner_compact.html`)**: Встраивается прямо в сообщения агента через `<agent-embed>` с актуальными progress bar'ами и карточками свободного места.
2. **Полноэкранный автономный дашборд (`ui/disk_cleaner_dashboard.html`)**: С графиками заполненности, фильтрами категорий, интерактивными кнопками Dry-Run и отправки в Корзину в реальном времени.

---

## 🚀 Быстрый старт

### Вариант 1. Использование в Google Antigravity (Как плагин/скилл)

1. Клонируйте репозиторий в каталог плагинов Antigravity:
   ```powershell
   git clone https://github.com/synchron1q/Antigravity-DiskCleaner.git ~/.gemini/config/plugins/disk-cleaner
   ```
2. Активируйте скилл в диалоге с агентом:
   > *"Проанализируй диск C:, покажи дашборд с мусором и очисти кэш в режиме Dry-Run"*

### Вариант 2. Прямой запуск из командной строки (Standalone CLI)

```powershell
# 1. Сканирование и создание интерактивного дашборда
python skills/disk-cleaner/scripts/disk_cleaner_core.py --scan --html-out ui/dashboard.html

# 2. Безопасная очистка мусора в Корзину Windows
python skills/disk-cleaner/scripts/disk_cleaner_core.py --clean-ids "user_temp,chrome_cache,recycle_bin" --execute --mode recycle

# 3. Запуск веб-сервера локального дашборда
python skills/disk-cleaner/scripts/disk_cleaner_core.py --serve --port 8765
```

### Вариант 3. Запуск через готовые `.bat` скрипты

- `scripts/Start-DiskCleaner.bat` — моментальный запуск сканирования и открытие веб-дашборда в браузере.
- `scripts/Uninstall-ApprovedApps.bat` — полуавтоматический запуск деинсталляторов тяжелых программ с запросом UAC.

---

## 📁 Структура проекта

```text
Antigravity-DiskCleaner/
├── plugin.json                 # Манифест плагина Antigravity
├── mcp_config.json             # Конфигурация MCP-сервера
├── LICENSE                     # MIT Лицензия
├── README.md                   # Документация проекта
├── assets/
│   └── logo.svg                # Фирменный SVG-логотип
├── rules/
│   └── AGENTS.md               # Правила и защитные гардрейлы для ИИ-агентов
├── skills/
│   └── disk-cleaner/
│       ├── SKILL.md            # Инструкция и документация скилла
│       └── scripts/
│           ├── disk_cleaner_core.py  # Нативное ядро (Win32 API, сканер, клинер)
│           └── mcp_server.py         # Stdio MCP Server (JSON-RPC 2.0)
├── ui/
│   ├── disk_cleaner_dashboard.html  # Полноэкранный Generative UI дашборд
│   └── disk_cleaner_compact.html    # Компактный встраиваемый виджет
└── scripts/
    ├── Start-DiskCleaner.bat        # Запуск сканирования и веб-интерфейса
    └── Uninstall-ApprovedApps.bat   # Пакетное удаление одобренных программ (UAC)
```

---

## 👤 Автор

**Serikov Farhat Ibragymuly** ([@synchron1q](https://github.com/synchron1q))

---

## 📄 Лицензия

Проект распространяется под открытой лицензией [MIT](LICENSE).
