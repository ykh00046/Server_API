"""
pytest 설정 및 공통 fixture
"""
import pytest
import sys
from pathlib import Path
import tempfile
import shutil

# 테스트에서 프로젝트 모듈을 import할 수 있도록 src 경로 추가
_src_root = Path(__file__).parent.parent / "src"
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))


@pytest.fixture
def test_data_dir():
    """테스트 데이터 디렉토리"""
    return Path(__file__).parent / "data"


@pytest.fixture
def temp_dir():
    """임시 디렉토리 (테스트 후 자동 정리)"""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    
    # 정리
    if temp_path.exists():
        shutil.rmtree(temp_path)


@pytest.fixture
def mock_excel_file(temp_dir):
    """임시 Excel 파일 경로"""
    return temp_dir / "test_materials.xlsx"


@pytest.fixture
def mock_db_file(temp_dir):
    """임시 SQLite DB 파일 경로"""
    return temp_dir / "test_processed.db"


@pytest.fixture
def sample_table_rows():
    """샘플 자재 테이블 데이터"""
    return [
        ["1", "MAT001", "Omnirad2100", "500", "R&D 실험용"],
        ["2", "MAT002", "TPO", "300", "생산 투입"],
        ["3", "MAT003", "Bisphenol A", "1000", "품질 테스트"]
    ]


@pytest.fixture
def sample_document_info():
    """샘플 문서 정보"""
    return {
        'doc_id': '20251127P001',
        'drafter': '홍길동',
        'department': '생산팀',
        'title': '자재 요청서'
    }
