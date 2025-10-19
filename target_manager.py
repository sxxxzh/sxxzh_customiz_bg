#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第一层：目标管理器 (sxxzh定制版)
负责加载和管理配置文件

开发者: sxxzh
版本: 1.1.2 - 加入UI 
"""

import os
import json
import time
import threading
from typing import Dict, List, Any, Optional

def log(msg):
    """日志输出"""
    timestamp = time.strftime('%H:%M:%S')
    print(f"[target-manager] {timestamp} - {msg}")

class TargetManager:
    """目标管理器"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config: Optional[Dict[str, Any]] = None
        self.config_mtime = 0
        self.lock = threading.Lock()
        
        # 创建默认配置
        if not os.path.exists(self.config_path):
            self._create_default_config()
        
        # 加载配置
        self._load_config()
    
    def _create_default_config(self):
        """创建默认配置文件"""
        default_config = {
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
                },
                {
                    "name": "Weixin",
                    "keywords": ["Weixin.exe", "Weixin"],
                    "image_path": "background.png",
                    "alpha": 40,
                    "brightness": 1.0,
                    "contrast": 1.0,
                    "saturation": 1.0
                }
            ]
        }
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            log(f"默认配置文件已创建: {self.config_path}")
        except Exception as e:
            log(f"创建默认配置文件失败: {e}")
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 验证配置格式
            if self._validate_config(config):
                with self.lock:
                    self.config = config
                    self.config_mtime = os.path.getmtime(self.config_path)
                log(f"配置加载成功，包含 {len(config.get('targets', []))} 个目标应用")
                return True
            else:
                log("配置验证失败，使用默认配置")
                return False
                
        except Exception as e:
            log(f"加载配置文件失败: {e}")
            return False
    
    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """验证配置格式"""
        try:
            # 检查必需字段
            if not isinstance(config, dict):
                return False
            
            # 检查 enabled 字段
            if 'enabled' not in config:
                config['enabled'] = True
            
            # 检查 scan_interval 字段
            if 'scan_interval' not in config:
                config['scan_interval'] = 3
            elif not isinstance(config['scan_interval'], int) or config['scan_interval'] < 1:
                config['scan_interval'] = 3
            
            # 检查 targets 字段
            if 'targets' not in config:
                config['targets'] = []
            elif not isinstance(config['targets'], list):
                return False
            
            # 验证每个目标配置
            valid_targets = []
            for target in config['targets']:
                if self._validate_target_config(target):
                    valid_targets.append(target)
            
            config['targets'] = valid_targets
            return True
            
        except:
            return False
    
    def _validate_target_config(self, target: Dict[str, Any]) -> bool:
        """验证单个目标配置"""
        try:
            # 必需字段
            if 'name' not in target or not target['name']:
                return False
            
            if 'keywords' not in target or not isinstance(target['keywords'], list):
                return False
            
            if not target['keywords']:
                return False
            
            # 可选字段设置默认值
            if 'image_path' not in target:
                target['image_path'] = 'background.png'
            
            if 'alpha' not in target:
                target['alpha'] = 40
            else:
                target['alpha'] = max(1, min(255, int(target['alpha'])))
            
            if 'brightness' not in target:
                target['brightness'] = 1.0
            else:
                target['brightness'] = max(0.1, min(5.0, float(target['brightness'])))
            
            if 'contrast' not in target:
                target['contrast'] = 1.0
            else:
                target['contrast'] = max(0.1, min(5.0, float(target['contrast'])))
            
            if 'saturation' not in target:
                target['saturation'] = 1.0
            else:
                target['saturation'] = max(0.1, min(5.0, float(target['saturation'])))
            
            return True
            
        except:
            return False
    
    def get_config(self) -> Optional[Dict[str, Any]]:
        """获取当前配置"""
        with self.lock:
            return self.config.copy() if self.config else None
    
    def is_config_updated(self) -> bool:
        """检查配置文件是否更新"""
        try:
            current_mtime = os.path.getmtime(self.config_path)
            if current_mtime > self.config_mtime:
                return True
        except:
            pass
        return False
    
    def reload_config(self) -> bool:
        """重新加载配置文件"""
        if self.is_config_updated():
            return self._load_config()
        return False
    
    def update_config(self, new_config: Dict[str, Any]) -> bool:
        """更新配置文件"""
        try:
            # 验证新配置
            if not self._validate_config(new_config):
                log("新配置验证失败")
                return False
            
            # 保存到文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, indent=4, ensure_ascii=False)
            
            # 重新加载配置
            if self._load_config():
                log("配置更新成功")
                return True
            else:
                log("配置更新后加载失败")
                return False
                
        except Exception as e:
            log(f"更新配置失败: {e}")
            return False
    
    def add_target(self, target_config: Dict[str, Any]) -> bool:
        """添加新的目标应用"""
        with self.lock:
            if not self.config:
                return False
            
            # 验证目标配置
            if not self._validate_target_config(target_config):
                log("目标配置验证失败")
                return False
            
            # 检查是否已存在同名目标
            for existing_target in self.config['targets']:
                if existing_target['name'] == target_config['name']:
                    log(f"目标 '{target_config['name']}' 已存在")
                    return False
            
            # 添加新目标
            self.config['targets'].append(target_config)
            
            # 保存到文件
            return self.update_config(self.config)
    
    def remove_target(self, target_name: str) -> bool:
        """移除目标应用"""
        with self.lock:
            if not self.config:
                return False
            
            # 查找并移除目标
            original_count = len(self.config['targets'])
            self.config['targets'] = [
                target for target in self.config['targets'] 
                if target['name'] != target_name
            ]
            
            if len(self.config['targets']) == original_count:
                log(f"未找到目标 '{target_name}'")
                return False
            
            # 保存到文件
            return self.update_config(self.config)
    
    def get_target_names(self) -> List[str]:
        """获取所有目标应用名称"""
        with self.lock:
            if not self.config:
                return []
            return [target['name'] for target in self.config['targets']]

def main():
    """测试函数"""
    manager = TargetManager()
    
    # 显示当前配置
    config = manager.get_config()
    if config:
        print("当前配置:")
        print(f"启用状态: {config.get('enabled', True)}")
        print(f"扫描间隔: {config.get('scan_interval', 3)}秒")
        print(f"目标应用: {[target['name'] for target in config.get('targets', [])]}")
    
    # 测试添加新目标
    new_target = {
        "name": "Sublime Text",
        "keywords": ["sublime_text.exe", "sublime_text"],
        "image_path": "background.png",
        "alpha": 30,
        "brightness": 1.0,
        "contrast": 1.1,
        "saturation": 1.3
    }
    
    if manager.add_target(new_target):
        print("新目标添加成功")
    else:
        print("新目标添加失败")

if __name__ == "__main__":
    main()