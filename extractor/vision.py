# extractor/vision.py
import json
import logging
import re
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
- 只返回JSON，不要其他文字"""


class VisionExtractor:
    def __init__(self, api_base: str, api_key: str, model: str, max_tokens: int = 2000):
        self.client = AsyncOpenAI(base_url=api_base, api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def extract_from_image(self, base64_image: str) -> dict:
        """从base64图片提取考勤数据。返回解析后的dict。"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": EXTRACT_PROMPT},
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
            content = response.choices[0].message.content
            return self._parse_response(content)
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return {"records": [], "has_more": False, "page_reached_top": True}

    def _parse_response(self, content: str) -> dict:
        """解析LLM返回的JSON。"""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    logger.warning(f"无法解析LLM返回: {content[:200]}")
                    return {"records": [], "has_more": False, "page_reached_top": True}
            else:
                logger.warning(f"无法解析LLM返回: {content[:200]}")
                return {"records": [], "has_more": False, "page_reached_top": True}

        data.setdefault("records", [])
        data.setdefault("has_more", False)
        data.setdefault("page_reached_top", True)
        return data
