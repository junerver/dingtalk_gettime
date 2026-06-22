# 钉钉考勤打卡时间提取服务 - 设计文档

## 概述

在Windows上实现一个HTTP服务，通过模拟键鼠操作钉钉桌面版客户端，导航到"工作通知"页面，逐屏截图并使用多模态大模型提取考勤打卡信息，持久化存储后提供查询接口，供外部Agent调用。

## 技术选型

| 组件 | 方案 | 理由 |
|------|------|------|
| UI自动化 | pyautogui | 成熟稳定，与Electron应用兼容好 |
| 窗口管理 | pywinctl + ctypes | 查找/激活钉钉窗口 |
| 截图 | Pillow + pyautogui | 截取窗口区域 |
| 数据提取 | 多模态LLM（OpenAI兼容API） | 用户自有接口，识别能力强 |
| Web框架 | FastAPI | 异步支持好，自动生成API文档 |
| 数据库 | SQLite + SQLAlchemy | 零配置，适合个人服务 |
| 配置 | YAML | 可读性好 |

## 系统架构

```
┌─────────────────────────────────────────┐
│          FastAPI HTTP Service           │
│   POST /api/extract  GET /api/records   │
├─────────────────────────────────────────┤
│              Core Layer                 │
│  ┌────────────┐ ┌────────────┐         │
│  │ DingTalk   │ │ Screenshot │         │
│  │ Automation │ │ Capture    │         │
│  └────────────┘ └────────────┘         │
│  ┌────────────┐ ┌────────────┐         │
│  │ Vision LLM │ │ Database   │         │
│  │ Client     │ │ (SQLite)   │         │
│  └────────────┘ └────────────┘         │
└─────────────────────────────────────────┘
```

## 目录结构

```
dingtalk_gettime/
├── main.py              # FastAPI入口，路由定义
├── config.py            # 配置管理（读取config.yaml）
├── config.yaml          # 用户配置文件
├── automation/
│   ├── __init__.py
│   ├── window.py        # 窗口查找、启动、激活钉钉
│   └── controller.py    # 键鼠操作：点击、滚动、等待
├── capture/
│   ├── __init__.py
│   └── screenshot.py    # 截图管理：截取、存储
├── extractor/
│   ├── __init__.py
│   └── vision.py        # 多模态LLM客户端，发送截图提取数据
├── database/
│   ├── __init__.py
│   ├── models.py        # SQLAlchemy ORM模型
│   └── crud.py          # 数据增删改查
└── requirements.txt     # Python依赖
```

## 数据模型

### attendance_records 表

```sql
CREATE TABLE attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_name TEXT,
    record_date TEXT NOT NULL,          -- YYYY-MM-DD
    punch_type TEXT NOT NULL,           -- "上班打卡" / "下班打卡"
    punch_time TEXT,                    -- HH:MM
    punch_result TEXT,                  -- 完整打卡结果文本
    punch_status TEXT,                  -- "成功" / "迟到" / "早退" / "缺卡"
    shift_time TEXT,                    -- 班次时间
    punch_method TEXT,                  -- "考勤机打卡" 等
    device_info TEXT,                   -- 设备信息
    notes TEXT,                         -- 备注
    raw_text TEXT,                      -- LLM原始返回JSON
    screenshot_path TEXT,               -- 截图文件路径
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(employee_name, record_date, punch_type)
);
```

冲突策略：`INSERT OR REPLACE`，相同人+日期+打卡类型的记录会被更新。

### 数据示例

```json
{
  "employee_name": "张三",
  "record_date": "2026-06-18",
  "punch_type": "下班打卡",
  "punch_time": "17:35",
  "punch_result": "✅ 17:35 下班打卡·成功",
  "punch_status": "成功",
  "shift_time": "06月18日 17:30下班",
  "punch_method": "考勤机打卡",
  "device_info": "G2门禁机KN6895",
  "notes": "下班打卡时间已更新到17:35"
}
```

## 自动化流程

### 导航路径

1. 查找钉钉窗口，若未运行则启动
2. 激活窗口并置前
3. 导航到"工作通知"页面（默认在底部，显示最新消息）
4. 逐屏截图提取（向上滚动查看更早记录）
5. 汇总去重，存入数据库

### 逐屏提取流程

```
初始状态：位于工作通知页面底部（最新消息）
循环：
  1. 截取当前屏幕
  2. 发送给多模态LLM提取考勤数据
  3. LLM返回结果 + has_more标志
  4. 若 has_more=false 或 已达最大翻页数 → 停止
  5. 向上滚动 scrolls_per_page 次
  6. 等待 scroll_delay 秒
  7. 回到步骤1
```

