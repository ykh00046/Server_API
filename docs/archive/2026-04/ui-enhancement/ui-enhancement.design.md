# Design: Dashboard UI Enhancement

> PDCA Phase: **Design**
> Feature: `ui-enhancement`
> Based on: `ui-enhancement.plan.md`
> Created: 2026-02-20
> Status: Draft

---

## 1. Architecture Overview

### 1.1 System Context

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Dashboard                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐│
│  │  Tab 1  │  │  Tab 2  │  │  Tab 3  │  │    Tab 4 NEW    ││
│  │ 상세이력 │  │ 실적추이 │  │ AI분석  │  │   제품 비교     ││
│  └────┬────┘  └────┬────┘  └────┬────┘  └────────┬────────┘│
│       │            │            │                  │         │
│  ┌────▼────────────▼────────────▼────────────────▼────────┐│
│  │              Shared Components Layer                     ││
│  │  [Theme Manager] [KPI Cards] [Chart Utils] [Preset Mgr] ││
│  └──────────────────────────────────────────────────────────┘│
│                              │                               │
│  ┌───────────────────────────▼─────────────────────────────┐│
│  │              Data Layer (Existing)                       ││
│  │  [load_records] [load_monthly_summary] [load_item_list] ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │   FastAPI API    │
                    │   (Port 8000)    │
                    └──────────────────┘
```

### 1.2 File Structure

```
dashboard/
├── app.py                 # Main application (modified)
├── components/            # NEW: Modular components
│   ├── __init__.py
│   ├── theme.py           # U1: Dark mode manager
│   ├── kpi_cards.py       # U2: KPI dashboard cards
│   ├── charts.py          # U3-U5: Chart components
│   ├── presets.py         # U7: Filter preset manager
│   └── responsive.py      # U8: Responsive utilities
└── styles/
    └── custom.css         # Custom CSS styles
```

---

## 2. Component Specifications

### 2.1 U1: Theme Manager (`components/theme.py`)

#### 2.1.1 Color Palette

| Element | Light Mode | Dark Mode |
|---------|------------|-----------|
| Background | `#FFFFFF` | `#0E1117` |
| Sidebar | `#F0F2F6` | `#262730` |
| Text Primary | `#1F1F1F` | `#FAFAFA` |
| Text Secondary | `#5C5C5C` | `#A0A0A0` |
| Accent | `#FF4B4B` | `#FF4B4B` |
| Chart Bg | `#FFFFFF` | `#111111` |
| Grid Lines | `#E0E0E0` | `#333333` |

#### 2.1.2 Implementation

```python
# dashboard/components/theme.py
import streamlit as st
from typing import Literal

ThemeMode = Literal["light", "dark"]

COLORS = {
    "light": {
        "bg": "#FFFFFF",
        "sidebar": "#F0F2F6",
        "text": "#1F1F1F",
        "text_secondary": "#5C5C5C",
        "chart_template": "plotly_white",
    },
    "dark": {
        "bg": "#0E1117",
        "sidebar": "#262730",
        "text": "#FAFAFA",
        "text_secondary": "#A0A0A0",
        "chart_template": "plotly_dark",
    }
}

def init_theme():
    """Initialize theme state."""
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False

def get_theme() -> ThemeMode:
    """Get current theme mode."""
    return "dark" if st.session_state.get("dark_mode", False) else "light"

def get_colors() -> dict:
    """Get color palette for current theme."""
    return COLORS[get_theme()]

def render_theme_toggle():
    """Render theme toggle in sidebar."""
    dark_mode = st.sidebar.toggle(
        "🌙 다크 모드",
        value=st.session_state.get("dark_mode", False),
        key="dark_mode_toggle"
    )
    st.session_state.dark_mode = dark_mode
    return dark_mode

def apply_custom_css():
    """Apply custom CSS based on theme."""
    colors = get_colors()
    st.markdown(f"""
    <style>
        /* Main background */
        .stApp {{
            background-color: {colors['bg']};
        }}
        /* Sidebar */
        [data-testid="stSidebar"] {{
            background-color: {colors['sidebar']};
        }}
        /* Text colors */
        .stMarkdown, .stMetric label {{
            color: {colors['text']};
        }}
        /* KPI Card styling */
        .kpi-card {{
            background-color: {colors['sidebar']};
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
    </style>
    """, unsafe_allow_html=True)
```

