#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
窗口尺寸缓存管理器 (sxxzh定制版)
负责记录和管理窗口的历史尺寸信息，提升背景渲染速度

开发者: sxxzh
版本: 1.0.0
"""

import os
import json
import time
import threading
import win32gui
import win32process
import win32api
import sys
from typing import Dict, Tuple, Optional, List
from collections import defaultdict, deque
from logger import log as _log

def log(msg):
    """统一日志输出"""
    _log(msg, module="size-cache", to_console=False)

class WindowSizeCache:
    """窗口尺寸缓存管理器"""
    
    def __init__(self, cache_file: str = "window_size_cache.json", max_history: int = 10):
        # 将缓存文件解析为在打包环境下可写的本地用户目录
        self.cache_file = self._resolve_cache_path(cache_file)
        log(f"尺寸缓存文件路径: {self.cache_file}")
        self.max_history = max_history
        self.lock = threading.RLock()
        self.should_exit = False
        
        # 防抖保存机制
        self.pending_save = False
        self.last_save_time = 0
        self.save_debounce_time = 2.0  # 2秒防抖时间
        
        # 缓存结构：
        # {
        #   "process_name": {
        #     "window_title_pattern": {
        #       "sizes": [(width, height, timestamp), ...],
        #       "last_used": timestamp,
        #       "usage_count": int
        #     }
        #   }
        # }
        self.cache_data = {}
        
        # 运行时缓存：当前活跃窗口的尺寸
        self.runtime_cache = {}  # hwnd -> (width, height, last_update)
        self.runtime_meta = {}  # hwnd -> (process_name, window_title_pattern)
        
        # 预测缓存：基于历史数据预测的最可能尺寸
        self.predicted_sizes = {}  # process_name -> (width, height, confidence)
        # 会话观测的进程集合：仅在本次会话实测过该进程后才启用预测
        self.session_observed_processes = set()
        
        # 加载缓存数据
        self._load_cache()
        
        # 启动自动保存线程
        self._start_auto_save_thread()

    def _resolve_cache_path(self, cache_file: str) -> str:
        """解析缓存文件路径：
        - 打包环境使用 `%LOCALAPPDATA%/sxxzh_bg_system/window_size_cache.json`
        - 开发环境使用源码目录下的相对路径
        - 若传入绝对路径，直接使用
        """
        # 绝对路径直接使用
        if os.path.isabs(cache_file):
            path = cache_file
        else:
            if getattr(sys, 'frozen', False):
                # 本地用户可写目录
                local_appdata = os.environ.get('LOCALAPPDATA')
                if not local_appdata:
                    # 兜底到用户主目录下的 AppData/Local
                    local_appdata = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
                app_dir = os.path.join(local_appdata, 'sxxzh_bg_system')
                try:
                    os.makedirs(app_dir, exist_ok=True)
                except Exception as e:
                    # 目录创建失败不影响后续，仍尝试写入
                    log(f"创建本地应用数据目录失败: {e}")
                path = os.path.join(app_dir, cache_file)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                path = os.path.join(base_dir, cache_file)
        # 确保父目录存在
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            try:
                os.makedirs(parent, exist_ok=True)
            except Exception:
                pass
        return path

    def _load_cache(self):
        """加载缓存数据"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache_data = json.load(f)
                log(f"已加载窗口尺寸缓存，包含 {len(self.cache_data)} 个应用程序的数据")
            else:
                self.cache_data = {}
                log("创建新的窗口尺寸缓存")
        except Exception as e:
            log(f"加载缓存失败: {e}")
            self.cache_data = {}

    def _save_cache(self):
        """保存缓存数据"""
        try:
            with self.lock:
                # 清理过期数据（超过30天的记录）
                current_time = time.time()
                cleaned_data = {}
                
                for process_name, process_data in self.cache_data.items():
                    cleaned_process_data = {}
                    for pattern, pattern_data in process_data.items():
                        # 保留最近30天的数据
                        if current_time - pattern_data.get('last_used', 0) < 30 * 24 * 3600:
                            # 清理过期的尺寸记录
                            sizes = pattern_data.get('sizes', [])
                            valid_sizes = [
                                (w, h, ts) for w, h, ts in sizes 
                                if current_time - ts < 30 * 24 * 3600
                            ]
                            if valid_sizes:
                                pattern_data['sizes'] = valid_sizes[-self.max_history:]
                                cleaned_process_data[pattern] = pattern_data
                    
                    if cleaned_process_data:
                        cleaned_data[process_name] = cleaned_process_data
                
                # 保存清理后的数据
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
                
                self.cache_data = cleaned_data
                
        except Exception as e:
            log(f"保存缓存失败: {e}")

    def _start_auto_save_thread(self):
        """启动自动保存线程"""
        def auto_save():
            while not self.should_exit:
                time.sleep(1)  # 每秒检查一次
                
                current_time = time.time()
                
                # 检查是否有待保存的数据且超过防抖时间
                if (self.pending_save and 
                    current_time - self.last_save_time >= self.save_debounce_time):
                    with self.lock:
                        if self.pending_save:  # 双重检查
                            self._save_cache_immediate()
                
                # 每5分钟定期保存一次（即使没有待保存数据）
                if current_time - self.last_save_time >= 300:
                    with self.lock:
                        self._save_cache_immediate()
        
        self.auto_save_thread = threading.Thread(target=auto_save, daemon=True)
        self.auto_save_thread.start()

    def _get_process_name(self, hwnd: int) -> str:
        """获取窗口的进程名"""
        hproc = None
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            hproc = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
            exe_path = win32process.GetModuleFileNameEx(hproc, 0)
            return os.path.basename(exe_path).lower()
        except:
            return "unknown"
        finally:
            if hproc:
                try:
                    win32api.CloseHandle(hproc)
                except:
                    pass

    def _get_window_pattern(self, hwnd: int) -> str:
        """获取窗口标题模式（用于匹配相似窗口）"""
        try:
            title = win32gui.GetWindowText(hwnd) or ""
            # 简化标题，移除可能变化的部分（如文件名、时间等）
            # 保留前20个字符作为模式
            pattern = title[:20] if title else "default"
            return pattern
        except:
            return "default"

    def reset_session_predicted(self):
        """清除当前会话的预测尺寸，避免使用历史会话的预测结果"""
        with self.lock:
            self.predicted_sizes.clear()
            try:
                self.session_observed_processes.clear()
            except Exception:
                pass

    def record_window_size(self, hwnd: int, width: int, height: int, process_name: Optional[str] = None, pattern: Optional[str] = None):
        """记录窗口尺寸"""
        if width <= 0 or height <= 0:
            return
        
        try:
            process_name = process_name or self._get_process_name(hwnd)
            pattern = pattern or self._get_window_pattern(hwnd)
            current_time = time.time()
            
            with self.lock:
                # 标记该进程在当前会话已实测过
                self.session_observed_processes.add(process_name)
                # 更新运行时缓存
                self.runtime_cache[hwnd] = (width, height, current_time)
                self.runtime_meta[hwnd] = (process_name, pattern)
                
                # 更新持久化缓存
                if process_name not in self.cache_data:
                    self.cache_data[process_name] = {}
                
                if pattern not in self.cache_data[process_name]:
                    self.cache_data[process_name][pattern] = {
                        'sizes': [],
                        'last_used': current_time,
                        'usage_count': 0
                    }
                
                pattern_data = self.cache_data[process_name][pattern]
                
                # 检查是否是新尺寸
                sizes = pattern_data['sizes']
                is_new_size = True
                for i, (w, h, ts) in enumerate(sizes):
                    if w == width and h == height:
                        # 更新时间戳
                        sizes[i] = (w, h, current_time)
                        is_new_size = False
                        break

                
                if is_new_size:
                    sizes.append((width, height, current_time))
                    # 保持最大历史记录数量
                    if len(sizes) > self.max_history:
                        sizes.pop(0)
                
                pattern_data['last_used'] = current_time
                pattern_data['usage_count'] += 1
                
                # 更新预测缓存
                self._update_predicted_size(process_name)
                
                log(f"记录窗口尺寸: {process_name} - {width}x{height}")
                
        except Exception as e:
            log(f"记录窗口尺寸失败: {e}")

    def _update_predicted_size(self, process_name: str):
        """更新预测尺寸"""
        try:
            if process_name not in self.cache_data:
                return
            
            # 收集所有尺寸数据，按使用频率和时间加权
            size_scores = defaultdict(float)
            current_time = time.time()
            
            for pattern_data in self.cache_data[process_name].values():
                usage_count = pattern_data.get('usage_count', 1)
                last_used = pattern_data.get('last_used', 0)
                
                # 时间权重：最近使用的权重更高
                time_weight = max(0.1, 1.0 - (current_time - last_used) / (7 * 24 * 3600))
                
                for width, height, timestamp in pattern_data.get('sizes', []):
                    size_key = (width, height)
                    # 综合权重：使用频率 * 时间权重 * 记录时间权重
                    record_time_weight = max(0.1, 1.0 - (current_time - timestamp) / (7 * 24 * 3600))
                    score = usage_count * time_weight * record_time_weight
                    size_scores[size_key] += score
            
            if size_scores:
                # 选择得分最高的尺寸
                best_size = max(size_scores.items(), key=lambda x: x[1])
                width, height = best_size[0]
                confidence = min(1.0, best_size[1] / 10.0)  # 归一化置信度
                
                self.predicted_sizes[process_name] = (width, height, confidence)
                
        except Exception as e:
            log(f"更新预测尺寸失败: {e}")

    def get_predicted_size(self, hwnd: int) -> Optional[Tuple[int, int, float]]:
        """获取预测的窗口尺寸"""
        try:
            # 首先检查运行时缓存
            if hwnd in self.runtime_cache:
                width, height, _ = self.runtime_cache[hwnd]
                return (width, height, 1.0)  # 运行时缓存置信度最高
            
            process_name = self._get_process_name(hwnd)
            # 仅在本次会话已实测过该进程后，才允许使用历史预测
            if process_name in self.session_observed_processes:
                # 然后检查预测缓存
                if process_name in self.predicted_sizes:
                    return self.predicted_sizes[process_name]
                
                # 如果没有预测数据，尝试从历史数据中获取最常用的尺寸
                if process_name in self.cache_data:
                    self._update_predicted_size(process_name)
                    if process_name in self.predicted_sizes:
                        return self.predicted_sizes[process_name]
            
            return None
            
        except Exception as e:
            log(f"获取预测尺寸失败: {e}")
            return None

    def remove_window(self, hwnd: int):
        """移除窗口（窗口关闭时调用）"""
        try:
            with self.lock:
                if hwnd in self.runtime_cache:
                    width, height, _ = self.runtime_cache[hwnd]
                    pn, pat = self.runtime_meta.get(hwnd, (None, None))
                    # 程序退出时不写入最后尺寸，避免跨会话影响判断
                    if not self.should_exit:
                        self.record_window_size(hwnd, width, height, process_name=pn, pattern=pat)
                        log(f"窗口 {hwnd} 关闭，标记保存尺寸数据: {width}x{height}")
                        self._schedule_save()
                    del self.runtime_cache[hwnd]
                    self.runtime_meta.pop(hwnd, None)
        except Exception as e:
            log(f"移除窗口失败: {e}")

    def _schedule_save(self):
        """调度保存操作（防抖）"""
        current_time = time.time()
        self.pending_save = True
        
        # 如果距离上次保存时间超过防抖时间，立即保存
        if current_time - self.last_save_time >= self.save_debounce_time:
            self._save_cache_immediate()
        # 否则标记为待保存，由自动保存线程处理

    def _save_cache_immediate(self):
        """立即保存缓存数据（不加锁，由调用者确保线程安全）"""
        try:
            # 清理过期数据（超过30天的记录）
            current_time = time.time()
            cleaned_data = {}
            
            for process_name, process_data in self.cache_data.items():
                cleaned_process_data = {}
                for pattern, pattern_data in process_data.items():
                    # 保留最近30天的数据
                    if current_time - pattern_data.get('last_used', 0) < 30 * 24 * 3600:
                        # 清理过期的尺寸记录
                        sizes = pattern_data.get('sizes', [])
                        valid_sizes = [
                            (w, h, ts) for w, h, ts in sizes 
                            if current_time - ts < 30 * 24 * 3600
                        ]
                        if valid_sizes:
                            pattern_data['sizes'] = valid_sizes[-self.max_history:]
                            cleaned_process_data[pattern] = pattern_data
                
                if cleaned_process_data:
                    cleaned_data[process_name] = cleaned_process_data
            
            # 保存清理后的数据
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
            
            self.cache_data = cleaned_data
            self.last_save_time = current_time
            self.pending_save = False
            log("窗口尺寸缓存已立即保存")
            
        except Exception as e:
            log(f"立即保存缓存失败: {e}")

    def get_cache_stats(self) -> Dict:
        """获取缓存统计信息"""
        try:
            with self.lock:
                stats = {
                    'total_processes': len(self.cache_data),
                    'runtime_windows': len(self.runtime_cache),
                    'predicted_sizes': len(self.predicted_sizes),
                    'total_size_records': 0
                }
                
                for process_data in self.cache_data.values():
                    for pattern_data in process_data.values():
                        stats['total_size_records'] += len(pattern_data.get('sizes', []))
                
                return stats
                
        except Exception as e:
            log(f"获取统计信息失败: {e}")
            return {}

    def clear_all(self, remove_file: bool = True):
        """清空所有缓存并可选删除缓存文件"""
        try:
            with self.lock:
                self.cache_data = {}
                self.runtime_cache = {}
                self.predicted_sizes = {}
                self.pending_save = False
                self.last_save_time = time.time()
                if remove_file:
                    try:
                        if os.path.exists(self.cache_file):
                            os.remove(self.cache_file)
                            log(f"已删除缓存文件: {self.cache_file}")
                    except Exception as e:
                        log(f"删除缓存文件失败: {e}")
            log("已清空窗口尺寸缓存数据")
        except Exception as e:
            log(f"清空缓存失败: {e}")

    def cleanup(self):
        """清理资源"""
        log("正在清理窗口尺寸缓存...")
        self.should_exit = True
        
        # 如果有待保存的数据，立即保存
        with self.lock:
            if self.pending_save:
                log("保存待保存的窗口尺寸数据...")
                self._save_cache_immediate()
            else:
                # 即使没有待保存数据，也执行一次常规保存
                self._save_cache()
        
        log("窗口尺寸缓存已保存")

# 全局缓存实例
_global_cache = None

def get_size_cache() -> WindowSizeCache:
    """获取全局尺寸缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = WindowSizeCache()
    return _global_cache

def main():
    """测试函数"""
    cache = WindowSizeCache()
    
    # 模拟记录一些窗口尺寸
    cache.record_window_size(12345, 1920, 1080)
    cache.record_window_size(12345, 1920, 1080)  # 重复记录
    cache.record_window_size(12345, 1366, 768)   # 不同尺寸
    
    # 获取预测尺寸
    predicted = cache.get_predicted_size(12345)
    if predicted:
        width, height, confidence = predicted
        print(f"预测尺寸: {width}x{height}, 置信度: {confidence:.2f}")
    
    # 显示统计信息
    stats = cache.get_cache_stats()
    print(f"缓存统计: {stats}")
    
    cache.cleanup()

if __name__ == "__main__":
    main()