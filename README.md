# dingtalk_gettime

从钉钉工作通知中自动提取上下班打卡时间，支持定时调度、SQLite 存储和 REST API 查询。

## 工作原理

1. 通过 PyAutoGUI 控制钉钉客户端，自动滚动"工作通知"会话
2. 对聊天区域截图，使用 Vision 模型（兼容 OpenAI API）识别打卡记录
3. 解析识别结果，提取姓名、日期、打卡类型（上班/下班）、时间、状态等字段
4. 存入 SQLite 数据库，提供 REST API 查询接口

## 项目结构

```
├── main.py                  # FastAPI 服务入口
├── config.py                # 配置加载
├── config.yaml              # 运行时配置（不提交，需自行创建）
├── config.yaml.sample       # 配置示例
├── ecosystem.config.js      # PM2 部署配置
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

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.yaml.sample config.yaml
```

编辑 `config.yaml`，填写：

- `dingtalk.path` — 钉钉客户端安装路径
- `vision.api_base` — Vision 模型 API 地址（兼容 OpenAI API 格式）
- `vision.api_key` — API 密钥

### 3. 启动

```bash
python main.py
```

服务默认运行在 `http://0.0.0.0:8345`。

### 4. PM2 部署（可选）

```bash
pm2 start ecosystem.config.js
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

## 运行环境

- Windows（需要钉钉客户端运行）
- Python 3.11+
- 支持 OpenAI API 格式的 Vision 模型服务
