# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

钉钉考勤打卡时间提取服务。服务运行在 Windows 当前登录用户桌面会话中，通过模拟操作钉钉桌面版客户端，截取工作通知内容区域截图，调用 OpenAI 兼容多模态接口提取考勤记录，写入 SQLite，并提供 HTTP 查询接口。

当前服务端口为 `8345`，默认接口地址：

```text
http://localhost:8345
```

注意：项目依赖桌面 GUI 自动化，不适合以 Windows Service / Session 0 方式运行。长期后台运行优先使用 PM2，并确保 PM2 进程运行在当前登录用户会话中。

## 常用命令

```powershell
# 安装 Python 依赖
pip install -r requirements.txt

# 直接启动服务，读取 config.yaml 中的 host/port
python main.py

# PM2 启动或重启服务
pm2 startOrRestart .\ecosystem.config.js

# 保存 PM2 当前进程列表
pm2 save

# 查看 PM2 进程
pm2 list

# 查看服务日志
pm2 logs dingtalk-gettime

# 重启 / 停止
pm2 restart dingtalk-gettime
pm2 stop dingtalk-gettime

# 运行全部测试
python -m pytest -q

# 运行单个测试文件
python -m pytest tests/test_crud.py -q

# 运行单个测试函数
python -m pytest tests/test_crud.py::test_upsert_inserts_new -q
```

PM2 配置文件为 `ecosystem.config.js`，服务日志写入：

```text
logs/pm2-out.log
logs/pm2-error.log
```

`logs/*.log` 已在 `.gitignore` 中忽略。

如果需要开机后自动恢复 PM2 进程，建议用 Windows 任务计划程序在“用户登录时”执行：

```powershell
pm2 resurrect
```

不要配置成“无论用户是否登录都运行”，否则 GUI 自动化可能无法操作钉钉窗口。

## API 使用

### GET /api/status

查看服务状态、钉钉运行状态、定时任务配置和数据库记录总数。

```powershell
curl.exe http://localhost:8345/api/status
```

返回示例：

```json
{
  "status": "running",
  "dingtalk_running": true,
  "last_extract_time": null,
  "scheduler": {
    "enabled": true,
    "extract_time": "21:30",
    "max_pages": 2,
    "last_scheduled_extract_time": null
  },
  "total_records": 11
}
```

### POST /api/extract

执行一次考勤提取。请求会激活钉钉、进入工作通知、回到底部，从最新消息开始向上翻页提取。

```powershell
curl.exe -X POST http://localhost:8345/api/extract `
  -H "Content-Type: application/json" `
  -d '{"date_range":"all"}'
```

指定本次最多处理页数：

```powershell
curl.exe -X POST http://localhost:8345/api/extract `
  -H "Content-Type: application/json" `
  -d '{"date_range":"all","max_pages":2}'
```

请求体字段：

- `date_range`: 当前保留字段，默认 `"all"`。
- `max_pages`: 可选，正整数。本次请求最多处理多少页截图。它会被 `automation.max_pages` 封顶，不能绕过全局上限。

返回示例：

```json
{
  "status": "ok",
  "pages_scanned": 2,
  "records_found": 1,
  "records": []
}
```

可能状态：

- `ok`: 提取流程完成。
- `busy`: 已有提取任务正在执行。服务用进程内锁避免手动提取和定时提取同时操作钉钉。
- `error`: 启动、窗口激活、截图、识图或入库流程异常。

### GET /api/records

查询考勤记录。

```powershell
curl.exe "http://localhost:8345/api/records"
curl.exe "http://localhost:8345/api/records?start_date=2026-06-01&end_date=2026-06-30"
curl.exe "http://localhost:8345/api/records?punch_type=上班打卡"
curl.exe "http://localhost:8345/api/records?employee=张三"
```

支持查询参数：

- `start_date`: 起始日期，格式 `YYYY-MM-DD`。
- `end_date`: 结束日期，格式 `YYYY-MM-DD`。
- `employee`: 员工名称。
- `punch_type`: `上班打卡` 或 `下班打卡`。

### GET /api/records/latest

查询最新一条记录。

```powershell
curl.exe http://localhost:8345/api/records/latest
```

### GET /api/records/daily-summary

按天汇总上下班记录。

```powershell
curl.exe "http://localhost:8345/api/records/daily-summary"
curl.exe "http://localhost:8345/api/records/daily-summary?start_date=2026-06-01&end_date=2026-06-30"
```

## 定时任务

定时提取配置在 `config.yaml`：

```yaml
scheduler:
  enabled: true
  extract_time: "21:30"
  max_pages: 2
```

行为：

- 服务启动后创建后台定时任务。
- 每天 `21:30` 自动执行一次考勤提取。
- 定时提取传入 `max_pages=2`，即只提取 2 页。
- 如果此时手动提取正在运行，定时提取会返回 `busy` 并跳过，避免两个任务同时操作钉钉。

## 关键配置

`config.yaml` 是运行配置入口。

```yaml
server:
  host: "0.0.0.0"
  port: 8345

automation:
  max_pages: 20
  duplicate_page_stop_threshold: 5
  scroll_amount: 1
  scrolls_per_page: 5

screenshots:
  content_crop_left_ratio: 0.385
  content_crop_top_ratio: 0.05
  content_crop_right_ratio: 1.0
  content_crop_bottom_ratio: 1.0

vision:
  max_tokens: 4000
  parse_retry_count: 2
  empty_result_retry_count: 1
```

配置含义：

