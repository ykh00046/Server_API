# UI/UX Enhancement Design Document

> **Feature**: UI/UX Enhancement
> **Status**: Design
> **Priority**: High
> **Created**: 2026-02-25
> **Based on**: ui-ux-enhancement.plan.md

---

## 1. System Architecture

### 1.1 Component Hierarchy

```
dashboard/app.py (Main Entry)
├── components/
│   ├── theme.py           → ThemeManager (Enhanced)
│   ├── kpi_cards.py       → KPICards (Enhanced)
│   ├── charts.py          → ChartManager (New)
│   ├── loading.py         → LoadingStates (New)
│   ├── notifications.py   → ToastManager (New)
│   ├── presets.py         → PresetManager (Enhanced)
│   ├── ai_section.py      → AISection (Enhanced)
│   └── responsive.py      → ResponsiveLayout (New)
└── styles/
    └── custom.css         → Custom CSS (New)
```

### 1.2 New Components

#### LoadingStates (`components/loading.py`)
```python
from dataclasses import dataclass
from typing import Optional
import streamlit as st

@dataclass
class SkeletonConfig:
    """Configuration for skeleton loading animation."""
    rows: int = 5
    height: int = 40
    animation: str = "pulse"  # pulse, wave, none

class LoadingStates:
    """Provides skeleton loading UI components."""

    @staticmethod
    def show_skeleton_table(config: SkeletonConfig = None) -> None:
        """Display skeleton table while loading."""
        config = config or SkeletonConfig()
        # Implementation with CSS animation

    @staticmethod
    def show_skeleton_chart(height: int = 400) -> None:
        """Display skeleton chart while loading."""
        # Gray box with pulse animation

    @staticmethod
    def show_skeleton_kpi(count: int = 4) -> None:
        """Display skeleton KPI cards while loading."""
        # Card placeholders with pulse animation
```

#### ToastManager (`components/notifications.py`)
```python
from enum import Enum
from typing import Optional
import streamlit as st

class ToastType(Enum):
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class ToastManager:
    """Manages toast notifications with queue support."""

    def __init__(self, position: str = "top-right"):
        self.position = position
        self._queue = []

    def show(self, message: str, type: ToastType = ToastType.INFO,
             duration: int = 3000) -> None:
        """Show toast notification."""
        # Implementation using st.toast or custom component

    def show_success(self, message: str) -> None:
        self.show(message, ToastType.SUCCESS)

    def show_error(self, message: str) -> None:
        self.show(message, ToastType.ERROR, duration=5000)

    def clear_all(self) -> None:
        """Clear all active toasts."""
        self._queue.clear()
```

#### ChartManager (`components/charts.py` - Enhanced)
```python
from typing import Optional, List, Dict, Any
import plotly.graph_objects as go
import pandas as pd

class ChartManager:
    """Enhanced chart management with interactivity."""

    def __init__(self, theme: str = "dark"):
        self.theme = theme
        self._fig = None

    def create_trend_chart(
        self,
        df: pd.DataFrame,
        x: str,
        y: str,
        title: str,
        enable_zoom: bool = True,
        enable_export: bool = True
    ) -> go.Figure:
        """Create interactive trend chart."""
        fig = go.Figure()

        # Add trace
        fig.add_trace(go.Scatter(
            x=df[x], y=df[y],
            mode='lines+markers',
            name=title,
            hovertemplate='%{x}<br>%{y:,.0f}<extra></extra>'
        ))

        # Configure interactivity
        fig.update_layout(
            dragmode='zoom' if enable_zoom else None,
            hovermode='x unified',
            # ... theme-specific styling
        )

        return fig

    def add_export_buttons(self, fig: go.Figure) -> go.Figure:
        """Add PNG/CSV export buttons to chart."""
        fig.update_layout(
            updatemenus=[{
                'type': 'buttons',
                'direction': 'left',
                'buttons': [
                    {'label': 'PNG', 'method': 'download', 'args': [{'format': 'png'}]},
                    {'label': 'CSV', 'method': 'skip'},  # Handled separately
                ]
            }]
        )
        return fig

    def enable_drill_down(
        self,
        fig: go.Figure,
        drill_callback: callable
    ) -> None:
        """Enable click-to-drill functionality."""
        # Use plotly_click event with st.components.v1.html
        pass
```

---

## 2. UI Component Specifications

### 2.1 KPI Cards Enhancement

**Current:**
```python
# Simple metric display
col1.metric("Total", value, delta)
```

**Enhanced:**
```python
class KPICard:
    """Enhanced KPI card with trend and sparkline."""

    def __init__(
        self,
        title: str,
        value: Any,
        delta: Optional[float] = None,
        trend_data: Optional[List[float]] = None,
        format: str = ",.0f"
    ):
        self.title = title
        self.value = value
        self.delta = delta
        self.trend_data = trend_data
        self.format = format

    def render(self) -> None:
        """Render KPI card with trend sparkline."""
        # Layout: Title | Value | Delta | Sparkline
        # Hover: Show last 7 days tooltip
        pass
```

### 2.2 Search Input with Debounce

