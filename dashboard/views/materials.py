"""자재요청 페이지 — webcloring-pdf가 백업한 자재 데이터(/materials)를 표시.

공용 렌더러(dataset_page.render)에 자재 데이터셋 파라미터만 넘긴다.
액상바인더출고 등 다른 데이터셋은 views/binder.py 처럼 prefix만 바꿔 재사용.
"""
from dataset_page import render

render(
    prefix="/materials",
    title="자재요청",
    icon=":material/receipt_long:",
    sheet_name="자재요청",
    file_base="material_requests",
    empty_msg="표시할 자재요청 데이터가 없습니다.",
)
