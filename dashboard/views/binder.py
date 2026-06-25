"""액상바인더출고 페이지 — webcloring-pdf가 PBHAv1.0 키워드로 수집해 백업한
액상바인더출고 데이터(/binder)를 표시. 자재요청과 동일한 화면·다운로드.

공용 렌더러(dataset_page.render)에 binder 데이터셋 파라미터만 넘긴다.
"""
from dataset_page import render

render(
    prefix="/binder",
    title="액상바인더출고",
    icon=":material/water_drop:",
    sheet_name="액상바인더출고",
    file_base="binder_requests",
    empty_msg="표시할 액상바인더출고 데이터가 없습니다.",
)
