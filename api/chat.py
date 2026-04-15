# api/chat.py
"""
Production Data Hub - AI Chat Endpoint

Provides natural language query interface using Google GenAI SDK.
Enhanced logging for tool call tracking and error diagnosis.

Migrated from deprecated google-generativeai to google-genai (2026-01)
Features:
- Automatic retry with exponential backoff + jitter for 429/5xx errors
- Token usage logging
- Tool call tracking
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import time
from datetime import date
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from dotenv import load_dotenv

# Add parent directory to path for shared module import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import get_logger
from shared.config import GEMINI_MODEL
from shared.logging_config import get_request_id
from shared.rate_limiter import chat_rate_limiter

# Load Environment Variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logger = get_logger(__name__)

# GenAI client factory extracted to api/_gemini_client.py (Act-1).
from ._gemini_client import get_client as _get_client  # noqa: F401
# Tool registry extracted to api/_tool_dispatch.py (Act-1).
from ._tool_dispatch import PRODUCTION_TOOLS

router = APIRouter(prefix="/chat", tags=["AI Chat"])


# ==========================================================
# Retry Configuration (Section 6.1)
# ==========================================================
MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds
MAX_TOTAL_DELAY = 15.0  # seconds
RETRYABLE_STATUS_CODES = {429, 500, 503}


# ==========================================================
# Multi-turn Session Store (extracted to api/_session_store.py in Act-1)
# ==========================================================
from . import _session_store as _sstore
# Re-exports for backward compatibility (tests + call sites).
_sessions = _sstore._sessions
SESSION_TTL = _sstore.SESSION_TTL
SESSION_MAX_TURNS = _sstore.SESSION_MAX_TURNS
SESSION_MAX_COUNT = _sstore.SESSION_MAX_COUNT
SESSION_CLEANUP_INTERVAL = _sstore.SESSION_CLEANUP_INTERVAL
CHAT_SESSION_MAX_PER_IP = _sstore.CHAT_SESSION_MAX_PER_IP
_get_session_history = _sstore.get_session_history
_save_session_history = _sstore.save_session_history
_cleanup_expired_sessions = _sstore.cleanup_expired_sessions


def _get_cleanup_counter() -> int:
    return _sstore._cleanup_counter


def _set_cleanup_counter(v: int) -> None:
    _sstore._cleanup_counter = v


# Test compatibility: some tests assign to `chat_mod._cleanup_counter`.
# Attribute access is redirected via module __getattr__/__setattr__ below.


# ==========================================================
# Models
# ==========================================================
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User query text")
    session_id: str | None = Field(default=None, max_length=100, description="Multi-turn session ID")


class ChatResponse(BaseModel):
    answer: str
    status: str = "success"
    tools_used: List[str] = []
    request_id: str = ""  # 요청 추적용 ID


# ==========================================================
# System Instruction Builder (Dynamic date)
# ==========================================================
def _build_system_instruction() -> str:
    """Build system instruction with current date."""
    today = date.today()
    weekdays = ['월', '화', '수', '목', '금', '토', '일']
    weekday_name = weekdays[today.weekday()]
    date_str = f"{today.year}년 {today.month}월 {today.day}일 {weekday_name}요일"
    current_year = today.year
    last_year = current_year - 1

    return f"""
너는 'Production Data Hub' 시스템의 전문 생산 데이터 분석가야.
사용자의 질문을 분석하여, 제공된 도구(Tools)를 사용하여 정확한 데이터를 조회하고 답변해줘.

