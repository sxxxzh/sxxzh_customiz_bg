# 窗口背景挂载系统（sxxzh_bg_system）

一个在 Windows 上运行的轻量后台工具，根据配置监控指定应用窗口，并创建/更新与之匹配的背景图像效果。项目由目标管理、窗口检测与背景创建三部分组成，已统一集中日志便于排错与维护。

## 功能特性

- 目标窗口监控：根据 `config.json` 的 `targets.keywords`（进程名或标题关键字）识别目标窗口。
- 背景挂载：为命中目标的窗口创建背景图（透明度、亮度、对比度、饱和度可调）。
- 实时事件检测：使用 Windows `WinEvent` Hook，支持 `SHOW/FOREGROUND/LOCATIONCHANGE` 等事件即时响应。
- 稳健最小化处理：最小化窗口不会被误判为关闭；恢复时即时重新检测激活。
- 集中日志：所有模块写入 `logs/sxxzh_bg_system.log`，超过 5MB 自动轮转为 `.log.1`。
- 托盘控制：支持托盘运行、查看日志、切换开机自启、隐藏/显示托盘图标。
- 托盘清理缓存：右键托盘选择“清理缓存”，删除 `window_size_cache.json` 与 `render_cache/` 内缓存文件，并清理临时配置文件；不影响 `config.json` 与日志。

## 系统要求

- 操作系统：Windows 10/11
- EXE 单文件版，无需安装 Python 或依赖

## 配置说明（config.json）

示例：

```json
{
  "enabled": true,
  "scan_interval": 3,
  "ignore_size": 120000,
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
    },
    {
      "name": "Weixin",
      "keywords": ["Weixin.exe", "Weixin"],
      "image_path": "background.png",
      "alpha": 40,
      "brightness": 1.0,
      "contrast": 1.0,
      "saturation": 1.0,
      "main_min_area": 80000
    }
  ]
}
```

- `enabled`：是否启用系统。
- `scan_interval`：扫描/轮询间隔（秒），用于兜底检测与状态同步（默认 3）。
- `ignore_size`：全局主窗口最小面积阈值，用于过滤过小窗口；未设置或非法时回退 10000。
- `targets`：目标应用列表：
  - `name`：目标名称（用于日志展示）。
  - `keywords`：用于匹配的关键字（进程名或窗口标题片段）。
  - `image_path`：背景图像路径（相对或绝对）。
  - `alpha`：透明度（范围 1–255，`40` 为示例值）。
  - `brightness` / `contrast` / `saturation`：图像调节参数（浮点，1.0 为不变）。
  - `main_min_area`：该目标主窗口最小面积阈值；优先于全局 `ignore_size`。

## 日志与排错

- 集中日志文件：`logs/sxxzh_bg_system.log`（位于可执行所在目录）。
- 轮转策略：超过 5MB 自动备份为 `sxxzh_bg_system.log.1` 并重建新文件。
- 日志格式：`[module] YYYY-MM-DD HH:MM:SS - message`。
- 模块名示例：`main`, `window-detector`, `target-manager`, `bg-creator`, `size-cache`。
- 在托盘菜单选择“显示信息”可直接打开日志文件并预览最近日志。

### 常见问题

- 无法检测窗口：确认关键字是否匹配实际进程名或窗口标题；检查窗口是否满足面积阈值。
- 日志未生成：确认进程具备写入权限；检查 `logs/` 文件夹是否存在（程序会自动创建）。
- 打包后开机自启：通过托盘菜单切换；如提示找不到可执行文件，请先完成打包。
- Pillow 图像问题：确保背景图存在且格式支持（建议 PNG）。
- 缓存过大或异常：右键托盘选择“清理缓存”，一键清理尺寸与渲染缓存；程序会在运行时按需重新生成。

## EXE 版功能与使用

- 运行方式：双击同目录 `sxxzh_bg_system.exe`，无需 Python 环境。
- 同目录文件：`config.json`、`background.png`、`logo.ico`、`render_cache/`、`logs/`。
- 文档：请仔细阅读 `README.md` 。
- 配置文件：编辑同目录 `config.json` 即生效；支持顶层 `ignore_size` 与每目标 `main_min_area`。
- 日志文件：`logs\sxxzh_bg_system.log`（超过 5MB 自动轮转为 `.log.1`）。
- 托盘菜单：显示信息、清理缓存、重新渲染、切换开机自启、退出。
- 缓存路径：渲染缓存位于 `render_cache/`；尺寸缓存位于 `%LOCALAPPDATA%\sxxzh_bg_system\window_size_cache.json`。
- 快速生效：修改配置后，右键托盘选择“重新渲染”。

## EXE 版更新日志（摘要）

- 新增每目标主窗口最小面积 `main_min_area`；未配置时使用全局 `ignore_size`。
- 事件钩子与扫描流程统一应用面积过滤，并在同一进程仅保留更大主窗口。
- 托盘新增“重新渲染”，快速应用配置变更；“清理缓存”一键清除尺寸与渲染缓存。

## 版权声明

- 版权所有 sxxxzh
