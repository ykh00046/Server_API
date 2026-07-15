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

# 로그 레벨 색 (텍스트 태그용 — 다크 배경 로그박스 기준으로도 읽혀야 함)
# textbox 는 모드와 무관하게 어두운 배경이므로 다크 계열을 기본으로 하나,
# 라이트 모드에서도 대비를 유지하도록 한 값으로 고정한다(로그는 어두운 패널).
LOG_INFO = "#cbd5e1"
LOG_WARN = "#fbbf24"
LOG_ERROR = "#f87171"
LOG_SUCCESS = "#34d399"

# 서비스 상태 뱃지 색 (상태바/라벨) — (light, dark)
STATUS_RUNNING = SUCCESS
STATUS_STOPPED = ("#94a3b8", "#64748b")
STATUS_ONE_SHOT = WARNING

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


def ctk_font(spec: dict):
    """FONT_* 사전 → customtkinter.CTkFont (지연 import로 순환 참조 회피)."""
    import customtkinter as ctk
    return ctk.CTkFont(**spec)
