# dashboard-pages-refactor Design Document

> **Summary**: 3개 페이지 파일별 helper 추출 단위 및 시그니처 설계
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-24
> **Status**: Design

---

## 1. Architecture Decisions

### AD-1: Hybrid 패턴 (products.py 일관성)

- 모듈 top-level = Streamlit entry (매 rerun마다 top-to-bottom 실행)
- 섹션은 `_render_*(args)` helper 함수로 추출
- helper는 인자만 사용 (implicit capture 금지)
- `render_page_header`, `get_filter_state`, `get_page_columns`, `render_ai_column`는 top-level 유지

### AD-2: 공통 세팅은 top-level에서 한 번

각 페이지가 필요로 하는 `colors`/`chart_template` 같은 공통 변수는 top-level에서 한 번 계산해 helper에 인자로 전달. DRY helper로 추출은 OoS (AD-2의 scope creep 방지).

### AD-3: Helper 네이밍 원칙

- `_render_<section>(args) -> None | data` — `_render_` prefix로 모듈 외부 비공개 의도 명시
- 섹션 이름은 해당 UI 의도를 반영 (e.g. `_render_kpi_section`, `_render_chart_row_1`)
- 결과를 재사용해야 하면 `return` (예: `_render_detail_table`이 prepared DataFrame 반환)

---

## 2. File-Level Changes

### 2.1 `dashboard/pages/overview.py`

**추출 helper 3개**:

```python
def _render_kpi_section(
    df, date_from, date_to, colors
) -> None:
    """KPI cards (총 생산량 / 배치 수 / 평균 / Top 제품) + spacer."""
    kpis = calculate_kpis(df, date_from, date_to)
    sparkline = get_sparkline_data(df)
    top_spark = get_sparkline_for_top_product(df, kpis["top_item"])
    render_kpi_cards(
        kpis, colors,
        sparkline_data=sparkline,
        batch_sparkline=sparkline,
        top_product_sparkline=top_spark,
    )
    st.markdown('<div class="bkit-spacer-8"></div>', unsafe_allow_html=True)


def _render_chart_row_1(
    df, date_from, date_to, db_ver, chart_template, colors
) -> None:
    """월별 추세(이중 축) + Top 10 bar — 2-col grid."""
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("**📈 월별 생산 추세**")
        summary_df = load_monthly_summary(date_from, date_to, db_ver=db_ver)
        if len(summary_df) > 0:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            # … 기존 로직 이동 …
            st.plotly_chart(fig, use_container_width=True, config=get_chart_config("monthly_trend"))
        else:
            st.info("데이터가 없습니다.")

    with chart_col2:
        st.markdown("**🏆 Top 10 제품별 생산량**")
        fig_bar = create_top10_bar_chart(df, chart_template, marker_color=colors["primary"])
        fig_bar.update_layout(height=360, margin=dict(l=80, r=20, t=30, b=40))
        st.plotly_chart(fig_bar, use_container_width=True, config=get_chart_config("top10"))


def _render_chart_row_2(df, chart_template) -> None:
    """생산 분포(donut) + 최근 현황 요약 테이블 — 2-col grid."""
    chart_col3, chart_col4 = st.columns(2)
    with chart_col3:
        st.markdown("**🍩 생산 분포**")
        fig_pie = create_distribution_pie(df, chart_template)
        fig_pie.update_layout(height=340, margin=dict(l=20, r=20, t=30, b=40))
        st.plotly_chart(fig_pie, use_container_width=True, config=get_chart_config("distribution"))

    with chart_col4:
        st.markdown("**📊 최근 현황 요약**")
        if not df.empty:
            recent = df.head(7)[["production_date", "item_code", "item_name", "good_quantity"]].copy()
            recent["production_date"] = df.head(7)["production_dt"].dt.strftime("%Y-%m-%d")
            recent = recent.rename(columns={
                "production_date": "생산일",
                "item_code": "코드",
                "item_name": "제품명",
                "good_quantity": "양품수량",
            })
            st.dataframe(recent, use_container_width=True, hide_index=True, height=340)
        else:
            st.info("데이터가 없습니다.")
```

**top-level (slim)**:
```python
render_page_header(...)
fs = get_filter_state()
# ... unpack fs ...
col_main, col_ai = get_page_columns()
with col_main:
    df, bad_dt = load_records(...)
    colors = get_colors()
    chart_template = colors.get("chart_template", "plotly_white")

    _render_kpi_section(df, date_from, date_to, colors)
    _render_chart_row_1(df, date_from, date_to, db_ver, chart_template, colors)
    _render_chart_row_2(df, chart_template)

    render_last_update()

render_ai_column(col_ai)
```

