def main():
    """主函数 - sxxzh定制版 v1.0.2"""
    # 记录启动信息
    log("="*60)
    log("窗口背景挂载系统启动")
    log(f"Python版本: {sys.version}")
    log(f"运行模式: {'打包模式' if getattr(sys, 'frozen', False) else '开发模式'}")
    log(f"命令行参数: {sys.argv}")
    log("="*60)
    
    # 检查是否是配置编辑器模式
    if len(sys.argv) > 1 and sys.argv[1] == '--config-editor':
        log("进入配置编辑器模式")
        try:
            from UI import main as ui_main
            config_path = sys.argv[2] if len(sys.argv) > 2 else "config.json"
            log(f"配置编辑器启动，配置文件: {config_path}")
            ui_main(config_path)
            log("配置编辑器已关闭")
        except Exception as e:
            log(f"配置编辑器运行出错: {e}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")
        finally:
            # 配置编辑器不需要单实例检查，直接退出
            sys.exit(0)
        return#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
窗口背景挂载系统 v4 - sxxzh
基于三层架构：
1. Target目标管理器 (target_manager.py)
2. 窗口检测器 (window_detector.py) 
3. 背景创建器 (bg_creator.py) - 原子程序

开发者: sxxzh
版本: 1.0.2 - 修复单实例检测问题
功能: 后台运行、自定义图标、签名版本
"""

import os
import sys
import time
import signal
import threading
import pystray
from PIL import Image, ImageDraw
from target_manager import TargetManager
from window_detector import WindowDetector

# 全局变量保存mutex引用，防止被垃圾回收
_mutex_handle = None
_lock_file = None

class SystemTrayIcon:
    """系统托盘图标管理器 - sxxzh定制版"""
    
    def __init__(self, system_instance):
        self.system = system_instance
        self.icon = None
        self.running = False
        self.hidden = False  # 托盘图标隐藏状态
        self.auto_start_enabled = False  # 开机自启状态
        
        # 初始化开机自启状态
        self._load_auto_start_status()
        
    def _load_auto_start_status(self):
        """加载开机自启状态"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                               r"Software\Microsoft\Windows\CurrentVersion\Run")
            try:
                winreg.QueryValueEx(key, "sxxzh_customiz_bg")
                self.auto_start_enabled = True
            except FileNotFoundError:
                self.auto_start_enabled = False
            winreg.CloseKey(key)
        except Exception:
            self.auto_start_enabled = False
    
    def create_icon_image(self):
        """创建托盘图标图像"""
        # 使用logo.ico文件作为托盘图标
        try:
            # 获取logo.ico文件的绝对路径
            if getattr(sys, 'frozen', False):
                # 打包后环境
                base_dir = os.path.dirname(sys.executable)
            else:
                # 开发环境
                base_dir = os.path.dirname(__file__)
            
            logo_path = os.path.join(base_dir, "logo.ico")
            
            if os.path.exists(logo_path):
                # 加载ICO文件并转换为PIL图像格式
                from PIL import Image
                icon_image = Image.open(logo_path)
                # 确保图像尺寸适合托盘图标（通常32x32或16x16）
                if icon_image.size != (32, 32):
                    icon_image = icon_image.resize((32, 32), Image.Resampling.LANCZOS)
                return icon_image
            else:
                log(f"警告：找不到logo.ico文件，路径：{logo_path}")
        except Exception as e:
            log(f"加载logo.ico失败: {e}")
        
        # 如果加载失败，回退到默认的蓝色圆形图标
        image = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        
        # 绘制一个蓝色的圆形图标
        dc.ellipse([4, 4, 28, 28], fill=(0, 120, 215, 255))  # 蓝色背景
        dc.ellipse([8, 8, 24, 24], fill=(255, 255, 255, 255))  # 白色内圆
        
        return image
    
    def on_quit(self, icon, item):
        """退出菜单项回调"""
        log("收到退出指令，正在停止系统...")
        self.system.stop()
        if self.icon:
            self.icon.stop()
        self.running = False
    
    def on_show_info(self, icon, item):
        """显示信息菜单项回调 - 使用默认文本编辑器打开日志文件"""
        # 确定日志文件路径
        if getattr(sys, 'frozen', False):
            log_dir = os.path.join(os.path.dirname(sys.executable), "logs")
        else:
            log_dir = os.path.join(os.path.dirname(__file__), "logs")
        
        log_file = os.path.join(log_dir, "sxxzh_bg_system.log")
        
        if os.path.exists(log_file):
            try:
                # 方法1: 使用Windows默认文本编辑器（记事本）
                import subprocess
                # 使用start命令，让Windows决定用什么程序打开.txt文件
                subprocess.Popen(['cmd', '/c', 'start', '', log_file], shell=True)
                log(f"已使用默认文本编辑器打开日志文件: {log_file}")
            except Exception as e1:
                try:
                    # 方法2: 如果start命令失败，尝试直接使用记事本
                    subprocess.Popen(['notepad.exe', log_file])
                    log(f"已使用记事本打开日志文件: {log_file}")
                except Exception as e2:
                    try:
                        # 方法3: 如果都失败，使用系统默认程序
                        os.startfile(log_file)
                        log(f"已使用系统默认程序打开日志文件: {log_file}")
                    except Exception as e3:
                        log(f"所有打开日志文件的方法都失败了: {e1}, {e2}, {e3}")
        else:
            log(f"日志文件不存在: {log_file}")
            # 尝试创建空的日志文件并打开
            try:
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write("窗口背景挂载系统日志文件\n")
                    f.write(f"创建时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("========================\n")
                
                # 使用默认文本编辑器打开新创建的文件
                import subprocess
                subprocess.Popen(['cmd', '/c', 'start', '', log_file], shell=True)
                log(f"已创建并使用默认文本编辑器打开新的日志文件: {log_file}")
            except Exception as e:
                log(f"创建日志文件失败: {e}")
    
    def on_toggle_auto_start(self, icon, item):
        """切换开机自启状态 - 修复版"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                               r"Software\Microsoft\Windows\CurrentVersion\Run",
                               0, winreg.KEY_SET_VALUE)
            
            if self.auto_start_enabled:
                # 禁用开机自启
                try:
                    winreg.DeleteValue(key, "sxxzh_customiz_bg")
                    self.auto_start_enabled = False
                    log("已禁用开机自启")
                except FileNotFoundError:
                    self.auto_start_enabled = False
                    log("开机自启项不存在，已更新状态")
            else:
                # 启用开机自启
                if getattr(sys, 'frozen', False):
                    # 打包后环境：使用当前可执行文件路径
                    exe_path = sys.executable
                else:
                    # 开发环境：假定打包后的路径
                    exe_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "dist", "sxxzh_customiz_bg", "sxxzh_customiz_bg.exe"))
                
                if os.path.exists(exe_path) or getattr(sys, 'frozen', False):
                    # 添加延迟启动参数，确保系统完全启动后再运行
                    # 使用 /min 参数（如果是快捷方式）或直接引号包裹路径
                    startup_cmd = f'"{exe_path}"'
                    
                    winreg.SetValueEx(key, "sxxzh_customiz_bg", 0, winreg.REG_SZ, startup_cmd)
                    self.auto_start_enabled = True
                    log(f"已启用开机自启")
                    log(f"启动命令: {startup_cmd}")
                    log(f"可执行文件路径: {exe_path}")
                else:
                    log(f"错误：找不到可执行文件: {exe_path}")
                    if not getattr(sys, 'frozen', False):
                        log("提示：请先使用PyInstaller打包程序")
            
            winreg.CloseKey(key)
            
            # 更新菜单状态
            if self.icon:
                self.icon.update_menu()
                
        except Exception as e:
            log(f"切换开机自启失败: {e}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")
    
    def on_toggle_hide(self, icon, item):
        """切换托盘图标隐藏状态"""
        if self.hidden:
            # 显示托盘图标
            if self.icon:
                self.icon.visible = True
                self.hidden = False
                log("已显示托盘图标")
        else:
            # 隐藏托盘图标
            if self.icon:
                self.icon.visible = False
                self.hidden = True
                log("已隐藏托盘图标")

    def on_edit_config(self, icon, item):
        """修改配置菜单项回调 - 启动可视化配置编辑器"""
        try:
            # 确定配置文件路径
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(__file__)
            
            config_file = os.path.join(base_dir, "config.json")
            
            log(f"启动配置编辑器: {config_file}")
            
            # 在单独的进程中启动配置编辑器，避免阻塞主程序
            import subprocess
            
            if getattr(sys, 'frozen', False):
                # 打包后环境：使用特殊参数启动配置编辑器
                exe_path = sys.executable
                # 直接使用subprocess启动配置编辑器，不进行导入检查
                # 因为打包后UI模块已经包含在可执行文件中
                try:
                    # 使用subprocess启动配置编辑器
                    subprocess.Popen([exe_path, '--config-editor', config_file])
                    log("配置编辑器已启动（打包模式）")
                except Exception as process_error:
                    log(f"启动配置编辑器进程失败: {process_error}")
                    log("降级到使用默认程序打开配置文件")
                    self._fallback_edit_config(config_file)
            else:
                # 开发环境：直接导入并运行
                try:
                    from UI import main as ui_main
                    import subprocess
                    
                    # 使用subprocess在新进程中运行UI，避免线程安全问题
                    subprocess.Popen([sys.executable, 'UI.py', config_file])
                    
                    log("配置编辑器已启动（开发模式）")
                except ImportError as import_error:
                    log(f"无法导入配置编辑器模块: {import_error}")
                    log("降级到使用默认程序打开配置文件")
                    self._fallback_edit_config(config_file)
            
        except Exception as e:
            log(f"启动配置编辑器失败: {e}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")
    
    def _fallback_edit_config(self, config_file):
        """降级方案：使用默认程序打开配置文件"""
        try:
            if os.path.exists(config_file):
                os.startfile(config_file)
                log(f"已使用默认程序打开配置文件: {config_file}")
            else:
                log(f"配置文件不存在: {config_file}")
                # 创建默认配置
                import json
                default_config = {
                    "enabled": True,
                    "scan_interval": 3,
                    "targets": [
                        {
                            "name": "记事本",
                            "process_name": "notepad.exe",
                            "window_title": "记事本",
                            "keywords": ["记事本", "notepad"],
                            "alpha": 40
                        }
                    ]
                }
                
                with open(config_file, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=2)
                
                log(f"已创建默认配置文件: {config_file}")
                os.startfile(config_file)
        except Exception as e:
            log(f"降级方案也失败了: {e}")
    
    def setup_menu(self):
        """设置托盘菜单"""
        menu_items = [
            pystray.MenuItem("显示信息", self.on_show_info),
            pystray.MenuItem("修改配置", self.on_edit_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("开机自启", self.on_toggle_auto_start, checked=lambda item: self.auto_start_enabled),
            pystray.MenuItem("隐藏托盘", self.on_toggle_hide),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self.on_quit)
        ]
        return pystray.Menu(*menu_items)
    
    def run(self):
        """运行托盘图标"""
        try:
            image = self.create_icon_image()
            menu = self.setup_menu()
            
            self.icon = pystray.Icon(
                "sxxzh_bg_system",
                image,
                "自定义背景-by sxxxzh",  # 悬停提示
                menu
            )
            
            self.running = True
            log("托盘图标即将启动...")
            self.icon.run()
            
        except Exception as e:
            log(f"托盘图标启动失败: {e}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")
            self.running = False
    
    def stop(self):
        """停止托盘图标"""
        if self.icon and self.running:
            self.icon.stop()
            self.running = False

def log(msg, module="main"):
    """日志输出 - 支持控制台和文件输出"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{module}] {timestamp} - {msg}"
    
    # 输出到控制台（开发模式）
    try:
        print(log_msg)
    except:
        pass  # 在无控制台环境下忽略print错误
    
    # 同时输出到日志文件（打包后可用）
    try:
        # 确定日志目录
        if getattr(sys, 'frozen', False):
            # 打包后环境：日志放在可执行文件同目录
            log_dir = os.path.join(os.path.dirname(sys.executable), "logs")
        else:
            # 开发环境：日志放在源代码目录
            log_dir = os.path.join(os.path.dirname(__file__), "logs")
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, "sxxzh_bg_system.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")
    except Exception as e:
        # 如果文件日志失败，尝试写入备用位置
        try:
            backup_log = os.path.join(os.path.expanduser("~"), "sxxzh_bg_system_backup.log")
            with open(backup_log, "a", encoding="utf-8") as f:
                f.write(f"[主日志失败] {log_msg}\n")
                f.write(f"[错误] {e}\n")
        except:
            pass  # 完全失败则放弃日志记录
    
    return log_msg

