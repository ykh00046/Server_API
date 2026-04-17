# dashboard-code-quality Design Document

> **Feature**: dashboard-code-quality
> **Plan**: `docs/01-plan/features/dashboard-code-quality.plan.md`
> **Date**: 2026-04-17
> **Status**: Design

---

## 1. Implementation Details

### S3: mutable default api_url (ai_section.py)

**Before**: `def render_ai_chat(api_url: str = f"{API_BASE_URL}/chat/stream")`
**After**: `def render_ai_chat(api_url: str | None = None)` + `api_url = api_url or f"{API_BASE_URL}/chat/stream"` inside body.
**Files**: 3 functions — `render_ai_chat`, `render_ai_section`, `render_ai_section_compact`

### S4: unused key param (loading.py)

Remove `key: Optional[str] = None` from `show_skeleton_table`, `show_skeleton_kpi`, `show_skeleton_chart`.

### S5: UI string Korean (presets.py, loading.py)

| Current (English) | Target (Korean) |
|--------------------|-----------------|
| "Filter Presets" | "필터 프리셋" |
| "Load Preset" | "프리셋 불러오기" |
| "-- Select --" | "-- 선택 --" |
| "Apply" | "적용" |
| "Delete" | "삭제" |
| "New Preset Name" | "새 프리셋 이름" |
| "e.g., BW0021 Last 30 Days" | "예: BW0021 최근 30일" |
| "Save Current Filters" | "현재 필터 저장" |
| "Deleted '...'" | "'...' 삭제됨" |
| "Preset '...' saved!" | "프리셋 '...' 저장됨!" |
| "Please enter a preset name" | "프리셋 이름을 입력하세요" |
| "Presets: N/M" | "프리셋: N/M" |
| "Last updated:" | "마지막 업데이트:" |
| "Loaded from cache" | "캐시에서 로드됨" |
| "Fetched from database" | "데이터베이스에서 로드됨" |

### S2: sys.path.insert removal

**Approach**: Streamlit runs with CWD=`dashboard/`, so `from shared.xxx` needs parent in path. Instead of `sys.path.insert`, use `PYTHONPATH` env var set in service start scripts.

**Files**:
- `dashboard/app.py:15` — remove `sys.path.insert(0, ...)`
- `dashboard/data.py:20` — remove `sys.path.insert(0, ...)`
- `start_services_hidden.vbs` — add `PYTHONPATH=<project_root>` before streamlit launch
- Keep one `sys.path` setup only in `app.py` entrypoint (single source), remove from `data.py`

**Revised approach**: Since Streamlit CWD varies and VBS script already manages the launch, safest is to keep `sys.path.insert` in `app.py` only (single entrypoint) and remove the duplicate in `data.py`. `data.py` will rely on the path already set by `app.py` (which loads first as the entrypoint).

### S1: unsafe_allow_html CSS consolidation

**Strategy**: Add utility CSS classes to `_BASE_RULES` in `theme.py`, then replace inline HTML with `st.markdown(class-based-html)` or plain Streamlit widgets.

**New CSS classes in theme.py `_BASE_RULES`**:
```css
.bkit-flex-center { display:flex; align-items:center; gap:8px; margin-bottom:15px; }
.bkit-status-dot { font-size:1.2rem; }
.bkit-hint-badge { background:var(--color-bg-card-alt); color:var(--color-primary); padding:6px 16px; border-radius:var(--radius-pill); font-size:0.85rem; font-weight:500; }
.bkit-spacer-8 { height:8px; }
.bkit-gradient-header { padding:10px 14px; background:var(--color-gradient); border-radius:var(--radius-sm); margin-bottom:10px; display:flex; justify-content:space-between; align-items:center; }
.bkit-gradient-header span { color:#fff; }
.bkit-zero-state { text-align:center; margin-top:60px; margin-bottom:40px; }
```

**File changes**:
- `ai_section.py`: Replace 11 inline HTML blocks with CSS class usage
- `kpi_cards.py`: Replace 1 inline HTML block
- `overview.py`: Replace 1 spacer div
- `app.py`: Replace 1 sidebar logo div

**Target**: 17 → 4~5 (theme.py 1 + ai_section chat CSS 2~3 + skeleton CSS 1)

---

## 2. Implementation Order

```
S3 → S4 → S5 → S2 → S1
```

---

## 3. Acceptance Criteria

- `grep -c "unsafe_allow_html" dashboard/` <= 5
- `grep -c "sys.path.insert" dashboard/` <= 1 (app.py only)
- `grep -c "api_url.*=.*f\"" dashboard/components/ai_section.py` == 0
- All pages render correctly
- 149+ tests pass
