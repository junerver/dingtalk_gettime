# dingtalk_gettime

从钉钉工作通知中自动提取上下班打卡时间，支持定时调度、SQLite 存储和 REST API 查询。

## 工作原理

1. 通过 PyAutoGUI 控制钉钉客户端，自动滚动"工作通知"会话
2. 对聊天区域截图，使用 Vision 模型（兼容 OpenAI API）识别打卡记录
3. 解析识别结果，提取姓名、日期、打卡类型（上班/下班）、时间、状态等字段
4. 存入 SQLite 数据库，提供 REST API 查询接口

截图提取会先批量采集页面，再关闭/最小化钉钉窗口后进行 AI 分析。默认当本次请求页数不超过 `vision.image_stitch_max_pages` 时，会把多页截图倒序纵向拼接为一张图，只请求一次 Vision 模型；页数超过阈值时继续使用逐页图片并发请求。

## 项目结构

```
├── main.py                  # FastAPI 服务入口
├── config.py                # 配置加载
├── config.yaml              # 运行时配置（不提交，需自行创建）
├── config.yaml.sample       # 配置示例
├── ecosystem.config.js      # PM2 部署配置
├── start.ps1                 # 干净启动脚本（释放端口 + 无窗口启动）
├── requirements.txt
├── automation/
│   ├── controller.py        # 钉钉窗口操作控制器
│   └── window.py            # 窗口检测与管理
├── capture/
│   └── screenshot.py        # 屏幕截图
├── database/
│   ├── models.py            # SQLAlchemy 模型
│   └── crud.py              # 数据库 CRUD
├── extractor/
│   ├── orchestrator.py      # 提取流程编排
│   └── vision.py            # Vision 模型调用
└── tests/
```

## 快速开始

### 1. 安装依赖

建议在项目内创建虚拟环境，并在其中安装依赖（`ecosystem.config.js` 默认使用 `.venv/Scripts/pythonw.exe` 作为解释器）：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> 注意：`jinja2` 已被显式加入 `requirements.txt`（用于 `Jinja2Templates`），安装依赖时会一并安装。

如果启用截图拼接，需要本机可执行 `magick` 命令。Windows 可安装 ImageMagick，并确认命令行中能执行：

```bash
magick -version
```

### 2. 配置

```bash
cp config.yaml.sample config.yaml
```

编辑 `config.yaml`，填写：

- `dingtalk.path` — 钉钉客户端安装路径
- `vision.api_base` — Vision 模型 API 地址（兼容 OpenAI API 格式）
- `vision.api_key` — API 密钥
- `vision.image_stitch_max_pages` — 截图页数小于等于该值时，倒序拼接为一张图后请求 Vision 模型，默认 `3`

### 3. 启动

```bash
python main.py
```

服务默认运行在 `http://0.0.0.0:8345`。

> 说明：`main.py` 已通过 `uvicorn.run(..., workers=1)` 强制单进程运行，避免 uvicorn 受环境中的 `WEB_CONCURRENCY` 影响而派生多进程、与 PM2 的进程管理冲突。

### 4. PM2 部署（后台静默运行，推荐）

本项目的 PM2 配置（`ecosystem.config.js`）使用 venv 内的 `pythonw.exe` 作为解释器，**以无控制台窗口的方式后台运行**，不会像 `python.exe` 那样在每次重启时弹出黑色终端窗口。

推荐使用随项目提供的启动脚本，它会先释放被占用的 `8345` 端口、删掉旧的 PM2 实例，再以无窗口方式启动，从根上避免"绑定失败 → 崩溃重启 → 弹窗"的循环：

```powershell
.\start.ps1
pm2 save
```

如需手动启动：

```bash
pm2 startOrRestart .\ecosystem.config.js
pm2 save
```

如果 PM2 启动后反复重启，并在日志中看到 `address already in use` 或 Windows `10048` 端口占用错误，通常是已有旧进程仍在占用 `8345`。先确认端口归属，再停掉旧进程后重新启动：

```powershell
Get-NetTCPConnection -LocalPort 8345
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'dingtalk_gettime|main.py' }
pm2 startOrRestart .\ecosystem.config.js
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 服务状态、调度信息、记录总数 |
| POST | `/api/extract` | 手动触发考勤提取 |
| GET | `/api/records` | 查询考勤记录（支持日期范围、员工、类型筛选） |
| GET | `/api/records/latest` | 最新一条记录 |
| GET | `/api/records/daily-summary` | 每日汇总 |

### 查询示例

```bash
# 查询指定日期范围
curl "http://localhost:8345/api/records?start_date=2026-06-01&end_date=2026-06-23"

# 手动提取
curl -X POST "http://localhost:8345/api/extract" -H "Content-Type: application/json" -d '{"max_pages": 3}'

# 每日汇总
curl "http://localhost:8345/api/records/daily-summary?start_date=2026-06-01"
```

## 定时调度

在 `config.yaml` 中配置：

```yaml
scheduler:
  enabled: true
  extract_time: "08:30"   # 每天自动提取时间
  max_pages: 2            # 提取页数
```

服务启动后会自动在指定时间执行提取任务。

## 关键配置

```yaml
automation:
  max_pages: 20

vision:
  max_tokens: 4000
  parse_retry_count: 2
  empty_result_retry_count: 1
  image_stitch_max_pages: 3
```

- `automation.max_pages`: 单次请求全局最大处理页数。
- `vision.image_stitch_max_pages`: 当本次请求计算后的页数小于等于该值，并且实际捕获超过 1 张截图时，启用截图拼接。默认 `3`；设为 `0` 可关闭拼接。
- 拼接顺序是倒序：后截取到的更早记录页面在上方，先截取到的较晚记录页面在下方，避免钉钉打卡记录时间线颠倒。
- 拼接失败或 `magick` 不可用时，服务会回退到逐页并发 Vision 请求。

## 运行环境

- Windows（需要钉钉客户端运行）
- Python 3.11+
- 支持 OpenAI API 格式的 Vision 模型服务
