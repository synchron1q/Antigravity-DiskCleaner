#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Disk Cleaner — Core Engine (Windows)
Анализ дискового пространства, поиск системного мусора, кэшей, старых загрузок,
дубликатов файлов, безопасная очистка (Dry-Run + Корзина Windows + Полное удаление)
и генерация интерактивных Generative UI виджетов.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import datetime as dt
import glob
import hashlib
import html
import http.server
import json
import os
import shutil
import socketserver
import stat
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ============================================================================
# Windows Native API Helpers (ctypes, zero external dependencies)
# ============================================================================

class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400

SHERB_NOCONFIRMATION = 0x00000001
SHERB_NOPROGRESSUI = 0x00000002
SHERB_NOSOUND = 0x00000004


def format_size(num_bytes: float | int) -> str:
    """Форматирует байты в человекочитаемый вид (Б, КБ, МБ, ГБ, ТБ)."""
    val = float(max(0, num_bytes))
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ", "ПБ"]
    idx = 0
    while val >= 1024.0 and idx < len(units) - 1:
        val /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(val)} {units[idx]}"
    return f"{val:.1f} {units[idx]}"


def query_recycle_bin() -> Tuple[int, int]:
    """Возвращает (размер_в_байтах, количество_элементов) в Корзине Windows."""
    if sys.platform != "win32":
        return 0, 0
    total_size = 0
    total_items = 0
    try:
        drives = get_drives_overview()
        for drv in drives:
            mount = drv.get("mount", "C:\\")
            info = SHQUERYRBINFO()
            info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
            res = ctypes.windll.shell32.SHQueryRecycleBinW(mount, ctypes.byref(info))
            if res == 0:
                total_size += max(0, int(info.i64Size))
                total_items += max(0, int(info.i64NumItems))
    except Exception:
        pass
    return total_size, total_items


def empty_recycle_bin() -> Tuple[bool, str]:
    """Очищает Корзину Windows."""
    if sys.platform != "win32":
        return False, "Supported only on Windows"
    try:
        flags = SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        # S_OK (0) or E_UNEXPECTED (-2147418113 when already empty)
        if res == 0 or res == -2147418113:
            return True, "Корзина успешно очищена"
        return False, f"Код возврата SHEmptyRecycleBinW: {res}"
    except Exception as exc:
        return False, str(exc)


def send_paths_to_recycle_bin(paths: List[str]) -> Tuple[int, int, List[str]]:
    """
    Отправляет список путей (файлов/папок) в Корзину Windows через SHFileOperationW.
    Возвращает (успешно_удалено, пропущено, список_ошибок).
    """
    if not paths:
        return 0, 0, []

    valid_paths = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not valid_paths:
        return 0, 0, []

    deleted_count = 0
    skipped_count = 0
    errors: List[str] = []

    # Process in chunks of 40 paths so locked files don't block the entire batch
    chunk_size = 40
    for i in range(0, len(valid_paths), chunk_size):
        chunk = valid_paths[i : i + chunk_size]
        # Double-null terminated string required by SHFileOperationW
        p_from = "\0".join(chunk) + "\0\0"
        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = p_from
        op.pTo = None
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        op.fAnyOperationsAborted = False
        op.hNameMappings = None
        op.lpszProgressTitle = None

        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if res == 0 and not op.fAnyOperationsAborted:
            deleted_count += len(chunk)
        else:
            # Fallback item-by-item for this chunk to isolate locked files
            for single_path in chunk:
                if not os.path.exists(single_path):
                    deleted_count += 1
                    continue
                single_op = SHFILEOPSTRUCTW()
                single_op.hwnd = None
                single_op.wFunc = FO_DELETE
                single_op.pFrom = single_path + "\0\0"
                single_op.pTo = None
                single_op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
                s_res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(single_op))
                if s_res == 0 and not os.path.exists(single_path):
                    deleted_count += 1
                else:
                    skipped_count += 1
                    if len(errors) < 10:
                        errors.append(f"Занят или недоступен: {os.path.basename(single_path)}")

    return deleted_count, skipped_count, errors


# ============================================================================
# Protected Paths Guardrail
# ============================================================================

def is_protected_path(path_str: str) -> bool:
    """Проверяет, не входит ли путь в список критически защищённых системных директорий."""
    try:
        norm = os.path.normcase(os.path.abspath(path_str)).rstrip("\\/")
    except Exception:
        return True

    user_profile = os.path.normcase(os.environ.get("USERPROFILE", r"C:\Users\Default")).rstrip("\\/")
    win_dir = os.path.normcase(os.environ.get("SystemRoot", r"C:\Windows")).rstrip("\\/")

    # Exact roots that must NEVER be deleted directly
    exact_forbidden = {
        "c:",
        "c:\\",
        "d:",
        "d:\\",
        win_dir,
        user_profile,
        os.path.join(user_profile, "desktop"),
        os.path.join(user_profile, "documents"),
        os.path.join(user_profile, "downloads"),
        os.path.join(user_profile, "appdata"),
        os.path.join(user_profile, "appdata\\local"),
        os.path.join(user_profile, "appdata\\roaming"),
        r"c:\program files",
        r"c:\program files (x86)",
        r"c:\programdata",
        r"c:\users",
    }
    if norm in exact_forbidden or len(norm) <= 3:
        return True

    # Prefixes that must NEVER have anything deleted inside them
    forbidden_prefixes = [
        os.path.join(win_dir, "system32"),
        os.path.join(win_dir, "syswow64"),
        os.path.join(win_dir, "winsxs"),
        os.path.join(win_dir, "boot"),
        os.path.join(win_dir, "fonts"),
        r"c:\program files",
        r"c:\program files (x86)",
    ]
    for prefix in forbidden_prefixes:
        if norm == prefix or norm.startswith(prefix + "\\"):
            return True

    return False


# ============================================================================
# 1. Drives Overview
# ============================================================================

def get_drives_overview(warning_pct: float = 20.0, critical_pct: float = 10.0) -> List[Dict[str, Any]]:
    """Собирает сводку по всем локальным дискам Windows."""
    drives: List[Dict[str, Any]] = []
    if sys.platform != "win32":
        usage = shutil.disk_usage("/")
        free_pct = round(usage.free / usage.total * 100, 1) if usage.total else 0.0
        drives.append({
            "drive": "/",
            "mount": "/",
            "label": "Root",
            "filesystem": "ext4/apfs",
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "total_human": format_size(usage.total),
            "used_human": format_size(usage.used),
            "free_human": format_size(usage.free),
            "used_pct": round(100.0 - free_pct, 1),
            "free_pct": free_pct,
            "status": "Critical" if free_pct < critical_pct else ("Warning" if free_pct < warning_pct else "OK"),
        })
        return drives

    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for i in range(26):
        if not (bitmask & (1 << i)):
            continue
        letter = f"{chr(65 + i)}:"
        mount = f"{letter}\\"
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(mount)
        # DRIVE_FIXED = 3, DRIVE_REMOVABLE = 2
        if drive_type not in (2, 3):
            continue

        try:
            usage = shutil.disk_usage(mount)
        except Exception:
            continue
        if usage.total <= 0:
            continue

        vol_name_buf = ctypes.create_unicode_buffer(261)
        fs_name_buf = ctypes.create_unicode_buffer(261)
        ctypes.windll.kernel32.GetVolumeInformationW(
            mount,
            vol_name_buf,
            ctypes.sizeof(vol_name_buf),
            None,
            None,
            None,
            fs_name_buf,
            ctypes.sizeof(fs_name_buf),
        )

        free_pct = round((usage.free / usage.total) * 100.0, 1)
        used_pct = round(100.0 - free_pct, 1)
        if free_pct < critical_pct:
            status = "Critical"
        elif free_pct < warning_pct:
            status = "Warning"
        else:
            status = "OK"

        drives.append({
            "drive": letter,
            "mount": mount,
            "label": vol_name_buf.value or "Локальный диск",
            "filesystem": fs_name_buf.value or "NTFS",
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "total_human": format_size(usage.total),
            "used_human": format_size(usage.used),
            "free_human": format_size(usage.free),
            "used_pct": used_pct,
            "free_pct": free_pct,
            "status": status,
        })

    return drives


# ============================================================================
# 2. Fast Directory & Junk Scanner
# ============================================================================