### 滚动策略

- 默认在工作通知页面底部，最新消息在最下方
- 向上滚动查看更早的历史记录
- 约5次滚动 = 1页内容
- 最多翻10页（可配置）

## LLM提取Prompt

向多模态LLM发送截图时使用以下prompt：

```
请分析这张钉钉"工作通知"截图中的考勤打卡信息。
对每条打卡记录，提取以下字段并返回JSON数组：

{
  "records": [
    {
      "punch_type": "上班打卡/下班打卡",
      "punch_time": "HH:MM",
      "punch_result": "完整打卡结果文本",
      "punch_status": "成功/迟到/早退/缺卡",
      "shift_time": "班次时间",
      "punch_method": "打卡方式",
      "device_info": "设备信息",
      "notes": "备注",
      "record_date": "YYYY-MM-DD"
    }
  ],
  "has_more": true/false,
  "page_reached_top": true/false
}

注意：
- has_more 表示上方是否可能还有更多打卡记录
- page_reached_top 表示是否已经看到最早的消息
- 如果截图中没有考勤信息，返回 {"records": [], "has_more": false, "page_reached_top": true}
- 只返回JSON，不要其他文字
```

## HTTP API

### POST /api/extract

触发考勤数据提取流程。

**请求体：**
```json
{
  "date_range": "today" | "this_week" | "this_month" | "all"
}
```

**响应（成功）：**
```json
{
  "status": "ok",
  "records_found": 12,
  "records_new": 8,
  "records_updated": 4,
  "records": [...]
}
```

**响应（错误）：**
```json
{
  "status": "error",
  "message": "钉钉未运行且启动失败"
}
```

### GET /api/records

查询考勤记录。

**参数：**
- `start_date` (可选): 开始日期 YYYY-MM-DD
- `end_date` (可选): 结束日期 YYYY-MM-DD
- `employee` (可选): 员工姓名
- `punch_type` (可选): "上班打卡" 或 "下班打卡"

**响应：**
```json
{
  "total": 20,
  "records": [...]
}
```

### GET /api/records/latest

获取最新一条考勤记录。

### GET /api/records/daily-summary

按天汇总（每天上下班合并显示）。

**参数：**
- `start_date` (可选)
- `end_date` (可选)

**响应：**
```json
{
  "summary": [
    {
      "date": "2026-06-18",
      "clock_in": { "time": "07:53", "status": "成功", "method": "考勤机打卡" },
      "clock_out": { "time": "17:35", "status": "成功", "method": "考勤机打卡" }
    }
  ]
}
```

### GET /api/status

服务状态信息。

**响应：**
```json
{
  "status": "running",
  "dingtalk_running": true,
  "last_extract_time": "2026-06-22T10:30:00",
  "total_records": 120
}
```

## 配置文件 (config.yaml)

```yaml
dingtalk:
  path: "C:\\Program Files\\DingTalk\\DingTalk.exe"
  launch_wait: 10        # 启动后等待秒数

automation:
  click_delay: 1.0       # 点击后等待秒数
  scroll_delay: 2.0      # 滚动后等待秒数
  scroll_amount: 5       # 每次滚动量（正=向上）
  scrolls_per_page: 5    # 每页滚动次数
  max_pages: 10          # 最多翻页数
  retry_count: 1         # UI操作失败重试次数

vision:
  api_base: "http://localhost:8000/v1"
  api_key: "your-api-key"
  model: "gpt-4o"
  max_tokens: 2000

database:
  path: "./data/attendance.db"

server:
  host: "0.0.0.0"
  port: 8080

screenshots:
  save_dir: "./data/screenshots"    # 截图保存目录
  keep_days: 30                      # 截图保留天数
```

## 错误处理

| 场景 | 处理方式 |
|------|----------|
| 钉钉未安装/启动失败 | 返回HTTP 503，消息：钉钉不可用 |
| UI操作超时（点击无响应） | 重试1次，仍失败返回错误 |
| LLM调用失败 | 重试2次，记录已提取的部分数据 |
| 截图为空/黑屏 | 检测并报错 |
| 无打卡记录 | 正常返回空数组 |
| 提取过程中断 | 已提取数据正常入库，返回partial状态 |

## 依赖

```
fastapi>=0.110.0
uvicorn>=0.29.0
pyautogui>=0.9.54
pywinctl>=0.4
Pillow>=10.0
sqlalchemy>=2.0
pyyaml>=6.0
httpx>=0.27.0
openai>=1.30.0
python-multipart>=0.0.9
```
