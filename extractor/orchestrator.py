# extractor/orchestrator.py
import logging
import time
from datetime import datetime

from sqlalchemy.orm import Session

from automation.window import activate_dingtalk
from automation.controller import scroll_up, wait
from capture.screenshot import ScreenshotManager
from database.crud import upsert_record
from extractor.vision import VisionExtractor

logger = logging.getLogger(__name__)


class ExtractOrchestrator:
    def __init__(self, config, db_session_factory):
        self.config = config
        self.db_session_factory = db_session_factory
        self.screenshot_mgr = ScreenshotManager(save_dir=config.screenshots.save_dir)
        self.vision = VisionExtractor(
            api_base=config.vision.api_base,
            api_key=config.vision.api_key,
            model=config.vision.model,
            max_tokens=config.vision.max_tokens,
        )

    async def run_extraction(self) -> dict:
        """执行完整的考勤数据提取流程。"""
        # 1. 激活钉钉窗口
        window = activate_dingtalk(
            self.config.dingtalk.path,
            self.config.dingtalk.launch_wait,
        )
        if window is None:
            return {"status": "error", "message": "钉钉未运行且启动失败"}

        all_records = []
        pages_scanned = 0

        for page in range(self.config.automation.max_pages):
            logger.info(f"扫描第 {page + 1} 页...")

            # 2. 截图
            screenshot = self.screenshot_mgr.capture_window(window)

            if self.screenshot_mgr.is_mostly_blank(screenshot):
                logger.warning("截图为空白，停止提取")
                break

            # 保存截图
            screenshot_path = self.screenshot_mgr.save(screenshot)
            base64_img = self.screenshot_mgr.to_base64(screenshot)

            # 3. LLM提取
            result = await self.vision.extract_from_image(base64_img)
            records = result.get("records", [])
            pages_scanned += 1

            logger.info(f"本页提取到 {len(records)} 条记录")

            # 4. 入库
            for record_data in records:
                record_data["raw_text"] = str(result)
                record_data["screenshot_path"] = screenshot_path
                with self.db_session_factory() as db:
                    upsert_result = upsert_record(db, record_data)
                    all_records.append(upsert_result["record"])

            # 5. 判断是否继续
            if result.get("page_reached_top") or not result.get("has_more"):
                logger.info("已到达顶部或无更多数据，停止提取")
                break

            # 6. 向上滚动
            for _ in range(self.config.automation.scrolls_per_page):
                scroll_up(
                    amount=self.config.automation.scroll_amount,
                    delay=self.config.automation.scroll_delay / self.config.automation.scrolls_per_page,
                )

            wait(self.config.automation.scroll_delay)

        return {
            "status": "ok",
            "pages_scanned": pages_scanned,
            "records_found": len(all_records),
            "records": all_records,
        }
