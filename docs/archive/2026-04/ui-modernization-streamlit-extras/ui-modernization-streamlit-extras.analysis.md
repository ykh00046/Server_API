# Gap Analysis: ui-modernization-streamlit-extras

- **Date**: 2026-04-15
- **Phase**: PDCA Check
- **Match Rate**: **97%**
- **Status**: ✅ Above 90% threshold → proceed to Report (no Act iteration needed)

## Scope

| Type | Path |
|---|---|
| Plan | `docs/01-plan/features/ui-modernization-streamlit-extras.plan.md` |
| Design | `docs/02-design/features/ui-modernization-streamlit-extras.design.md` |
| Impl | `api/_chat_stream.py`, `api/chat.py`, `tests/test_chat_stream.py`, `shared/ui/theme.py`, `dashboard/components/ai_section.py`, `dashboard/components/kpi_cards.py`, `requirements.txt`, `dashboard/app.py` |

## Design-by-design verification

| Design § | Spec | Implementation | Status |
|---|---|---|---|
| §2.1 | `POST /chat/stream`, text/event-stream + cache/buffering headers | `chat.py` → `streaming_response()` sets `Cache-Control:no-cache`, `X-Accel-Buffering:no`, `Connection:keep-alive` | ✅ |
| §2.1 | Rate limit reuse before stream | `chat.py:351` calls `_enforce_rate_limit` pre-stream | ✅ |
| §2.2 | Event order `meta → [tool_call]* → token+ → done` | `_chat_stream.py` emits in order; `test_stream_tool_call_event` asserts order | ✅ |
| §2.2 | tool_call from `candidates.parts.function_call` with dedup | `_chat_stream.py:84–96`, `tools_emitted` set | ✅ |
| §2.3 | `_sse()` helper with `ensure_ascii=False` | `_chat_stream.py:36` | ✅ |
| §2.3 | `run_stream()` signature (query/session_id/client_ip/request_id/system_instruction) | `_chat_stream.py:39–45` exact | ✅ |
| §2.3 | Persist session only after successful completion | `_chat_stream.py:116` post-loop | ✅ |
| §2.3 | Mid-stream error → `event: error` then return | `_chat_stream.py:103–110` | ✅ |
| §2.4 | Route wiring reuses `_enforce_rate_limit`, `_cleanup_expired_sessions`, `_build_system_instruction`, `ChatRequest` | `chat.py:348–361` exact | ✅ |
| §3.1 | `client.aio.models.generate_content_stream` + None-check on `chunk.text` | `_chat_stream.py:74,99` | ✅ |
| §3.2 | No retry on streaming | `run_stream` contains no retry; `_generate_with_retry` stays in sync `/chat/` | ✅ |
| §4.1 | httpx SSE client: toast on tool_call, error surface, `_last_chat_meta` on done | `ai_section.py:56–102` exact | ✅ |
| §4.2 | `st.write_stream` integration | `ai_section.py:300` | ✅ |
| §4.3 | shadcn starter cards with try/except fallback | `ai_section.py:20–25` (`_HAS_SHADCN`), `_render_starter_card` at 105–125 | ✅ |
| §5.1 | `TOKENS_LIGHT/DARK/HIGH_CONTRAST` + `apply_custom_css` injection | `theme.py:47–98,222–234` | ✅ |
| §5.2 | No hardcoded `#667eea`/`#764ba2` in `dashboard/components/` | grep returns 0 matches | ✅ |
| §5.3 | Sidebar 4-mode toggle + `apply_custom_css` called from `app.py` | `app.py:61–62`; `render_theme_toggle` with `auto/light/dark/high-contrast` | ✅ |
| §6 | `requirements.txt`: httpx + streamlit-shadcn-ui | lines 17–18 | ✅ |
| §7.1 | 6 new SSE tests | `meta_first`, `tokens_and_done`, `tool_call_event`, `rate_limited`, `session_persisted`, `error_event_when_client_missing` — all present | ✅ |
| §10 | 134+ existing + ≥6 new tests pass | 136 + 6 = **142 pass** | ✅ |
| §10 | Playwright desktop/tablet + high-contrast render | Verified: 1440×900, 1024×768, high-contrast mode | ✅ |
| §10 | High-contrast ≥ 4.5:1 (WCAG AA) | `#000000` on `#ffffff` → 21:1 | ✅ |

## Gap List

- **Missing (Design O, Impl X):** none
- **Added (Design X, Impl O):** none
- **Changed (Design ≠ Impl):** none critical

## Advisory (non-blocking)

1. `ai_section.py:181` references Streamlit built-in `--text-color` instead of project token `var(--color-text)`. Harmless but inconsistent with token-only policy in §5.2.
2. `requirements.txt` does not pin `streamlit>=1.31` (§12 Open Item). Runtime works on 1.54.
3. kpi_cards sparkline color uses `CHART_COLORS[mode]` (Python lookup) rather than pure CSS var — acceptable because Streamlit-rendered sparkline SVG cannot consume CSS custom properties from Python context.

## Score Breakdown

| Category | Score |
|---|---|
| API contract (§2) | 100% |
| Gemini streaming (§3) | 100% |
| Frontend SSE + shadcn (§4) | 100% |
| CSS token system (§5) | 95% |
| File change plan (§6) | 100% |
| Tests (§7) | 100% |
| Success criteria (§10) | 100% |
| **Overall** | **97%** |

## Verification During Do Phase

- Bug found & fixed: `render_ai_section()` default api_url was `/chat/` (old non-streaming endpoint), causing UI to bypass the new SSE path. Corrected to `/chat/stream`.
- End-to-end streaming verified via Playwright: query "한 줄로만 인사해줘" → streamed response "안녕하세요! 무엇을 도와드릴까요?" in ~1.8s.

## Recommendation

Match rate **97% ≥ 90%** → **skip Act (iterate)** and proceed directly to **Report** phase:

```
/pdca report ui-modernization-streamlit-extras
```