#### 2.1.3 Location in app.py

```python
# dashboard/app.py (after imports)
from components.theme import init_theme, render_theme_toggle, apply_custom_css, get_colors

# After st.set_page_config
init_theme()
render_theme_toggle()
apply_custom_css()
```

---

### 2.2 U2: KPI Cards (`components/kpi_cards.py`)

#### 2.2.1 KPI Metrics Definition

| Metric | Description | Format | Delta |
|--------|-------------|--------|-------|
| `total_qty` | 총 생산량 | `{value:,} ea` | 이전 기간 대비 % |
| `batch_count` | 생산 건수 | `{value:,} 건` | - |
| `daily_avg` | 일평균 생산량 | `{value:,.0f} ea` | - |
| `top_item` | 최다 생산 제품 | `item_code` | - |

#### 2.2.2 Implementation

```python
# dashboard/components/kpi_cards.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from typing import Optional

def calculate_kpis(
    df: pd.DataFrame,
    date_from: Optional[date],
    date_to: Optional[date]
) -> dict:
    """
    Calculate KPI metrics from dataframe.

    Args:
        df: Production records dataframe
        date_from: Start date
        date_to: End date

    Returns:
        dict with keys: total_qty, batch_count, daily_avg, top_item, top_item_name
    """
    if df.empty:
        return {
            "total_qty": 0,
            "batch_count": 0,
            "daily_avg": 0,
            "top_item": "-",
            "top_item_name": "-",
            "prev_total_qty": 0,
            "delta_pct": 0
        }

    total_qty = int(df["good_quantity"].sum())
    batch_count = len(df)

    # Calculate daily average
    if date_from and date_to:
        days = (date_to - date_from).days + 1
        daily_avg = total_qty / max(days, 1)
    else:
        daily_avg = total_qty / 30  # Default assumption

    # Top item
    item_totals = df.groupby("item_code")["good_quantity"].sum()
    if not item_totals.empty:
        top_item = item_totals.idxmax()
        top_item_name = df[df["item_code"] == top_item]["item_name"].iloc[0]
    else:
        top_item = "-"
        top_item_name = "-"

    return {
        "total_qty": total_qty,
        "batch_count": batch_count,
        "daily_avg": daily_avg,
        "top_item": top_item,
        "top_item_name": top_item_name,
    }

def render_kpi_cards(kpis: dict, colors: dict):
    """
    Render 4 KPI metric cards.

    Args:
        kpis: KPI values dict
        colors: Theme color palette
    """
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="📊 총 생산량",
            value=f"{kpis['total_qty']:,} ea",
            delta=None
        )

    with col2:
        st.metric(
            label="📦 생산 건수",
            value=f"{kpis['batch_count']:,} 건",
            delta=None
        )

    with col3:
        st.metric(
            label="📈 일평균 생산량",
            value=f"{kpis['daily_avg']:,.0f} ea",
            delta=None
        )

    with col4:
        st.metric(
            label="🏆 최다 생산 제품",
            value=kpis['top_item'],
            delta=kpis['top_item_name'][:20] if len(kpis['top_item_name']) > 20 else kpis['top_item_name']
        )

    st.divider()
```

#### 2.2.3 Location in app.py

```python
# In main content area, before tabs
from components.kpi_cards import calculate_kpis, render_kpi_cards

# After loading data
kpis = calculate_kpis(df, date_from, date_to)
render_kpi_cards(kpis, get_colors())
```

---

### 2.3 U3: Product Comparison Charts (`components/charts.py`)

#### 2.3.1 Chart Types

