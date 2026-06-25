# extractor/orchestrator.py
import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy.orm import Session

from automation.window import activate_dingtalk, is_dingtalk_running, close_window
import pyautogui
from automation.controller import (
    prepare_work_notification_view,
    focus_window_for_scroll,
    scroll_window_wheel_message,
    wait,
    WHEEL_DELTA,
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
            delay=self.config.automation.click_delay,
            scroll_step_delay=self.config.automation.scroll_step_delay,
            click_settle_delay=self.config.automation.click_settle_delay,
        )

    def _scroll_page(self, window, current_screenshot) -> bool:
        """滚动到更早消息，并验证截图是否发生变化。"""
        # 聚焦窗口一次，后续滚动不再重复聚焦
        focus_window_for_scroll(
            window,
            x_ratio=self.config.automation.scroll_focus_x_ratio,
            y_ratio=self.config.automation.scroll_focus_y_ratio,
            click=False,
        )

        # 直接滚动，无需每次重新聚焦窗口
        scroll_step_delay = 0.05
        for _ in range(self.config.automation.scrolls_per_page):
            pyautogui.scroll(self.config.automation.scroll_amount * WHEEL_DELTA)
            time.sleep(scroll_step_delay)

        wait(0.5)
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
                delay=scroll_step_delay,
                x_ratio=self.config.automation.scroll_focus_x_ratio,
                y_ratio=self.config.automation.scroll_focus_y_ratio,
            )

        wait(0.5)
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

    async def run_extraction(self, max_pages: int | None = None, dry_run: bool = False) -> dict:
        """Execute the full attendance extraction flow.

        New flow: batch capture screenshots, minimize DingTalk window,
        then analyze all screenshots in parallel to reduce window occupation.

        dry_run: 跳过 AI 分析，仅测试窗口激活和截图流程。
        """

        # 1. Activate DingTalk window
        window = activate_dingtalk(
            self.config.dingtalk.path,
            self.config.dingtalk.launch_wait,
        )
        if window is None:
            if is_dingtalk_running():
                return {'status': 'error', 'message': 'DingTalk running but cannot find main window'}
            return {'status': 'error', 'message': 'DingTalk not running and failed to start'}

        self._prepare_work_notification(window)

        page_limit = self._page_limit(max_pages)
        logger.info(f'Max pages to capture this run: {page_limit}')

        # ---- Phase 1: Batch capture screenshots ----
        captured_pages = []
        for page in range(page_limit):
            logger.info(f'Capturing page {page + 1}...')

            screenshot = self._capture_content(window)

            if self.screenshot_mgr.is_mostly_blank(screenshot):
                logger.warning('Screenshot is blank, stopping capture')
                break

            screenshot_path = self.screenshot_mgr.save(screenshot)
            base64_img = self.screenshot_mgr.to_base64(screenshot)
            captured_pages.append({
                'screenshot': screenshot,
                'screenshot_path': screenshot_path,
                'base64_img': base64_img,
                'page_num': page + 1,
            })

            if page >= page_limit - 1:
                logger.info('Reached max capture pages')
                break

            if not self._scroll_page(window, screenshot):
                logger.info('Reached top or cannot scroll further, stopping capture')
                break

        # Capture done, close DingTalk window (退到系统托盘)
        close_window(window)
        logger.info(
            f'Capture phase done, {len(captured_pages)} pages captured, DingTalk closed to tray'
        )

        if not captured_pages:
            return {
                'status': 'ok',
                'pages_scanned': 0,
                'records_found': 0,
                'records': [],
            }

        if dry_run:
            logger.info(f'dry_run: 跳过 AI 分析，已捕获 {len(captured_pages)} 页')
            return {
                'status': 'ok',
                'pages_scanned': len(captured_pages),
                'records_found': 0,
                'records': [],
            }

        # ---- Phase 2: Parallel AI analysis ----
        async def _analyze_page(page_data: dict):
            result = await self.vision.extract_from_image(page_data['base64_img'])
            return result, page_data

        analysis_tasks = [_analyze_page(p) for p in captured_pages]
        analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)

        # ---- Phase 3: Aggregate and store records ----
        all_records = []
        pages_scanned = 0

        for idx, analysis_result in enumerate(analysis_results):
            page_data = captured_pages[idx]
            page_num = page_data['page_num']

            if isinstance(analysis_result, Exception):
                logger.error(f'Page {page_num} AI analysis failed: {analysis_result}')
                continue

            result, _ = analysis_result
            records = result.get('records', [])
            pages_scanned += 1
            logger.info(f'Page {page_num}: extracted {len(records)} records')

            inserted_count = 0
            updated_count = 0
            skipped_count = 0
            ignored_count = 0
            for record_data in records:
                record_data['raw_text'] = str(result)
                record_data['screenshot_path'] = page_data['screenshot_path']
                with self.db_session_factory() as db:
                    upsert_result = upsert_record(db, record_data)
                    if upsert_result['action'] == 'inserted':
                        inserted_count += 1
                    elif upsert_result['action'] == 'updated':
                        updated_count += 1
                    elif upsert_result['action'] == 'skipped':
                        skipped_count += 1
                    elif upsert_result['action'] == 'ignored':
                        ignored_count += 1

                    if upsert_result['action'] in {'inserted', 'updated'}:
                        all_records.append(upsert_result['record'])

            if records:
                logger.info(
                    f'Page {page_num}: inserted {inserted_count}, updated {updated_count}, '
                    f'skipped {skipped_count}, ignored {ignored_count}'
                )

        return {
            'status': 'ok',
            'pages_scanned': pages_scanned,
            'records_found': len(all_records),
            'records': all_records,
        }
