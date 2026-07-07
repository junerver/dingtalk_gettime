# extractor/vision.py
import json
import logging
import re
from datetime import datetime
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """请分析这张钉钉"工作通知"截图中的考勤打卡信息。
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
- 忽略"打卡·无效"、"打卡-无效"、"无效原因"等无效打卡卡片，不要放入records
- 同一日期同一类型有多条有效打卡时：上班打卡只保留最早时间，下班打卡只保留最晚时间
- 必须返回一个完整、可被 json.loads 直接解析的JSON对象
- 不要返回Markdown代码块，不要返回解释文字
- 不确定的字段返回空字符串，不要省略字段"""

PARSE_RETRY_SUFFIX = """

上一次返回不是完整可解析JSON。请重新读取同一张图片，只返回完整JSON对象，确保双引号、逗号、括号全部闭合。"""

EMPTY_RECHECK_SUFFIX = """

上一次没有提取到记录。请重新检查图片中每一条工作通知卡片，只要存在有效的上班打卡、下班打卡、打卡成功、迟到、早退、缺卡等考勤信息，就必须提取为records；"打卡·无效"不属于有效记录。"""

STITCHED_IMAGE_INSTRUCTIONS = """

这张图片由多页钉钉工作通知截图按上下方向拼接而成。请按从上到下的顺序阅读整张图片，拼接边界不代表记录中断；后截取到的更早记录页面在上方，先截取到的较晚记录页面在下方。"""

RECORD_FIELDS = (
    "punch_type",
    "punch_time",
    "punch_result",
    "punch_status",
    "shift_time",
    "punch_method",
    "device_info",
    "notes",
    "record_date",
)


class LLMResponseParseError(ValueError):
    pass


