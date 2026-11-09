#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Disk Cleaner — Stdio MCP Server (JSON-RPC 2.0)
Предоставляет нативные MCP-инструменты агенту Antigravity без внешних зависимостей:
- disk_overview_and_junk
- analyze_disk_space
- clean_disk_junk
- generate_disk_dashboard
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional

# Ensure current script directory is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import disk_cleaner_core as core


SERVER_INFO = {
    "name": "disk-cleaner-mcp",
    "version": "1.0.0",
}

TOOLS = [
    {
        "name": "disk_overview_and_junk",
        "description": (
            "Быстро проверяет все локальные диски Windows (занятое/свободное место, здоровье) "
            "и сканирует все категории системного мусора, кэшей браузеров, кэшей пакетов и Корзину."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "analyze_disk_space",
        "description": (
            "Глубокий анализ диска: находит топ самых тяжёлых папок, самые крупные файлы (> min_large_mb МБ), "
            "старые/крупные файлы в папке Загрузки (Downloads) и 100% дубликаты файлов по SHA-256."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_path": {
                    "type": "string",
                    "description": "Необязательный путь к папке для анализа (по умолчанию анализируется профиль пользователя).",
                },
                "min_large_mb": {
                    "type": "number",
                    "description": "Минимальный размер крупного файла в МБ (по умолчанию 20).",
                    "default": 20,
                },
                "old_days": {
                    "type": "integer",
                    "description": "Порог возраста файлов в Загрузках в днях (по умолчанию 14).",
                    "default": 14,
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "clean_disk_junk",
        "description": (
            "Безопасная очистка выбранных категорий мусора (target_ids) и/или конкретных файлов/дубликатов (custom_paths). "
            "По умолчанию работает в режиме симуляции (dry_run=true). Для реальной очистки передайте dry_run=false. "
            "По умолчанию отправляет файлы в Корзину Windows (mode='recycle'), либо удаляет навсегда (mode='permanent')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Список ID категорий мусора: recycle_bin, user_temp, win_temp, crash_dumps, wer_reports, "
                        "thumb_cache, win_update_cache, chrome_cache, edge_cache, yandex_cache, brave_cache, "
                        "firefox_cache, dev_pkg_cache, scratch_logs."
                    ),
                },
                "custom_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Список конкретных путей к файлам или папкам (например, лишние копии дубликатов или старые загрузки).",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Если true (по умолчанию) — только рассчитывает сколько места освободится, ничего не удаляя.",
                    "default": True,
                },
                "mode": {
                    "type": "string",
                    "enum": ["recycle", "permanent"],
                    "description": "Режим удаления: 'recycle' (отправить в Корзину Windows) или 'permanent' (удалить навсегда).",
                    "default": "recycle",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "generate_disk_dashboard",
        "description": (
            "Выполняет полный анализ дисков, мусора, загрузок и дубликатов и генерирует интерактивный HTML-дашборд "
            "(Generative UI) и компактный виджет по указанным путям."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dashboard_output_path": {
                    "type": "string",
                    "description": "Абсолютный путь для сохранения полного интерактивного HTML-дашборда (в папке артефактов).",
                },
                "compact_output_path": {
                    "type": "string",
                    "description": "Необязательный путь для сохранения компактного inline-виджета (<agent-embed>).",
                },
                "target_path": {
                    "type": "string",
                    "description": "Необязательный путь для глубокого анализа конкретной директории.",
                },
            },
            "required": ["dashboard_output_path"],
            "additionalProperties": False,
        },
    },
]


def handle_call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if name == "disk_overview_and_junk":
            res = {
                "drives": core.get_drives_overview(),
                "junk": core.scan_junk(),
            }
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(res, ensure_ascii=False, indent=2),
                    }
                ],
                "isError": False,
            }

        elif name == "analyze_disk_space":
            res = core.analyze_disk(
                target_path=arguments.get("target_path"),
                min_large_mb=float(arguments.get("min_large_mb", 20.0)),
                old_days=int(arguments.get("old_days", 14)),
            )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(res, ensure_ascii=False, indent=2),
                    }
                ],
                "isError": False,
            }

        elif name == "clean_disk_junk":
            res = core.clean_items(
                target_ids=arguments.get("target_ids", []),
                custom_paths=arguments.get("custom_paths", []),
                dry_run=bool(arguments.get("dry_run", True)),
                mode=str(arguments.get("mode", "recycle")),
            )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(res, ensure_ascii=False, indent=2),
                    }
                ],
                "isError": False,
            }

        elif name == "generate_disk_dashboard":
            report = core.build_full_report(target_path=arguments.get("target_path"))
            dash_path = arguments["dashboard_output_path"]
            saved_dash = core.generate_html_widget(report, dash_path, compact=False)
            saved_compact = None
            if arguments.get("compact_output_path"):
                saved_compact = core.generate_html_widget(
                    report, arguments["compact_output_path"], compact=True
                )
            summary = {
                "status": "ok",
                "dashboard_output_path": saved_dash,
                "compact_output_path": saved_compact,
                "potential_savings_human": report["potential_savings_human"],
                "total_junk_human": report["junk"]["total_junk_human"],
                "safe_junk_human": report["junk"]["safe_junk_human"],
                "old_downloads_human": report["analysis"]["old_downloads"]["total_human"],
                "duplicates_wasted_human": report["analysis"]["duplicates"]["total_wasted_human"],
                "drives": report["drives"],
                "top_junk_categories": [
                    {
                        "id": i["id"],
                        "name": i["name"],
                        "size_human": i["size_human"],
                        "file_count": i["file_count"],
                        "safety": i["safety"],
                    }
                    for i in report["junk"]["items"][:8]
                ],
            }
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(summary, ensure_ascii=False, indent=2),
                    }
                ],
                "isError": False,
            }

        else:
            return {
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                "isError": True,
            }
    except Exception as exc:
        return {
            "content": [{"type": "text", "text": f"Error executing {name}: {exc}"}],
            "isError": True,
        }


def process_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = msg.get("method")
    msg_id = msg.get("id")

    # Notifications have no id
    if msg_id is None:
        return None

    if method == "initialize":
        params = msg.get("params") or {}
        client_proto = params.get("protocolVersion", "2024-11-05")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": client_proto,
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": SERVER_INFO,
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        params = msg.get("params") or {}
        t_name = params.get("name", "")
        t_args = params.get("arguments") or {}
        result = handle_call_tool(t_name, t_args)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }

    if method in ("resources/list", "prompts/list"):
        key = "resources" if method == "resources/list" else "prompts"
        return {"jsonrpc": "2.0", "id": msg_id, "result": {key: []}}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    if sys.platform == "win32":
        try:
            sys.stdin.reconfigure(encoding="utf-8")
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue

        # Support both Content-Length framed and line-delimited JSON-RPC
        if stripped.lower().startswith("content-length:"):
            length = int(stripped.split(":", 1)[1].strip())
            # Read until empty line
            while True:
                hdr = sys.stdin.readline()
                if not hdr or hdr.strip() == "":
                    break
            body = sys.stdin.read(length)
            try:
                msg = json.loads(body)
            except Exception:
                continue
            resp = process_message(msg)
            if resp is not None:
                out_bytes = json.dumps(resp, ensure_ascii=False).encode("utf-8")
                sys.stdout.write(f"Content-Length: {len(out_bytes)}\r\n\r\n")
                sys.stdout.write(out_bytes.decode("utf-8"))
                sys.stdout.flush()
        else:
            try:
                msg = json.loads(stripped)
            except Exception:
                continue
            resp = process_message(msg)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    main()