def scan_dir_stats(
    paths: List[str],
    file_glob: Optional[str] = None,
    max_files: int = 25000,
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """
    Быстро подсчитывает размер (в байтах), число файлов и топ-5 самых больших файлов
    внутри переданного списка директорий или файлов.
    """
    total_bytes = 0
    file_count = 0
    top_samples: List[Tuple[int, str]] = []

    stack = [p for p in paths if p and os.path.exists(p)]
    visited = set()

    while stack and file_count < max_files:
        current = stack.pop()
        try:
            real_cur = os.path.normcase(os.path.abspath(current))
            if real_cur in visited:
                continue
            visited.add(real_cur)
        except Exception:
            continue

        if os.path.isfile(current):
            try:
                sz = os.path.getsize(current)
                total_bytes += sz
                file_count += 1
                top_samples.append((sz, current))
            except Exception:
                pass
            continue

        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if not file_glob:
                                stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            if file_glob and not Path(entry.name).match(file_glob):
                                continue
                            sz = entry.stat(follow_symlinks=False).st_size
                            total_bytes += sz
                            file_count += 1
                            if len(top_samples) < 20 or sz > top_samples[-1][0]:
                                top_samples.append((sz, entry.path))
                                top_samples.sort(key=lambda x: x[0], reverse=True)
                                if len(top_samples) > 5:
                                    top_samples = top_samples[:5]
                    except Exception:
                        continue
        except Exception:
            continue

    top_samples.sort(key=lambda x: x[0], reverse=True)
    formatted_samples = [
        {
            "name": os.path.basename(p),
            "path": p,
            "size_bytes": sz,
            "size_human": format_size(sz),
        }
        for sz, p in top_samples[:5]
    ]
    return total_bytes, file_count, formatted_samples


def get_junk_definitions() -> List[Dict[str, Any]]:
    """Возвращает каталог всех проверяемых категорий мусора и кэшей Windows."""
    local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
    roaming_app = os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming"))
    user_temp = os.environ.get("TEMP", os.path.join(local_app, "Temp"))
    win_dir = os.environ.get("SystemRoot", r"C:\Windows")
    prog_data = os.environ.get("ProgramData", r"C:\ProgramData")
    user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))

    # Find Firefox cache2 dirs dynamically
    ff_profiles = glob.glob(os.path.join(local_app, r"Mozilla\Firefox\Profiles\*\cache2"))
    # Find Chrome/Edge/Brave/Yandex profile caches across Default and Profile *
    def browser_cache_dirs(base_user_data: str) -> List[str]:
        res = []
        if not os.path.isdir(base_user_data):
            return res
        for prof in ["Default"] + [f"Profile {i}" for i in range(1, 6)]:
            p_dir = os.path.join(base_user_data, prof)
            if os.path.isdir(p_dir):
                for sub in ("Cache", "Code Cache", "GPUCache", r"Service Worker\CacheStorage"):
                    cand = os.path.join(p_dir, sub)
                    if os.path.isdir(cand):
                        res.append(cand)
        return res

    # Find large .log files in scratch projects
    scratch_logs = glob.glob(os.path.join(user_profile, r".gemini\antigravity\scratch\**\*.log"), recursive=True)

    return [
        {
            "id": "recycle_bin",
            "name": "Корзина Windows (Recycle Bin)",
            "category": "recycle_bin",
            "category_label": "Корзина",
            "safety": "safe",
            "description": "Файлы, ранее удалённые в Корзину на всех локальных дисках.",
            "paths": ["RECYCLE_BIN"],
        },
        {
            "id": "user_temp",
            "name": "Временные файлы пользователя (%TEMP%)",
            "category": "system_temp",
            "category_label": "Системный мусор Windows",
            "safety": "safe",
            "description": "Временные файлы установщиков, распакованных архивов и запущенных программ.",
            "paths": list(dict.fromkeys([os.path.join(local_app, "Temp"), user_temp])),
        },
        {
            "id": "win_temp",
            "name": "Системные временные файлы (Windows\\Temp)",
            "category": "system_temp",
            "category_label": "Системный мусор Windows",
            "safety": "safe",
            "description": "Системная папка временных файлов служб Windows.",
            "paths": [os.path.join(win_dir, "Temp")],
        },
        {
            "id": "crash_dumps",
            "name": "Дампы падений и ошибок (CrashDumps & Minidump)",
            "category": "logs_dumps",
            "category_label": "Логи и дампы",
            "safety": "safe",
            "description": "Тяжёлые дампы памяти (.dmp) после сбоев программ и системы.",
            "paths": [
                os.path.join(local_app, "CrashDumps"),
                os.path.join(win_dir, "Minidump"),
                os.path.join(local_app, "D3DSCache"),
            ],
        },
        {
            "id": "wer_reports",
            "name": "Отчёты об ошибках Windows (WER)",
            "category": "logs_dumps",
            "category_label": "Логи и дампы",
            "safety": "safe",
            "description": "Накопленные архивы и очереди диагностики Windows Error Reporting.",
            "paths": [
                os.path.join(local_app, r"Microsoft\Windows\WER"),
                os.path.join(prog_data, r"Microsoft\Windows\WER"),
            ],
        },
        {
            "id": "thumb_cache",
            "name": "Кэш эскизов Проводника (Thumbnails)",
            "category": "system_temp",
            "category_label": "Системный мусор Windows",
            "safety": "safe",
            "description": "Базы предпросмотра картинок и видео (thumbcache_*.db).",
            "paths": [os.path.join(local_app, r"Microsoft\Windows\Explorer")],
            "file_glob": "thumbcache_*.db",
        },
        {
            "id": "win_update_cache",
            "name": "Кэш загрузок обновлений Windows (SoftwareDistribution)",
            "category": "system_temp",
            "category_label": "Системный мусор Windows",
            "safety": "safe",
            "description": "Скачанные пакеты уже установленных обновлений Windows.",
            "paths": [os.path.join(win_dir, r"SoftwareDistribution\Download")],
        },
        {
            "id": "chrome_cache",
            "name": "Кэш браузера Google Chrome",
            "category": "browser_cache",
            "category_label": "Кэши браузеров",
            "safety": "safe",
            "description": "Временный веб-кэш, GPUCache и Code Cache (пароли, история и сессии НЕ затрагиваются).",
            "paths": browser_cache_dirs(os.path.join(local_app, r"Google\Chrome\User Data")),
        },
        {
            "id": "edge_cache",
            "name": "Кэш браузера Microsoft Edge",
            "category": "browser_cache",
            "category_label": "Кэши браузеров",
            "safety": "safe",
            "description": "Временный веб-кэш Edge (пароли, вкладки и куки НЕ затрагиваются).",
            "paths": browser_cache_dirs(os.path.join(local_app, r"Microsoft\Edge\User Data")),
        },
        {
            "id": "yandex_cache",
            "name": "Кэш Яндекс.Браузера",
            "category": "browser_cache",
            "category_label": "Кэши браузеров",
            "safety": "safe",
            "description": "Временный кэш Яндекс.Браузера без удаления авторизаций.",
            "paths": browser_cache_dirs(os.path.join(local_app, r"Yandex\YandexBrowser\User Data")),
        },
        {
            "id": "brave_cache",
            "name": "Кэш браузера Brave",
            "category": "browser_cache",
            "category_label": "Кэши браузеров",
            "safety": "safe",
            "description": "Временный веб-кэш Brave Browser.",
            "paths": browser_cache_dirs(os.path.join(local_app, r"BraveSoftware\Brave-Browser\User Data")),
        },
        {
            "id": "firefox_cache",
            "name": "Кэш браузера Mozilla Firefox",
            "category": "browser_cache",
            "category_label": "Кэши браузеров",
            "safety": "safe",
            "description": "Кэш профилей Firefox (cache2).",
            "paths": ff_profiles,
        },
        {
            "id": "dev_pkg_cache",
            "name": "Кэши менеджеров пакетов (pip, npm, uv)",
            "category": "dev_cache",
            "category_label": "Кэши разработки",
            "safety": "safe",
            "description": "Скачанные архивы колёс Python (.whl) и пакетов npm/uv.",
            "paths": [
                os.path.join(local_app, r"pip\cache"),
                os.path.join(local_app, "npm-cache"),
                os.path.join(roaming_app, "npm-cache"),
                os.path.join(local_app, r"uv\cache"),
            ],
        },
        {
            "id": "scratch_logs",
            "name": "Разросшиеся лог-файлы в проектах (*.log)",
            "category": "logs_dumps",
            "category_label": "Логи и дампы",
            "safety": "review",
            "description": "Накопленные .log файлы в песочнице проектов Antigravity.",
            "paths": scratch_logs,
        },
    ]


