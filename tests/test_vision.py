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
    assert result["has_more"] is True
    assert result["page_reached_top"] is False
    assert result["error"] == "parse_failed"


@pytest.mark.asyncio
async def test_extract_retries_after_invalid_json():
    extractor = VisionExtractor(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        model="gpt-4o",
    )

    invalid_response = MagicMock()
    invalid_response.choices = [MagicMock()]
    invalid_response.choices[0].message.content = '{"records": [{"punch_type": "下班打卡"'

    valid_response = MagicMock()
    valid_response.choices = [MagicMock()]
    valid_response.choices[0].message.content = MOCK_LLM_RESPONSE

    create_mock = AsyncMock(side_effect=[invalid_response, valid_response])
    with patch.object(extractor.client.chat.completions, "create", create_mock):
        result = await extractor.extract_from_image("fake_base64")

    assert create_mock.await_count == 2
    assert len(result["records"]) == 1
    assert result["records"][0]["punch_time"] == "17:35"


@pytest.mark.asyncio
async def test_extract_rechecks_empty_result():
    extractor = VisionExtractor(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        model="gpt-4o",
    )

    empty_response = MagicMock()
    empty_response.choices = [MagicMock()]
    empty_response.choices[0].message.content = json.dumps({
        "records": [],
        "has_more": False,
        "page_reached_top": True,
    })

    valid_response = MagicMock()
    valid_response.choices = [MagicMock()]
    valid_response.choices[0].message.content = MOCK_LLM_RESPONSE

    create_mock = AsyncMock(side_effect=[empty_response, valid_response])
    with patch.object(extractor.client.chat.completions, "create", create_mock):
        result = await extractor.extract_from_image("fake_base64")

    assert create_mock.await_count == 2
    assert len(result["records"]) == 1


def test_parse_response_extracts_json_from_text():
    extractor = VisionExtractor(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        model="gpt-4o",
    )

    data = extractor._parse_response(f"下面是结果：\n{MOCK_LLM_RESPONSE}\n结束")

    assert data["records"][0]["punch_time"] == "17:35"


def test_normalize_result_infers_date_and_fields():
    extractor = VisionExtractor(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        model="gpt-4o",
    )

    result = extractor._normalize_result({
        "records": [
            {
                "punch_type": "",
                "punch_time": "7：5",
                "punch_result": "07:05 上班打卡·成功",
                "punch_status": "",
                "shift_time": "06月12日 08:30上班",
                "punch_method": "考勤机打卡",
                "device_info": "G2",
                "notes": "",
                "record_date": "",
            }
        ],
        "has_more": "true",
        "page_reached_top": "false",
    })

    assert result["records"][0]["punch_type"] == "上班打卡"
    assert result["records"][0]["punch_time"] == "07:05"
    assert result["records"][0]["record_date"].endswith("-06-12")
    assert result["records"][0]["punch_status"] == "成功"
    assert result["has_more"] is True


def test_normalize_result_ignores_invalid_and_selects_preferred_records():
    extractor = VisionExtractor(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        model="gpt-4o",
    )

    result = extractor._normalize_result({
        "records": [
            {
                "punch_type": "上班打卡",
                "punch_time": "08:09",
                "punch_result": "08:09 打卡·无效",
                "punch_status": "无效",
                "shift_time": "06月12日 08:30上班",
                "punch_method": "考勤机打卡",
                "device_info": "G2门禁机KN6895",
                "notes": "已经打过卡了，上班时间以最早打卡时间为准",
                "record_date": "2026-06-12",
            },
            {
                "punch_type": "上班打卡",
                "punch_time": "08:02",
                "punch_result": "08:02 上班打卡·成功",
                "punch_status": "成功",
                "shift_time": "06月12日 08:30上班",
                "record_date": "2026-06-12",
            },
            {
                "punch_type": "上班打卡",
                "punch_time": "07:53",
                "punch_result": "07:53 上班打卡·成功",
                "punch_status": "成功",
                "shift_time": "06月12日 08:30上班",
                "record_date": "2026-06-12",
            },
            {
                "punch_type": "下班打卡",
                "punch_time": "18:38",
                "punch_result": "18:38 下班打卡·成功",
                "punch_status": "成功",
                "shift_time": "06月12日 17:30下班",
                "record_date": "2026-06-12",
            },
            {
                "punch_type": "下班打卡",
                "punch_time": "19:20",
                "punch_result": "19:20 下班打卡·成功",
                "punch_status": "成功",
                "shift_time": "06月12日 17:30下班",
                "record_date": "2026-06-12",
            },
        ],
        "has_more": True,
        "page_reached_top": False,
    })

    assert len(result["records"]) == 2
    by_type = {record["punch_type"]: record for record in result["records"]}
    assert by_type["上班打卡"]["punch_time"] == "07:53"
    assert by_type["下班打卡"]["punch_time"] == "19:20"


@pytest.mark.asyncio
async def test_extract_recovers_records_from_truncated_json():
    extractor = VisionExtractor(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        model="gpt-4o",
        parse_retry_count=0,
        empty_result_retry_count=0,
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = """
{
  "records": [
    {
      "punch_type": "下班打卡",
      "punch_time": "18:38",
      "punch_result": "18:38 下班打卡•成功",
      "punch_status": "成功",
      "shift_time": "06月12日 17:30下班",
      "punch_method": "考勤机打卡",
      "device_info": "G2门禁机KN6895",
      "notes": "",
      "record_date": "2026-06-12"
    }
"""

    with patch.object(extractor.client.chat.completions, "create",
                      new_callable=AsyncMock, return_value=mock_response):
        result = await extractor.extract_from_image("fake_base64")

    assert len(result["records"]) == 1
    assert result["records"][0]["punch_time"] == "18:38"
    assert result["records"][0]["record_date"] == "2026-06-12"
    assert result["has_more"] is True
