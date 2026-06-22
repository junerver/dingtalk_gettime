# tests/test_vision.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from extractor.vision import VisionExtractor


MOCK_LLM_RESPONSE = json.dumps({
    "records": [
        {
            "punch_type": "下班打卡",
            "punch_time": "17:35",
            "punch_result": "✅ 17:35 下班打卡·成功",
            "punch_status": "成功",
            "shift_time": "06月18日 17:30下班",
            "punch_method": "考勤机打卡",
            "device_info": "G2门禁机KN6895",
            "notes": "下班打卡时间已更新到17:35",
            "record_date": "2026-06-18",
        }
    ],
    "has_more": True,
    "page_reached_top": False,
})


@pytest.mark.asyncio
async def test_extract_from_base64():
    extractor = VisionExtractor(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        model="gpt-4o",
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = MOCK_LLM_RESPONSE

    with patch.object(extractor.client.chat.completions, "create",
                      new_callable=AsyncMock, return_value=mock_response):
        result = await extractor.extract_from_image("fake_base64_string")

    assert len(result["records"]) == 1
    assert result["records"][0]["punch_time"] == "17:35"
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_extract_handles_invalid_json():
    extractor = VisionExtractor(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        model="gpt-4o",
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "这不是JSON"

    with patch.object(extractor.client.chat.completions, "create",
                      new_callable=AsyncMock, return_value=mock_response):
        result = await extractor.extract_from_image("fake_base64")

    assert result["records"] == []
    assert result["has_more"] is False
