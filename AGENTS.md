# AGENTS.md

## 基本要求

- 使用中文回答问题。
- 修改代码前先阅读相关文件，优先沿用当前项目结构和测试风格。
- 不要提交或输出真实 `config.yaml` 中的 API Key、数据库、日志、截图等运行数据。
- 运行命令优先使用 PowerShell 语法。本项目在 Windows 桌面会话中运行，涉及 GUI 自动化，不适合作为 Windows Service / Session 0 运行。

## rtk 注意事项

rtk 不能直接代理 PowerShell 内置 cmdlet，需要让它代理 `powershell` 进程本身来进行指令执行。

## 项目概览

这是钉钉考勤打卡时间提取服务：

- FastAPI 提供 HTTP 接口，默认端口 `8345`。
- 自动化模块激活钉钉桌面客户端并进入工作通知。
- 截图模块截取并裁剪右侧工作通知内容区域。
- Vision 模型按 OpenAI 兼容接口提取考勤记录。
- SQLite 保存记录，并提供查询、最新记录、每日汇总接口。

## 常用命令

```powershell
pip install -r requirements.txt
python main.py

# 推荐用 start.ps1 启动：会先释放 8345 端口再启动，避免 PM2 崩溃重启循环
.\start.ps1
# 等价手动命令（需先确保 8345 端口空闲）：
pm2 startOrRestart .\ecosystem.config.js
pm2 save
pm2 list
pm2 logs dingtalk-gettime

python -m pytest -q
python -m pytest tests/test_orchestrator.py -q
python -m pytest tests/test_vision.py -q
python -m pytest tests/test_screenshot.py -q
```

## PM2 运行注意事项

- PM2 配置文件是 `ecosystem.config.js`。
- 解释器使用 **venv 内的 `pythonw` 绝对路径**（见配置注释）。进程以**无窗口**方式后台运行，不会弹出终端黑框。
- 服务日志在 `logs/pm2-out.log` 和 `logs/pm2-error.log`。
- **解释器绝对不能写成 `python` 或 `pythonw` 裸名**：PM2 守护进程按自身 cwd 解析，会命中全局 Python（未安装本项目依赖），导致 `ModuleNotFoundError` / `ImportError` → 进程秒退 → PM2 每 5 秒重启一次 → 每次重生产生一个闪烁的黑框终端窗口（即用户报的“不断弹出并自动关闭”）。
- `requirements.txt` 已显式包含 `jinja2`（之前缺失，即使 venv 也会因 `Jinja2Templates` 导入失败而崩溃重启）。修改依赖后请同步更新该文件。
- `main.py` 的 `uvicorn.run(..., workers=1)` 强制单进程。原因：若环境存在 `WEB_CONCURRENCY`（部分机器/PM2 默认会注入），uvicorn 会派生 worker 子进程，使 PM2 只跟踪不绑端口的父进程；本项目已由 PM2 负责进程管理，不应再让 uvicorn 自管多进程。
- 若启动后反复重启，先看日志：

```powershell
pm2 logs dingtalk-gettime --lines 100 --nostream
```

- 如果日志中出现 `Errno 10048`、`address already in use` 或端口 `8345` 绑定失败，检查是否有旧的非 PM2 进程占用端口：

```powershell
Get-NetTCPConnection -LocalPort 8345
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'dingtalk_gettime|main.py' }
```

确认是本项目旧 `python main.py` 进程后，再停止旧进程并用 PM2 启动。不要误杀无关进程。
- 最干净的启动方式始终用 `.\start.ps1`：它会先释放 8345 端口、删除旧 PM2 实例，再无窗口启动，从根本上避免绑定失败引发的崩溃重启循环。

## 截图拼接逻辑

`vision.image_stitch_max_pages` 控制是否启用截图拼接，默认值为 `3`：

- 当本次请求计算后的页数小于等于该值，并且实际捕获超过 1 张截图时，启用拼接。
- 当页数超过阈值时，继续使用逐页截图并发请求 Vision 模型。
- 设置为 `0` 可关闭拼接。

拼接使用本机 `magick` 命令：

```powershell
magick convert -append 3.png 2.png 1.png out.png
```

必须保持倒序拼接：钉钉提取从最新消息开始向上滚动，后截取到的是更早记录，所以后截图要放在上方，先截图要放在下方。拼接失败或 `magick` 不可用时，编排器会回退到逐页并发 Vision 请求。

相关文件：

- `capture/screenshot.py`: `stitch_vertical()` 和 `file_to_base64()`。
- `extractor/orchestrator.py`: 拼接阈值判断、倒序拼接、失败回退。
- `extractor/vision.py`: 拼接图片专用提示词。
- `tests/test_orchestrator.py`: 倒序拼接和超过阈值回退测试。
- `tests/test_screenshot.py`: `magick convert -append` 命令顺序测试。

## 配置注意事项

`config.yaml` 是运行配置入口，通常不提交。示例配置维护在 `config.yaml.sample`。

关键配置：

```yaml
automation:
  max_pages: 20

vision:
  max_tokens: 4000
  parse_retry_count: 2
  empty_result_retry_count: 1
  image_stitch_max_pages: 3
```

## 测试要求

- 修改配置读取时，更新 `tests/test_config.py`。
- 修改截图保存、裁剪、拼接时，更新 `tests/test_screenshot.py`。
- 修改编排流程时，更新 `tests/test_orchestrator.py`。
- 修改提示词、JSON 解析、记录归一化时，更新 `tests/test_vision.py`。
- `git diff --check` 只有 Windows 换行提示时可以接受。