class BackgroundSystem:
    """背景挂载系统主控制器 - sxxzh定制版"""
    
    def __init__(self, config_path="config.json", tray_mode=False):
        # 确定配置文件路径
        if getattr(sys, 'frozen', False):
            # 打包后环境
            base_dir = os.path.dirname(sys.executable)
        else:
            # 开发环境
            base_dir = os.path.dirname(__file__)
        
        # 如果config_path是相对路径，转换为绝对路径
        if not os.path.isabs(config_path):
            config_path = os.path.join(base_dir, config_path)
        
        self.config_path = config_path
        self.target_manager = None
        self.window_detector = None
        self.should_exit = False
        self.config_reload_thread = None
        self.tray_mode = tray_mode
        self.tray_icon = None
        self.main_thread = None
    
    def initialize(self):
        """初始化系统"""
        log("正在初始化窗口背景挂载系统...")
        log(f"配置文件路径: {self.config_path}")
        log(f"工作目录: {os.getcwd()}")
        log(f"可执行文件路径: {sys.executable if getattr(sys, 'frozen', False) else '开发模式'}")
        
        try:
            # 初始化第一层：目标管理器
            self.target_manager = TargetManager(self.config_path)
            
            # 检查配置是否加载成功
            config = self.target_manager.get_config()
            if not config:
                log("配置加载失败，系统无法启动")
                return False
            
            log("目标管理器初始化成功")
            
            # 初始化第二层：窗口检测器
            self.window_detector = WindowDetector(self.target_manager)
            log("窗口检测器初始化成功")
            
            # 启动配置重载线程
            self._start_config_reload_thread()
            
            log("系统初始化完成")
            return True
            
        except Exception as e:
            log(f"系统初始化失败: {e}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")
            return False
    
    def _start_config_reload_thread(self):
        """启动配置重载线程"""
        def config_reload_worker():
            while not self.should_exit:
                try:
                    # 每5秒检查一次配置更新
                    time.sleep(5)
                    
                    if self.target_manager.is_config_updated():
                        log("检测到配置文件更新，重新加载配置...")
                        if self.target_manager.reload_config():
                            log("配置重载成功")
                        else:
                            log("配置重载失败")
                            
                except Exception as e:
                    log(f"配置重载线程出错: {e}")
        
        self.config_reload_thread = threading.Thread(
            target=config_reload_worker,
            daemon=True
        )
        self.config_reload_thread.start()
        log("配置重载线程已启动")
    
    def run(self):
        """运行系统"""
        if not self.initialize():
            log("系统初始化失败，退出")
            return
        
        if self.tray_mode:
            # 托盘模式 - 后台运行
            self._run_in_tray_mode()
        else:
            # 控制台模式 - 前台运行
            self._run_in_console_mode()
    
    def _run_in_console_mode(self):
        """控制台模式运行"""
        # 显示启动信息
        self._show_startup_info()
        
        log("系统启动成功，开始监控窗口...")
        log("按 Ctrl+C 停止系统")
        
        try:
            # 运行窗口检测器
            self.window_detector.run()
            
        except KeyboardInterrupt:
            log("收到中断信号，正在停止系统...")
        except Exception as e:
            log(f"系统运行出错: {e}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")
        finally:
            self.cleanup()
    
    def _run_in_tray_mode(self):
        """托盘模式运行"""
        log("系统启动成功，进入托盘模式...")
        
        try:
            # 创建托盘图标
            self.tray_icon = SystemTrayIcon(self)
            
            # 在后台线程中运行窗口检测器
            def window_detector_worker():
                try:
                    log("窗口检测器线程启动...")
                    self.window_detector.run()
                except Exception as e:
                    log(f"窗口检测器运行出错: {e}")
                    import traceback
                    log(f"详细错误: {traceback.format_exc()}")
            
            self.main_thread = threading.Thread(
                target=window_detector_worker,
                daemon=True
            )
            self.main_thread.start()
            
            # 给窗口检测器一点启动时间
            time.sleep(0.5)
            
            # 运行托盘图标（这会阻塞当前线程）
            log("托盘图标启动中...")
            self.tray_icon.run()
            log("托盘图标已停止")
            
        except Exception as e:
            log(f"托盘模式运行出错: {e}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")
        finally:
            self.cleanup()
    
    def _show_startup_info(self):
        """显示启动信息"""
        config = self.target_manager.get_config()
        if not config:
            return
        
        print("\n" + "="*60)
        print("窗口背景挂载系统 v4.1")
        print("="*60)
        
        enabled = config.get('enabled', True)
        scan_interval = config.get('scan_interval', 3)
        targets = config.get('targets', [])
        
        print(f"系统状态: {'已启用' if enabled else '已禁用'}")
        print(f"扫描间隔: {scan_interval} 秒")
        print(f"监控目标: {len(targets)} 个应用")
        
        if targets:
            print("\n目标应用列表:")
            for i, target in enumerate(targets, 1):
                name = target.get('name', '未知')
                keywords = target.get('keywords', [])
                alpha = target.get('alpha', 40)
                print(f"  {i}. {name} (透明度: {alpha}%)")
                print(f"     关键词: {', '.join(keywords)}")
        
        print("="*60 + "\n")
    
    def stop(self):
        """停止系统"""
        log("正在停止系统...")
        self.should_exit = True
        if self.window_detector:
            self.window_detector.stop()
    
    def cleanup(self):
        """清理资源"""
        log("正在清理系统资源...")
        
        self.should_exit = True
        
        if self.window_detector:
            self.window_detector.cleanup()
        
        # 等待配置重载线程结束
        if self.config_reload_thread and self.config_reload_thread.is_alive():
            self.config_reload_thread.join(timeout=3)
        
        # 清理单实例资源
        cleanup_single_instance()
        
        log("系统已完全停止")

