# 窗口背景挂载系统 v4

## 简介
这是一个基于三层架构的窗口背景挂载系统，可以自动为指定窗口添加背景图片。

## 功能特性
- 目标窗口自动检测
- 实时背景挂载
- 配置文件热重载
- 多窗口支持

## 使用方法
1. 双击运行 `start.bat` 启动程序
2. 或直接运行 `window_background_system.exe`
3. 程序会自动加载 `config.json` 配置文件

## 配置文件说明
编辑 `config.json` 文件来配置需要挂载背景的窗口：
- `enabled`: 系统开关
- `scan_interval`: 扫描间隔（秒）
- `targets`: 目标窗口列表

## 系统要求
- Windows 操作系统
- .NET Framework 4.5+
- 不需要安装Python

## 技术支持
如有问题请联系开发者。