```python
from datetime import datetime
import streamlit as st

class DebouncedSearch:
    """Search input with client-side debouncing."""

    def __init__(self, key: str, debounce_ms: int = 300):
        self.key = key
        self.debounce_ms = debounce_ms

    def render(self, placeholder: str = "검색...") -> str:
        """Render debounced search input."""
        # Use st.text_input with on_change callback
        # Store last search time in session state
        # Only trigger search after debounce period
        pass

    def get_value(self) -> str:
        """Get current search value."""
        return st.session_state.get(f"{self.key}_value", "")
```

### 2.3 Responsive Grid Layout

```python
class ResponsiveLayout:
    """Responsive grid that adapts to screen size."""

    @staticmethod
    def get_columns(preferred: int = 4) -> int:
        """Get optimal column count based on viewport."""
        # Use streamlit-javascript to detect viewport width
        # Return appropriate column count:
        # - Desktop (>1200px): preferred
        # - Tablet (768-1200px): 2
        # - Mobile (<768px): 1

    @staticmethod
    def render_responsive_grid(items: list, render_func: callable) -> None:
        """Render items in responsive grid."""
        cols = ResponsiveLayout.get_columns()
        for i in range(0, len(items), cols):
            row = st.columns(cols)
            for j, item in enumerate(items[i:i+cols]):
                with row[j]:
                    render_func(item)
```

---

## 3. Performance Optimizations

### 3.1 Component Caching Strategy

```python
from functools import lru_cache
from typing import Tuple
import hashlib

def cache_key_from_params(**kwargs) -> str:
    """Generate cache key from parameters."""
    key_str = str(sorted(kwargs.items()))
    return hashlib.md5(key_str.encode()).hexdigest()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_chart_data(
    query_hash: str,
    date_from: str,
    date_to: str
) -> pd.DataFrame:
    """Cache chart data with parameter-based key."""
    # Fetch data from API
    pass
```

### 3.2 Lazy Loading Implementation

```python
def lazy_load_section(
    section_key: str,
    load_func: callable,
    placeholder_text: str = "Loading..."
) -> Any:
    """Lazy load heavy sections only when visible."""
    # Use st.container with placeholder
    # Load content on first visibility
    # Cache result in session state
    pass
```

---

## 4. Accessibility Enhancements

### 4.1 ARIA Labels

```python
def accessible_metric(label: str, value: str, description: str = None) -> None:
    """Render accessible metric with ARIA labels."""
    st.markdown(f"""
    <div role="status" aria-label="{label}" aria-live="polite">
        <span class="metric-label">{label}</span>
        <span class="metric-value" aria-describedby="metric-desc">{value}</span>
        {f'<span id="metric-desc" class="sr-only">{description}</span>' if description else ''}
    </div>
    """, unsafe_allow_html=True)
```

### 4.2 Keyboard Navigation

```python
# Add keyboard shortcut hints to buttons
def action_button(label: str, key: str, shortcut: str = None) -> bool:
    """Button with keyboard shortcut support."""
    if shortcut:
        label = f"{label} ({shortcut})"
    return st.button(label, key=key)
```

---

## 5. Mobile Optimization

### 5.1 Touch-Friendly Controls

```python
def touch_friendly_slider(
    label: str,
    min_val: int,
    max_val: int,
    default: int,
    key: str
) -> int:
    """Larger touch targets for mobile."""
    # Use larger step sizes on mobile
    # Increase touch target size via CSS
    return st.slider(label, min_val, max_val, default, key=key)
```

### 5.2 Responsive Sidebar

```python
def responsive_sidebar() -> None:
    """Collapsible sidebar for mobile."""
    # Auto-collapse on mobile (<768px)
    # Expandable via hamburger menu
    pass
```

---

## 6. Custom CSS

### 6.1 Skeleton Animation

```css
/* styles/custom.css */
.skeleton {
    background: linear-gradient(90deg, #2b2b2b 25%, #3b3b3b 50%, #2b2b2b 75%);
    background-size: 200% 100%;
    animation: skeleton-pulse 1.5s ease-in-out infinite;
}

@keyframes skeleton-pulse {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

/* Toast notifications */
.toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
}

.toast {
    padding: 12px 20px;
    border-radius: 8px;
    margin-bottom: 10px;
    animation: slide-in 0.3s ease-out;
}

.toast.success { background: #4caf50; }
.toast.error { background: #ef5350; }
.toast.warning { background: #ffb74d; }
.toast.info { background: #2196f3; }

@keyframes slide-in {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}
```

---

## 7. File Changes Summary

| File | Action | Changes |
|------|--------|---------|
| `components/loading.py` | Create | Skeleton loading components |
| `components/notifications.py` | Create | Toast notification system |
| `components/charts.py` | Modify | Add zoom, export, drill-down |
| `components/kpi_cards.py` | Modify | Add sparklines, trends |
| `components/responsive.py` | Create | Responsive layout utilities |
| `styles/custom.css` | Create | Custom CSS animations |
| `app.py` | Modify | Integrate new components |

---

## 8. Testing Checklist

### 8.1 Functional Tests
- [ ] Skeleton loading displays correctly
- [ ] Toast notifications appear and dismiss
- [ ] Chart zoom/pan works
- [ ] Export generates valid files
- [ ] Responsive layout adapts to viewport

### 8.2 Performance Tests
- [ ] Page load time < 2s
- [ ] Chart render < 200ms
- [ ] No memory leaks on long sessions

### 8.3 Accessibility Tests
- [ ] Screen reader compatible
- [ ] Keyboard navigation works
- [ ] Color contrast meets WCAG AA

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-25 | Initial design |