def signal_handler(signum, frame):
    """信号处理函数"""
    log("收到停止信号")
    if 'system' in globals():
        globals()['system'].stop()

def check_single_instance():
    """
    检查是否已经有实例在运行
    改进版：持有mutex引用，更好的错误处理
    """
    global _mutex_handle
    
    log(f"开始单实例检查，当前进程PID: {os.getpid()}")
    
    try:
        import win32event
        import win32api
        import winerror
        
        # 创建命名的互斥体 - 使用Global前缀确保系统范围
        mutex_name = "Global\\sxxzh_customiz_bg_single_instance"
        log(f"尝试创建Mutex: {mutex_name}")
        
        try:
            # 创建互斥体并保存句柄
            _mutex_handle = win32event.CreateMutex(None, False, mutex_name)
            last_error = win32api.GetLastError()
            
            log(f"CreateMutex返回句柄: {_mutex_handle}, LastError: {last_error}")
            
            if last_error == winerror.ERROR_ALREADY_EXISTS:
                log("检测到已有实例在运行（ERROR_ALREADY_EXISTS）")
                # 清理句柄
                if _mutex_handle:
                    win32api.CloseHandle(_mutex_handle)
                    _mutex_handle = None
                return False
            
            # 检查是否成功创建
            if _mutex_handle == 0 or _mutex_handle is None:
                log("警告：Mutex创建失败，句柄无效")
                return True  # 允许继续运行
            
            log(f"单实例检查通过（Mutex），句柄: {_mutex_handle}")
            return True
            
        except Exception as create_error:
            log(f"创建Mutex时出错: {create_error}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")
            return True  # 出错时允许运行
            
    except ImportError as import_error:
        log(f"警告：无法导入win32api模块: {import_error}")
        log("提示：请安装 pywin32 包 (pip install pywin32)")
        # 降级到备用方案
        return check_single_instance_fallback()
    
    except Exception as e:
        log(f"单实例检查失败: {e}")
        import traceback
        log(f"详细错误: {traceback.format_exc()}")
        return True  # 如果检查失败，允许运行