### 2.2 `dashboard/pages/batches.py`

**추출 helper 3개**:

```python
def _render_kpi_cards(df) -> None:
    """총 레코드 / 생산일 수 / 일 평균 배치 — 3-col KPI row + spacer."""
    kpi1, kpi2, kpi3 = st.columns(3)
    unique_days = df["production_dt"].dt.date.nunique() if not df.empty else 0
    avg_daily = len(df) / max(unique_days, 1) if not df.empty else 0
    with kpi1:
        st.metric("총 레코드", f"{len(df):,}건")
    with kpi2:
        st.metric("생산일 수", f"{unique_days}일")
    with kpi3:
        st.metric("일 평균 배치", f"{avg_daily:.1f}건")
    st.markdown('<div class="bkit-spacer-8"></div>', unsafe_allow_html=True)


def _render_detail_table(df) -> "pd.DataFrame":
    """상세 테이블 렌더 + display_detail DataFrame 반환 (export에서 재사용)."""
    display_detail = df[
        ["production_date", "item_code", "item_name", "good_quantity", "lot_number"]
    ].copy()
    display_detail["production_date"] = df["production_dt"].dt.strftime("%Y-%m-%d")
    display_detail = display_detail.rename(columns={
        "production_date": "생산일",
        "item_code": "제품코드",
        "item_name": "제품명",
        "good_quantity": "양품수량",
        "lot_number": "LOT 번호",
    })
    st.dataframe(display_detail, use_container_width=True, hide_index=True)
    return display_detail


def _render_export_buttons(df, display_detail) -> None:
    """Excel/CSV 다운로드 버튼 2개."""
    export_col1, export_col2, _ = st.columns([1, 1, 4])
    with export_col1:
        st.download_button(
            "📥 Excel 다운로드",
            _cached_excel_bytes(df),
            "production_records.xlsx",
            use_container_width=True,
        )
    with export_col2:
        csv_data = display_detail.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📋 CSV 다운로드",
            csv_data,
            "production_records.csv",
            mime="text/csv",
            use_container_width=True,
        )
```

### 2.3 `dashboard/pages/trends.py`

**추출 helper 2개**:

```python
def _render_trend_chart(
    summary_df, x_col, agg_unit, colors, chart_template
) -> None:
    """총 생산량 막대(좌축) + 배치 수 라인(우축) 이중 축 차트."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    # … 기존 로직 이동 …
    st.plotly_chart(fig, use_container_width=True, config=get_chart_config(f"trends_{agg_unit}"))


def _render_summary_table(summary_df) -> None:
    """요약 테이블 (컬럼 renaming + 평균 배치 크기 반올림)."""
    col_rename = {
        "year_month": "연월",
        "production_day": "생산일",
        "year_week": "주차",
        "total_production": "총 생산량",
        "batch_count": "배치 수",
        "avg_batch_size": "평균 배치 크기",
    }
    display_summary = summary_df.rename(columns=col_rename)
    if "평균 배치 크기" in display_summary.columns:
        display_summary["평균 배치 크기"] = display_summary["평균 배치 크기"].round(1)
    st.dataframe(display_summary, use_container_width=True, hide_index=True)
```

**top-level**:
```python
# ... 기존 데이터 로드 ...
if len(summary_df) == 0:
    st.info("선택한 기간에 데이터가 없습니다.")
else:
    _render_trend_chart(summary_df, x_col, agg_unit, colors, chart_template)
    _render_summary_table(summary_df)
```

---

## 3. Test Plan

| Test | 명령 | 기대 |
|------|------|------|
| compile 3 pages | `py_compile` each | ok |
| full pytest | `pytest tests/ -q` | 163 passed, 0 regression |
| sanity grep | `grep -E "^def _render_" dashboard/pages/{overview,batches,trends}.py` | 8 matches (3+3+2) |

수동 smoke: 대시보드 실행 후 모든 탭 전환, KPI/차트/테이블 정상 렌더링 확인.

---

## 4. Rollback

각 페이지는 독립적이므로 commit 단위 revert로 안전 롤백:
- overview commit revert → overview만 원복
- batches / trends 동일

---

## 5. Open Questions

- (해결됨) 공통 세팅 helper 추출 여부 → AD-2에서 YAGNI로 결정.
- (해결됨) batches display_detail 재사용 방식 → `_render_detail_table`이 반환, export 함수가 받음.