| Chart | Type | Purpose |
|-------|------|---------|
| Top 10 Bar | Horizontal Bar | 상위 10개 제품 생산량 비교 |
| Distribution Pie | Pie (Donut) | 제품별 생산 비중 |
| Trend Lines | Multi-line | 선택 제품별 기간 추이 |

#### 2.3.2 Implementation

```python
# dashboard/components/charts.py
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Optional

def create_top10_bar_chart(df: pd.DataFrame, template: str) -> go.Figure:
    """Create horizontal bar chart for top 10 products."""
    if df.empty:
        return go.Figure()

    # Aggregate by item
    item_totals = df.groupby(["item_code", "item_name"])["good_quantity"].sum().reset_index()
    item_totals = item_totals.nlargest(10, "good_quantity")

    fig = go.Figure(go.Bar(
        x=item_totals["good_quantity"],
        y=item_totals["item_code"],
        orientation='h',
        text=item_totals["good_quantity"].apply(lambda x: f"{x:,}"),
        textposition='outside',
        marker_color='#1f77b4',
        hovertemplate=(
            "<b>%{y}</b><br>"
            "생산량: %{x:,} ea<br>"
            "<extra></extra>"
        )
    ))

    fig.update_layout(
        title="Top 10 생산 제품",
        xaxis_title="생산량 (ea)",
        yaxis_title="제품코드",
        template=template,
        height=400,
        yaxis=dict(autorange="reversed"),
        margin=dict(l=100, r=50, t=50, b=50)
    )

    return fig

def create_distribution_pie(df: pd.DataFrame, template: str) -> go.Figure:
    """Create donut chart for product distribution."""
    if df.empty:
        return go.Figure()

    # Aggregate by item
    item_totals = df.groupby("item_code")["good_quantity"].sum().reset_index()
    total = item_totals["good_quantity"].sum()

    # Top 10 + Others
    top10 = item_totals.nlargest(10, "good_quantity")
    if len(item_totals) > 10:
        others_sum = item_totals[~item_totals["item_code"].isin(top10["item_code"])]["good_quantity"].sum()
        others_row = pd.DataFrame([{"item_code": "기타", "good_quantity": others_sum}])
        top10 = pd.concat([top10, others_row], ignore_index=True)

    fig = go.Figure(go.Pie(
        labels=top10["item_code"],
        values=top10["good_quantity"],
        hole=0.4,
        textinfo='percent+label',
        textposition='outside',
        hovertemplate=(
            "<b>%{label}</b><br>"
            "생산량: %{value:,} ea<br>"
            "비중: %{percent}<extra></extra>"
        )
    ))

    fig.update_layout(
        title="제품별 생산 비중",
        template=template,
        height=400,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2)
    )

    return fig

def create_trend_lines(
    df: pd.DataFrame,
    item_codes: list[str],
    agg_unit: str,
    template: str
) -> go.Figure:
    """Create multi-line trend chart for selected products."""
    if df.empty or not item_codes:
        return go.Figure()

    # Filter by selected items
    filtered = df[df["item_code"].isin(item_codes)]

    # Determine period column
    if agg_unit == "일별":
        filtered["period"] = filtered["production_date"]
    elif agg_unit == "주별":
        filtered["period"] = filtered["production_dt"].dt.to_period("W").astype(str)
    else:
        filtered["period"] = filtered["year_month"]

    # Aggregate
    agg_df = filtered.groupby(["period", "item_code"])["good_quantity"].sum().reset_index()

    fig = go.Figure()

    for item_code in item_codes:
        item_data = agg_df[agg_df["item_code"] == item_code]
        fig.add_trace(go.Scatter(
            x=item_data["period"],
            y=item_data["good_quantity"],
            mode='lines+markers',
            name=item_code,
            hovertemplate=(
                f"<b>{item_code}</b><br>"
                "기간: %{x}<br>"
                "생산량: %{y:,} ea<extra></extra>"
            )
        ))

    fig.update_layout(
        title="제품별 생산 추이",
        xaxis_title="기간",
        yaxis_title="생산량 (ea)",
        template=template,
        height=400,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )

    return fig
```

