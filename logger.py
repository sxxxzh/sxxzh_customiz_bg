#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志模块：将不同子模块的日志写入同一日志文件，并可选同时输出到控制台。
- 日志文件：logs/sxxzh_bg_system.log（打包模式在可执行同目录的 logs，开发模式在源目录的 logs）
- 简易大小轮转：超过 5MB 自动备份为 sxxzh_bg_system.log.1 并重建新文件
"""

import os
import sys
import time
from typing import Optional

_MAX_BYTES = 5 * 1024 * 1024  # 5MB
_BACKUP_NAME = "sxxzh_bg_system.log.1"
_LOG_NAME = "sxxzh_bg_system.log"


def _get_log_dir() -> str:
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def _get_log_file() -> str:
    return os.path.join(_get_log_dir(), _LOG_NAME)


def _rotate_if_needed(log_file: str) -> None:
    try:
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            if size >= _MAX_BYTES:
                backup = os.path.join(os.path.dirname(log_file), _BACKUP_NAME)
                # 删除旧备份（如果有）
                try:
                    if os.path.exists(backup):
                        os.remove(backup)
                except Exception:
                    pass
                # 备份现有日志文件
                try:
                    os.replace(log_file, backup)
                except Exception:
                    # 如果替换失败，忽略轮转避免影响写入
                    pass
    except Exception:
        # 轮转失败不影响正常写入
        pass


def log(msg: str, module: str = "main", to_console: bool = True) -> str:
    """写日志到统一文件，并可选输出到控制台。
    返回最终写入的文本，便于上层复用。
    """
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{module}] {timestamp} - {msg}"

    # 控制台输出（开发时便于观察）
    if to_console:
        try:
            print(line)
        except Exception:
            pass

    # 写入文件
    try:
        log_file = _get_log_file()
        _rotate_if_needed(log_file)
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except Exception:
        # 失败时尝试备用位置
        try:
            backup_log = os.path.join(os.path.expanduser("~"), "sxxzh_bg_system_backup.log")
            with open(backup_log, 'a', encoding='utf-8') as f:
                f.write(f"[主日志失败] {line}\n")
        except Exception:
            pass

    return line