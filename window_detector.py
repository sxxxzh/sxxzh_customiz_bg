#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二层：窗口检测器 (sxxzh定制版)
实时监控目标窗口出现/消失
控制第三层进程的创建和删除

开发者: sxxzh
版本: 1.0.1 修复结构与扫描逻辑
"""

import os
import sys
import win32gui
import win32process
import win32api
import win32con
import time
import subprocess
import json
import threading
from collections import defaultdict
from window_size_cache import get_size_cache
import ctypes
from ctypes import wintypes
import logger

# 统一日志
def log(msg):
    try:
        return logger.log(msg, module="detector")
    except Exception:
        return msg

# WinEvent 常量
EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_DESTROY = 0x8001
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_HIDE = 0x8003
EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_LOCATIONCHANGE = 0x800B
EVENT_OBJECT_NAMECHANGE = 0x800C

WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
PM_REMOVE = 0x0001

class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT)
    ]

# 全局钩子状态
_global_win_event_hooks = []
_global_detector_ref = None
_last_event_times = {}
_event_debounce_ms = 50
_event_debug_counts = {}

# 回调签名
WinEventProcType = ctypes.WINFUNCTYPE(
    None,
    ctypes.c_void_p, ctypes.c_uint, wintypes.HWND,
    ctypes.c_long, ctypes.c_long, ctypes.c_uint, ctypes.c_uint
)
_win_event_proc = None

# 恢复安全关闭句柄函数
def _safe_close_handle(handle):
    try:
        win32api.CloseHandle(handle)
    except Exception:
        pass

# WinEvent 钩子安装/卸载
def install_win_event_hooks(detector):
    global _global_detector_ref, _win_event_proc
    _global_detector_ref = detector
    user32 = ctypes.windll.user32
    try:
        user32.SetWinEventHook.restype = ctypes.c_void_p
        user32.UnhookWinEvent.argtypes = [ctypes.c_void_p]
        user32.UnhookWinEvent.restype = wintypes.BOOL
    except Exception:
        pass
    _win_event_proc = WinEventProcType(_win_event_callback)
    flags = WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS

    def hook(ev):
        h = user32.SetWinEventHook(ev, ev, None, _win_event_proc, 0, 0, flags)
        if h:
            _global_win_event_hooks.append(h)
        else:
            log(f"SetWinEventHook failed for event {ev}")

    for ev in (
        EVENT_OBJECT_CREATE,
        EVENT_OBJECT_SHOW,
        EVENT_OBJECT_NAMECHANGE,
        EVENT_SYSTEM_FOREGROUND,
        EVENT_OBJECT_DESTROY,
        EVENT_OBJECT_HIDE,
        EVENT_OBJECT_LOCATIONCHANGE,
    ):
        hook(ev)

    if _global_win_event_hooks:
        log(f"WinEvent hooks active: {len(_global_win_event_hooks)}")


def uninstall_win_event_hooks():
    user32 = ctypes.windll.user32
    for h in list(_global_win_event_hooks):
        try:
            user32.UnhookWinEvent(h)
        except Exception:
            pass
        _global_win_event_hooks.remove(h)
    log("WinEvent hooks removed")

# 辅助：主窗口候选（顶层、无 owner、非工具窗）
def _has_window_owner(hwnd):
    try:
        return bool(win32gui.GetWindow(hwnd, win32con.GW_OWNER))
    except Exception:
        return False


def _is_tool_window(hwnd):
    try:
        exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        return bool(exstyle & win32con.WS_EX_TOOLWINDOW)
    except Exception:
        return False


def _is_main_window_candidate(hwnd):
    try:
        if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            return False
        if win32gui.GetParent(hwnd):
            return False
        if _has_window_owner(hwnd):
            return False
        if _is_tool_window(hwnd):
            return False
        return True
    except Exception:
        return False


def _win_event_callback(hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
    if not hwnd:
        return
    # 接受窗口相关事件的 OBJID_WINDOW(0) 和 OBJID_CLIENT(-4)，系统前景事件不受此限制
    if event not in (EVENT_SYSTEM_FOREGROUND,) and idObject not in (0, -4):
        return
    try:
        if win32gui.GetParent(hwnd):
            return
        if _has_window_owner(hwnd) or _is_tool_window(hwnd):
            return
    except Exception:
        pass
    det = _global_detector_ref
    if det is None:
        return
    # 轻量调试：记录前几次事件类型与对象
    try:
        key = (int(hwnd), int(event), int(idObject))
        cnt = _event_debug_counts.get(key, 0)
        if cnt < 3:
            #log(f"WinEvent: event={event}, idObject={idObject}, hwnd={hwnd}")
            _event_debug_counts[key] = cnt + 1
    except Exception:
        pass
    now = time.time()
    last = _last_event_times.get(hwnd, 0)
    debounce_s = (getattr(det, 'event_debounce_ms', _event_debounce_ms) / 1000.0)
    if event != EVENT_OBJECT_DESTROY and (now - last) < debounce_s:
        return
    _last_event_times[hwnd] = now
    try:
        det.event_hits_counts[event] += 1
    except Exception:
        pass
    try:
        if event in (EVENT_OBJECT_CREATE, EVENT_OBJECT_SHOW, EVENT_SYSTEM_FOREGROUND, EVENT_OBJECT_NAMECHANGE):
            _handle_window_appearance(det, hwnd)
        elif event == EVENT_OBJECT_DESTROY:
            _handle_window_disappear(det, hwnd)
        elif event == EVENT_OBJECT_HIDE:
            pass
        elif event == EVENT_OBJECT_LOCATIONCHANGE:
            try:
                cfg = det.config_manager.get_config() or {}
                targets = cfg.get('targets', [])
                target = _match_hwnd_against_targets(det, hwnd, targets)
                if target:
                    _record_current_size(det, hwnd)
                    if hwnd not in det.active_windows and det._is_window_suitable(hwnd, target=target):
                        _handle_window_appearance(det, hwnd)
            except Exception:
                pass
    except Exception as e:
        log(f"WinEvent callback error: {e}")


def _match_hwnd_against_targets(detector, hwnd, targets):
    try:
        if win32gui.GetParent(hwnd) or _has_window_owner(hwnd) or _is_tool_window(hwnd):
            return None
    except Exception:
        pass
    if not win32gui.IsWindow(hwnd):
        return None
    title = win32gui.GetWindowText(hwnd) or ""
    cls_name = win32gui.GetClassName(hwnd) or ""
    exe_name = ""
    hproc = None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        hproc = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
        exe_name = os.path.basename(win32process.GetModuleFileNameEx(hproc, 0)).lower()
    except Exception:
        exe_name = ""
    finally:
        if hproc:
            _safe_close_handle(hproc)
    # 针对微信：排除托盘/剪贴板等非主窗口类，避免误命中
    try:
        cls_lower = cls_name.lower()
        exe_lower = exe_name.lower()
        if ('weixin.exe' in exe_lower or 'wechat.exe' in exe_lower):
            exclude_subs = ('clipboardview', 'trayiconmessagewindow')
            if any(s in cls_lower for s in exclude_subs):
                log(f"目标窗口过滤: 忽略非主窗口类 hwnd={hwnd}, cls={cls_name}, exe={exe_name}")
                return None
    except Exception:
        pass
    for target in targets:
        keywords = target.get('keywords', [])
        for keyword in keywords:
            kw = keyword.lower()
            if (kw in title.lower() or kw in cls_name.lower() or kw in exe_name):
                if detector._is_window_suitable(hwnd, target=target):
                    return target
                else:
                    return None
    return None


def _record_current_size(detector, hwnd):
    try:
        if win32gui.IsIconic(hwnd):
            return
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        w = right - left
        h = bottom - top
        if w <= 0 or h <= 0:
            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
        if w > 0 and h > 0:
            detector._record_window_size(hwnd, w, h)
    except Exception:
        pass


def _handle_window_disappear(detector, hwnd):
    try:
        with detector.lock:
            if hwnd in detector.active_windows:
                log(f"事件检测到目标窗口关闭: {hwnd}")
                try:
                    detector.process_manager.stop_bg_creator(hwnd)
                except Exception:
                    pass
                try:
                    detector.active_windows.remove(hwnd)
                except Exception:
                    pass
                try:
                    detector.size_cache.remove_window(hwnd)
                except Exception:
                    pass
                try:
                    detector.window_size_monitor.pop(hwnd, None)
                except Exception:
                    pass
    except Exception:
        pass


def _handle_window_appearance(detector, hwnd):
    cfg = detector.config_manager.get_config()
    if not cfg or not cfg.get('enabled', True):
        return
    target = _match_hwnd_against_targets(detector, hwnd, cfg.get('targets', []))
    if not target:
        return
    with detector.lock:
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = None
        if pid is not None:
            try:
                existing_same_pid = None
                for ah in list(detector.active_windows):
                    try:
                        _, apid = win32process.GetWindowThreadProcessId(ah)
                    except Exception:
                        apid = None
                    if apid == pid:
                        existing_same_pid = ah
                        break
                if existing_same_pid and existing_same_pid != hwnd:
                    try:
                        new_cls = win32gui.GetClassName(hwnd) or ""
                        old_cls = win32gui.GetClassName(existing_same_pid) or ""
                    except Exception:
                        new_cls, old_cls = "", ""
                    if getattr(detector, 'same_pid_compare_require_same_class', True) and (new_cls.lower() != old_cls.lower()):
                        log(f"同进程不同类别窗口，跳过面积比较: old={existing_same_pid}, old_cls={old_cls}, new={hwnd}, new_cls={new_cls}")
                    else:
                        def _get_area(h):
                            try:
                                rect = win32gui.GetWindowRect(h)
                                return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])
                            except Exception:
                                try:
                                    l, t, r, b = win32gui.GetClientRect(h)
                                    return max(0, r - l) * max(0, b - t)
                                except Exception:
                                    return 0
                        new_area = _get_area(hwnd)
                        old_area = _get_area(existing_same_pid)
                        if new_area >= old_area:
                            log(f"事件发现同进程更大主窗口，切换: {existing_same_pid} -> {hwnd}, pid={pid}, area {old_area} -> {new_area}")
                            detector.process_manager.stop_bg_creator(existing_same_pid)
                            if existing_same_pid in detector.active_windows:
                                detector.active_windows.remove(existing_same_pid)
                            detector.size_cache.remove_window(existing_same_pid)
                            detector.window_size_monitor.pop(existing_same_pid, None)
                        else:
                            log(f"同进程已有更大主窗口，忽略新窗口: hwnd={hwnd}, pid={pid}, area {new_area} < {old_area}, old={existing_same_pid}, old_cls={old_cls}, new_cls={new_cls}")
                            return
            except Exception:
                pass
        _record_current_size(detector, hwnd)
        try:
            predicted = detector.size_cache.get_predicted_size(hwnd)
            try:
                left, top, right, bottom = win32gui.GetClientRect(hwnd)
                cw, ch = right - left, bottom - top
                if cw <= 0 or ch <= 0:
                    rect = win32gui.GetWindowRect(hwnd)
                    cw = rect[2] - rect[0]
                    ch = rect[3] - rect[1]
            except Exception:
                cw, ch = 0, 0
            if predicted:
                pw, ph, conf = predicted
                log(f"预测尺寸: {pw}x{ph} (conf={conf:.2f})，当前尺寸: {cw}x{ch}")
        except Exception:
            pass
        try:
            if getattr(detector, 'foreground_only', False):
                fg = win32gui.GetForegroundWindow()
                if fg != hwnd:
                    log(f"非前台窗口，暂不启动背景: {hwnd}")
                    return
        except Exception:
            pass
        if hwnd not in detector.active_windows:
            log(f"事件检测到新目标窗口: {hwnd} - {target.get('name','Unknown')}")
            if detector.process_manager.start_bg_creator(hwnd, target):
                detector.active_windows.add(hwnd)
                _record_current_size(detector, hwnd)
        else:
            _record_current_size(detector, hwnd)


class ProcessManager:
    """第三层进程管理：负责启动/停止背景创建器子进程"""
    def __init__(self):
        self.processes = {}  # hwnd -> Popen
        self.temp_files = {}  # hwnd -> temp config path
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

    def _temp_config_path(self, hwnd):
        return os.path.join(self.base_dir, f"temp_bg_config_{hwnd}.json")

    def start_bg_creator(self, hwnd, target_config):
        try:
            cfg_path = self._temp_config_path(hwnd)
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(target_config, f, ensure_ascii=False)
            self.temp_files[hwnd] = cfg_path
            # 构造子进程命令：通过 main.py 进入 --bg-creator 模式
            if getattr(sys, 'frozen', False):
                exe = sys.executable
                cmd = [exe, '--bg-creator', str(hwnd), cfg_path]
            else:
                py = sys.executable
                main_py = os.path.join(self.base_dir, 'main.py')
                cmd = [py, main_py, '--bg-creator', str(hwnd), cfg_path]
            p = subprocess.Popen(cmd, creationflags=win32con.DETACHED_PROCESS)
            self.processes[hwnd] = p
            log(f"已启动背景创建器: hwnd={hwnd}, pid={p.pid}")
            return True
        except Exception as e:
            log(f"启动背景创建器失败: {e}")
            return False

    def stop_bg_creator(self, hwnd):
        p = self.processes.pop(hwnd, None)
        if p:
            try:
                p.terminate()
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            log(f"已停止背景创建器: hwnd={hwnd}")
        cfg_path = self.temp_files.pop(hwnd, None)
        if cfg_path:
            try:
                if os.path.exists(cfg_path):
                    os.remove(cfg_path)
            except Exception:
                pass

    def stop_all(self):
        for hwnd in list(self.processes.keys()):
            try:
                self.stop_bg_creator(hwnd)
            except Exception:
                pass

    def _cleanup_temp_files(self):
        try:
            for fn in os.listdir(self.base_dir):
                if fn.startswith('temp_bg_config_') and fn.endswith('.json'):
                    fp = os.path.join(self.base_dir, fn)
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
            log("已清理临时配置文件")
        except Exception:
            pass


class WindowDetector:
    """窗口检测器：事件驱动为主，扫描为兜底"""
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.active_windows = set()
        self.lock = threading.RLock()
        self.size_cache = get_size_cache()
        self.window_size_monitor = {}
        self.process_manager = ProcessManager()
        self.should_exit = False
        # 调度参数
        self.scan_interval_min = 2.0
        self.size_monitor_interval = 1.0
        self.closure_check_interval = 2.0
        # 事件统计
        self.event_hits_counts = defaultdict(int)
        # 行为配置
        self.same_pid_compare_require_same_class = True
        self.foreground_only = False
        self.event_debounce_ms = _event_debounce_ms

    def _record_window_size(self, hwnd, w, h):
        try:
            # 轻微抖动过滤（<5像素变化忽略）
            prev = self.window_size_monitor.get(hwnd)
            if prev:
                pw, ph = prev
                if abs(pw - w) < 5 and abs(ph - h) < 5:
                    return
            self.window_size_monitor[hwnd] = (w, h)
            self.size_cache.record_window_size(hwnd, w, h)
        except Exception:
            pass

    def _is_window_suitable(self, hwnd, target=None):
        try:
            if not _is_main_window_candidate(hwnd):
                return False
            # 客户区优先
            try:
                l, t, r, b = win32gui.GetClientRect(hwnd)
                w, h = r - l, b - t
            except Exception:
                w = h = 0
            if w <= 0 or h <= 0:
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    w, h = rect[2] - rect[0], rect[3] - rect[1]
                except Exception:
                    w = h = 0
            area = max(0, w) * max(0, h)
            cfg = self.config_manager.get_config() or {}
            min_area_cfg = int(cfg.get('ignore_size', 10000))
            min_area_target = int((target or {}).get('main_min_area', 0))
            min_area = max(min_area_cfg, min_area_target)
            if area < min_area:
                return False
            # 记录尺寸
            if w > 0 and h > 0:
                self._record_window_size(hwnd, w, h)
            return True
        except Exception:
            return False

    def scan_windows(self):
        cfg = self.config_manager.get_config()
        if not cfg or not cfg.get('enabled', True):
            return
        targets = cfg.get('targets', [])
        matched = []
        current_hwnds = []

        def enum_windows(hwnd, param):
            try:
                if not _is_main_window_candidate(hwnd):
                    return
                current_hwnds.append(hwnd)
                target = _match_hwnd_against_targets(self, hwnd, targets)
                if target:
                    matched.append((hwnd, target))
            except Exception:
                pass

        try:
            win32gui.EnumWindows(enum_windows, None)
        except Exception as e:
            log(f"枚举窗口失败: {e}")
            return

        # 按进程ID去重，保留最大窗口（可选同类比较）
        by_pid = {}
        for hwnd, target in matched:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                pid = None
            if pid is None:
                continue
            # 计算面积
            def _get_area(h):
                try:
                    rect = win32gui.GetWindowRect(h)
                    return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])
                except Exception:
                    try:
                        l, t, r, b = win32gui.GetClientRect(h)
                        return max(0, r - l) * max(0, b - t)
                    except Exception:
                        return 0
            area = _get_area(hwnd)
            cls = ''
            try:
                cls = win32gui.GetClassName(hwnd) or ''
            except Exception:
                cls = ''
            prev = by_pid.get(pid)
            if not prev:
                by_pid[pid] = (hwnd, area, cls, target)
            else:
                phwnd, parea, pcls, ptarget = prev
                if self.same_pid_compare_require_same_class and (cls.lower() != pcls.lower()):
                    # 不同类别，不比较，保留已有
                    continue
                if area >= parea:
                    by_pid[pid] = (hwnd, area, cls, target)

        # 启动/切换背景，处理同进程更大窗口
        for pid, (hwnd, area, cls, target) in by_pid.items():
            existing_same_pid = None
            for ah in list(self.active_windows):
                try:
                    _, apid = win32process.GetWindowThreadProcessId(ah)
                except Exception:
                    apid = None
                if apid == pid:
                    existing_same_pid = ah
                    break
            if existing_same_pid and existing_same_pid != hwnd:
                try:
                    old_cls = win32gui.GetClassName(existing_same_pid) or ''
                except Exception:
                    old_cls = ''
                if self.same_pid_compare_require_same_class and (cls.lower() != old_cls.lower()):
                    log(f"扫描同进程不同类别窗口，跳过面积比较: old={existing_same_pid}, old_cls={old_cls}, new={hwnd}, new_cls={cls}")
                else:
                    def _get_area(h):
                        try:
                            rect = win32gui.GetWindowRect(h)
                            return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])
                        except Exception:
                            try:
                                l, t, r, b = win32gui.GetClientRect(h)
                                return max(0, r - l) * max(0, b - t)
                            except Exception:
                                return 0
                    old_area = _get_area(existing_same_pid)
                    if area >= old_area:
                        log(f"扫描发现同进程更大主窗口，切换: {existing_same_pid} -> {hwnd}, pid={pid}, area {old_area} -> {area}")
                        self.process_manager.stop_bg_creator(existing_same_pid)
                        if existing_same_pid in self.active_windows:
                            self.active_windows.remove(existing_same_pid)
                        self.size_cache.remove_window(existing_same_pid)
                        self.window_size_monitor.pop(existing_same_pid, None)
                    else:
                        log(f"扫描同进程已有更大主窗口，跳过: hwnd={hwnd}, pid={pid}, area {area} < {old_area}, old={existing_same_pid}, old_cls={old_cls}, new_cls={cls}")
                        continue
            # 可选：仅前台窗口
            if getattr(self, 'foreground_only', False):
                try:
                    if win32gui.GetForegroundWindow() != hwnd:
                        log(f"非前台窗口，暂不启动背景: {hwnd}")
                        continue
                except Exception:
                    pass
            if hwnd not in self.active_windows:
                log(f"扫描检测到新目标窗口: {hwnd} - {target.get('name','Unknown')}")
                if self.process_manager.start_bg_creator(hwnd, target):
                    self.active_windows.add(hwnd)
                    _record_current_size(self, hwnd)
            else:
                _record_current_size(self, hwnd)

        # 移除已关闭窗口（兜底）
        windows_to_remove = []
        for ah in list(self.active_windows):
            if ah not in current_hwnds:
                if not win32gui.IsWindow(ah):
                    windows_to_remove.append(ah)
        for ah in windows_to_remove:
            self.process_manager.stop_bg_creator(ah)
            try:
                self.active_windows.remove(ah)
            except Exception:
                pass
            self.size_cache.remove_window(ah)
            self.window_size_monitor.pop(ah, None)

    def _monitor_window_sizes(self):
        for hwnd in list(self.active_windows):
            try:
                _record_current_size(self, hwnd)
            except Exception:
                pass

    def _check_window_closures(self):
        windows_to_remove = []
        for hwnd in list(self.active_windows):
            try:
                if not win32gui.IsWindow(hwnd):
                    windows_to_remove.append(hwnd)
            except Exception:
                pass
        for hwnd in windows_to_remove:
            self.process_manager.stop_bg_creator(hwnd)
            try:
                self.active_windows.remove(hwnd)
            except Exception:
                pass
            self.size_cache.remove_window(hwnd)
            self.window_size_monitor.pop(hwnd, None)

    def rerender_now(self, full_reset=True):
        try:
            log("收到手动重新渲染指令，准备刷新背景")
            if full_reset:
                try:
                    self.process_manager.stop_all()
                except Exception as e:
                    log(f"停止现有背景进程失败: {e}")
                with self.lock:
                    hwnds = list(self.active_windows)
                    for hwnd in hwnds:
                        try:
                            self.size_cache.remove_window(hwnd)
                        except Exception:
                            pass
                        self.window_size_monitor.pop(hwnd, None)
                    self.active_windows.clear()
            self.scan_windows()
            log("重新渲染完成")
            return True
        except Exception as e:
            log(f"重新渲染失败: {e}")
            return False

    def run(self):
        log("窗口检测器启动")
        try:
            install_win_event_hooks(self)
        except Exception as e:
            log(f"安装 WinEvent 钩子失败: {e}")
        try:
            last_scan_time = 0
            last_size_monitor_time = 0
            last_closure_check_time = 0
            user32 = ctypes.windll.user32
            msg = MSG()
            while not self.should_exit:
                # 轻量消息泵，确保钩子回调可被调度
                try:
                    while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                except Exception:
                    pass
                current_time = time.time()
                config = self.config_manager.get_config()
                base_scan = (config.get('scan_interval', self.scan_interval_min) if config else self.scan_interval_min)
                scan_interval = max(base_scan, self.scan_interval_min)
                if current_time - last_scan_time >= scan_interval:
                    self.scan_windows()
                    last_scan_time = current_time
                if current_time - last_size_monitor_time >= self.size_monitor_interval:
                    self._monitor_window_sizes()
                    last_size_monitor_time = current_time
                if current_time - last_closure_check_time >= self.closure_check_interval:
                    self._check_window_closures()
                    last_closure_check_time = current_time
                time.sleep(0.1)
        except KeyboardInterrupt:
            log("收到中断信号")
        except Exception as e:
            log(f"窗口检测器运行出错: {e}")
        finally:
            self.cleanup()

    def stop(self):
        self.should_exit = True
        try:
            self.size_cache.should_exit = True
        except Exception:
            pass

    def cleanup(self):
        # 防重复清理（避免退出路径重复触发）
        if getattr(self, "_cleanup_done", False):
            return
        self._cleanup_done = True

        log("正在清理资源...")
        try:
            self.process_manager.stop_all()
        except Exception:
            pass
        try:
            uninstall_win_event_hooks()
        except Exception as e:
            log(f"卸载 WinEvent 钩子失败: {e}")
        try:
            if hasattr(self, 'size_cache'):
                self.size_cache.cleanup()
        except Exception:
            pass
        try:
            total = sum(self.event_hits_counts.values())
            log(f"WinEvent命中总数: {total}, 细分: {dict(self.event_hits_counts)}")
        except Exception as e:
            log(f"统计WinEvent命中时出错: {e}")
        log("窗口检测器已停止")


def main():
    """简单测试入口（仅开发模式）"""
    class TempConfigManager:
        def get_config(self):
            return {
                "enabled": True,
                "scan_interval": 3,
                "targets": [
                    {
                        "name": "Notepad",
                        "keywords": ["notepad.exe", "记事本"],
                        "image_path": "background.png",
                        "alpha": 40,
                        "brightness": 1.0,
                        "contrast": 1.0,
                        "saturation": 1.0,
                        "main_min_area": 100000
                    }
                ]
            }
    detector = WindowDetector(TempConfigManager())
    try:
        detector.run()
    except KeyboardInterrupt:
        detector.stop()


if __name__ == "__main__":
    main()