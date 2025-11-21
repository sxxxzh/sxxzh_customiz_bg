# 更新日志（CHANGELOG）

本文件记录窗口背景挂载系统（sxxzh_bg_system）的重要变更、修复与优化。格式参考 Keep a Changelog。

## 2025-10-22
### 新增
- 目标级主窗口面积阈值 `main_min_area`：每个目标可定义最小客户区面积，达到即视为主窗口并触发背景渲染。
- 顶层 `ignore_size`（全局最小面积阈值）：作为缺省值，当目标未配置 `main_min_area` 时生效。
- 托盘菜单新增“重新渲染”：手动停止当前背景并立即扫描/挂载，使配置变更快速生效。

### 变更
- `WindowDetector._is_window_suitable(hwnd, target)` 支持目标级阈值，调用处统一传入 `target`。
- 事件钩子与扫描流程在适配性检查阶段应用面积过滤；同进程仅保留面积更大的主窗口。
- `target_manager.py` 默认模板包含 `ignore_size` 与每目标 `main_min_area`；加载时校验并补齐缺失字段（旧 `config.json` 运行时也生效）。

### 日志
- 新增：`主窗口面积选择: area=<A>, min_area=<M> (target.main_min_area|config.ignore_size)`，用于判定来源与阈值。
- 保留：`事件检测到新目标窗口`、`同进程发现更大主窗口，切换/忽略新窗口`。

### 使用建议
- 在 `config.json` 为每个目标设置 `main_min_area`；未设置则使用顶层 `ignore_size`。
- 编辑配置后点击托盘“重新渲染”，并在 `logs\sxxzh_bg_system.log` 观察阈值与主窗口选择日志。

## 2025-10-21
### 修复
- 修复开机自启时缓存保存失败（Permission denied）。将窗口尺寸缓存文件迁移到本地用户目录 `%LOCALAPPDATA%\sxxzh_bg_system\window_size_cache.json`，避免工作目录为 `C:\Windows\System32` 或受限路径时写入失败。
- 清理缓存按钮兼容新路径：执行后会删除该文件并重置内存缓存。

### 变更
- 打包方式调整为 `onedir`：`config.json`、`background.png`、`logo.ico` 与 `render_cache/` 外置到 `dist\\sxxzh_bg_system\\`，支持运行时直接编辑与替换。
- 记录尺寸缓存路径日志，便于排查：关键字 `尺寸缓存文件路径:`。

### 验证建议
- 开机自启后，应在 `%LOCALAPPDATA%\\sxxzh_bg_system\\window_size_cache.json` 看到缓存文件生成并随窗口变化更新。
- 查看集中日志 `logs\\sxxzh_bg_system.log`，应出现缓存保存成功日志，无 `Permission denied` 报错。

## 2025-10-20
### 新增
- 托盘菜单新增“清理缓存”按钮：一键清空窗口尺寸缓存（删除 `window_size_cache.json`）、删除 `render_cache/` 内渲染缓存文件，并清理第三层临时配置文件；不影响 `config.json` 与集中日志。

### 优化
- 事件回调去抖可配置：新增 `event_debounce_ms`（默认 120ms），降低事件风暴。
- 尺寸变化记录阈值：新增 `size_change_px_threshold`（默认 8 像素），忽略小抖动。
- 尺寸监测间隔可配置：新增 `size_monitor_interval`（默认 0.3 秒），减少轮询负担。
- 扫描间隔下限：引入 `scan_interval_min` 机制，避免配置过小导致 CPU 占用过高（保持兜底扫描与事件驱动平衡）。

## 2025-10-19
### 新增
- 新增集中日志模块 `logger.py`：
  - 所有模块统一写入 `logs/sxxzh_bg_system.log`。
  - 简易大小轮转：超过 5MB 自动备份到 `sxxzh_bg_system.log.1`，继续写新文件。
  - 日志格式统一：`[module] YYYY-MM-DD HH:MM:SS - message`。
- 新增文档：`README.md` 与 `CHANGELOG.md`。

### 变更
- 统一 `main.py`, `window_detector.py`, `target_manager.py`, `bg_creator.py`, `window_size_cache.py` 的日志输出到集中日志：
  - 移除各模块的本地时间戳与散乱打印，统一由 `logger.py` 生成。
  - `bg_creator` 与 `size-cache` 默认不输出到控制台（`to_console=False`），避免重复与噪声。
  - `main.py` 开发模式下重定向 `stdout/stderr` 到集中日志，取消独立的 `stdout.log`/`stderr.log`。
- 保留 `window_detector` 的目标窗口日志精简策略，继续抑制非目标噪声。

### 修复
- 修复最小化窗口被误判为关闭的问题：
  - 扫描移除逻辑中加入 `win32gui.IsIconic(hwnd)` 检查，最小化不再被移除或清理进程缓存。
  - 事件处理忽略 `EVENT_OBJECT_HIDE` 的“消失”误判；在 `EVENT_OBJECT_LOCATIONCHANGE` 命中时即时触发出现检测与激活。
  - 恢复时无需等待兜底扫描，即刻通过 `SHOW/FOREGROUND/LOCATIONCHANGE` 事件完成激活。

### 验证建议
- 目标窗口最小化→等待→恢复：
  - 日志不应出现移除/保存动作（最小化阶段）。
  - 恢复瞬间应记录目标命中并激活（可能来源于 `LOCATIONCHANGE`）。
- 日志轮转：在日志累计超过 5MB 后，生成 `sxxzh_bg_system.log.1`，新日志继续写入 `sxxzh_bg_system.log`。

## 1.0.1（历史）
### 修复
- 修复开机自启问题（托盘菜单可切换，详细日志记录启动命令与路径）。

## 初始版本（历史）
- 基础三层架构：`target_manager` / `window_detector` / `bg_creator`。
- 支持配置化目标与背景参数、托盘运行、日志输出。

---
未来计划：
- 支持模块白名单/等级过滤接口（仅记录指定模块或等级）。
- 增加更多日志轮转策略（保留多份备份或按天轮转）。
- 增强目标匹配规则（正则、窗口类名、进程路径等）。