def scan_junk() -> Dict[str, Any]:
    """Сканирует все категории мусора и возвращает структурированный отчёт."""
    defs = get_junk_definitions()
    items: List[Dict[str, Any]] = []
    total_junk_bytes = 0
    safe_junk_bytes = 0
    total_junk_files = 0

    for d in defs:
        if d["id"] == "recycle_bin":
            rb_size, rb_count = query_recycle_bin()
            if rb_size > 0 or rb_count > 0:
                items.append({
                    "id": d["id"],
                    "name": d["name"],
                    "category": d["category"],
                    "category_label": d["category_label"],
                    "safety": d["safety"],
                    "description": d["description"],
                    "paths": ["Корзина Windows (все диски)"],
                    "size_bytes": rb_size,
                    "size_human": format_size(rb_size),
                    "file_count": rb_count,
                    "samples": [{"name": f"Объектов в Корзине: {rb_count}", "path": "RecycleBin", "size_bytes": rb_size, "size_human": format_size(rb_size)}],
                })
                total_junk_bytes += rb_size
                safe_junk_bytes += rb_size
                total_junk_files += rb_count
            continue

        existing_paths = [p for p in d["paths"] if p and os.path.exists(p)]
        if not existing_paths:
            continue

        sz, cnt, samples = scan_dir_stats(existing_paths, file_glob=d.get("file_glob"))
        if sz <= 0 and cnt <= 0:
            continue

        items.append({
            "id": d["id"],
            "name": d["name"],
            "category": d["category"],
            "category_label": d["category_label"],
            "safety": d["safety"],
            "description": d["description"],
            "paths": existing_paths,
            "size_bytes": sz,
            "size_human": format_size(sz),
            "file_count": cnt,
            "samples": samples,
        })
        total_junk_bytes += sz
        if d["safety"] == "safe":
            safe_junk_bytes += sz
        total_junk_files += cnt

    items.sort(key=lambda x: x["size_bytes"], reverse=True)
    return {
        "total_junk_bytes": total_junk_bytes,
        "total_junk_human": format_size(total_junk_bytes),
        "safe_junk_bytes": safe_junk_bytes,
        "safe_junk_human": format_size(safe_junk_bytes),
        "total_junk_files": total_junk_files,
        "categories_count": len(items),
        "items": items,
    }


# ============================================================================
# 3. Deep Disk Analyzer (Top Dirs, Large Files, Old Downloads, Duplicates)
# ============================================================================

def fast_hash_file(filepath: str, full: bool = False) -> Optional[str]:
    """
    Быстрое хэширование файла:
    - Если full=False: берёт первые 64 КБ + последние 64 КБ + размер файла (мгновенный отсев).
    - Если full=True: полный SHA-256 хэш (с лимитом до 512 МБ для скорости).
    """
    try:
        sz = os.path.getsize(filepath)
        h = hashlib.sha256()
        h.update(str(sz).encode("ascii"))
        with open(filepath, "rb") as f:
            if not full or sz <= 131072:
                head = f.read(65536)
                h.update(head)
                if sz > 65536:
                    f.seek(max(0, sz - 65536))
                    h.update(f.read(65536))
                return h.hexdigest()
            else:
                # Read full file in 1MB chunks
                while True:
                    chunk = f.read(1048576)
                    if not chunk:
                        break
                    h.update(chunk)
                return h.hexdigest()
    except Exception:
        return None