def check_single_instance_fallback():
    """
    备用方案：使用PID文件实现单实例检测
    适用于无法使用win32api的情况
    """
    try:
        import tempfile
        
        pid_file = os.path.join(tempfile.gettempdir(), "sxxzh_customiz_bg.pid")
        log(f"使用PID文件方案: {pid_file}")
        
        # 检查PID文件是否存在
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    old_pid = int(f.read().strip())
                
                log(f"发现PID文件，旧进程PID: {old_pid}")
                
                # 尝试导入psutil检查进程
                try:
                    import psutil
                    
                    # 检查该PID的进程是否还在运行
                    if psutil.pid_exists(old_pid):
                        try:
                            proc = psutil.Process(old_pid)
                            proc_name = proc.name().lower()
                            log(f"旧进程仍在运行: {proc_name}")
                            
                            # 检查是否是同一个程序
                            if 'sxxzh_customiz_bg' in proc_name or 'python' in proc_name:
                                log("检测到已有实例在运行（PID文件+psutil）")
                                return False
                        except (psutil.NoSuchProcess, psutil.AccessDenied) as proc_error:
                            log(f"无法访问旧进程: {proc_error}")
                    else:
                        log("旧进程已不存在")
                    
                except ImportError:
                    log("警告：无法导入psutil，无法准确检测进程")
                    # 没有psutil时，假设旧进程可能还在运行
                    # 但由于无法确认，我们采取保守策略：等待一段时间
                    log("等待3秒后重试...")
                    time.sleep(3)
                    
                    # 再次检查文件是否还存在（如果旧进程已退出，文件应该被清理）
                    if os.path.exists(pid_file):
                        log("PID文件仍然存在，可能有实例在运行")
                        return False
                
                # 旧进程已不存在，删除旧PID文件
                log("清理旧PID文件")
                os.remove(pid_file)
                
            except Exception as read_error:
                log(f"读取PID文件失败: {read_error}")
                # 删除损坏的PID文件
                try:
                    os.remove(pid_file)
                    log("已删除损坏的PID文件")
                except:
                    pass
        
        # 写入当前PID
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        
        log(f"单实例检查通过（PID文件），当前PID已写入: {os.getpid()}")
        return True
        
    except Exception as e:
        log(f"PID文件检查失败: {e}")
        import traceback
        log(f"详细错误: {traceback.format_exc()}")
        return True  # 如果检查失败，允许运行