---

### 2.4 U4: Trend Aggregation Unit Selection

#### 2.4.1 Data Loading Functions

```python
# Add to dashboard/app.py

@st.cache_data(ttl=60)
def load_daily_summary(date_from, date_to, db_ver):
    """Load daily aggregated data."""
    # ... similar to load_monthly_summary but grouped by date
    pass

@st.cache_data(ttl=60)
def load_weekly_summary(date_from, date_to, db_ver):
    """Load weekly aggregated data."""
    # ... similar to load_monthly_summary but grouped by week
    pass
```

#### 2.4.2 UI Component

```python
# In Tab 2 (실적 추이)
agg_unit = st.radio(
    "집계 단위",
    options=["일별", "주별", "월별"],
    index=2,  # Default: 월별
    horizontal=True
)

# Load appropriate data
if agg_unit == "일별":
    summary_df = load_daily_summary(date_from, date_to, db_ver=current_db_ver)
    x_col = "production_date"
elif agg_unit == "주별":
    summary_df = load_weekly_summary(date_from, date_to, db_ver=current_db_ver)
    x_col = "year_week"
else:
    summary_df = load_monthly_summary(date_from, date_to, db_ver=current_db_ver)
    x_col = "year_month"
```

---

### 2.5 U5: Chart Interaction Enhancement

#### 2.5.1 Range Selector Implementation

```python
def add_range_selector(fig: go.Figure) -> go.Figure:
    """Add range selector buttons to chart."""
    fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="1주", step="day", stepmode="backward"),
                dict(count=14, label="2주", step="day", stepmode="backward"),
                dict(count=1, label="1개월", step="month", stepmode="backward"),
                dict(count=3, label="3개월", step="month", stepmode="backward"),
                dict(count=6, label="6개월", step="month", stepmode="backward"),
                dict(step="all", label="전체")
            ]),
            font=dict(size=10)
        )
    )
    return fig

def add_download_button(fig: go.Figure, filename: str) -> go.Figure:
    """Add download button to chart modebar."""
    fig.update_layout(
        modebar_add=["downloadCSV"],
        config={
            'displayModeBar': True,
            'scrollZoom': True,
            'displaylogo': False,
            'toImageButtonOptions': {
                'format': 'png',
                'filename': filename,
                'height': 800,
                'width': 1200,
                'scale': 2
            }
        }
    )
    return fig
```

---

### 2.6 U6: Loading State Display

#### 2.6.1 Implementation

```python
# dashboard/components/loading.py
import streamlit as st
from datetime import datetime
from functools import wraps
from typing import Callable

def show_loading_status(message: str = "데이터 로딩 중..."):
    """Context manager for loading state."""
    class LoadingContext:
        def __init__(self, msg):
            self.msg = msg
            self.placeholder = None
            self.progress_bar = None

        def __enter__(self):
            self.placeholder = st.empty()
            self.progress_bar = self.placeholder.progress(0, text=self.msg)
            return self

        def __exit__(self, *args):
            self.progress_bar.empty()

        def update(self, progress: float, message: str = None):
            """Update progress (0.0 - 1.0)."""
            msg = message or self.msg
            self.progress_bar.progress(int(progress * 100), text=msg)

    return LoadingContext(message)

def render_last_update():
    """Render last update timestamp."""
    st.caption(f"📅 마지막 업데이트: {datetime.now():%Y-%m-%d %H:%M:%S}")

def render_cache_status(cache_hit: bool):
    """Render cache hit/miss indicator."""
    if cache_hit:
        st.success("⚡ 캐시에서 로드됨", icon="✅")
    else:
        st.info("📊 데이터베이스에서 조회됨", icon="🔄")
```

---

### 2.7 U7: Filter Preset Manager (`components/presets.py`)

#### 2.7.1 Data Structure

```python
# Preset schema
preset_schema = {
    "name": str,           # Preset name
    "item_codes": list,    # Selected item codes
    "date_from": str,      # ISO date or "relative:-30d"
    "date_to": str,        # ISO date or "relative:0d"
    "keyword": str,        # Search keyword
    "limit": int,          # Row limit
    "created_at": str      # ISO timestamp
}
```