class VisionExtractor:
    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        max_tokens: int = 4000,
        parse_retry_count: int = 2,
        empty_result_retry_count: int = 1,
    ):
        self.client = AsyncOpenAI(base_url=api_base, api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.parse_retry_count = parse_retry_count
        self.empty_result_retry_count = empty_result_retry_count

    async def extract_from_image(self, base64_image: str, image_instructions: str = "") -> dict:
        """从base64图片提取考勤数据。返回解析后的dict。"""
        parse_failures = 0
        request_failures = 0
        empty_retries = 0
        prompt_suffix = ""
        last_partial_result = None

        while True:
            prompt = self._build_prompt(prompt_suffix, image_instructions=image_instructions)
            try:
                content = await self._request_completion(base64_image, prompt)
            except Exception as e:
                request_failures += 1
                logger.warning(f"LLM调用失败，准备重试: {e}")
                if request_failures > self.parse_retry_count:
                    logger.error(f"LLM调用多次失败: {e}")
                    return self._fallback_result("request_failed")
                prompt_suffix = PARSE_RETRY_SUFFIX
                continue

            try:
                data = self._parse_response(content)
                result = self._normalize_result(data)
            except LLMResponseParseError:
                parse_failures += 1
                partial_result = self._partial_result(content)
                if partial_result and partial_result["records"]:
                    last_partial_result = partial_result
                    logger.warning(
                        "LLM返回不是完整JSON，已从片段中临时恢复 "
                        f"{len(partial_result['records'])} 条记录，将继续重试确认"
                    )
                logger.warning(
                    "无法解析LLM返回，准备重试 "
                    f"({parse_failures}/{self.parse_retry_count}): "
                    f"{self._preview(content)}"
                )
                if parse_failures > self.parse_retry_count:
                    if last_partial_result and last_partial_result["records"]:
                        logger.warning("LLM返回连续解析失败，使用从片段中恢复的记录")
                        return last_partial_result
                    logger.error("LLM返回连续解析失败，放弃当前截图")
                    return self._fallback_result("parse_failed")
                prompt_suffix = PARSE_RETRY_SUFFIX
                continue

            if result["records"]:
                return result
            if empty_retries >= self.empty_result_retry_count:
                if last_partial_result and last_partial_result["records"]:
                    logger.warning("LLM复核仍为空，使用从片段中恢复的记录")
                    return last_partial_result
                return result

            empty_retries += 1
            logger.info(
                "LLM本页提取到0条记录，进行复核 "
                f"({empty_retries}/{self.empty_result_retry_count})"
            )
            prompt_suffix = EMPTY_RECHECK_SUFFIX

    def _build_prompt(self, suffix: str = "", image_instructions: str = "") -> str:
        current_date = datetime.now().strftime("%Y-%m-%d")
        return (
            f"当前日期是 {current_date}。如果截图只显示月日，请按当前年份推断record_date。\n\n"
            f"{EXTRACT_PROMPT}{image_instructions}{suffix}"
        )

    async def _request_completion(self, base64_image: str, prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content or ""

    def _parse_response(self, content: str) -> dict:
        """解析LLM返回的JSON。"""
        for candidate in self._json_candidates(content):
            for text in (candidate, self._sanitize_json(candidate)):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue
        raise LLMResponseParseError("LLM response is not valid JSON")

    def _json_candidates(self, content: str) -> list[str]:
        content = (content or "").strip()
        candidates = []
        if content:
            candidates.append(content)

        for match in re.finditer(r"```(?:json)?\s*(.*?)```", content, re.DOTALL | re.IGNORECASE):
            candidates.append(match.group(1).strip())

        candidates.extend(self._balanced_json_substrings(content))

        seen = set()
        unique_candidates = []
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)
        return unique_candidates

    def _balanced_json_substrings(self, text: str) -> list[str]:
        substrings = []
        start = None
        stack = []
        in_string = False
        escaped = False

        for idx, char in enumerate(text):
            if start is None:
                if char in "{[":
                    start = idx
                    stack = [char]
                continue

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char in "{[":
                stack.append(char)
            elif char in "}]":
                if not stack or not self._brackets_match(stack[-1], char):
                    start = None
                    stack = []
                    continue
                stack.pop()
                if not stack:
                    substrings.append(text[start:idx + 1])
                    start = None

        return substrings

    def _partial_result(self, content: str) -> dict | None:
        records = []
        seen = set()
        for candidate in self._balanced_json_substrings_from_each_start(content or ""):
            try:
                data = json.loads(self._sanitize_json(candidate))
            except json.JSONDecodeError:
                continue
            if not self._looks_like_record_object(data):
                continue
            marker = json.dumps(data, ensure_ascii=False, sort_keys=True)
            if marker in seen:
                continue
            seen.add(marker)
            records.append(data)

        if not records:
            return None
        return self._normalize_result({
            "records": records,
            "has_more": True,
            "page_reached_top": False,
        })

    def _balanced_json_substrings_from_each_start(self, text: str) -> list[str]:
        substrings = []
        for idx, char in enumerate(text):
            if char not in "{[":
                continue
            substring = self._balanced_json_from_start(text, idx)
            if substring:
                substrings.append(substring)
        return substrings

    def _balanced_json_from_start(self, text: str, start: int) -> str | None:
        stack = [text[start]]
        in_string = False
        escaped = False

        for idx in range(start + 1, len(text)):
            char = text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char in "{[":
                stack.append(char)
            elif char in "}]":
                if not stack or not self._brackets_match(stack[-1], char):
                    return None
                stack.pop()
                if not stack:
                    return text[start:idx + 1]

        return None

    def _looks_like_record_object(self, data) -> bool:
        if not isinstance(data, dict):
            return False
        if not any(field in data for field in RECORD_FIELDS):
            return False
        combined = " ".join(
            self._clean_text(data.get(field, ""))
            for field in RECORD_FIELDS
        )
        return bool(
            "打卡" in combined
            or "上班" in combined
            or "下班" in combined
            or re.search(r"\d{1,2}[:：]\d{1,2}", combined)
        )

    def _sanitize_json(self, text: str) -> str:
        text = text.strip().lstrip("\ufeff")
        return re.sub(r",\s*([}\]])", r"\1", text)

    def _normalize_result(self, data) -> dict:
        if isinstance(data, list):
            data = {"records": data}
        if not isinstance(data, dict):
            raise LLMResponseParseError("LLM response root is not an object")

        records = data.get("records", [])
        if not isinstance(records, list):
            records = []

        normalized_records = []
        discarded = 0
        for record in records:
            normalized = self._normalize_record(record)
            if normalized:
                normalized_records.append(normalized)
            else:
                discarded += 1

        if discarded:
            logger.warning(f"丢弃 {discarded} 条字段不足或无效的LLM记录")

        normalized_records = self._select_preferred_records(normalized_records)

        return {
            "records": normalized_records,
            "has_more": self._to_bool(data.get("has_more"), default=False),
            "page_reached_top": self._to_bool(data.get("page_reached_top"), default=True),
        }

    def _normalize_record(self, record) -> dict | None:
        if not isinstance(record, dict):
            return None

        normalized = {
            field: self._clean_text(record.get(field, ""))
            for field in RECORD_FIELDS
        }

        normalized["punch_type"] = self._normalize_punch_type(
            normalized["punch_type"] or normalized["punch_result"]
        )
        normalized["punch_time"] = self._normalize_time(
            normalized["punch_time"] or normalized["punch_result"]
        )
        normalized["record_date"] = self._normalize_date(
            normalized["record_date"]
        ) or self._infer_record_date(normalized)
        normalized["punch_status"] = self._normalize_status(
            normalized["punch_status"] or normalized["punch_result"]
        )

        if self._is_invalid_record(normalized):
            return None

        if not normalized["punch_type"] or not normalized["record_date"]:
            return None

        return normalized

    def _select_preferred_records(self, records: list[dict]) -> list[dict]:
        selected = {}
        order = []

        for record in records:
            key = (
                record.get("employee_name"),
                record.get("record_date"),
                record.get("punch_type"),
            )
            if key not in selected:
                selected[key] = record
                order.append(key)
                continue

            selected[key] = self._preferred_record(selected[key], record)

        return [selected[key] for key in order]

    def _preferred_record(self, current: dict, candidate: dict) -> dict:
        punch_type = candidate.get("punch_type")
        current_minutes = self._record_minutes(current)
        candidate_minutes = self._record_minutes(candidate)

        if candidate_minutes is None:
            return current
        if current_minutes is None:
            return candidate

        if punch_type == "上班打卡" and candidate_minutes < current_minutes:
            return candidate
        if punch_type == "下班打卡" and candidate_minutes > current_minutes:
            return candidate

        return current

    def _record_minutes(self, record: dict) -> int | None:
        value = record.get("punch_time") or record.get("punch_result")
        match = re.search(r"(\d{1,2})[:：](\d{1,2})", value or "")
        if not match:
            return None

        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour > 23 or minute > 59:
            return None
        return hour * 60 + minute

    def _is_invalid_record(self, record: dict) -> bool:
        combined = " ".join(str(record.get(field, "") or "") for field in RECORD_FIELDS)
        return "无效" in combined

    def _clean_text(self, value) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _normalize_punch_type(self, value: str) -> str:
        if "上班" in value:
            return "上班打卡"
        if "下班" in value:
            return "下班打卡"
        return value.strip()

    def _normalize_time(self, value: str) -> str:
        value = value.replace("：", ":")
        match = re.search(r"(\d{1,2}):(\d{1,2})", value)
        if not match:
            return value.strip()
        return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"

    def _normalize_date(self, value: str) -> str:
        value = value.replace("/", "-").replace(".", "-").strip()
        match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
        if match:
            return (
                f"{int(match.group(1)):04d}-"
                f"{int(match.group(2)):02d}-"
                f"{int(match.group(3)):02d}"
            )

        match = re.search(r"(\d{1,2})月(\d{1,2})日", value)
        if match:
            return self._date_from_month_day(match)

        return ""

    def _infer_record_date(self, record: dict) -> str:
        text = " ".join(
            record.get(field, "")
            for field in ("shift_time", "punch_result", "notes")
        )
        match = re.search(r"(\d{1,2})月(\d{1,2})日", text)
        if not match:
            return ""
        return self._date_from_month_day(match)

    def _date_from_month_day(self, match) -> str:
        year = datetime.now().year
        return f"{year:04d}-{int(match.group(1)):02d}-{int(match.group(2)):02d}"

    def _normalize_status(self, value: str) -> str:
        if "无效" in value:
            return "无效"
        for status in ("成功", "迟到", "早退", "缺卡"):
            if status in value:
                return status
        return value.strip()

    def _to_bool(self, value, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "是", "有"}:
                return True
            if normalized in {"false", "0", "no", "n", "否", "无"}:
                return False
        return default

    def _fallback_result(self, reason: str) -> dict:
        return {
            "records": [],
            "has_more": True,
            "page_reached_top": False,
            "error": reason,
        }

    def _preview(self, content: str, limit: int = 800) -> str:
        return (content or "").replace("\n", "\\n")[:limit]

    def _brackets_match(self, opening: str, closing: str) -> bool:
        return (opening == "{" and closing == "}") or (opening == "[" and closing == "]")
