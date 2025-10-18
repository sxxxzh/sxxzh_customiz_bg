#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
窗口背景挂载系统 v4 - sxxzh
基于三层架构：
1. Target目标管理器 (target_manager.py)
2. 窗口检测器 (window_detector.py) 
3. 背景创建器 (bg_creator.py) - 原子程序

开发者: sxxzh
版本: 1.0.0
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
            logo_path = os.path.join(os.path.dirname(__file__), "logo.ico")
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
        """显示信息菜单项回调 - 显示详细系统信息"""
        import datetime
        
        # 获取配置信息
        config = self.system.target_manager.get_config()
        
        # 构建详细信息
        info_lines = []
        info_lines.append("=== 窗口背景挂载系统信息 ===")
        info_lines.append(f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if config:
            enabled = config.get('enabled', True)
            scan_interval = config.get('scan_interval', 3)
            targets = config.get('targets', [])
            
            info_lines.append(f"系统状态: {'已启用' if enabled else '已禁用'}")
            info_lines.append(f"扫描间隔: {scan_interval} 秒")
            info_lines.append(f"监控目标: {len(targets)} 个应用")
            
            if targets:
                info_lines.append("目标应用列表:")
                for i, target in enumerate(targets, 1):
                    name = target.get('name', '未知')
                    process_name = target.get('process_name', '')
                    window_title = target.get('window_title', '')
                    info_lines.append(f"  {i}. {name}")
                    if process_name:
                        info_lines.append(f"     进程: {process_name}")
                    if window_title:
                        info_lines.append(f"     窗口: {window_title}")
        else:
            info_lines.append("配置信息: 不可用")
        
        # 日志文件信息
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        log_file = os.path.join(log_dir, "sxxzh_bg_system.log")
        
        if os.path.exists(log_file):
            file_size = os.path.getsize(log_file)
            info_lines.append(f"日志文件: {log_file}")
            info_lines.append(f"日志大小: {file_size} 字节")
            
            # 显示最近几行日志
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        info_lines.append("最近日志:")
                        # 显示最后5行日志
                        for line in lines[-5:]:
                            info_lines.append(f"  {line.strip()}")
            except Exception as e:
                info_lines.append(f"读取日志失败: {e}")
        else:
            info_lines.append("日志文件: 不存在")
        
        info_lines.append("========================")
        
        # 输出到日志
        for line in info_lines:
            log(line, "info")
        
        # 使用更简单的方式显示信息 - 通过系统默认文本编辑器
        try:
            # 创建临时信息文件
            import tempfile
            import uuid
            
            info_file = os.path.join(tempfile.gettempdir(), f"window_bg_info_{uuid.uuid4().hex}.txt")
            with open(info_file, "w", encoding="utf-8") as f:
                f.write("\n".join(info_lines))
            
            # 使用系统默认程序打开文本文件
            os.startfile(info_file)
            
            # 记录操作
            log(f"系统信息已保存到临时文件: {info_file}")
            
        except Exception as e:
            # 如果文件方式不可用，只输出到日志
            log(f"显示系统信息失败: {e}")
    
    def on_toggle_auto_start(self, icon, item):
        """切换开机自启状态"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                               r"Software\Microsoft\Windows\CurrentVersion\Run",
                               0, winreg.KEY_SET_VALUE)
            
            if self.auto_start_enabled:
                # 禁用开机自启
                winreg.DeleteValue(key, "sxxzh_customiz_bg")
                self.auto_start_enabled = False
                log("已禁用开机自启")
            else:
                # 启用开机自启 - 智能检测打包环境
                if getattr(sys, 'frozen', False):
                    # 打包后环境：使用当前可执行文件路径
                    exe_path = sys.executable
                else:
                    # 开发环境：使用打包后的可执行文件路径
                    exe_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "dist", "sxxzh_customiz_bg", "sxxzh_customiz_bg.exe"))
                
                if os.path.exists(exe_path):
                    winreg.SetValueEx(key, "sxxzh_customiz_bg", 0, winreg.REG_SZ, f'"{exe_path}"')
                    self.auto_start_enabled = True
                    log(f"已启用开机自启，路径: {exe_path}")
                else:
                    if getattr(sys, 'frozen', False):
                        log("错误：打包后程序路径异常，无法设置开机自启")
                    else:
                        log("错误：找不到可执行文件，请先打包程序")
            
            winreg.CloseKey(key)
            
            # 更新菜单状态
            if self.icon:
                self.icon.update_menu()
                
        except Exception as e:
            log(f"切换开机自启失败: {e}")
    
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
        """修改配置菜单项回调 - 使用默认程序打开配置文件"""
        try:
            # 优先使用与可执行文件同一目录下的配置文件
            if getattr(sys, 'frozen', False):
                # 打包后环境：使用可执行文件所在目录
                base_dir = os.path.dirname(sys.executable)
            else:
                # 开发环境：使用源代码目录
                base_dir = os.path.dirname(__file__)
            
            config_file = os.path.join(base_dir, "config.json")
            
            if os.path.exists(config_file):
                # 使用系统默认程序打开JSON文件
                os.startfile(config_file)
                log(f"已打开配置文件: {config_file}")
                
                # 显示提示信息
                log("配置文件已打开，修改后可能不能即使重载成功,请保存并重启程序生效")
                
            else:
                log(f"配置文件不存在: {config_file}")
                
                # 尝试创建默认配置文件
                try:
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
                    log("默认配置文件已创建并打开，请根据需要进行修改")
                    
                except Exception as create_error:
                    log(f"创建默认配置文件失败: {create_error}")
                    
        except Exception as e:
            log(f"打开配置文件失败: {e}")
    
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
            self.icon.run()
            
        except Exception as e:
            log(f"托盘图标启动失败: {e}")
            self.running = False
    
    def stop(self):
        """停止托盘图标"""
        if self.icon and self.running:
            self.icon.stop()
            self.running = False

def log(msg, module="main"):
    """日志输出 - 支持控制台和文件输出"""
    timestamp = time.strftime('%H:%M:%S')
    log_msg = f"[{module}] {timestamp} - {msg}"
    
    # 输出到控制台（开发模式）
    print(log_msg)
    
    # 同时输出到日志文件（打包后可用）
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, "sxxzh_bg_system.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")
    except Exception as e:
        # 如果文件日志失败，只输出到控制台
        print(f"[log] 文件日志写入失败: {e}")
    
    return log_msg

class BackgroundSystem:
    """背景挂载系统主控制器 - sxxzh定制版"""
    
    def __init__(self, config_path="config.json", tray_mode=False):
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
                    self.window_detector.run()
                except Exception as e:
                    log(f"窗口检测器运行出错: {e}")
                    # 记录错误到文件
                    with open("sxxzh_bg_error.log", "a", encoding="utf-8") as f:
                        f.write(f"窗口检测器错误: {e}\n")
            
            self.main_thread = threading.Thread(
                target=window_detector_worker,
                daemon=True
            )
            self.main_thread.start()
            
            # 运行托盘图标（这会阻塞当前线程）
            log("托盘图标启动中...")
            self.tray_icon.run()
            log("托盘图标已停止")
            
        except Exception as e:
            log(f"托盘模式运行出错: {e}")
            # 记录错误到文件
            with open("sxxzh_bg_error.log", "a", encoding="utf-8") as f:
                f.write(f"托盘模式错误: {e}\n")
        finally:
            self.cleanup()
    
    def _show_startup_info(self):
        """显示启动信息"""
        config = self.target_manager.get_config()
        if not config:
            return
        
        print("\n" + "="*60)
        print("窗口背景挂载系统 v4")
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
        
        log("系统已完全停止")

def signal_handler(signum, frame):
    """信号处理函数"""
    log("收到停止信号")
    if 'system' in globals():
        globals()['system'].stop()

def main():
    """主函数 - sxxzh定制版"""
    # 检查是否是背景创建器模式
    if len(sys.argv) > 1 and sys.argv[1] == '--bg-creator':
        # 背景创建器模式 - 直接运行bg_creator
        if len(sys.argv) >= 4:
            from bg_creator import main as bg_creator_main
            # 修改sys.argv以匹配bg_creator的期望格式
            sys.argv = [sys.argv[0], sys.argv[2], sys.argv[3]]
            bg_creator_main()
        else:
            print("错误：背景创建器模式需要目标窗口句柄和配置文件参数")
            sys.exit(1)
        return
    
    # 正常模式 - 运行完整的窗口背景系统
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 创建系统实例（启用托盘模式）
    system = BackgroundSystem(tray_mode=True)
    
    # 保存到全局变量以便信号处理
    globals()['system'] = system
    
    # 运行系统（托盘模式）
    system.run()

def main_no_console():
    """无控制台版本的主函数 - sxxzh定制版"""
    # 检查是否是背景创建器模式
    if len(sys.argv) > 1 and sys.argv[1] == '--bg-creator':
        # 背景创建器模式 - 直接运行bg_creator
        if len(sys.argv) >= 4:
            from bg_creator import main as bg_creator_main
            # 修改sys.argv以匹配bg_creator的期望格式
            sys.argv = [sys.argv[0], sys.argv[2], sys.argv[3]]
            bg_creator_main()
        else:
            # 在无控制台模式下，使用文件日志记录错误
            with open("sxxzh_bg_error.log", "a", encoding="utf-8") as f:
                f.write("错误：背景创建器模式需要目标窗口句柄和配置文件参数\n")
            sys.exit(1)
        return
    
    # 正常模式 - 运行完整的窗口背景系统（托盘模式）
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 创建系统实例（启用托盘模式）
    system = BackgroundSystem(tray_mode=True)
    
    # 保存到全局变量以便信号处理
    globals()['system'] = system
    
    # 运行系统（托盘模式）
    system.run()

if __name__ == "__main__":
    main()