def cleanup_single_instance():
    """
    清理单实例资源
    在程序退出时调用
    """
    global _mutex_handle
    
    log("开始清理单实例资源...")
    
    # 清理Mutex句柄
    if _mutex_handle:
        try:
            import win32api
            win32api.CloseHandle(_mutex_handle)
            log(f"Mutex句柄已释放: {_mutex_handle}")
            _mutex_handle = None
        except Exception as e:
            log(f"释放Mutex句柄失败: {e}")
    
    # 清理PID文件
    try:
        import tempfile
        pid_file = os.path.join(tempfile.gettempdir(), "sxxzh_customiz_bg.pid")
        
        if os.path.exists(pid_file):
            # 验证PID文件中的PID是否是当前进程
            try:
                with open(pid_file, 'r') as f:
                    file_pid = int(f.read().strip())
                
                if file_pid == os.getpid():
                    os.remove(pid_file)
                    log(f"PID文件已清理: {pid_file}")
                else:
                    log(f"PID文件不属于当前进程（文件PID: {file_pid}, 当前PID: {os.getpid()}）")
            except Exception as verify_error:
                log(f"验证PID文件失败: {verify_error}")
                # 即使验证失败也尝试删除
                try:
                    os.remove(pid_file)
                    log("已强制删除PID文件")
                except:
                    pass
                    
    except Exception as e:
        log(f"清理PID文件失败: {e}")
    
    log("单实例资源清理完成")


