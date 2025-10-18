#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二层：窗口检测器 (sxxzh定制版)
实时监控目标窗口出现/消失
控制第三层进程的创建和删除

开发者: sxxzh
版本: 1.0.0
"""

import os
import sys
import win32gui
import win32process
import win32api
import time
import subprocess
import json
import threading
from collections import defaultdict

def log(msg):
    """日志输出"""
    timestamp = time.strftime('%H:%M:%S')
    print(f"[window-detector] {timestamp} - {msg}")

class ProcessManager:
    """进程管理器 - 管理第三层进程"""
    
    def __init__(self):
        self.active_processes = {}  # hwnd -> process
        self.lock = threading.Lock()
    
    def start_bg_creator(self, target_hwnd, config):
        """启动第三层背景创建器进程"""
        with self.lock:
            if target_hwnd in self.active_processes:
                log(f"目标窗口 {target_hwnd} 的背景进程已存在")
                return False
            
            try:
                # 构建命令行参数 - 使用临时文件传递配置，避免JSON转义问题
                import tempfile
                import uuid
                
                # 创建临时配置文件
                config_file = os.path.join(tempfile.gettempdir(), f"window_bg_config_{uuid.uuid4().hex}.json")
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                
                # 构建命令行参数 - 改进版本，支持打包环境
                if getattr(sys, 'frozen', False):
                    # 打包后环境：直接运行可执行文件，bg_creator作为模块调用
                    cmd = [
                        sys.executable,  # 主程序可执行文件
                        '--bg-creator',  # 特殊参数标识背景创建器模式
                        str(target_hwnd),
                        config_file
                    ]
                else:
                    # 开发环境：使用Python运行bg_creator.py
                    cmd = [
                        sys.executable, 
                        os.path.join(os.path.dirname(__file__), 'bg_creator.py'),
                        str(target_hwnd),
                        config_file
                    ]
                
                # 启动进程 - 使用shell=False避免PowerShell转义问题
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
                
                self.active_processes[target_hwnd] = process
                log(f"启动背景创建器进程，目标窗口: {target_hwnd}, PID: {process.pid}")
                
                # 启动监控线程
                monitor_thread = threading.Thread(
                    target=self._monitor_process,
                    args=(target_hwnd, process),
                    daemon=True
                )
                monitor_thread.start()
                
                return True
                
            except Exception as e:
                log(f"启动背景创建器失败: {e}")
                # 清理临时文件
                try:
                    if os.path.exists(config_file):
                        os.remove(config_file)
                except:
                    pass
                return False
    
    def _monitor_process(self, target_hwnd, process):
        """监控进程状态"""
        try:
            # 读取进程输出
            stdout, stderr = process.communicate(timeout=5)
            
            if stdout:
                log(f"背景创建器进程输出 (窗口 {target_hwnd}): {stdout.strip()}")
            if stderr:
                log(f"背景创建器进程错误 (窗口 {target_hwnd}): {stderr.strip()}")
            
            return_code = process.returncode
            
            with self.lock:
                if target_hwnd in self.active_processes:
                    del self.active_processes[target_hwnd]
                    log(f"背景创建器进程已退出，目标窗口: {target_hwnd}, 返回码: {return_code}")
                    
        except subprocess.TimeoutExpired:
            # 如果进程超时，强制终止并读取输出
            try:
                stdout, stderr = process.communicate()
                if stdout:
                    log(f"背景创建器进程超时输出 (窗口 {target_hwnd}): {stdout.strip()}")
                if stderr:
                    log(f"背景创建器进程超时错误 (窗口 {target_hwnd}): {stderr.strip()}")
                
                process.kill()
                return_code = process.returncode
                
                with self.lock:
                    if target_hwnd in self.active_processes:
                        del self.active_processes[target_hwnd]
                        log(f"背景创建器进程超时终止，目标窗口: {target_hwnd}, 返回码: {return_code}")
                        
            except Exception as e:
                log(f"处理超时进程时出错: {e}")
                
        except Exception as e:
            log(f"监控进程时出错: {e}")
    
    def stop_bg_creator(self, target_hwnd):
        """停止指定窗口的背景创建器进程"""
        with self.lock:
            if target_hwnd not in self.active_processes:
                return False
            
            process = self.active_processes[target_hwnd]
            
            try:
                # 终止进程
                process.terminate()
                process.wait(timeout=5)
                del self.active_processes[target_hwnd]
                log(f"已停止目标窗口 {target_hwnd} 的背景进程")
                return True
                
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait()
                except:
                    pass
                del self.active_processes[target_hwnd]
                log(f"强制终止目标窗口 {target_hwnd} 的背景进程")
                return True
                
            except Exception as e:
                log(f"停止背景创建器失败: {e}")
                return False
    
    def stop_all(self):
        """停止所有背景创建器进程并清理临时文件"""
        # 先获取所有需要停止的窗口句柄，避免在循环中持有锁
        with self.lock:
            hwnds = list(self.active_processes.keys())
        
        # 逐个停止进程，避免死锁
        for hwnd in hwnds:
            self.stop_bg_creator(hwnd)
        
        # 清理临时配置文件
        self._cleanup_temp_files()
        log(f"已停止所有背景进程，共 {len(hwnds)} 个，临时文件已清理")
    
    def _cleanup_temp_files(self):
        """清理临时配置文件"""
        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_files = []
        
        # 查找所有以window_bg_config_开头的临时文件
        for filename in os.listdir(temp_dir):
            if filename.startswith("window_bg_config_") and filename.endswith(".json"):
                temp_files.append(os.path.join(temp_dir, filename))
        
        # 删除找到的临时文件
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    log(f"清理临时文件: {temp_file}")
            except Exception as e:
                log(f"清理临时文件失败 {temp_file}: {e}")

class WindowDetector:
    """窗口检测器"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.process_manager = ProcessManager()
        self.active_windows = set()  # 当前活跃的目标窗口
        self.should_exit = False
        self.lock = threading.Lock()
    
    def find_target_windows(self, targets):
        """查找所有匹配的目标窗口"""
        matched_windows = []
        
        def enum_windows(hwnd, param):
            if not win32gui.IsWindowVisible(hwnd):
                return
            
            # 获取窗口信息
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                hproc = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
                exe_name = win32process.GetModuleFileNameEx(hproc, 0)
                exe_name = os.path.basename(exe_name).lower()
            except:
                exe_name = ""
            
            title = win32gui.GetWindowText(hwnd) or ""
            cls_name = win32gui.GetClassName(hwnd) or ""
            
            # 检查每个目标配置
            for target in targets:
                keywords = target.get('keywords', [])
                
                # 检查是否匹配任何关键词
                for keyword in keywords:
                    keyword_lower = keyword.lower()
                    if (keyword_lower in title.lower() or 
                        keyword_lower in cls_name.lower() or 
                        keyword_lower in exe_name):
                        
                        # 检查窗口大小是否合适
                        if self._is_window_suitable(hwnd):
                            matched_windows.append((hwnd, target))
                            break
        
        win32gui.EnumWindows(enum_windows, None)
        return matched_windows
    
    def _is_window_suitable(self, hwnd):
        """检查窗口是否适合添加背景"""
        try:
            # 获取客户区大小
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            width = right - left
            height = bottom - top
            
            # 如果客户区太小，检查窗口矩形
            if width <= 0 or height <= 0:
                rect = win32gui.GetWindowRect(hwnd)
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]
            
            # 窗口太小不适合
            if width < 100 or height < 100:
                return False
                
            return True
            
        except:
            return False
    
    def scan_windows(self):
        """扫描窗口并管理进程"""
        config = self.config_manager.get_config()
        if not config or not config.get('enabled', True):
            return
        
        targets = config.get('targets', [])
        if not targets:
            return
        
        try:
            # 查找匹配的窗口（使用超时保护）
            current_windows = self.find_target_windows(targets)
            current_hwnds = {hwnd for hwnd, _ in current_windows}
            
            with self.lock:
                # 检查需要启动的新窗口
                for hwnd, target_config in current_windows:
                    if hwnd not in self.active_windows:
                        log(f"发现新目标窗口: {hwnd} - {target_config.get('name', 'Unknown')}")
                        
                        # 启动背景创建器进程
                        if self.process_manager.start_bg_creator(hwnd, target_config):
                            self.active_windows.add(hwnd)
                
                # 检查需要停止的窗口
                windows_to_remove = []
                for hwnd in self.active_windows:
                    if hwnd not in current_hwnds:
                        # 检查窗口是否还存在
                        if not win32gui.IsWindow(hwnd):
                            log(f"目标窗口 {hwnd} 已关闭")
                            windows_to_remove.append(hwnd)
                        else:
                            # 窗口存在但不再匹配目标，检查是否仍然可见
                            if not win32gui.IsWindowVisible(hwnd):
                                log(f"目标窗口 {hwnd} 不再可见")
                                windows_to_remove.append(hwnd)
                
                # 移除已关闭的窗口并停止对应进程
                for hwnd in windows_to_remove:
                    self.process_manager.stop_bg_creator(hwnd)
                    self.active_windows.remove(hwnd)
                    
        except Exception as e:
            log(f"扫描窗口时出错: {e}")
            # 出错时继续运行，避免整个系统崩溃
    
    def run(self):
        """运行窗口检测器"""
        log("窗口检测器启动")
        
        try:
            last_scan_time = 0
            
            while not self.should_exit:
                current_time = time.time()
                
                # 获取扫描间隔
                config = self.config_manager.get_config()
                scan_interval = config.get('scan_interval', 3) if config else 3
                
                # 只有在需要扫描时才执行扫描
                if current_time - last_scan_time >= scan_interval:
                    # 扫描窗口
                    self.scan_windows()
                    last_scan_time = current_time
                
                # 使用更短的等待时间，避免阻塞
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            log("收到中断信号")
        except Exception as e:
            log(f"窗口检测器运行出错: {e}")
        finally:
            self.cleanup()
    
    def stop(self):
        """停止窗口检测器"""
        self.should_exit = True
    
    def cleanup(self):
        """清理资源"""
        log("正在清理资源...")
        self.process_manager.stop_all()
        log("窗口检测器已停止")

def main():
    """测试函数"""
    # 临时配置管理器
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
                        "saturation": 1.0
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