[데이터 조회 규칙]
1. 사용자가 제품 이름(예: 'P물', '에이제품')이나 키워드로 물어보면, 반드시 `search_production_items` 도구를 먼저 사용하여 실제 제품 코드(item_code)를 확인해.
2. "작년", "{last_year}년", "단종", "예전", "과거" 같은 표현이 있으면 include_archive=True로 검색해. (기본값이 True이므로 대부분 그대로 두면 됨)
3. "올해", "최근", "현재 제품만" 같은 표현이 있으면 include_archive=False로 검색해.
4. 제품 코드를 확인한 후에만 `get_production_summary`를 사용하여 수치를 조회해.
5. 월별 추이나 기간별 흐름을 물어보면 `get_monthly_trend`를 사용해. 특정 제품의 추이가 궁금하면 item_code를 함께 넣어줘.
6. "가장 많이 생산된", "상위 제품", "순위", "랭킹" 등을 물어보면 `get_top_items`를 사용해.
7. "이번 달 vs 저번 달", "올해 vs 작년", "전월 대비", "비교", "대비", "차이" 같은 표현이 있으면 `compare_periods`를 사용해.
8. "최근 이력", "마지막 N건", "언제 만들었어", "최근 생산" 같은 표현이 있으면 `get_item_history`를 사용해.
9. 복잡한 조건(로트번호 패턴, 다중 필터 등)이 필요하면 `execute_custom_query`로 직접 SQL을 작성해. 사용 가능한 컬럼: production_date, item_code, item_name, good_quantity, lot_number
10. 데이터가 없으면 추측하지 말고 "조회된 데이터가 없습니다"라고 정직하게 말해.
11. 오늘 날짜는 {date_str}이야. '올해'는 {current_year}년, '작년'은 {last_year}년을 의미해.

[답변 형식 — 반드시 지켜야 할 규칙]
1. **항상 Markdown 표(table)를 사용해.** 순위, 비교, 요약, 이력 등 데이터가 포함된 답변에는 반드시 표를 만들어.
   번호 리스트(1. 2. 3.)로 데이터를 나열하지 마. 표가 훨씬 읽기 좋아.
2. 수치 데이터에는 반드시 **천 단위 구분자(,)와 단위(개, 건 등)**를 붙여줘.
3. 답변의 근거가 된 **조회 기간**을 첫 줄에 명시해.

[분석적 답변 — 단순 조회가 아닌 인사이트 제공]
1. 데이터 조회 후 반드시 **분석적 해석**을 1-2문장 추가해.
   - 예: "B0061이 전체의 46%를 차지하며 압도적 1위입니다."
   - 예: "전월 대비 51% 증가는 신규 수주 증가와 연관될 수 있습니다."
   - 예: "BW0021은 최근 7일 평균 550개로 안정적인 생산량을 유지합니다."
2. 가능하면 **관련 부가 정보**를 함께 제공해:
   - 순위 질문 → 각 제품의 **점유율(%)**을 계산해서 표에 포함
   - 기간 요약 → **전기 대비 증감률**을 추가 조회해서 언급
   - 특정 제품 질문 → **전체 대비 해당 제품의 비중**을 계산
   - 이력 질문 → **평균 생산량, 최대/최소** 같은 통계 요약 추가
3. 여러 도구를 **조합**해서 풍부한 답변을 만들어.
   예: "상위 5개 제품"을 물어보면 `get_top_items`로 순위를 얻고,
   추가로 `get_production_summary`나 `get_monthly_trend`를 사용해서
   1위 제품의 추이나 전체 비중도 함께 언급해.
4. 데이터가 0이거나 없으면 **이전 기간 데이터를 추가 조회**하여 참고 정보로 제공해.
   예: "해당 기간에 데이터가 없습니다. 대신 직전 30일(12/14~1/12) 데이터를 조회했습니다."

