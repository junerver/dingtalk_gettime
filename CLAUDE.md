# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

钉钉考勤打卡时间提取服务：通过 pyautogui 模拟键鼠操作 Windows 钉钉桌面版客户端，截图后调用多模态大模型（OpenAI 兼容 API）提取考勤数据，存入 SQLite 并提供 HTTP 查询接口。

## 常用命令

```powershell
# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py

# 运行全部测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_crud.py -v

# 运行单个测试函数
python -m pytest tests/test_crud.py::test_upsert_inserts_new -v
```

## 架构

数据流：`HTTP请求 → FastAPI路由 → ExtractOrchestrator → automation(窗口/键鼠) → capture(截图) → extractor(LLM提取) → database(存储)`

- **main.py** — FastAPI 入口，模块级加载 config 和初始化 DB engine。测试通过 monkeypatch 替换这些全局变量
- **config.py** — dataclass 配置体系，`load_config()` 读取 config.yaml 并填充默认值
- **automation/** — `window.py` 用 pywinctl 查找/激活钉钉窗口；`controller.py` 封装 pyautogui 键鼠操作
- **capture/screenshot.py** — `ScreenshotManager` 负责窗口截图、保存、base64 转换、空白检测
- **extractor/vision.py** — `VisionExtractor` 通过 OpenAI 兼容 API 发送截图提取结构化 JSON，含 markdown 代码块解析容错
- **extractor/orchestrator.py** — `ExtractOrchestrator` 编排完整流程：激活钉钉 → 逐屏截图 → LLM提取 → 入库 → 向上滚动翻页
- **database/** — SQLAlchemy ORM (`models.py`) + CRUD 操作 (`crud.py`)，upsert 按 employee_name + record_date + punch_type 去重

## 关键设计决策

- 钉钉工作通知页面默认在底部（最新消息），向上滚动查看更早记录，约5次滚动=1页
- 每条考勤记录包含：punch_type（上班/下班打卡）、punch_time、punch_status、shift_time、punch_method、device_info、notes
- LLM 返回 JSON 中的 `has_more` 和 `page_reached_top` 字段控制翻页终止
- config.yaml 中包含敏感 API Key，已在 .gitignore 中排除

## 测试

tests/ 使用 pytest + pytest-asyncio。conftest.py 将项目根目录加入 sys.path。API 测试通过 mock `main.config` 和 `main.SessionLocal` 使用临时数据库。vision 测试通过 mock OpenAI client 的 `create` 方法。