#### 2.7.2 Implementation

```python
# dashboard/components/presets.py
import streamlit as st
from datetime import date, datetime
from typing import Optional
import json

MAX_PRESETS = 10

def init_presets():
    """Initialize preset storage."""
    if "filter_presets" not in st.session_state:
        st.session_state.filter_presets = {}

def get_preset_names() -> list[str]:
    """Get list of preset names."""
    return list(st.session_state.get("filter_presets", {}).keys())

def save_preset(
    name: str,
    item_codes: Optional[list],
    date_from: Optional[date],
    date_to: Optional[date],
    keyword: Optional[str],
    limit: int
) -> bool:
    """Save current filter settings as preset."""
    if not name or not name.strip():
        return False

    presets = st.session_state.get("filter_presets", {})

    # Enforce max presets
    if len(presets) >= MAX_PRESETS and name not in presets:
        st.warning(f"최대 {MAX_PRESETS}개 프리셋만 저장할 수 있습니다.")
        return False

    presets[name] = {
        "item_codes": item_codes,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "keyword": keyword,
        "limit": limit,
        "created_at": datetime.now().isoformat()
    }

    st.session_state.filter_presets = presets
    return True

def load_preset(name: str) -> Optional[dict]:
    """Load preset by name."""
    presets = st.session_state.get("filter_presets", {})
    preset = presets.get(name)
    if preset:
        # Convert date strings back to date objects
        if preset.get("date_from"):
            preset["date_from"] = date.fromisoformat(preset["date_from"])
        if preset.get("date_to"):
            preset["date_to"] = date.fromisoformat(preset["date_to"])
    return preset

def delete_preset(name: str) -> bool:
    """Delete preset by name."""
    presets = st.session_state.get("filter_presets", {})
    if name in presets:
        del presets[name]
        st.session_state.filter_presets = presets
        return True
    return False

def render_preset_manager(
    current_item_codes,
    current_date_from,
    current_date_to,
    current_keyword,
    current_limit
) -> Optional[dict]:
    """
    Render preset management UI in sidebar.

    Returns:
        Loaded preset dict if selected, None otherwise
    """
    st.sidebar.divider()
    st.sidebar.subheader("💾 필터 프리셋")

    # Load preset dropdown
    preset_names = get_preset_names()
    if preset_names:
        selected_preset = st.sidebar.selectbox(
            "프리셋 불러오기",
            options=[""] + preset_names,
            index=0,
            key="preset_selector"
        )
        if selected_preset:
            preset = load_preset(selected_preset)
            if st.sidebar.button("✅ 적용", key="apply_preset"):
                return preset
            if st.sidebar.button("🗑️ 삭제", key="delete_preset"):
                delete_preset(selected_preset)
                st.rerun()

    # Save preset
    st.sidebar.text_input(
        "새 프리셋 이름",
        key="new_preset_name",
        placeholder="예: BW0021 최근 30일"
    )
    if st.sidebar.button("💾 현재 필터 저장", key="save_preset"):
        name = st.session_state.get("new_preset_name", "").strip()
        if save_preset(
            name,
            current_item_codes,
            current_date_from,
            current_date_to,
            current_keyword,
            current_limit
        ):
            st.sidebar.success(f"'{name}' 저장됨!")
            st.rerun()

    return None
```

---

### 2.8 U8: Responsive Layout

#### 2.8.1 Screen Size Detection