[어조]
- 친절하고 전문적인 어조를 사용해.
- 마무리에 "추가로 궁금한 점이 있으면 질문해 주세요" 같은 후속 안내를 짧게 넣어줘.
"""


def _is_retryable_error(e: Exception) -> tuple[bool, int]:
    """
    Check if the error is retryable.
    Returns (is_retryable, status_code).
    """
    status_code = 0

    if isinstance(e, (ClientError, ServerError)):
        status_code = getattr(e, 'status', 0) or 0
        # Extract status code from error message if not in attribute
        if status_code == 0:
            error_msg = str(e)
            for code in RETRYABLE_STATUS_CODES:
                if str(code) in error_msg:
                    status_code = code
                    break

        if status_code in RETRYABLE_STATUS_CODES:
            return True, status_code

    return False, status_code


def _calculate_delay(attempt: int) -> float:
    """
    Calculate delay with exponential backoff + jitter.
    Formula: min(base * 2^attempt + random_jitter, max_delay)

    v8: Added overflow protection by capping exponential base.
    """
    # Cap the exponential to prevent overflow (max 2^10 = 1024)
    capped_attempt = min(attempt, 10)
    exponential = BASE_DELAY * (2 ** capped_attempt)
    jitter = random.uniform(0, 1)  # Add 0-1 second random jitter
    # Use a reasonable max per-attempt delay (5 seconds)
    max_per_attempt_delay = 5.0
    delay = min(exponential + jitter, max_per_attempt_delay)
    return delay


def _enforce_rate_limit(client_ip: str, request_id: str) -> None:
    if chat_rate_limiter.is_allowed(client_ip):
        return
    retry_after = chat_rate_limiter.retry_after(client_ip)
    logger.warning(
        f"[Chat Rate Limited] request_id={request_id} | ip={client_ip} | "
        f"retry_after={retry_after}s"
    )
    raise HTTPException(
        status_code=429,
        detail={
            "code": "RATE_LIMITED",
            "message": f"Rate limit exceeded. Try again in {retry_after} seconds.",
        },
        headers={"Retry-After": str(retry_after)},
    )


def _ensure_ai_enabled(request_id: str):
    client_obj = _get_client()
    if client_obj is None:
        logger.error(f"[Chat] request_id={request_id} | API key not configured")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "AI_DISABLED",
                "message": "Gemini API Key is not configured.",
            },
        )
    return client_obj


async def _generate_with_retry(client_obj, contents, system_instruction, request_id, query_preview):
    """Run Gemini call with retry/backoff. Returns response or raises last_error."""
    last_error: Exception | None = None
    total_delay = 0.0
    for attempt in range(MAX_RETRIES):
        try:
            return await asyncio.to_thread(
                client_obj.models.generate_content,
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=PRODUCTION_TOOLS,
                ),
            )
        except (ClientError, ServerError) as e:
            last_error = e
            retryable, status_code = _is_retryable_error(e)
            if retryable and attempt < MAX_RETRIES - 1:
                delay = _calculate_delay(attempt)
                total_delay += delay
                if total_delay > MAX_TOTAL_DELAY:
                    logger.warning(
                        f"[Chat Retry] request_id={request_id} | "
                        f"delay budget exceeded ({total_delay:.1f}s)."
                    )
                    break
                logger.warning(
                    f"[Chat Retry] request_id={request_id} | status={status_code} | "
                    f"attempt={attempt+1}/{MAX_RETRIES} | delay={delay:.1f}s | error={e}"
                )
                await asyncio.sleep(delay)
                continue
            break
        except Exception as e:
            last_error = e
            break
    raise last_error if last_error else RuntimeError("Gemini call failed")


@router.post("/", response_model=ChatResponse)
async def chat_with_data(request: ChatRequest, http_request: Request):
    """Orchestrator: rate-limit → AI guard → call → persist session → respond."""
    request_id = get_request_id()
    start_time = time.perf_counter()
    client_ip = http_request.client.host if http_request.client else "unknown"

    _enforce_rate_limit(client_ip, request_id)
    client_obj = _ensure_ai_enabled(request_id)

    query_preview = request.query[:100] + ("..." if len(request.query) > 100 else "")
    logger.info(f"[Chat Request] request_id={request_id} | query='{query_preview}'")

    _cleanup_expired_sessions()
    history = _get_session_history(request.session_id, client_ip)
    user_content = types.Content(
        role="user", parts=[types.Part.from_text(text=request.query)]
    )
    contents = history + [user_content]

    try:
        response = await _generate_with_retry(
            client_obj, contents, _build_system_instruction(), request_id, query_preview
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            f"[Chat Error] request_id={request_id} | query='{query_preview}' | "
            f"error={type(e).__name__}: {e} | duration_ms={duration_ms:.1f}"
        )
        return ChatResponse(
            answer=_get_user_friendly_error(e),
            status="error",
            request_id=request_id,
        )

    tools_used, tool_calls_detail = _extract_tool_info(response, request_id)
    duration_ms = (time.perf_counter() - start_time) * 1000
    token_info = _log_token_usage(response, request_id)
    if tools_used:
        logger.info(
            f"[Chat Response] request_id={request_id} | tools_used={tools_used} | "
            f"tool_calls={tool_calls_detail} | {token_info} | duration_ms={duration_ms:.1f}"
        )
    else:
        logger.warning(
            f"[Chat Response] request_id={request_id} | NO TOOLS USED — potential hallucination | "
            f"query='{query_preview}' | {token_info} | duration_ms={duration_ms:.1f}"
        )

    if request.session_id:
        model_content = types.Content(
            role="model", parts=[types.Part.from_text(text=response.text)]
        )
        _save_session_history(
            request.session_id, history + [user_content, model_content], client_ip
        )

    return ChatResponse(
        answer=response.text, tools_used=tools_used, request_id=request_id
    )


def _extract_tool_info(response, request_id: str) -> tuple[List[str], List[str]]:
    """Extract tool usage information from response."""
    tools_used = []
    tool_calls_detail = []

    try:
        # Check candidates for function calls
        if hasattr(response, 'candidates') and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            tool_name = part.function_call.name
                            if tool_name not in tools_used:
                                tools_used.append(tool_name)
                                args = dict(part.function_call.args) if hasattr(part.function_call, 'args') else {}
                                tool_calls_detail.append(f"{tool_name}({args})")

        # Check automatic_function_calling_history
        if hasattr(response, 'automatic_function_calling_history'):
            for entry in response.automatic_function_calling_history:
                if hasattr(entry, 'parts'):
                    for part in entry.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            tool_name = part.function_call.name
                            if tool_name not in tools_used:
                                tools_used.append(tool_name)
                                args = dict(part.function_call.args) if hasattr(part.function_call, 'args') else {}
                                tool_calls_detail.append(f"{tool_name}({args})")

    except (IndexError, AttributeError, TypeError) as e:
        logger.warning(
            f"[Chat] request_id={request_id} | "
            f"Failed to extract tool info: {type(e).__name__}: {e}"
        )

    return tools_used, tool_calls_detail


def _log_token_usage(response, request_id: str) -> str:
    """Log and return token usage info."""
    token_info = ""
    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        um = response.usage_metadata
        prompt_tokens = getattr(um, 'prompt_token_count', 0)
        response_tokens = getattr(um, 'candidates_token_count', 0)
        total_tokens = getattr(um, 'total_token_count', 0)
        token_info = f"tokens(prompt={prompt_tokens}, response={response_tokens}, total={total_tokens})"
        logger.info(f"[Token Usage] request_id={request_id} | {token_info}")
    return token_info


def _get_user_friendly_error(e: Exception) -> str:
    """Return user-friendly error message based on error type."""
    error_str = str(e)

    if isinstance(e, ClientError):
        if '429' in error_str or 'quota' in error_str.lower():
            return (
                "죄송합니다. 현재 AI 서비스 사용량이 한도에 도달했습니다. "
                "잠시 후 다시 시도해 주세요. "
                "(무료 API 일일 한도 초과일 수 있습니다)"
            )
        elif '401' in error_str or '403' in error_str:
            return "AI 서비스 인증에 문제가 발생했습니다. 관리자에게 문의해 주세요."

    if isinstance(e, ServerError):
        return (
            "AI 서비스가 일시적으로 불안정합니다. "
            "잠시 후 다시 시도해 주세요."
        )

    return f"죄송합니다. 질문을 처리하는 중에 오류가 발생했습니다: {str(e)}"
