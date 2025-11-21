#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
背景创建器 - 原子程序 (sxxzh定制版)
负责为指定窗口创建半透明背景

开发者: sxxzh
版本: 1.0.0
"""

import os
import sys
import ctypes
import win32gui
import win32con
import win32api
import win32process
from PIL import Image, ImageEnhance
import time
import json
import threading
import hashlib
import pythoncom
from window_size_cache import get_size_cache
from logger import log as _log

def log(msg):
    """统一的日志输出到集中日志文件"""
    try:
        _log(msg, module="bg-creator", to_console=False)
    except Exception:
        pass

class BackgroundCreator:
    """背景创建器类 - 基于v3版本实现"""
    
    # 窗口样式常量
    WS_EX_LAYERED = 0x80000
    WS_EX_TRANSPARENT = 0x20
    ULW_ALPHA = 0x2
    AC_SRC_OVER = 0x0
    AC_SRC_ALPHA = 0x1
    
    # ctypes结构体定义
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    
    class SIZE(ctypes.Structure):
        _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]
    
    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [
            ("BlendOp", ctypes.c_byte),
            ("BlendFlags", ctypes.c_byte),
            ("SourceConstantAlpha", ctypes.c_byte),
            ("AlphaFormat", ctypes.c_byte)
        ]
    
    def __init__(self, target_hwnd, config):
        """
        初始化背景创建器
        
        Args:
            target_hwnd: 目标窗口句柄
            config: 配置参数
        """
        self.target_hwnd = target_hwnd
        self.config = config
        self.bg_hwnd = None
        self.should_exit = False
        self.use_window_rect = False
        self.current_size = (0, 0)
        self.size_cache = get_size_cache()  # 窗口尺寸缓存
        # 图片渲染缓存（按尺寸与参数）
        self._render_cache = {}
        self._render_cache_capacity = 8
        self._render_cache_hits = 0
        self._render_cache_misses = 0
        # 持久化渲染缓存目录
        self._render_cache_dir = None
        try:
            base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            self._render_cache_dir = os.path.join(base_path, 'render_cache')
            os.makedirs(self._render_cache_dir, exist_ok=True)
        except Exception:
            pass
        
        # 从配置中获取参数
        self.image_path = config.get('image_path', 'background.png')
        self.alpha = config.get('alpha', 40)
        self.brightness = config.get('brightness', 1.0)
        self.contrast = config.get('contrast', 1.0)
        self.saturation = config.get('saturation', 1.0)
        
        # 获取目标窗口名称
        self.target_name = win32gui.GetWindowText(target_hwnd) or f"窗口_{target_hwnd}"
        
        log(f"背景创建器初始化 - 目标窗口: {target_hwnd} ({self.target_name}), 透明度: {self.alpha}")
    
    def create_background_window(self):
        """创建背景窗口 - 基于v3版本实现"""
        try:
            # 创建窗口类
            wc = win32gui.WNDCLASS()
            self.hinst = wc.hInstance = win32api.GetModuleHandle(None)
            wc.lpszClassName = f"WindowBgLayer_{id(self)}"
            wc.lpfnWndProc = win32gui.DefWindowProc
            
            try:
                win32gui.RegisterClass(wc)
            except:
                pass
            
            # 优先获取实际尺寸；仅在失败时回退缓存尺寸
            w, h = 0, 0
            try:
                left, top, right, bottom = win32gui.GetClientRect(self.target_hwnd)
                w, h = right - left, bottom - top
                log(f"  获取实际窗口尺寸: {w}x{h}")
            except:
                pass
            if w <= 0 or h <= 0:
                predicted_size = self.size_cache.get_predicted_size(self.target_hwnd)
                if predicted_size:
                    w, h, confidence = predicted_size
                    log(f"  回退使用缓存尺寸: {w}x{h} (置信度: {confidence:.2f})")
                else:
                    log(f"  无法获取 {self.target_name} 窗口客户区")
                    return False
            
            # 诊断信息
            log(f"  窗口信息: 客户区 {w}x{h}, 类名 {win32gui.GetClassName(self.target_hwnd)}")
            
            # 检测是否为 Electron/Chromium 应用
            cls_name = win32gui.GetClassName(self.target_hwnd).lower()
            if 'chrome' in cls_name or 'electron' in cls_name:
                log(f"  ⚠️  检测到 Chromium/Electron 应用，背景可能不可见")
            
            # 如果客户区为0，尝试使用窗口矩形
            if w <= 0 or h <= 0:
                log(f"  客户区无效，尝试使用窗口矩形...")
                try:
                    rect = win32gui.GetWindowRect(self.target_hwnd)
                    w, h = rect[2] - rect[0], rect[3] - rect[1]
                    log(f"  窗口矩形大小: {w}x{h}")
                    self.use_window_rect = True
                except:
                    log(f"  无法获取窗口矩形")
                    return False
            else:
                self.use_window_rect = False
            
            # 如果客户区太小（< 200x200），尝试查找子窗口
            if w < 200 or h < 200:
                log(f"  客户区较小，尝试查找内容子窗口...")
                actual_parent = self._find_actual_content_window()
                if actual_parent and actual_parent != self.target_hwnd:
                    self.target_hwnd = actual_parent
                    try:
                        left, top, right, bottom = win32gui.GetClientRect(self.target_hwnd)
                        w, h = right - left, bottom - top
                        log(f"  使用子窗口大小: {w}x{h}")
                        self.use_window_rect = False
                    except:
                        pass
            
            # 最终检查
            if w <= 0 or h <= 0:
                log(f"  ❌ 无法获取有效的窗口大小")
                return False
            
            # 创建窗口风格
            if self.use_window_rect:
                window_style = win32con.WS_POPUP
                try:
                    rect = win32gui.GetWindowRect(self.target_hwnd)
                    x, y = rect[0], rect[1]
                except:
                    x, y = 0, 0
                parent = None
            else:
                window_style = win32con.WS_CHILD
                x, y = 0, 0
                parent = self.target_hwnd
            
            self.bg_hwnd = win32gui.CreateWindowEx(
                self.WS_EX_LAYERED | self.WS_EX_TRANSPARENT,
                wc.lpszClassName,
                "",
                window_style | win32con.WS_VISIBLE,
                x, y, w, h,
                parent, 0, self.hinst, None
            )
            
            if not self.bg_hwnd:
                log(f"  ❌ 创建背景窗口失败")
                return False
            
            win32gui.SetWindowPos(
                self.bg_hwnd, win32con.HWND_BOTTOM,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
            )
            
            win32gui.ShowWindow(self.bg_hwnd, win32con.SW_SHOW)
            self.current_size = (w, h)
            log(f"  ✓ 背景窗口已创建 (hwnd: {self.bg_hwnd})")
            return True
            
        except Exception as e:
            log(f"创建背景窗口时出错: {e}")
            return False
    
    def _find_actual_content_window(self):
        """尝试找到实际的内容编辑区域窗口"""
        content_windows = []
        
        def enum_child(hwnd, param):
            try:
                cls_name = win32gui.GetClassName(hwnd).lower()
                content_keywords = [
                    'scintilla', 'edit', 'richedit', 'view', 
                    'content', 'editor', 'text', 'document',
                    'qt5', 'qwidget'
                ]
                if any(k in cls_name for k in content_keywords):
                    if win32gui.IsWindowVisible(hwnd):
                        rect = win32gui.GetClientRect(hwnd)
                        w, h = rect[2] - rect[0], rect[3] - rect[1]
                        if w > 100 and h > 100:
                            content_windows.append((hwnd, w * h, cls_name))
            except:
                pass
        
        try:
            win32gui.EnumChildWindows(self.target_hwnd, enum_child, None)
            if content_windows:
                content_windows.sort(key=lambda x: x[1], reverse=True)
                log(f"    找到 {len(content_windows)} 个子窗口，选择: {content_windows[0][2]}")
                return content_windows[0][0]
        except:
            pass
        
        return None
    
    def set_image(self):
        """设置背景图片及参数"""
        # 固定图片路径为相对于可执行文件的相对路径
        image_path = None
        
        # 首先检查是否是绝对路径
        if os.path.isabs(self.image_path):
            image_path = self.image_path
        else:
            # 相对路径，优先使用可执行文件所在目录
            if getattr(sys, 'frozen', False):
                # 打包后环境：相对于可执行文件目录
                base_path = os.path.dirname(sys.executable)
                image_path = os.path.join(base_path, self.image_path)
            else:
                # 开发环境：相对于脚本文件目录
                base_path = os.path.dirname(os.path.abspath(__file__))
                image_path = os.path.join(base_path, self.image_path)
            
            log(f"  图片路径: {image_path}")
        
        if not image_path or not os.path.exists(image_path):
            log(f"  ⚠️  图片不存在，尝试的路径:")
            if os.path.isabs(self.image_path):
                log(f"    绝对路径: {self.image_path}")
            else:
                possible_paths = [
                    os.path.join(os.getcwd(), self.image_path),
                    os.path.join(os.path.dirname(sys.executable), self.image_path) if getattr(sys, 'frozen', False) else None,
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), self.image_path)
                ]
                for path in possible_paths:
                    if path:
                        log(f"    尝试路径: {path}")
            return False
        
        try:
            self.img = Image.open(image_path).convert("RGBA")
            self._image_resolved_path = image_path
            log(f"  ✓ 图片加载成功: {image_path} (alpha: {self.alpha})")
            # 预热预测尺寸的磁盘缓存（提高窗口重开命中率）
            try:
                predicted = self.size_cache.get_predicted_size(self.target_hwnd)
                if predicted:
                    pw, ph, conf = predicted
                    if pw > 0 and ph > 0 and getattr(self, '_render_cache_dir', None):
                        base_id = self._image_resolved_path or self.image_path
                        key_str = f"{base_id}|{int(pw)}|{int(ph)}|{int(self.alpha)}|{round(float(self.brightness),4)}|{round(float(self.contrast),4)}|{round(float(self.saturation),4)}"
                        file_id = hashlib.sha1(key_str.encode('utf-8')).hexdigest()
                        fp = os.path.join(self._render_cache_dir, f"{file_id}.bin")
                        if not os.path.exists(fp):
                            try:
                                img_preheat = self.img.resize((pw, ph), Image.LANCZOS)
                                if self.brightness != 1.0:
                                    img_preheat = ImageEnhance.Brightness(img_preheat).enhance(self.brightness)
                                if self.contrast != 1.0:
                                    img_preheat = ImageEnhance.Contrast(img_preheat).enhance(self.contrast)
                                if self.saturation != 1.0:
                                    img_preheat = ImageEnhance.Color(img_preheat).enhance(self.saturation)
                                r, g, b, _ = img_preheat.split()
                                a = Image.new("L", img_preheat.size, self.alpha)
                                img_preheat = Image.merge("RGBA", (b, g, r, a))
                                raw_data_preheat = img_preheat.tobytes()
                                with open(fp, 'wb') as f:
                                    f.write(raw_data_preheat)
                                log(f"  ↯ 预热磁盘缓存 predicted={pw}x{ph} file={file_id}.bin")
                            except Exception as e2:
                                log(f"  ⚠️ 预热磁盘缓存失败: {e2}")
                        else:
                            log(f"  ✓ 预测尺寸磁盘缓存已存在 predicted={pw}x{ph}")
            except Exception as e:
                log(f"  ⚠️ 预热磁盘缓存失败: {e}")
            return True
        except Exception as e:
            log(f"  ❌ 加载图片失败: {e}")
            return False
    
    def update(self):
        """更新背景窗口 - 简化版本，只负责初始更新"""
        if not self.bg_hwnd or not self.img:
            return False
        
        try:
            # 确保背景窗口可见
            win32gui.ShowWindow(self.bg_hwnd, win32con.SW_SHOW)
            
            # 获取窗口大小
            try:
                if self.use_window_rect:
                    rect = win32gui.GetWindowRect(self.target_hwnd)
                    w, h = rect[2] - rect[0], rect[3] - rect[1]
                    x, y = rect[0], rect[1]
                else:
                    left, top, right, bottom = win32gui.GetClientRect(self.target_hwnd)
                    w, h = right - left, bottom - top
                    x, y = 0, 0
                
                # 检查窗口大小是否有效
                if w <= 0 or h <= 0:
                    return False
                
                # 更新窗口位置和大小
                win32gui.MoveWindow(self.bg_hwnd, x, y, w, h, True)
                
                # 检查尺寸是否发生变化，如果是则记录到缓存
                if self.current_size != (w, h):
                    self.size_cache.record_window_size(self.target_hwnd, w, h)
                    if self.current_size != (0, 0):  # 不是初始化
                        log(f"  窗口尺寸变化: {self.current_size[0]}x{self.current_size[1]} -> {w}x{h}")
                
                self.current_size = (w, h)
                
                # 更新分层窗口
                self._update_layered_window(w, h)
                
                # 确保背景窗口在底部
                win32gui.SetWindowPos(
                    self.bg_hwnd, win32con.HWND_BOTTOM,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                    win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
                )
                
                return True
                
            except Exception as size_error:
                if "height and width must be > 0" not in str(size_error):
                    log(f"获取窗口大小时出错: {size_error}")
                return False
            
        except Exception as e:
            log(f"更新背景窗口时出错: {e}")
            return False
    
    def _update_layered_window(self, w, h):
        """使用分层窗口API更新背景"""
        # 渲染缓存命中检测与记录
        key = (
            int(w),
            int(h),
            int(self.alpha),
            round(float(self.brightness), 4),
            round(float(self.contrast), 4),
            round(float(self.saturation), 4),
        )
        if hasattr(self, "_render_cache") and key in self._render_cache:
            raw_data = self._render_cache[key]
            self._render_cache_hits += 1
            log(f"  ✓ 命中缓存图片 key={key} (缓存大小={len(self._render_cache)})")
        else:
            # 先尝试磁盘持久化缓存
            raw_data = None
            file_path = None
            try:
                if getattr(self, '_render_cache_dir', None):
                    base_id = getattr(self, '_image_resolved_path', None) or self.image_path
                    key_str = f"{base_id}|{int(w)}|{int(h)}|{int(self.alpha)}|{round(float(self.brightness),4)}|{round(float(self.contrast),4)}|{round(float(self.saturation),4)}"
                    file_id = hashlib.sha1(key_str.encode('utf-8')).hexdigest()
                    file_path = os.path.join(self._render_cache_dir, f"{file_id}.bin")
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            raw_data = f.read()
                        self._render_cache[key] = raw_data
                        self._render_cache_hits += 1
                        log(f"  ✓ 命中磁盘缓存 key={key} file={file_id}.bin (缓存大小={len(self._render_cache)})")
            except Exception as e:
                log(f"  ⚠️ 读磁盘缓存失败: {e}")

            if raw_data is None:
                # 调整尺寸与参数
                img = self.img.resize((w, h), Image.LANCZOS)
                if self.brightness != 1.0:
                    img = ImageEnhance.Brightness(img).enhance(self.brightness)
                if self.contrast != 1.0:
                    img = ImageEnhance.Contrast(img).enhance(self.contrast)
                if self.saturation != 1.0:
                    img = ImageEnhance.Color(img).enhance(self.saturation)
                r, g, b, _ = img.split()
                a = Image.new("L", img.size, self.alpha)
                img_pre = Image.merge("RGBA", (b, g, r, a))
                raw_data = img_pre.tobytes()

                # 写入缓存（简单容量控制）
                try:
                    if not hasattr(self, "_render_cache"):
                        self._render_cache = {}
                        self._render_cache_capacity = 8
                    if len(self._render_cache) >= getattr(self, "_render_cache_capacity", 8):
                        try:
                            self._render_cache.pop(next(iter(self._render_cache)))
                        except Exception:
                            self._render_cache.clear()
                    self._render_cache[key] = raw_data
                except Exception:
                    pass

                # 写入磁盘缓存
                try:
                    if file_path is None and getattr(self, '_render_cache_dir', None):
                        base_id = getattr(self, '_image_resolved_path', None) or self.image_path
                        key_str = f"{base_id}|{int(w)}|{int(h)}|{int(self.alpha)}|{round(float(self.brightness),4)}|{round(float(self.contrast),4)}|{round(float(self.saturation),4)}"
                        file_id = hashlib.sha1(key_str.encode('utf-8')).hexdigest()
                        file_path = os.path.join(self._render_cache_dir, f"{file_id}.bin")
                    if file_path:
                        with open(file_path, 'wb') as f:
                            f.write(raw_data)
                        log(f"  ↯ 写入磁盘缓存 file={os.path.basename(file_path)} size={len(raw_data)}")
                except Exception as e:
                    log(f"  ⚠️ 写入磁盘缓存失败: {e}")

                self._render_cache_misses += 1
                log(f"  ⟳ 未命中缓存，重新渲染图片 key={key}")
        
        hdc = win32gui.GetDC(0)
        hdc_mem = win32gui.CreateCompatibleDC(hdc)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", ctypes.c_ushort),
                ("biBitCount", ctypes.c_ushort),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = win32con.BI_RGB
        ptr = ctypes.c_void_p()
        gdi32 = ctypes.windll.gdi32
        hbitmap = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi),
                                        win32con.DIB_RGB_COLORS, ctypes.byref(ptr), None, 0)
        ctypes.memmove(ptr, raw_data, len(raw_data))
        win32gui.SelectObject(hdc_mem, hbitmap)
        
        blend = self.BLENDFUNCTION()
        blend.BlendOp = self.AC_SRC_OVER
        blend.BlendFlags = 0
        blend.SourceConstantAlpha = self.alpha
        blend.AlphaFormat = 0
        
        ctypes.windll.user32.UpdateLayeredWindow(
            self.bg_hwnd, hdc, None,
            ctypes.byref(self.SIZE(w, h)),
            hdc_mem,
            ctypes.byref(self.POINT(0, 0)),
            0, ctypes.byref(blend), self.ULW_ALPHA
        )
        
        gdi32.DeleteObject(hbitmap)
        win32gui.DeleteDC(hdc_mem)
        win32gui.ReleaseDC(0, hdc)
    

    
    def run(self):
        """运行背景创建器主循环 - 使用v2版本的消息泵机制"""
        log("开始运行背景创建器")
        
        # 创建背景窗口
        if not self.create_background_window():
            log("背景窗口创建失败")
            return False
        
        # 设置背景图片
        if not self.set_image():
            log("背景图片设置失败")
            return False
        
        # 初始更新一次
        self.update()
        
        # 初始化变量
        self.should_exit = False
        
        try:
            # 启动轮询线程（类似于v2版本的实现）
            poll_thread = threading.Thread(target=self.poll_thread)
            poll_thread.daemon = True
            poll_thread.start()
            
            log("轮询线程已启动，开始消息循环")
            
            # 使用v2版本的消息泵机制
            while not self.should_exit:
                try:
                    # 处理Windows消息队列（关键改进）
                    pythoncom.PumpWaitingMessages()
                    
                    # 短暂等待，避免CPU占用过高
                    time.sleep(0.01)
                    
                except KeyboardInterrupt:
                    log("用户中断，退出")
                    self.should_exit = True
                    break
                except Exception as e:
                    log(f"消息循环错误: {e}")
                    # 继续运行，不退出
                    time.sleep(0.1)
                
        except KeyboardInterrupt:
            log("用户中断，退出")
        except Exception as e:
            log(f"运行错误: {e}")
        finally:
            self.should_exit = True
            # 等待轮询线程结束
            time.sleep(0.1)
            self.cleanup()
        
        return True

    def poll_thread(self):
        """轮询线程 - 监控窗口状态并更新背景"""
        while not self.should_exit:
            # 检查目标窗口是否还存在
            if not win32gui.IsWindow(self.target_hwnd):
                log("目标窗口已关闭，退出")
                self.should_exit = True
                break
            
            # 检查背景窗口是否还存在
            if not win32gui.IsWindow(self.bg_hwnd):
                log("背景窗口已关闭，退出")
                self.should_exit = True
                break
            
            # 基于v3版本的更新逻辑：只在需要时更新
            try:
                # 检查目标窗口是否可见
                if not win32gui.IsWindowVisible(self.target_hwnd):
                    # 目标窗口不可见，隐藏背景窗口
                    if win32gui.IsWindowVisible(self.bg_hwnd):
                        win32gui.ShowWindow(self.bg_hwnd, win32con.SW_HIDE)
                else:
                    # 目标窗口可见，确保背景窗口可见
                    if not win32gui.IsWindowVisible(self.bg_hwnd):
                        win32gui.ShowWindow(self.bg_hwnd, win32con.SW_SHOW)
                    
                    # 检查窗口大小是否变化
                    try:
                        if self.use_window_rect:
                            rect = win32gui.GetWindowRect(self.target_hwnd)
                            w, h = rect[2] - rect[0], rect[3] - rect[1]
                        else:
                            left, top, right, bottom = win32gui.GetClientRect(self.target_hwnd)
                            w, h = right - left, bottom - top
                        
                        # 只有当大小发生变化时才更新
                        if (w, h) != self.current_size and w > 0 and h > 0:
                            self.current_size = (w, h)
                            self._update_layered_window(w, h)
                    except:
                        pass
            except:
                pass
            
            # 使用v2版本的等待时间：0.05秒
            time.sleep(0.05)

    def cleanup(self):
        """清理资源"""
        log("开始清理资源...")
        
        # 确保轮询线程已经停止
        self.should_exit = True
        time.sleep(0.1)  # 给轮询线程一点时间退出
        
        # 清理背景窗口
        if self.bg_hwnd:
            try:
                if win32gui.IsWindow(self.bg_hwnd):
                    log("正在销毁背景窗口...")
                    # 先隐藏窗口
                    win32gui.ShowWindow(self.bg_hwnd, win32con.SW_HIDE)
                    # 然后销毁窗口
                    win32gui.DestroyWindow(self.bg_hwnd)
                    log("背景窗口已销毁")
            except Exception as e:
                log(f"销毁窗口时出错: {e}")
            finally:
                self.bg_hwnd = None
        
        # 输出渲染缓存统计
        try:
            hits = getattr(self, '_render_cache_hits', 0)
            misses = getattr(self, '_render_cache_misses', 0)
            total = hits + misses
            cache_size = len(getattr(self, '_render_cache', {}))
            log(f"渲染缓存统计: 命中={hits} 未命中={misses} 总={total} 当前缓存条目={cache_size}")
        except Exception as e:
            log(f"统计渲染缓存时出错: {e}")
        
        log("资源清理完成")

def main():
    """背景创建器主函数"""
    if len(sys.argv) < 3:
        print("用法: python bg_creator.py <目标窗口句柄> <配置文件路径或JSON字符串>")
        sys.exit(1)
    
    try:
        target_hwnd = int(sys.argv[1])
        config_arg = sys.argv[2]
        
        log(f"接收到的参数: target_hwnd={target_hwnd}, config_arg={config_arg}")
        
        # 首先检查是否是文件路径
        if os.path.exists(config_arg):
            log(f"配置文件存在: {config_arg}")
            # 从配置文件读取配置
            with open(config_arg, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 删除临时配置文件
            try:
                os.remove(config_arg)
            except:
                pass
        else:
            log(f"配置文件不存在，尝试解析为JSON: {config_arg}")
            # 尝试直接解析为JSON字符串
            try:
                # 修复JSON字符串中的转义字符
                config_str = config_arg.replace('\\"', '"')
                log(f"处理后的JSON字符串: {config_str}")
                config = json.loads(config_str)
                log(f"JSON解析成功: {config}")
            except json.JSONDecodeError as e:
                log(f"无法解析配置参数: {config_arg}")
                log(f"JSON解析错误: {e}")
                sys.exit(1)
        
        log("=" * 60)
        log("🎨 背景创建器启动")
        log(f"目标窗口: {target_hwnd}")
        log("=" * 60)
        
        creator = BackgroundCreator(target_hwnd, config)
        creator.run()
        
    except Exception as e:
        log(f"启动失败: {e}")
        import traceback
        log(f"详细错误信息: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()