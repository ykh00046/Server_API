"""manager_theme — CustomTkinter 테마 상수 (manager.py + portal_settings_dialog.py 공유).

대시보드(.streamlit/config.toml)와 동일한 블루/슬레이트 팔레트를 쓴다:
  primary #2563eb, 슬레이트 중립(#f8fafc/#e2e8f0/#0f172a 계열),
  성공 #0d9488, 경고 #f59e0b, 오류 #dc2626.

customtkinter의 fg_color/text_color 는 (light, dark) 튜플을 받아
라이트/다크 외형 전환(ctk.set_appearance_mode)에 자동으로 대응한다.
이 파일이 색·간격·폰트의 단일 출처이다 — 새 색을 추가할 때 여기만 고친다.
"""

from __future__ import annotations

# ==========================================================
# 색상 — (light, dark) 튜플. 대시보드 config.toml 팔레트와 정렬.
# ==========================================================
# Primary 블루 (대시보드 primaryColor: light #2563eb / dark #3b82f6)
PRIMARY = ("#2563eb", "#3b82f6")
PRIMARY_HOVER = ("#1d4ed8", "#2563eb")

# 성공/경고/오류 (대시보드 greenColor/orangeColor/redColor 계열)
SUCCESS = ("#0d9488", "#2dd4bf")
WARNING = ("#f59e0b", "#fbbf24")
ERROR = ("#dc2626", "#f87171")

# 슬레이트 중립 (대시보드 backgroundColor/secondaryBackgroundColor/borderColor)
# 카드 배경 — light: 흰에 가까운 슬레이트, dark: 딥 슬레이트
BG_CARD = ("#ffffff", "#1e293b")
BG_PANEL = ("#f8fafc", "#0f172a")  # 루트/프레임 배경
BG_INNER = ("#f1f5f9", "#334155")  # 내부 행/입력 프레임
BORDER = ("#e2e8f0", "#334155")

# 텍스트 — 대시보드 textColor: light #0f172a / dark #e2e8f0
TEXT = ("#0f172a", "#e2e8f0")
TEXT_MUTED = ("#64748b", "#94a3b8")
TEXT_INVERSE = ("#ffffff", "#0f172a")  # primary 배경 위 글자

# 로그 박스는 두 모드 모두 다크 터미널로 고정한다(LOG_BG) — 라이트 모드에서
# 연회색 로그 글자가 흰 배경에 묻히는 것을 막고, 터미널 관례를 따른다.
LOG_BG = "#0f172a"
LOG_BORDER = ("#e2e8f0", "#1e293b")
LOG_INFO = "#cbd5e1"
LOG_WARN = "#fbbf24"
LOG_ERROR = "#f87171"
LOG_SUCCESS = "#34d399"

# 서비스 상태 뱃지 색 (상태바/라벨) — (light, dark)
STATUS_RUNNING = SUCCESS
STATUS_STOPPED = ("#94a3b8", "#64748b")
STATUS_ONE_SHOT = WARNING

# 상태 pill 뱃지 — 소프트 배경 + 진한 글자 (원색 채움 대신 저채도 pill)
PILL_RUNNING_BG = ("#ccfbf1", "#134e4a")
PILL_RUNNING_TEXT = ("#0f766e", "#5eead4")
PILL_STOPPED_BG = ("#e2e8f0", "#334155")
PILL_STOPPED_TEXT = ("#64748b", "#94a3b8")

# 포털 1회 실행(amber) 단색 — _launch_portal_auto에서 단일 hex로 쓰던 값의 호환
ONE_SHOT_AMBER = "#ffb74d"

# ==========================================================
# 간격 / 코너 반경 (일관된 리듬)
# ==========================================================
RADIUS_PANEL = 15
RADIUS_BADGE = 14
RADIUS_SMALL = 8
PAD_OUTER = 20          # 루트 → 패널 외곽
PAD_PANEL = 15          # 패널 내부 기본
PAD_TIGHT = 8
GAP_CONTROL = 5         # 버튼 사이 간격
STATUS_BAR_HEIGHT = 4
BUTTON_WIDTH = 80

# 로그 폰트 / 제목 폰트 (크기만 — 패밀리는 시스템 기본 Segoe UI)
FONT_LOG = ("Consolas", 12)
FONT_LOG_COMPACT = ("Consolas", 10)
FONT_TITLE = {"family": "Segoe UI", "size": 24, "weight": "bold"}
FONT_PANEL_TITLE = {"family": "Segoe UI", "size": 18, "weight": "bold"}
FONT_PANEL_TITLE_COMPACT = {"family": "Segoe UI", "size": 16, "weight": "bold"}
FONT_STATUS = {"family": "Segoe UI", "size": 14}
FONT_BADGE = {"family": "Segoe UI", "size": 12, "weight": "bold"}


# ==========================================================
# 버튼 위계 — 채색(filled) 면적은 primary 액션 하나로 제한한다.
#   primary  : 각 패널의 주 액션(Start, 전체 시작)만 파랑 채움
#   outline  : 보조 강조(Run Now) — 파랑 테두리, 투명 배경
#   danger   : 파괴적 액션(Stop, 전체 중지) — 빨강 테두리, hover 시에만 채움 느낌
#   ghost    : 나머지 전부(Open/Docs/Settings/복사/지우기) — 중립 테두리
# CTkButton(**btn_*()) 형태로 쓴다.
# ==========================================================
_GHOST_HOVER = ("#e2e8f0", "#475569")
_PRIMARY_SOFT = ("#dbeafe", "#1e3a5f")
_DANGER_SOFT = ("#fee2e2", "#450a0a")


def btn_primary() -> dict:
    return {"fg_color": PRIMARY, "hover_color": PRIMARY_HOVER, "text_color": "#ffffff"}


def btn_outline_primary() -> dict:
    return {
        "fg_color": "transparent", "border_width": 1,
        "border_color": PRIMARY, "text_color": PRIMARY, "hover_color": _PRIMARY_SOFT,
    }


def btn_danger() -> dict:
    return {
        "fg_color": "transparent", "border_width": 1,
        "border_color": ERROR, "text_color": ERROR, "hover_color": _DANGER_SOFT,
    }


def btn_ghost() -> dict:
    return {
        "fg_color": "transparent", "border_width": 1,
        "border_color": BORDER, "text_color": TEXT, "hover_color": _GHOST_HOVER,
    }


def seg_style() -> dict:
    """세그먼트 버튼: 연슬레이트 트랙 + 흰(다크: 슬레이트) pill 선택 — 무채색 유지."""
    selected = ("#ffffff", "#475569")
    return {
        "fg_color": BG_INNER,
        "selected_color": selected,
        "selected_hover_color": selected,
        "unselected_color": BG_INNER,
        "unselected_hover_color": _GHOST_HOVER,
        "text_color": TEXT,
    }


def ctk_font(spec: dict):
    """FONT_* 사전 → customtkinter.CTkFont (지연 import로 순환 참조 회피)."""
    import customtkinter as ctk
    return ctk.CTkFont(**spec)