def analyze_disk(
    target_path: Optional[str] = None,
    min_large_mb: float = 20.0,
    old_days: int = 14,
    max_scan_files: int = 35000,
) -> Dict[str, Any]:
    """
    Выполняет глубокий анализ:
    1. Топ тяжёлых папок профиля (или target_path)
    2. Топ самых крупных файлов (> min_large_mb МБ)
    3. Старые или тяжёлые файлы в папке Загрузки (Downloads)
    4. Поиск 100% дубликатов файлов
    """
    user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    downloads_dir = os.path.join(user_profile, "Downloads")
    desktop_dir = os.path.join(user_profile, "Desktop")
    documents_dir = os.path.join(user_profile, "Documents")
    gemini_dir = os.path.join(user_profile, ".gemini")
    local_app = os.environ.get("LOCALAPPDATA", os.path.join(user_profile, r"AppData\Local"))
    roaming_app = os.environ.get("APPDATA", os.path.join(user_profile, r"AppData\Roaming"))

    if target_path and os.path.isdir(target_path):
        scan_roots = [os.path.abspath(target_path)]
    else:
        scan_roots = [
            d for d in [
                downloads_dir,
                desktop_dir,
                documents_dir,
                gemini_dir,
                local_app,
                roaming_app,
            ]
            if os.path.isdir(d)
        ]

    min_large_bytes = int(min_large_mb * 1024 * 1024)
    now_ts = time.time()
    old_cutoff_ts = now_ts - (old_days * 86400)

    # 1. Measure key directories breakdown
    dir_candidates: List[Tuple[str, str]] = []
    if target_path and os.path.isdir(target_path):
        try:
            with os.scandir(target_path) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        dir_candidates.append((entry.name, entry.path))
        except Exception:
            pass
    else:
        named_dirs = [
            ("Downloads (Загрузки)", downloads_dir),
            ("Desktop (Рабочий стол)", desktop_dir),
            ("Documents (Документы)", documents_dir),
            (".gemini (Antigravity & AI)", gemini_dir),
            ("Videos (Видео)", os.path.join(user_profile, "Videos")),
            ("Pictures (Изображения)", os.path.join(user_profile, "Pictures")),
        ]
        for label, dpath in named_dirs:
            if os.path.isdir(dpath):
                dir_candidates.append((label, dpath))
        # Also top subfolders inside AppData\Local
        if os.path.isdir(local_app):
            try:
                with os.scandir(local_app) as it:
                    for entry in it:
                        if entry.is_dir(follow_symlinks=False) and entry.name.lower() not in ("microsoft", "packages"):
                            dir_candidates.append((f"AppData\\Local\\{entry.name}", entry.path))
            except Exception:
                pass

    top_dirs: List[Dict[str, Any]] = []
    for label, dpath in dir_candidates:
        sz, cnt, _ = scan_dir_stats([dpath], max_files=6000)
        if sz >= 5 * 1024 * 1024:  # >= 5 MB
            top_dirs.append({
                "name": label,
                "path": dpath,
                "size_bytes": sz,
                "size_human": format_size(sz),
                "file_count": cnt,
            })
    top_dirs.sort(key=lambda x: x["size_bytes"], reverse=True)
    top_dirs = top_dirs[:15]

    # 2. Walk user folders for Large Files & Duplicate Candidates
    large_files: List[Dict[str, Any]] = []
    size_buckets: Dict[int, List[str]] = {}
    scanned_files = 0

    # For large files & duplicates, focus on user-meaningful roots first so it's fast & relevant
    walk_roots = (
        [os.path.abspath(target_path)]
        if (target_path and os.path.isdir(target_path))
        else [
            d for d in [
                downloads_dir,
                desktop_dir,
                documents_dir,
                gemini_dir,
                os.path.join(user_profile, "Videos"),
                os.path.join(user_profile, "Pictures"),
                local_app,
            ]
            if os.path.isdir(d)
        ]
    )

    skip_dir_names = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "winsxs",
        "system32",
    }

    stack = list(reversed(walk_roots))
    visited_dirs = set()

    while stack and scanned_files < max_scan_files:
        cur_dir = stack.pop()
        try:
            norm_cur = os.path.normcase(os.path.abspath(cur_dir))
            if norm_cur in visited_dirs:
                continue
            visited_dirs.add(norm_cur)
        except Exception:
            continue

        try:
            with os.scandir(cur_dir) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name.lower() in skip_dir_names:
                                continue
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            scanned_files += 1
                            st = entry.stat(follow_symlinks=False)
                            sz = st.st_size
                            if sz >= min_large_bytes:
                                mtime_dt = dt.datetime.fromtimestamp(st.st_mtime)
                                large_files.append({
                                    "name": entry.name,
                                    "path": entry.path,
                                    "ext": os.path.splitext(entry.name)[1].lower() or "file",
                                    "size_bytes": sz,
                                    "size_human": format_size(sz),
                                    "modified": mtime_dt.strftime("%Y-%m-%d %H:%M"),
                                    "age_days": max(0, int((now_ts - st.st_mtime) // 86400)),
                                })
                            # Candidate for duplicate detection (>= 512 KB and <= 500 MB, not inside AppData\Local internal caches)
                            if 524288 <= sz <= 524288000 and "\\appdata\\local\\" not in norm_cur:
                                size_buckets.setdefault(sz, []).append(entry.path)
                    except Exception:
                        continue
        except Exception:
            continue

    large_files.sort(key=lambda x: x["size_bytes"], reverse=True)
    large_files = large_files[:25]

    # 3. Old or Heavy Downloads analysis
    old_downloads: List[Dict[str, Any]] = []
    old_downloads_total_bytes = 0
    if os.path.isdir(downloads_dir):
        try:
            for root_d, _, files_d in os.walk(downloads_dir):
                for fname in files_d:
                    fpath = os.path.join(root_d, fname)
                    try:
                        st = os.stat(fpath)
                        sz = st.st_size
                        age_days = max(0, int((now_ts - st.st_mtime) // 86400))
                        # Include if older than old_days OR larger than 10 MB
                        if (st.st_mtime < old_cutoff_ts and sz >= 1024 * 1024) or sz >= 10 * 1024 * 1024:
                            old_downloads_total_bytes += sz
                            old_downloads.append({
                                "name": fname,
                                "path": fpath,
                                "ext": os.path.splitext(fname)[1].lower() or "file",
                                "size_bytes": sz,
                                "size_human": format_size(sz),
                                "age_days": age_days,
                                "modified": dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
                                "reason": f"Старше {age_days} дн." if age_days >= old_days else "Крупная загрузка",
                            })
                    except Exception:
                        continue
        except Exception:
            pass
    old_downloads.sort(key=lambda x: x["size_bytes"], reverse=True)
    old_downloads = old_downloads[:25]

    # 4. Two-stage Duplicate Detection
    duplicate_groups: List[Dict[str, Any]] = []
    total_wasted_bytes = 0
    same_size_candidates = [
        (sz, paths) for sz, paths in size_buckets.items() if len(paths) > 1
    ]
    same_size_candidates.sort(key=lambda x: x[0] * (len(x[1]) - 1), reverse=True)

    for sz, paths in same_size_candidates[:80]:
        # Stage 1: Fast partial hash
        partial_map: Dict[str, List[str]] = {}
        for p in paths:
            ph = fast_hash_file(p, full=False)
            if ph:
                partial_map.setdefault(ph, []).append(p)

        # Stage 2: Full SHA-256 hash on partial matches
        for _, p_list in partial_map.items():
            if len(p_list) < 2:
                continue
            full_map: Dict[str, List[str]] = {}
            for p in p_list:
                fh = fast_hash_file(p, full=True)
                if fh:
                    full_map.setdefault(fh, []).append(p)

            for fh, identical_paths in full_map.items():
                if len(identical_paths) < 2:
                    continue
                # Sort by creation/modification time so oldest is marked original
                try:
                    identical_paths.sort(key=lambda x: os.path.getmtime(x))
                except Exception:
                    pass
                wasted = sz * (len(identical_paths) - 1)
                total_wasted_bytes += wasted
                duplicate_groups.append({
                    "name": os.path.basename(identical_paths[0]),
                    "hash_short": fh[:12],
                    "file_size_bytes": sz,
                    "file_size_human": format_size(sz),
                    "count": len(identical_paths),
                    "wasted_bytes": wasted,
                    "wasted_human": format_size(wasted),
                    "original": identical_paths[0],
                    "duplicates": identical_paths[1:],
                    "all_paths": identical_paths,
                })

    duplicate_groups.sort(key=lambda x: x["wasted_bytes"], reverse=True)
    duplicate_groups = duplicate_groups[:20]

    return {
        "scanned_files_count": scanned_files,
        "top_dirs": top_dirs,
        "large_files": large_files,
        "old_downloads": {
            "total_bytes": old_downloads_total_bytes,
            "total_human": format_size(old_downloads_total_bytes),
            "count": len(old_downloads),
            "items": old_downloads,
        },
        "duplicates": {
            "total_wasted_bytes": total_wasted_bytes,
            "total_wasted_human": format_size(total_wasted_bytes),
            "groups_count": len(duplicate_groups),
            "groups": duplicate_groups,
        },
    }


# ============================================================================
# 4. Safe Cleaner Engine (Dry-Run + Recycle Bin + Permanent Delete)
# ============================================================================

def collect_cleanable_entries(
    target_ids: Optional[List[str]] = None,
    custom_paths: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Собирает список конкретных элементов для очистки по ID категорий мусора и/или custom_paths.
    Возвращает (список_элементов, нужно_ли_очистить_корзину).
    """
    defs_by_id = {d["id"]: d for d in get_junk_definitions()}
    target_ids = target_ids or []
    custom_paths = custom_paths or []

    clean_recycle_bin = "recycle_bin" in target_ids
    entries: List[Dict[str, Any]] = []

    for tid in target_ids:
        if tid == "recycle_bin":
            continue
        d = defs_by_id.get(tid)
        if not d:
            continue
        f_glob = d.get("file_glob")
        for root_p in d["paths"]:
            if not root_p or not os.path.exists(root_p):
                continue
            if is_protected_path(root_p):
                continue
            if os.path.isfile(root_p):
                try:
                    sz = os.path.getsize(root_p)
                    entries.append({
                        "category_id": tid,
                        "category_name": d["name"],
                        "path": root_p,
                        "is_dir": False,
                        "size_bytes": sz,
                    })
                except Exception:
                    pass
            elif os.path.isdir(root_p):
                # Collect direct children of cache/temp dir so root folder itself stays intact
                try:
                    with os.scandir(root_p) as it:
                        for child in it:
                            if f_glob and not Path(child.name).match(f_glob):
                                continue
                            if is_protected_path(child.path):
                                continue
                            if child.is_file(follow_symlinks=False):
                                sz = child.stat(follow_symlinks=False).st_size
                                entries.append({
                                    "category_id": tid,
                                    "category_name": d["name"],
                                    "path": child.path,
                                    "is_dir": False,
                                    "size_bytes": sz,
                                })
                            elif child.is_dir(follow_symlinks=False) and not f_glob:
                                sz, _, _ = scan_dir_stats([child.path], max_files=3000)
                                entries.append({
                                    "category_id": tid,
                                    "category_name": d["name"],
                                    "path": child.path,
                                    "is_dir": True,
                                    "size_bytes": sz,
                                })
                except Exception:
                    pass

    for cp in custom_paths:
        if not cp or not os.path.exists(cp):
            continue
        abs_cp = os.path.abspath(cp)
        if is_protected_path(abs_cp):
            continue
        try:
            if os.path.isfile(abs_cp):
                sz = os.path.getsize(abs_cp)
                entries.append({
                    "category_id": "custom",
                    "category_name": "Выбранный пользователем файл",
                    "path": abs_cp,
                    "is_dir": False,
                    "size_bytes": sz,
                })
            elif os.path.isdir(abs_cp):
                sz, _, _ = scan_dir_stats([abs_cp], max_files=5000)
                entries.append({
                    "category_id": "custom",
                    "category_name": "Выбранная пользователем папка",
                    "path": abs_cp,
                    "is_dir": True,
                    "size_bytes": sz,
                })
        except Exception:
            pass

    return entries, clean_recycle_bin


def clean_items(
    target_ids: Optional[List[str]] = None,
    custom_paths: Optional[List[str]] = None,
    dry_run: bool = True,
    mode: str = "recycle",
) -> Dict[str, Any]:
    """
    Выполняет безопасную очистку выбранных категорий и/или путей.
    - dry_run=True: ничего не удаляет, проверяет блокировки и считает точный объём.
    - mode="recycle": отправляет файлы/папки в Корзину Windows (рекомендуется).
    - mode="permanent": окончательное удаление без Корзины.
    """
    entries, include_recycle_bin = collect_cleanable_entries(target_ids, custom_paths)
    rb_size, rb_items = (query_recycle_bin() if include_recycle_bin else (0, 0))

    total_candidate_bytes = sum(e["size_bytes"] for e in entries) + rb_size
    if dry_run:
        # Check which files might be locked by open processes
        deletable_bytes = rb_size
        locked_bytes = 0
        deletable_count = (1 if include_recycle_bin and rb_items > 0 else 0)
        locked_count = 0
        preview_items = []

        if include_recycle_bin and (rb_size > 0 or rb_items > 0):
            preview_items.append({
                "name": f"Корзина Windows ({rb_items} объектов)",
                "path": "RecycleBin",
                "category": "Корзина Windows",
                "size_bytes": rb_size,
                "size_human": format_size(rb_size),
                "status": "ready",
            })

        for e in entries:
            p = e["path"]
            is_locked = False
            if not e["is_dir"]:
                try:
                    # Test if file is locked by another process
                    with open(p, "ab"):
                        pass
                except PermissionError:
                    is_locked = True
                except Exception:
                    pass
            if is_locked:
                locked_bytes += e["size_bytes"]
                locked_count += 1
            else:
                deletable_bytes += e["size_bytes"]
                deletable_count += 1

            if len(preview_items) < 40:
                preview_items.append({
                    "name": os.path.basename(p),
                    "path": p,
                    "category": e["category_name"],
                    "size_bytes": e["size_bytes"],
                    "size_human": format_size(e["size_bytes"]),
                    "status": "locked (будет пропущен)" if is_locked else "ready",
                })

        preview_items.sort(key=lambda x: x["size_bytes"], reverse=True)
        return {
            "dry_run": True,
            "mode": mode,
            "summary": (
                f"[DRY-RUN ПРЕВЬЮ] Готово к очистке: {format_size(deletable_bytes)} "
                f"({deletable_count} объектов). Занято активными процессами (будет безопасно пропущено): "
                f"{format_size(locked_bytes)} ({locked_count} объектов)."
            ),
            "would_free_bytes": deletable_bytes,
            "would_free_human": format_size(deletable_bytes),
            "locked_bytes": locked_bytes,
            "locked_human": format_size(locked_bytes),
            "deletable_count": deletable_count,
            "locked_count": locked_count,
            "total_candidate_bytes": total_candidate_bytes,
            "preview_items": preview_items[:30],
        }

    # Actual execution (dry_run=False)
    freed_bytes = 0
    deleted_count = 0
    skipped_count = 0
    errors: List[str] = []

    if include_recycle_bin and (rb_size > 0 or rb_items > 0):
        ok, msg = empty_recycle_bin()
        if ok:
            freed_bytes += rb_size
            deleted_count += rb_items
        else:
            errors.append(msg)

    if mode == "recycle":
        paths_to_recycle = [e["path"] for e in entries if os.path.exists(e["path"])]
        size_lookup = {os.path.abspath(e["path"]): e["size_bytes"] for e in entries}
        del_cnt, skip_cnt, err_list = send_paths_to_recycle_bin(paths_to_recycle)
        deleted_count += del_cnt
        skipped_count += skip_cnt
        errors.extend(err_list)
        for abs_p, sz in size_lookup.items():
            if not os.path.exists(abs_p):
                freed_bytes += sz
    else:
        # Permanent deletion
        for e in entries:
            p = e["path"]
            sz = e["size_bytes"]
            if not os.path.exists(p):
                continue
            try:
                if e["is_dir"]:
                    shutil.rmtree(p, ignore_errors=False)
                else:
                    try:
                        os.chmod(p, stat.S_IWRITE)
                    except Exception:
                        pass
                    os.unlink(p)
                freed_bytes += sz
                deleted_count += 1
            except Exception as exc:
                # If directory partially failed because of 1 locked file inside, delete unlocked files inside
                if e["is_dir"] and os.path.isdir(p):
                    sub_freed = 0
                    for root_sub, dirs_sub, files_sub in os.walk(p, topdown=False):
                        for fn in files_sub:
                            fp = os.path.join(root_sub, fn)
                            try:
                                fsz = os.path.getsize(fp)
                                os.unlink(fp)
                                sub_freed += fsz
                            except Exception:
                                skipped_count += 1
                        for dn in dirs_sub:
                            try:
                                os.rmdir(os.path.join(root_sub, dn))
                            except Exception:
                                pass
                    freed_bytes += sub_freed
                    if sub_freed > 0:
                        deleted_count += 1
                else:
                    skipped_count += 1
                    if len(errors) < 10:
                        errors.append(f"{os.path.basename(p)}: занят процессом")

    action_label = "отправлено в Корзину" if mode == "recycle" else "удалено навсегда"
    return {
        "dry_run": False,
        "mode": mode,
        "summary": (
            f"Очистка завершена ({action_label}): освобождено {format_size(freed_bytes)}, "
            f"обработано объектов: {deleted_count}, пропущено занятых файлов: {skipped_count}."
        ),
        "freed_bytes": freed_bytes,
        "freed_human": format_size(freed_bytes),
        "deleted_count": deleted_count,
        "skipped_count": skipped_count,
        "errors": errors[:10],
    }


# ============================================================================
# 5. Full Report & Generative UI Widget Builder
# ============================================================================

def build_full_report(target_path: Optional[str] = None) -> Dict[str, Any]:
    """Собирает единый полный отчёт о дисках, мусоре и анализе файлов."""
    t0 = time.time()
    drives = get_drives_overview()
    junk = scan_junk()
    analysis = analyze_disk(target_path=target_path)
    elapsed = round(time.time() - t0, 2)

    potential_savings = (
        junk["total_junk_bytes"]
        + analysis["duplicates"]["total_wasted_bytes"]
        + analysis["old_downloads"]["total_bytes"]
    )

    return {
        "generated_at": dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "scan_duration_sec": elapsed,
        "potential_savings_bytes": potential_savings,
        "potential_savings_human": format_size(potential_savings),
        "drives": drives,
        "junk": junk,
        "analysis": analysis,
    }


def generate_html_widget(
    report: Dict[str, Any],
    output_path: str,
    compact: bool = False,
    live_api: bool = False,
) -> str:
    """
    Генерирует интерактивный Generative UI HTML-виджет для Antigravity.
    - compact=True: компактный inline-виджет (<agent-embed>, до 480px высотой, bg-transparent).
    - compact=False: полноэкранный интерактивный дашборд с вкладками, чекбоксами,
      Dry-Run симулятором, поиском дубликатов и кнопками очистки.
    """
    data_json = json.dumps(report, ensure_ascii=False)

    if compact:
        compact_payload = {
            "drives": report.get("drives", [])[:4],
            "junk": {
                "items": [
                    {
                        "name": i["name"],
                        "category_label": i["category_label"],
                        "size_human": i["size_human"],
                        "file_count": i["file_count"],
                    }
                    for i in report.get("junk", {}).get("items", [])[:5]
                ]
            },
        }
        compact_json = json.dumps(compact_payload, ensure_ascii=False)
        # Compact inline widget (<500px height budget, transparent root background per generative_ui skill)
        html_doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-3">
  <div class="bg-[var(--card)] text-[var(--foreground)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
    <div class="flex items-center justify-between gap-3 border-b border-[var(--border)] pb-3 mb-3">
      <div class="flex items-center gap-2.5">
        <div class="w-9 h-9 rounded-lg bg-sky-500/15 border border-sky-500/30 flex items-center justify-center text-lg">🧹</div>
        <div>
          <h2 class="text-[var(--foreground)] font-semibold text-base leading-tight">Antigravity Disk Cleaner</h2>
          <p class="text-[var(--muted-foreground)] text-xs">Скан за {report['scan_duration_sec']} сек • Потенциал очистки: <span class="text-emerald-500 font-semibold">{report['potential_savings_human']}</span></p>
        </div>
      </div>
      <div class="text-right">
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
          🛡️ Dry-Run + Корзина
        </span>
      </div>
    </div>

    <!-- Drives Row -->
    <div id="drives-row" class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mb-3"></div>

    <!-- Summary KPI Pills -->
    <div class="grid grid-cols-4 gap-2 mb-3">
      <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
        <div class="text-[var(--muted-foreground)] text-xs">Системный мусор</div>
        <div class="text-sm font-bold text-amber-500 mt-0.5">{report['junk']['total_junk_human']}</div>
        <div class="text-[var(--muted-foreground)] text-xs">{report['junk']['total_junk_files']} файлов</div>
      </div>
      <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
        <div class="text-[var(--muted-foreground)] text-xs">Безопасный кэш</div>
        <div class="text-sm font-bold text-emerald-500 mt-0.5">{report['junk']['safe_junk_human']}</div>
        <div class="text-[var(--muted-foreground)] text-xs">В 1 клик</div>
      </div>
      <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
        <div class="text-[var(--muted-foreground)] text-xs">Загрузки (Downloads)</div>
        <div class="text-sm font-bold text-sky-500 mt-0.5">{report['analysis']['old_downloads']['total_human']}</div>
        <div class="text-[var(--muted-foreground)] text-xs">{report['analysis']['old_downloads']['count']} крупных/старых</div>
      </div>
      <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
        <div class="text-[var(--muted-foreground)] text-xs">Дубликаты</div>
        <div class="text-sm font-bold text-purple-500 mt-0.5">{report['analysis']['duplicates']['total_wasted_human']}</div>
        <div class="text-[var(--muted-foreground)] text-xs">{report['analysis']['duplicates']['groups_count']} групп</div>
      </div>
    </div>

    <!-- Top Junk Categories Compact List -->
    <div id="top-junk" class="space-y-1.5"></div>
  </div>

  <script>
    const DATA = {compact_json};
    const drivesEl = document.getElementById('drives-row');
    DATA.drives.forEach(d => {{
      const barColor = d.status === 'Critical' ? 'bg-rose-500' : (d.status === 'Warning' ? 'bg-amber-500' : 'bg-sky-500');
      drivesEl.innerHTML += `
        <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
          <div class="flex justify-between items-center text-xs mb-1">
            <span class="font-semibold">${{d.drive}} ${{d.label}} (${{d.filesystem}})</span>
            <span class="text-[var(--muted-foreground)]">Свободно <b class="text-[var(--foreground)]">${{d.free_human}}</b> из ${{d.total_human}}</span>
          </div>
          <div class="w-full h-2 rounded-full bg-[var(--border)] overflow-hidden">
            <div class="h-full ${{barColor}}" style="width: ${{d.used_pct}}%"></div>
          </div>
        </div>
      `;
    }});

    const junkEl = document.getElementById('top-junk');
    DATA.junk.items.slice(0, 4).forEach(item => {{
      junkEl.innerHTML += `
        <div class="flex items-center justify-between text-xs px-2.5 py-1.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
          <div class="flex items-center gap-2 truncate">
            <span class="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-500 font-medium">${{item.category_label}}</span>
            <span class="font-medium truncate">${{item.name}}</span>
          </div>
          <div class="font-semibold whitespace-nowrap ml-2">${{item.size_human}} <span class="text-[var(--muted-foreground)] font-normal">(${{item.file_count}})</span></div>
        </div>
      `;
    }});
  </script>
</body>
</html>"""
    else:
        # Full Standalone Interactive Dashboard Artifact / Web App
        html_doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Antigravity Disk Cleaner — Интерактивный Дашборд</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-[var(--background)] text-[var(--foreground)] antialiased p-5">
  <div class="max-w-6xl mx-auto space-y-5">

    <!-- Header Banner -->
    <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 shadow-sm flex flex-col md:flex-row md:items-center md:justify-between gap-4">
      <div class="flex items-start gap-3.5">
        <div class="w-12 h-12 rounded-xl bg-sky-500/15 border border-sky-500/30 flex items-center justify-center text-2xl shrink-0">🧹</div>
        <div>
          <div class="flex items-center gap-2 flex-wrap">
            <h1 class="text-xl font-bold text-[var(--foreground)]">Antigravity Disk Cleaner</h1>
            <span class="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
              🛡️ Dry-Run + Корзина Windows
            </span>
          </div>
          <p class="text-xs text-[var(--muted-foreground)] mt-1">
            Сформирован: {report['generated_at']} • Время анализа: {report['scan_duration_sec']} сек • Проверено файлов: {report['analysis']['scanned_files_count']}
          </p>
        </div>
      </div>

      <!-- Dynamic Selection Summary & Action Box -->
      <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-3.5 flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <div>
          <div class="text-xs text-[var(--muted-foreground)]">Выбрано к безопасной очистке:</div>
          <div id="selected-total-size" class="text-lg font-bold text-emerald-500">0 Б</div>
          <div id="selected-total-count" class="text-xs text-[var(--muted-foreground)]">0 категорий / файлов</div>
        </div>
        <div class="flex flex-wrap gap-2">
          <button onclick="runAction('dry_run')" class="px-3 py-2 rounded-lg text-xs font-semibold bg-sky-500/15 text-sky-400 border border-sky-500/30 hover:bg-sky-500/25 transition">
            🔍 Симуляция (Dry-Run)
          </button>
          <button onclick="runAction('recycle')" class="px-3 py-2 rounded-lg text-xs font-semibold bg-emerald-500 text-white hover:bg-emerald-600 transition shadow-sm">
            🗑️ В Корзину
          </button>
          <button onclick="runAction('permanent')" class="px-3 py-2 rounded-lg text-xs font-semibold bg-rose-500/15 text-rose-400 border border-rose-500/30 hover:bg-rose-500/25 transition">
            ⚡ Удалить навсегда
          </button>
        </div>
      </div>
    </div>

    <!-- Status / Dry-Run Output Drawer -->
    <div id="action-drawer" class="hidden bg-[var(--card)] border border-sky-500/40 rounded-xl p-4 shadow-sm space-y-3">
      <div class="flex items-center justify-between">
        <div id="drawer-title" class="text-sm font-semibold text-sky-400">Результат проверки</div>
        <button onclick="document.getElementById('action-drawer').classList.add('hidden')" class="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">✕ Закрыть</button>
      </div>
      <div id="drawer-body" class="text-xs space-y-2"></div>
    </div>

    <!-- Drives Cards -->
    <div id="drives-grid" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>

    <!-- Navigation Tabs -->
    <div class="flex flex-wrap gap-2 border-b border-[var(--border)] pb-2">
      <button onclick="switchTab('junk')" id="tab-btn-junk" class="px-3.5 py-2 rounded-lg text-xs font-semibold bg-sky-500 text-white transition">
        🧹 Системный мусор и кэши ({report['junk']['total_junk_human']})
      </button>
      <button onclick="switchTab('dirs')" id="tab-btn-dirs" class="px-3.5 py-2 rounded-lg text-xs font-semibold bg-[var(--card)] text-[var(--muted-foreground)] border border-[var(--border)] transition">
        📂 Тяжёлые папки и Гиганты
      </button>
      <button onclick="switchTab('downloads')" id="tab-btn-downloads" class="px-3.5 py-2 rounded-lg text-xs font-semibold bg-[var(--card)] text-[var(--muted-foreground)] border border-[var(--border)] transition">
        📥 Загрузки Downloads ({report['analysis']['old_downloads']['total_human']})
      </button>
      <button onclick="switchTab('duplicates')" id="tab-btn-duplicates" class="px-3.5 py-2 rounded-lg text-xs font-semibold bg-[var(--card)] text-[var(--muted-foreground)] border border-[var(--border)] transition">
        👯 Дубликаты ({report['analysis']['duplicates']['total_wasted_human']})
      </button>
    </div>

    <!-- TAB 1: Junk Categories -->
    <div id="tab-junk" class="space-y-3">
      <div class="flex items-center justify-between flex-wrap gap-2">
        <p class="text-xs text-[var(--muted-foreground)]">
          Отметьте галочками категории мусора для очистки. Все пункты с меткой <b>Безопасно</b> содержат только временный кэш (пароли, история и личные документы не затрагиваются).
        </p>
        <div class="flex gap-2">
          <button onclick="selectJunk('safe')" class="px-2.5 py-1 rounded text-xs bg-[var(--card)] border border-[var(--border)] hover:border-emerald-500/50">Выбрать все безопасные</button>
          <button onclick="selectJunk('none')" class="px-2.5 py-1 rounded text-xs bg-[var(--card)] border border-[var(--border)]">Снять выбор</button>
        </div>
      </div>
      <div id="junk-list" class="space-y-2.5"></div>
    </div>

    <!-- TAB 2: Top Dirs & Large Files -->
    <div id="tab-dirs" class="hidden grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 space-y-3">
        <h3 class="text-sm font-semibold">📂 Топ самых тяжёлых папок</h3>
        <div id="top-dirs-list" class="space-y-2"></div>
      </div>
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 space-y-3">
        <h3 class="text-sm font-semibold">🐘 Самые крупные файлы (&gt; 20 МБ)</h3>
        <div id="large-files-list" class="space-y-2"></div>
      </div>
    </div>

    <!-- TAB 3: Old / Heavy Downloads -->
    <div id="tab-downloads" class="hidden bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-sm font-semibold">📥 Старые и крупные файлы в папке «Загрузки» (Downloads)</h3>
          <p class="text-xs text-[var(--muted-foreground)]">Отметьте ненужные установщики (.exe, .msi, .iso, .zip), чтобы включить их в очистку в Корзину.</p>
        </div>
      </div>
      <div id="downloads-list" class="space-y-2"></div>
    </div>

    <!-- TAB 4: Duplicates -->
    <div id="tab-duplicates" class="hidden bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 class="text-sm font-semibold">👯 Полные дубликаты файлов (проверено по SHA-256)</h3>
          <p class="text-xs text-[var(--muted-foreground)]">Оригинал остаётся нетронутым, а лишние копии можно отметить галочкой для отправки в Корзину.</p>
        </div>
        <button onclick="selectAllDuplicates()" class="px-2.5 py-1 rounded text-xs bg-purple-500/15 text-purple-400 border border-purple-500/30">Отметить все лишние копии</button>
      </div>
      <div id="duplicates-list" class="space-y-3"></div>
    </div>

  </div>

  <script>
    const DATA = {data_json};
    const LIVE_API = {'true' if live_api else 'false'};

    const selectedJunkIds = new Set(DATA.junk.items.filter(i => i.safety === 'safe').map(i => i.id));
    const selectedCustomPaths = new Map(); // path -> size_bytes

    function formatBytes(bytes) {{
      let val = Math.max(0, Number(bytes) || 0);
      const units = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
      let idx = 0;
      while (val >= 1024 && idx < units.length - 1) {{
        val /= 1024;
        idx++;
      }}
      return idx === 0 ? `${{Math.round(val)}} ${{units[idx]}}` : `${{val.toFixed(1)}} ${{units[idx]}}`;
    }}

    function esc(str) {{
      const d = document.createElement('div');
      d.textContent = str ?? '';
      return d.innerHTML;
    }}

    function renderDrives() {{
      const grid = document.getElementById('drives-grid');
      grid.innerHTML = '';
      DATA.drives.forEach(d => {{
        const color = d.status === 'Critical' ? 'bg-rose-500' : (d.status === 'Warning' ? 'bg-amber-500' : 'bg-sky-500');
        const badge = d.status === 'Critical'
          ? '<span class="px-2 py-0.5 rounded text-xs bg-rose-500/15 text-rose-500 font-semibold">Критично</span>'
          : (d.status === 'Warning'
            ? '<span class="px-2 py-0.5 rounded text-xs bg-amber-500/15 text-amber-500 font-semibold">Внимание</span>'
            : '<span class="px-2 py-0.5 rounded text-xs bg-emerald-500/15 text-emerald-500 font-semibold">Норма</span>');

        grid.innerHTML += `
          <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm space-y-2.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-base font-bold">💾 ${{esc(d.drive)}} ${{esc(d.label)}}</span>
                <span class="text-xs text-[var(--muted-foreground)]">(${{esc(d.filesystem)}})</span>
              </div>
              ${{badge}}
            </div>
            <div class="w-full h-3 rounded-full bg-[var(--background)] border border-[var(--border)] overflow-hidden">
              <div class="h-full ${{color}} transition-all" style="width: ${{d.used_pct}}%"></div>
            </div>
            <div class="flex justify-between text-xs text-[var(--muted-foreground)]">
              <span>Занято: <b class="text-[var(--foreground)]">${{esc(d.used_human)}}</b> (${{d.used_pct}}%)</span>
              <span>Свободно: <b class="text-emerald-500">${{esc(d.free_human)}}</b> из ${{esc(d.total_human)}}</span>
            </div>
          </div>
        `;
      }});
    }}

    function renderJunk() {{
      const list = document.getElementById('junk-list');
      list.innerHTML = '';
      DATA.junk.items.forEach(item => {{
        const checked = selectedJunkIds.has(item.id) ? 'checked' : '';
        const safetyBadge = item.safety === 'safe'
          ? '<span class="px-2 py-0.5 rounded text-xs bg-emerald-500/15 text-emerald-500 font-medium">Безопасно</span>'
          : '<span class="px-2 py-0.5 rounded text-xs bg-amber-500/15 text-amber-500 font-medium">Проверить</span>';

        const samplesHtml = (item.samples || []).map(s =>
          `<span class="inline-block px-2 py-0.5 rounded bg-[var(--background)] border border-[var(--border)] text-xs text-[var(--muted-foreground)]">${{esc(s.name)}} (${{esc(s.size_human)}})</span>`
        ).join(' ');

        list.innerHTML += `
          <label class="block bg-[var(--card)] border border-[var(--border)] hover:border-sky-500/40 rounded-xl p-3.5 cursor-pointer transition">
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-start gap-3">
                <input type="checkbox" class="mt-1 w-4 h-4 accent-emerald-500" ${{checked}} onchange="toggleJunk('${{item.id}}', this.checked)">
                <div class="space-y-1">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-sm font-semibold">${{esc(item.name)}}</span>
                    <span class="px-2 py-0.5 rounded text-xs bg-sky-500/15 text-sky-400">${{esc(item.category_label)}}</span>
                    ${{safetyBadge}}
                  </div>
                  <p class="text-xs text-[var(--muted-foreground)]">${{esc(item.description)}}</p>
                  <div class="text-xs text-[var(--muted-foreground)] font-mono truncate max-w-2xl">${{esc((item.paths || []).join(' • '))}}</div>
                  ${{samplesHtml ? `<div class="flex flex-wrap gap-1.5 pt-1">${{samplesHtml}}</div>` : ''}}
                </div>
              </div>
              <div class="text-right shrink-0">
                <div class="text-sm font-bold text-[var(--foreground)]">${{esc(item.size_human)}}</div>
                <div class="text-xs text-[var(--muted-foreground)]">${{item.file_count}} объектов</div>
              </div>
            </div>
          </label>
        `;
      }});
    }}

    function renderDirsAndLarge() {{
      const dirsList = document.getElementById('top-dirs-list');
      const maxDir = Math.max(1, ...(DATA.analysis.top_dirs || []).map(d => d.size_bytes));
      dirsList.innerHTML = (DATA.analysis.top_dirs || []).map(d => {{
        const pct = Math.max(4, Math.round((d.size_bytes / maxDir) * 100));
        return `
          <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)] space-y-1">
            <div class="flex justify-between text-xs">
              <span class="font-semibold truncate">${{esc(d.name)}}</span>
              <span class="font-bold whitespace-nowrap ml-2">${{esc(d.size_human)}}</span>
            </div>
            <div class="w-full h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
              <div class="h-full bg-indigo-500" style="width: ${{pct}}%"></div>
            </div>
            <div class="text-xs text-[var(--muted-foreground)] font-mono truncate">${{esc(d.path)}}</div>
          </div>
        `;
      }}).join('') || '<p class="text-xs text-[var(--muted-foreground)]">Нет данных</p>';

      const filesList = document.getElementById('large-files-list');
      filesList.innerHTML = (DATA.analysis.large_files || []).map((f, idx) => {{
        const checked = selectedCustomPaths.has(f.path) ? 'checked' : '';
        return `
          <label class="flex items-center justify-between gap-2 p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)] cursor-pointer hover:border-sky-500/40">
            <div class="flex items-center gap-2.5 min-w-0">
              <input type="checkbox" class="w-4 h-4 accent-emerald-500 shrink-0" ${{checked}} data-path="${{esc(f.path)}}" data-size="${{f.size_bytes}}" onchange="toggleCustomPath(this)">
              <div class="min-w-0">
                <div class="text-xs font-semibold truncate">${{esc(f.name)}}</div>
                <div class="text-xs text-[var(--muted-foreground)] font-mono truncate">${{esc(f.path)}}</div>
              </div>
            </div>
            <div class="text-right shrink-0">
              <div class="text-xs font-bold text-amber-500">${{esc(f.size_human)}}</div>
              <div class="text-xs text-[var(--muted-foreground)]">${{f.age_days}} дн. назад</div>
            </div>
          </label>
        `;
      }}).join('') || '<p class="text-xs text-[var(--muted-foreground)]">Крупных файлов не найдено</p>';
    }}

    function renderDownloads() {{
      const dlList = document.getElementById('downloads-list');
      const items = DATA.analysis.old_downloads?.items || [];
      dlList.innerHTML = items.map(f => {{
        const checked = selectedCustomPaths.has(f.path) ? 'checked' : '';
        return `
          <label class="flex items-center justify-between gap-3 p-3 rounded-lg bg-[var(--background)] border border-[var(--border)] cursor-pointer hover:border-sky-500/40">
            <div class="flex items-center gap-3 min-w-0">
              <input type="checkbox" class="w-4 h-4 accent-emerald-500 shrink-0" ${{checked}} data-path="${{esc(f.path)}}" data-size="${{f.size_bytes}}" onchange="toggleCustomPath(this)">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-semibold truncate">${{esc(f.name)}}</span>
                  <span class="px-2 py-0.5 rounded text-xs bg-sky-500/15 text-sky-400">${{esc(f.reason)}}</span>
                </div>
                <div class="text-xs text-[var(--muted-foreground)] font-mono truncate">${{esc(f.path)}}</div>
              </div>
            </div>
            <div class="text-right shrink-0">
              <div class="text-xs font-bold">${{esc(f.size_human)}}</div>
              <div class="text-xs text-[var(--muted-foreground)]">${{esc(f.modified)}}</div>
            </div>
          </label>
        `;
      }}).join('') || '<p class="text-xs text-[var(--muted-foreground)]">Старых или тяжёлых загрузок не обнаружено</p>';
    }}

    function renderDuplicates() {{
      const dupList = document.getElementById('duplicates-list');
      const groups = DATA.analysis.duplicates?.groups || [];
      dupList.innerHTML = groups.map(g => {{
        const copiesHtml = g.duplicates.map(dp => {{
          const checked = selectedCustomPaths.has(dp) ? 'checked' : '';
          return `
            <label class="flex items-center justify-between gap-2 p-2 rounded bg-[var(--card)] border border-[var(--border)] cursor-pointer">
              <div class="flex items-center gap-2 min-w-0">
                <input type="checkbox" class="w-4 h-4 accent-purple-500 shrink-0 dup-checkbox" ${{checked}} data-path="${{esc(dp)}}" data-size="${{g.file_size_bytes}}" onchange="toggleCustomPath(this)">
                <span class="px-1.5 py-0.5 rounded text-xs bg-purple-500/15 text-purple-400">Копия</span>
                <span class="text-xs font-mono truncate">${{esc(dp)}}</span>
              </div>
              <span class="text-xs font-semibold shrink-0">${{esc(g.file_size_human)}}</span>
            </label>
          `;
        }}).join('');

        return `
          <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-2">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-xs font-bold">${{esc(g.name)}}</span>
                <span class="text-xs text-[var(--muted-foreground)]">SHA-256: ${{esc(g.hash_short)}}… (${{g.count}} экз.)</span>
              </div>
              <span class="text-xs font-bold text-purple-400">Лишний вес: ${{esc(g.wasted_human)}}</span>
            </div>
            <div class="p-2 rounded bg-emerald-500/10 border border-emerald-500/20 text-xs flex items-center gap-2">
              <span class="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-medium">Оригинал (сохраняется)</span>
              <span class="font-mono truncate">${{esc(g.original)}}</span>
            </div>
            <div class="space-y-1.5">${{copiesHtml}}</div>
          </div>
        `;
      }}).join('') || '<p class="text-xs text-[var(--muted-foreground)]">Полных дубликатов не найдено</p>';
    }}

    function updateTotals() {{
      let bytes = 0;
      let count = 0;
      DATA.junk.items.forEach(item => {{
        if (selectedJunkIds.has(item.id)) {{
          bytes += item.size_bytes;
          count++;
        }}
      }});
      for (const sz of selectedCustomPaths.values()) {{
        bytes += sz;
        count++;
      }}
      document.getElementById('selected-total-size').textContent = formatBytes(bytes);
      document.getElementById('selected-total-count').textContent = `${{selectedJunkIds.size}} категорий + ${{selectedCustomPaths.size}} отдельных файлов`;
    }}

    function toggleJunk(id, isChecked) {{
      if (isChecked) selectedJunkIds.add(id);
      else selectedJunkIds.delete(id);
      updateTotals();
    }}

    function selectJunk(mode) {{
      selectedJunkIds.clear();
      if (mode === 'safe') {{
        DATA.junk.items.filter(i => i.safety === 'safe').forEach(i => selectedJunkIds.add(i.id));
      }}
      renderJunk();
      updateTotals();
    }}

    function toggleCustomPath(el) {{
      const p = el.getAttribute('data-path');
      const sz = Number(el.getAttribute('data-size') || 0);
      if (el.checked) selectedCustomPaths.set(p, sz);
      else selectedCustomPaths.delete(p);
      updateTotals();
    }}

    function selectAllDuplicates() {{
      (DATA.analysis.duplicates?.groups || []).forEach(g => {{
        g.duplicates.forEach(dp => selectedCustomPaths.set(dp, g.file_size_bytes));
      }});
      renderDuplicates();
      updateTotals();
    }}

    function switchTab(tab) {{
      ['junk', 'dirs', 'downloads', 'duplicates'].forEach(t => {{
        const el = document.getElementById('tab-' + t);
        const btn = document.getElementById('tab-btn-' + t);
        if (t === tab) {{
          el.classList.remove('hidden');
          btn.className = 'px-3.5 py-2 rounded-lg text-xs font-semibold bg-sky-500 text-white transition';
        }} else {{
          el.classList.add('hidden');
          btn.className = 'px-3.5 py-2 rounded-lg text-xs font-semibold bg-[var(--card)] text-[var(--muted-foreground)] border border-[var(--border)] transition';
        }}
      }});
    }}

    async function runAction(actionType) {{
      const drawer = document.getElementById('action-drawer');
      const title = document.getElementById('drawer-title');
      const body = document.getElementById('drawer-body');
      drawer.classList.remove('hidden');

      const ids = Array.from(selectedJunkIds);
      const paths = Array.from(selectedCustomPaths.keys());

      if (ids.length === 0 && paths.length === 0) {{
        title.textContent = 'Ничего не выбрано';
        body.innerHTML = '<p>Отметьте хотя бы одну категорию мусора или файл галочкой.</p>';
        return;
      }}

      if (LIVE_API) {{
        title.textContent = '⏳ Выполняется операция...';
        body.innerHTML = '<p>Пожалуйста, подождите...</p>';
        try {{
          const resp = await fetch('/api/clean', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{
              target_ids: ids,
              custom_paths: paths,
              dry_run: actionType === 'dry_run',
              mode: actionType === 'permanent' ? 'permanent' : 'recycle'
            }})
          }});
          const res = await resp.json();
          title.textContent = actionType === 'dry_run' ? '🔍 Результат Dry-Run превью' : '✅ Очистка выполнена';
          body.innerHTML = `<div class="font-semibold">${{esc(res.summary)}}</div>`;
        }} catch (e) {{
          title.textContent = 'Ошибка соединения';
          body.innerHTML = `<p>${{esc(String(e))}}</p>`;
        }}
        return;
      }}

      // Static artifact mode: show simulated Dry-Run breakdown + one-click command/prompt for Antigravity
      let totalBytes = 0;
      const chosenNames = [];
      DATA.junk.items.forEach(i => {{
        if (selectedJunkIds.has(i.id)) {{
          totalBytes += i.size_bytes;
          chosenNames.push(`${{i.name}} (${{i.size_human}})`);
        }}
      }});
      for (const [p, sz] of selectedCustomPaths.entries()) {{
        totalBytes += sz;
        chosenNames.push(`${{p.split(/[\\\\/]/).pop()}} (${{formatBytes(sz)}})`);
      }}

      const modeFlag = actionType === 'dry_run'
        ? '--dry-run'
        : (actionType === 'permanent' ? '--execute --mode permanent' : '--execute --mode recycle');

      const idsArg = ids.length ? `--clean-ids ${{ids.join(',')}}` : '';
      const chatPrompt = actionType === 'dry_run'
        ? `Запусти Dry-Run проверку очистки для категорий: ${{ids.join(', ')}}`
        : `Очисти выбранные категории (${{ids.join(', ')}}) в режиме ${{actionType === 'permanent' ? 'полного удаления' : 'отправки в Корзину'}}`;

      title.textContent = actionType === 'dry_run'
        ? `🔍 Симуляция Dry-Run: будет освобождено ~${{formatBytes(totalBytes)}}`
        : `🛡️ Готово к выполнению (${{actionType === 'permanent' ? 'Полное удаление' : 'В Корзину Windows'}}) — ~${{formatBytes(totalBytes)}}`;

      body.innerHTML = `
        <p class="text-[var(--muted-foreground)]">Выбранные элементы (${{chosenNames.length}}): <b>${{esc(chosenNames.slice(0, 8).join(', '))}}${{chosenNames.length > 8 ? '…' : ''}}</b></p>
        <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)] flex items-center justify-between gap-2">
          <code class="text-xs text-emerald-400 break-all">Напишите в чат Antigravity: «${{esc(chatPrompt)}}»</code>
          <button onclick="navigator.clipboard.writeText('${{esc(chatPrompt)}}'); this.textContent='Скопировано!'" class="px-2.5 py-1 rounded bg-sky-500 text-white text-xs font-semibold shrink-0">Скопировать для чата</button>
        </div>
      `;
    }}

    renderDrives();
    renderJunk();
    renderDirsAndLarge();
    renderDownloads();
    renderDuplicates();
    updateTotals();
  </script>
</body>
</html>"""

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return os.path.abspath(output_path)


# ============================================================================
# 6. Local Interactive Web Server (--serve)
# ============================================================================

def run_web_server(port: int = 8765) -> None:
    """Запускает локальный интерактивный веб-сервер Disk Cleaner с живым API очистки."""
    report_cache = build_full_report()
    tmp_html = os.path.join(os.environ.get("TEMP", "."), "agy_disk_cleaner_live.html")

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            nonlocal report_cache
            if self.path.startswith("/api/rescan"):
                report_cache = build_full_report()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(report_cache, ensure_ascii=False).encode("utf-8"))
                return

            generate_html_widget(report_cache, tmp_html, compact=False, live_api=True)
            with open(tmp_html, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self) -> None:
            if self.path == "/api/clean":
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                payload = json.loads(raw)
                res = clean_items(
                    target_ids=payload.get("target_ids", []),
                    custom_paths=payload.get("custom_paths", []),
                    dry_run=bool(payload.get("dry_run", True)),
                    mode=payload.get("mode", "recycle"),
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return
            self.send_response(404)
            self.end_headers()

    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"Antigravity Disk Cleaner Web UI запущен: http://127.0.0.1:{port}", flush=True)
        httpd.serve_forever()


# ============================================================================
# CLI Interface
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Antigravity Disk Cleaner CLI & Engine")
    parser.add_argument("--scan", action="store_true", help="Полное сканирование дисков, мусора и дубликатов (JSON)")
    parser.add_argument("--junk-only", action="store_true", help="Быстрое сканирование только категорий мусора")
    parser.add_argument("--target-path", type=str, default=None, help="Путь для глубокого анализа")
    parser.add_argument("--clean-ids", type=str, default="", help="Список ID категорий через запятую (например user_temp,chrome_cache,recycle_bin)")
    parser.add_argument("--clean-paths", type=str, nargs="*", default=[], help="Конкретные пути к файлам/папкам для очистки")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Симуляция без удаления (по умолчанию)")
    parser.add_argument("--execute", action="store_true", help="Выполнить реальную очистку (отключает dry-run)")
    parser.add_argument("--mode", choices=["recycle", "permanent"], default="recycle", help="Режим очистки: recycle (в Корзину) или permanent (навсегда)")
    parser.add_argument("--html-out", type=str, default="", help="Сохранить полный интерактивный HTML-дашборд по указанному пути")
    parser.add_argument("--compact-out", type=str, default="", help="Сохранить компактный inline HTML-виджет по указанному пути")
    parser.add_argument("--json-out", type=str, default="", help="Сохранить JSON-отчёт напрямую в UTF-8 файл")
    parser.add_argument("--serve", action="store_true", help="Запустить локальный интерактивный веб-сервер")
    parser.add_argument("--port", type=int, default=8765, help="Порт для --serve (по умолчанию 8765)")

    args = parser.parse_args()

    if args.serve:
        run_web_server(port=args.port)
        return

    if args.clean_ids or args.clean_paths:
        ids = [x.strip() for x in args.clean_ids.split(",") if x.strip()]
        is_dry = not args.execute
        res = clean_items(
            target_ids=ids,
            custom_paths=args.clean_paths,
            dry_run=is_dry,
            mode=args.mode,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if args.junk_only:
        res = {
            "drives": get_drives_overview(),
            "junk": scan_junk(),
        }
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    report = build_full_report(target_path=args.target_path)
    if args.html_out:
        generate_html_widget(report, args.html_out, compact=False)
    if args.compact_out:
        generate_html_widget(report, args.compact_out, compact=True)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as jf:
            json.dump(report, jf, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