def main():
    """主函数 - sxxzh定制版 v1.0.2"""
    # 记录启动信息
    log("="*60)
    log("窗口背景挂载系统启动")
    log(f"Python版本: {sys.version}")
    log(f"运行模式: {'打包模式' if getattr(sys, 'frozen', False) else '开发模式'}")
    log(f"命令行参数: {sys.argv}")
    log("="*60)
    
    # 检查是否是配置编辑器模式 - 配置编辑器模式应该绕过单例检测
    if len(sys.argv) > 1 and sys.argv[1] == '--config-editor':
        # 配置编辑器模式 - 直接运行UI.py的配置编辑器
        log("进入配置编辑器模式")
        config_file = sys.argv[2] if len(sys.argv) > 2 else "config.json"
        
        try:
            # 尝试导入并运行配置编辑器
            import UI
            UI.main(config_file)
            log("配置编辑器已正常退出")
        except Exception as e:
            log(f"配置编辑器启动失败: {e}")
            import traceback
            log(f"详细错误: {traceback.format_exc()}")
            # 降级到使用默认程序打开配置文件
            try:
                if os.path.exists(config_file):
                    os.startfile(config_file)
                    log(f"已使用默认程序打开配置文件: {config_file}")
            except Exception as fallback_error:
                log(f"降级方案也失败: {fallback_error}")
        
        sys.exit(0)
    
    # 检查是否是背景创建器模式 - 背景创建器模式也应该绕过单例检测
    if len(sys.argv) > 1 and sys.argv[1] == '--bg-creator':
        # 背景创建器模式 - 直接运行bg_creator
        log("进入背景创建器模式")
        if len(sys.argv) >= 4:
            from bg_creator import main as bg_creator_main
            # 修改sys.argv以匹配bg_creator的期望格式
            sys.argv = [sys.argv[0], sys.argv[2], sys.argv[3]]
            bg_creator_main()
        else:
            log("错误：背景创建器模式需要目标窗口句柄和配置文件参数")
            sys.exit(1)
        return
    
    # 单实例检查 - 只在正常模式下进行
    if not check_single_instance():
        log("程序已退出，确保只有一个实例在运行")
        log("如果您确定没有其他实例在运行，请检查临时目录中的PID文件")
        sys.exit(0)
    
    # 正常模式 - 运行完整的窗口背景系统
    try:
        # 注册信号处理
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 等待系统启动完成（特别是开机自启时）
        # 给系统一些时间来完成启动过程
        if getattr(sys, 'frozen', False):
            log("等待系统环境就绪...")
            time.sleep(2)  # 延迟2秒
        
        # 创建系统实例（启用托盘模式）
        system = BackgroundSystem(tray_mode=True)
        
        # 保存到全局变量以便信号处理
        globals()['system'] = system
        
        # 运行系统（托盘模式）
        log("准备运行系统主循环...")
        system.run()
        
    except Exception as e:
        log(f"主函数发生严重错误: {e}")
        import traceback
        log(f"详细错误: {traceback.format_exc()}")
        
        # 确保错误被记录
        try:
            error_file = os.path.join(os.path.expanduser("~"), "sxxzh_bg_critical_error.log")
            with open(error_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"错误: {e}\n")
                f.write(f"堆栈:\n{traceback.format_exc()}\n")
        except:
            pass
    
    finally:
        # 确保清理资源
        cleanup_single_instance()


def main_no_console():
    """无控制台版本的主函数 - sxxzh定制版 v1.0.2"""
    # 重定向标准输出和错误输出到日志文件
    try:
        if getattr(sys, 'frozen', False):
            log_dir = os.path.join(os.path.dirname(sys.executable), "logs")
        else:
            log_dir = os.path.join(os.path.dirname(__file__), "logs")
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 重定向stdout和stderr
        sys.stdout = open(os.path.join(log_dir, "stdout.log"), "a", encoding="utf-8")
        sys.stderr = open(os.path.join(log_dir, "stderr.log"), "a", encoding="utf-8")
    except:
        pass
    
    # 调用主函数
    main()


if __name__ == "__main__":
    main()