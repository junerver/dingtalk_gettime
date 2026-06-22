# extractor/orchestrator.py
import logging
import time
from datetime import datetime

from sqlalchemy.orm import Session

from automation.window import activate_dingtalk, is_dingtalk_running
from automation.controller import (
    prepare_work_notification_view,
    scroll_up,
    scroll_window_wheel_message,
    wait,
)
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
            parse_retry_count=config.vision.parse_retry_count,
            empty_result_retry_count=config.vision.empty_result_retry_count,
        )

    def _crop_content(self, screenshot):
        return self.screenshot_mgr.crop_by_ratios(
            screenshot,
            left_ratio=self.config.screenshots.content_crop_left_ratio,
            top_ratio=self.config.screenshots.content_crop_top_ratio,
            right_ratio=self.config.screenshots.content_crop_right_ratio,
            bottom_ratio=self.config.screenshots.content_crop_bottom_ratio,
        )

    def _capture_content(self, window):
        return self._crop_content(self.screenshot_mgr.capture_window(window))

    def _prepare_work_notification(self, window) -> None:
        prepare_work_notification_view(
            window,
            conversation_list_scrolls=self.config.automation.conversation_list_scrolls,
            conversation_list_scroll_amount=self.config.automation.conversation_list_scroll_amount,
            conversation_list_x_ratio=self.config.automation.conversation_list_x_ratio,
            conversation_list_y_ratio=self.config.automation.conversation_list_y_ratio,
            first_conversation_x_ratio=self.config.automation.work_notification_x_ratio,
            first_conversation_y_ratio=self.config.automation.work_notification_y_ratio,
            second_conversation_x_ratio=self.config.automation.fallback_conversation_x_ratio,
            second_conversation_y_ratio=self.config.automation.fallback_conversation_y_ratio,
            bottom_reset_scrolls=self.config.automation.bottom_reset_scrolls,
            bottom_reset_scroll_amount=self.config.automation.bottom_reset_scroll_amount,
            content_x_ratio=self.config.automation.scroll_focus_x_ratio,
            content_y_ratio=self.config.automation.scroll_focus_y_ratio,
            delay=min(self.config.automation.click_delay, 0.2),
        )

    def _scroll_page(self, window, current_screenshot) -> bool:
        """滚动到更早消息，并验证截图是否发生变化。"""
        per_scroll_delay = (
            self.config.automation.scroll_delay
            / self.config.automation.scrolls_per_page
        )

        for _ in range(self.config.automation.scrolls_per_page):
            scroll_up(
                amount=self.config.automation.scroll_amount,
                delay=per_scroll_delay,
                window=window,
                x_ratio=self.config.automation.scroll_focus_x_ratio,
                y_ratio=self.config.automation.scroll_focus_y_ratio,
            )

        wait(self.config.automation.scroll_delay)
        after_scroll = self._capture_content(window)
        changed_ratio = self.screenshot_mgr.changed_pixel_ratio(
            current_screenshot,
            after_scroll,
        )
        logger.info(f"滚动后截图变化比例: {changed_ratio:.4f}")
        if not self.screenshot_mgr.images_are_similar(current_screenshot, after_scroll):
            return True

        logger.warning("滚动后截图几乎未变化，尝试通过窗口消息发送滚轮事件")
        for _ in range(self.config.automation.scrolls_per_page):
            scroll_window_wheel_message(
                window,
                amount=self.config.automation.scroll_amount,
                delay=per_scroll_delay,
                x_ratio=self.config.automation.scroll_focus_x_ratio,
                y_ratio=self.config.automation.scroll_focus_y_ratio,
            )

        wait(self.config.automation.scroll_delay)
        after_message_scroll = self._capture_content(window)
        changed_ratio = self.screenshot_mgr.changed_pixel_ratio(
            current_screenshot,
            after_message_scroll,
        )
        logger.info(f"备用滚动后截图变化比例: {changed_ratio:.4f}")
        if self.screenshot_mgr.images_are_similar(current_screenshot, after_message_scroll):
            logger.warning("滚动后截图仍未变化，停止提取以避免重复扫描同一页")
            return False

        return True

    def _page_limit(self, requested_max_pages: int | None = None) -> int:
        configured_limit = max(0, self.config.automation.max_pages)
        if requested_max_pages is None:
            return configured_limit
        return min(configured_limit, max(0, requested_max_pages))

    async def run_extraction(self, max_pages: int | None = None) -> dict:
        """执行完整的考勤数据提取流程。"""
        # 1. 激活钉钉窗口
        window = activate_dingtalk(
            self.config.dingtalk.path,
            self.config.dingtalk.launch_wait,
        )
        if window is None:
            if is_dingtalk_running():
                return {"status": "error", "message": "钉钉正在运行，但无法找到或激活主窗口"}
            return {"status": "error", "message": "钉钉未运行且启动失败"}

        self._prepare_work_notification(window)

        all_records = []
        pages_scanned = 0
        consecutive_duplicate_pages = 0
        page_limit = self._page_limit(max_pages)
        logger.info(f"本次请求最多处理 {page_limit} 页截图")

        for page in range(page_limit):
            logger.info(f"扫描第 {page + 1} 页...")

            # 2. 截图
            screenshot = self._capture_content(window)

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
            inserted_count = 0
            updated_count = 0
            skipped_count = 0
            ignored_count = 0
            for record_data in records:
                record_data["raw_text"] = str(result)
                record_data["screenshot_path"] = screenshot_path
                with self.db_session_factory() as db:
                    upsert_result = upsert_record(db, record_data)
                    if upsert_result["action"] == "inserted":
                        inserted_count += 1
                    elif upsert_result["action"] == "updated":
                        updated_count += 1
                    elif upsert_result["action"] == "skipped":
                        skipped_count += 1
                    elif upsert_result["action"] == "ignored":
                        ignored_count += 1

                    if upsert_result["action"] in {"inserted", "updated"}:
                        all_records.append(upsert_result["record"])

            # 5. 判断是否继续
            valid_record_count = len(records) - ignored_count
            if valid_record_count > 0 and inserted_count == 0 and updated_count == 0:
                consecutive_duplicate_pages += 1
                logger.info(
                    "本页记录均为数据库已有数据，连续重复页数: "
                    f"{consecutive_duplicate_pages}/{self.config.automation.duplicate_page_stop_threshold}"
                )
            else:
                consecutive_duplicate_pages = 0

            if records:
                logger.info(
                    f"本页新增 {inserted_count} 条，更新已有 {updated_count} 条，"
                    f"跳过已有 {skipped_count} 条，忽略无效 {ignored_count} 条"
                )

            if (
                self.config.automation.duplicate_page_stop_threshold > 0
                and consecutive_duplicate_pages >= self.config.automation.duplicate_page_stop_threshold
            ):
                logger.info("连续重复页数达到阈值，停止提取")
                break

            if page >= page_limit - 1:
                logger.info("已达到本次请求最大处理页数，停止提取")
                break

            model_says_no_more = result.get("page_reached_top") or not result.get("has_more")
            if model_says_no_more:
                logger.info("模型判断已到达顶部或无更多数据，将尝试滚动截图验证")

            # 6. 向上滚动。是否到顶以滚动后的截图变化为准，避免模型误判导致提前停止。
            if not self._scroll_page(window, screenshot):
                logger.info("已到达顶部或无法继续滚动，停止提取")
                break

        return {
            "status": "ok",
            "pages_scanned": pages_scanned,
            "records_found": len(all_records),
            "records": all_records,
        }