```python
# dashboard/components/responsive.py
import streamlit as st
import streamlit.components.v1 as components

def detect_screen_width() -> int:
    """
    Detect screen width using JavaScript.
    Returns 0 if detection fails (fallback to desktop).
    """
    js_code = """
    <script>
        const width = window.innerWidth || document.documentElement.clientWidth;
        window.parent.postMessage({type: 'streamlit:setComponentValue', value: width}, '*');
    </script>
    """
    try:
        return components.html(js_code, height=0)
    except:
        return 1024  # Default to desktop

def is_mobile() -> bool:
    """Check if current viewport is mobile (<768px)."""
    # Streamlit doesn't support dynamic width detection well
    # Use CSS media queries instead
    return False  # Simplified for now

def get_responsive_columns(count: int = 4) -> list:
    """
    Get column count based on screen size.

    Desktop (>=768px): count columns
    Mobile (<768px): 1 column
    """
    # Use CSS to handle responsiveness
    cols = st.columns(count)
    return cols

def apply_responsive_css():
    """Apply responsive CSS for mobile optimization."""
    st.markdown("""
    <style>
        /* Mobile responsive adjustments */
        @media (max-width: 768px) {
            /* Stack KPI cards vertically */
            div[data-testid="stHorizontalBlock"] > div {
                flex-direction: column !important;
                width: 100% !important;
            }

            /* Increase touch targets */
            .stButton button {
                min-height: 44px;
                padding: 12px 20px;
            }

            /* Adjust font sizes */
            .stMetric label {
                font-size: 0.9rem !important;
            }
            .stMetric value {
                font-size: 1.2rem !important;
            }

            /* Hide sidebar on mobile by default */
            [data-testid="stSidebar"] {
                width: 280px !important;
            }
        }

        /* Tablet adjustments */
        @media (min-width: 768px) and (max-width: 1024px) {
            div[data-testid="stHorizontalBlock"] > div {
                flex-wrap: wrap;
            }
        }
    </style>
    """, unsafe_allow_html=True)
```

---

## 3. Implementation Order

### Phase 1: Foundation (U1, U6, U8)
1. Create `dashboard/components/` directory structure
2. Implement `theme.py` (U1)
3. Implement `loading.py` (U6)
4. Implement `responsive.py` (U8)
5. Integrate into `app.py`

### Phase 2: Data Visualization (U2, U3, U4, U5)
1. Implement `kpi_cards.py` (U2)
2. Implement `charts.py` with all chart types (U3)
3. Add aggregation unit selection (U4)
4. Add chart interaction enhancements (U5)

### Phase 3: User Experience (U7)
1. Implement `presets.py` (U7)
2. Add preset manager to sidebar
3. Final integration and testing

---

## 4. Testing Checklist

### U1: Dark Mode
- [ ] Toggle switches theme immediately
- [ ] All charts use correct template
- [ ] Text readable in both modes
- [ ] Theme persists across reruns

### U2: KPI Cards
- [ ] Values match API responses
- [ ] Handles empty data gracefully
- [ ] Responsive on mobile (stacks vertically)

### U3: Product Comparison
- [ ] Top 10 bar chart displays correctly
- [ ] Pie chart shows correct percentages
- [ ] Trend lines work with multiple items

### U4: Aggregation Units
- [ ] Daily aggregation works
- [ ] Weekly aggregation works
- [ ] Monthly aggregation (existing) still works

### U5: Chart Interactions
- [ ] Range selector buttons function
- [ ] Download button creates PNG
- [ ] Zoom/pan works

### U6: Loading States
- [ ] Progress bar shows during load
- [ ] Last update timestamp accurate
- [ ] Cache status indicator works

### U7: Filter Presets
- [ ] Save preset stores all values
- [ ] Load preset restores all values
- [ ] Delete preset removes from list
- [ ] Max 10 presets enforced

### U8: Responsive Layout
- [ ] KPI cards stack on mobile
- [ ] Charts resize appropriately
- [ ] Touch targets adequate size

---

## 5. Dependencies

```txt
# requirements.txt additions
streamlit>=1.28.0  # toggle component
plotly>=5.18.0     # latest templates
pandas>=2.0.0      # existing
```

---

## 6. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Large dataset rendering | Limit chart data points to 1000 max |
| Session state memory | Limit presets to 10, clean expired |
| CSS conflicts | Use scoped selectors |
| Mobile browser issues | Test on Chrome/Safari mobile |