- `automation.max_pages`: 单次请求全局最大处理页数，默认 `20`。
- `automation.duplicate_page_stop_threshold`: 连续多少页都是数据库已有有效记录后停止，默认 `5`。
- `scroll_amount` + `scrolls_per_page`: 每页向上滚动量。当前配置等价于手动滚轮滚动 5 次。
- `screenshots.content_crop_*`: 从完整钉钉窗口截图裁剪出右侧工作通知内容区域，减少多模态 token 消耗。
- `vision.parse_retry_count`: LLM 返回坏 JSON 时的重试次数。
- `vision.empty_result_retry_count`: LLM 返回空记录时的复核次数。

注意：`config.yaml` 当前包含真实多模态 API Key。修改或提交相关内容时要主动检查是否需要脱敏。

## 架构

数据流：

```text
HTTP请求 / 定时任务
  -> FastAPI 路由
  -> ExtractOrchestrator
  -> automation 窗口/键鼠模拟
  -> capture 窗口截图与内容区域裁剪
  -> extractor 多模态识图与 JSON harness
  -> database 入库与业务去重
  -> HTTP 响应
```

主要模块：

- `main.py`：FastAPI 入口、PM2/直接启动入口、定时任务、提取任务锁、API 路由。
- `config.py`：dataclass 配置体系，`load_config()` 读取 `config.yaml` 并填充默认值。
- `automation/window.py`：查找、启动、激活钉钉窗口，包含 Win32 窗口查找逻辑。
- `automation/controller.py`：封装点击、滚动、会话切换、工作通知回底等模拟操作。
- `capture/screenshot.py`：窗口截图、内容区域裁剪、空白检测、截图相似度检测。优先使用窗口句柄截图，避免截到终端或其它窗口。
- `extractor/vision.py`：多模态识图、JSON 解析、坏 JSON 重试、空结果复核、截断 JSON 片段恢复、记录归一化。
- `extractor/orchestrator.py`：完整提取流程编排。LLM 的 `has_more/page_reached_top` 只是软信号，是否继续主要以滚动后截图变化和重复页阈值判断。
- `database/models.py`：SQLAlchemy ORM 模型。
- `database/crud.py`：入库、查询、每日汇总。入库时执行业务规则去重和最终记录选择。
- `ecosystem.config.js`：PM2 启动配置。

## 提取流程

单次提取的主要步骤：

1. 激活钉钉主窗口。
2. 准备工作通知会话：滚动左侧会话列表，点击第二条会话，再点击置顶的工作通知，实现进入工作通知并回到底部。
3. 截取钉钉窗口，并裁剪右侧工作通知内容区域。
4. 调用多模态接口识别考勤记录。
5. 入库并按业务规则更新、跳过或忽略记录。
6. 如果没有达到页数上限、重复页阈值或截图不变停止条件，则向上滚动一页继续。

停止条件：

- 达到本次请求 `max_pages` 或全局 `automation.max_pages`。
- 截图为空白。
- 连续重复页数达到 `duplicate_page_stop_threshold`。
- 滚动后截图几乎不变，备用滚轮消息也无法改变截图。

## 业务规则

识图层和数据库层都有兜底：

- 忽略 `"打卡·无效"`、`"打卡-无效"`、`"无效原因"` 等无效打卡卡片，不入库。
- 同一日期同一类型多条有效记录：
  - `上班打卡` 保留最早时间。
  - `下班打卡` 保留最晚时间。
- 如果数据库已有更优记录，新识别到的较差记录返回 `skipped`，不覆盖。
- 如果识别到更优记录，返回 `updated` 并更新数据库。
- 新日期/新类型首次入库返回 `inserted`。

编排日志会按页统计：

```text
本页新增 X 条，更新已有 Y 条，跳过已有 Z 条，忽略无效 N 条
```

## LLM Harness

`VisionExtractor` 不应把模型偶发失败直接当成“没有记录”：

- 直接解析 JSON。
- 支持从 Markdown 代码块、前后混杂文本中提取 JSON。
- 返回半截 JSON 时会重试。
- 重试仍失败时，会尽量从已闭合的单条记录对象中恢复有效记录。
- 首次返回空记录时会复核一次。
- 解析失败最终返回 `has_more=true/page_reached_top=false/error=parse_failed`，避免误判已经到顶。

## 测试

测试使用 `pytest` 和 `pytest-asyncio`。

```powershell
python -m pytest -q
python -m pytest tests/test_api.py -q
python -m pytest tests/test_orchestrator.py -q
python -m pytest tests/test_vision.py -q
python -m pytest tests/test_crud.py -q
```

测试重点：

- API 参数校验和 `max_pages` 传递。
- 定时时间计算。
- 编排层翻页、页数上限、重复页停止。
- 识图层坏 JSON 重试、空结果复核、截断 JSON 恢复、无效记录过滤。
- 数据库层无效记录忽略、上班最早、下班最晚。
- 截图裁剪和窗口截图容错。

## 开发注意事项

- 这个项目会真实操作 Windows 桌面和钉钉窗口。运行提取接口前，应确保当前用户已登录 Windows，钉钉可正常显示。
- 不要把服务部署为普通 Windows Service。需要后台运行时使用 PM2，开机恢复用任务计划程序在用户登录时执行 `pm2 resurrect`。
- 如果修改钉钉 UI 坐标比例，优先调整 `config.yaml`，再补充控制器或截图测试。
- 如果修改数据库入库语义，同步更新 `tests/test_crud.py` 和 `tests/test_orchestrator.py`。
- 如果修改 LLM 提示或解析逻辑，同步更新 `tests/test_vision.py`。
- `git diff --check` 只有 Windows 换行提示时可以接受；不要提交运行生成的日志、截图、数据库或 `__pycache__` 文件。
