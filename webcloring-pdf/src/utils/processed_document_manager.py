"""
영속적 처리 이력 관리 모듈

SQLite를 사용하여 문서 처리 이력을 영속적으로 저장하고,
중복 처리 방지 및 수정본 감지 기능을 제공합니다.
"""
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# 프로젝트 루트 (기본 DB 경로 계산용)
project_root = Path(__file__).parent.parent.parent

from utils.logger import logger


class ProcessedDocumentManager:
    """영속적 처리 이력 관리 클래스
    
    문서 처리 이력을 SQLite 데이터베이스에 저장하여:
    - 프로그램 재시작 후에도 중복 처리 방지
    - 문서 수정본 감지 및 재처리
    - 처리 통계 및 이력 조회
    
    Attributes:
        db_path: SQLite 데이터베이스 파일 경로
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """초기화
        
        Args:
            db_path: 데이터베이스 파일 경로 (기본값: data/state/processed_documents.db)
        """
        if db_path is None:
            db_path = project_root / "data" / "state" / "processed_documents.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        
        logger.info(f"ProcessedDocumentManager 초기화: {self.db_path}")
    
    def _init_database(self):
        """데이터베이스 및 테이블 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            # 메인 테이블 생성
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_documents (
                    doc_id TEXT PRIMARY KEY,
                    doc_hash TEXT NOT NULL,
                    drafter TEXT,
                    department TEXT,
                    processed_at TIMESTAMP NOT NULL,
                    status TEXT NOT NULL,
                    pdf_path TEXT,
                    excel_row INTEGER,
                    error_message TEXT,
                    version TEXT NOT NULL
                )
            """)
            
            # 인덱스 생성
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_at 
                ON processed_documents(processed_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status 
                ON processed_documents(status)
            """)
            
            conn.commit()
            logger.debug("데이터베이스 테이블 및 인덱스 생성 완료")
    
    def calculate_hash(self, table_rows: List) -> str:
        """문서 내용 해시 계산
        
        문서의 자재 데이터를 기반으로 SHA-256 해시를 생성합니다.
        문서가 수정되면 해시가 변경되어 수정본을 감지할 수 있습니다.
        
        Args:
            table_rows: 자재 데이터 리스트
            
        Returns:
            16자리 해시 문자열
        """
        content = str(sorted(table_rows)).encode('utf-8')
        full_hash = hashlib.sha256(content).hexdigest()
        return full_hash[:16]  # 앞 16자만 사용
    
    def is_processed(self, doc_id: str, doc_hash: str) -> Dict[str, any]:
        """문서 처리 여부 확인
        
        3가지 상황을 구분합니다:
        1. 미처리 문서 (신규)
        2. 이미 처리된 문서 (스킵)
        3. 수정된 문서 (재처리 필요)
        
        Args:
            doc_id: 문서 고유 ID (문서번호)
            doc_hash: 문서 내용 해시
            
        Returns:
            {
                'processed': bool,      # 처리 여부
                'modified': bool,       # 수정본 여부
                'previous': dict|None  # 이전 처리 정보
            }
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM processed_documents WHERE doc_id = ?",
                (doc_id,)
            )
            row = cursor.fetchone()
            
            if row is None:
                # 신규 문서
                return {
                    'processed': False,
                    'modified': False,
                    'previous': None
                }
            
            previous = dict(row)
            
            if previous['doc_hash'] == doc_hash:
                # 동일 문서 - 스킵
                logger.debug(f"문서 {doc_id}: 이미 처리됨 (해시 일치)")
                return {
                    'processed': True,
                    'modified': False,
                    'previous': previous
                }
            else:
                # 수정본 - 재처리 필요
                logger.info(
                    f"문서 {doc_id}: 수정본 감지 "
                    f"(이전: {previous['doc_hash']}, 현재: {doc_hash})"
                )
                return {
                    'processed': True,
                    'modified': True,
                    'previous': previous
                }
    
    def mark_processed(
        self,
        doc_id: str,
        doc_hash: str,
        status: str = 'success',
        drafter: Optional[str] = None,
        department: Optional[str] = None,
        pdf_path: Optional[str] = None,
        excel_row: Optional[int] = None,
        error_message: Optional[str] = None,
        version: str = '3.1'
    ):
        """문서 처리 완료 기록
        
        Args:
            doc_id: 문서 ID
            doc_hash: 문서 해시
            status: 처리 상태 ('success', 'failed', 'skipped')
            drafter: 기안자
            department: 부서
            pdf_path: PDF 파일 경로
            excel_row: Excel 행 번호
            error_message: 오류 메시지 (실패 시)
            version: 프로그램 버전
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO processed_documents
                    (doc_id, doc_hash, drafter, department, processed_at, 
                     status, pdf_path, excel_row, error_message, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc_id,
                    doc_hash,
                    drafter,
                    department,
                    datetime.now().isoformat(),
                    status,
                    pdf_path,
                    excel_row,
                    error_message,
                    version
                ))
                conn.commit()
            
            logger.debug(f"문서 {doc_id} 처리 기록 완료 (상태: {status})")
            
        except Exception as e:
            logger.error(f"문서 {doc_id} 처리 기록 실패: {e}")
            raise
    
    def get_statistics(self) -> Dict[str, any]:
        """처리 통계 정보 조회
        
        Returns:
            {
                'total': int,           # 전체 처리 문서 수
                'success': int,         # 성공 문서 수
                'failed': int,          # 실패 문서 수
                'skipped': int,         # 스킵 문서 수
                'success_rate': float   # 성공률 (%)
            }
        """
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM processed_documents"
            ).fetchone()[0]
            
            success = conn.execute(
                "SELECT COUNT(*) FROM processed_documents WHERE status='success'"
            ).fetchone()[0]
            
            failed = conn.execute(
                "SELECT COUNT(*) FROM processed_documents WHERE status='failed'"
            ).fetchone()[0]
            
            skipped = conn.execute(
                "SELECT COUNT(*) FROM processed_documents WHERE status='skipped'"
            ).fetchone()[0]
            
            success_rate = (success / total * 100) if total > 0 else 0
            
            return {
                'total': total,
                'success': success,
                'failed': failed,
                'skipped': skipped,
                'success_rate': round(success_rate, 2)
            }
    
    def get_recent_documents(self, limit: int = 10) -> List[Dict]:
        """최근 처리 문서 조회
        
        Args:
            limit: 조회할 문서 수
            
        Returns:
            문서 정보 리스트 (최신순)
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM processed_documents
                ORDER BY processed_at DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_failed_documents(self) -> List[Dict]:
        """실패한 문서 목록 조회
        
        Returns:
            실패 문서 정보 리스트
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM processed_documents
                WHERE status = 'failed'
                ORDER BY processed_at DESC
            """)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def reset(self, confirm: bool = False):
        """처리 이력 초기화 (주의!)
        
        Args:
            confirm: True일 때만 실행 (안전장치)
        """
        if not confirm:
            raise ValueError("reset()은 confirm=True로만 실행 가능합니다")
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM processed_documents")
            conn.commit()
        
        logger.warning("⚠️ 처리 이력이 모두 초기화되었습니다")
    
    def export_to_csv(self, output_path: Path):
        """처리 이력을 CSV로 내보내기
        
        Args:
            output_path: CSV 파일 경로
        """
        import csv
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM processed_documents")
            
            rows = cursor.fetchall()
            if not rows:
                logger.warning("내보낼 데이터가 없습니다")
                return
            
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows([dict(row) for row in rows])
        
        logger.info(f"처리 이력을 CSV로 내보냈습니다: {output_path}")


if __name__ == "__main__":
    # 간단한 테스트
    print("ProcessedDocumentManager 테스트\n")
    
    # 임시 DB 생성
    test_db = Path("test_processed.db")
    if test_db.exists():
        test_db.unlink()
    
    manager = ProcessedDocumentManager(test_db)
    
    # 1. 신규 문서 처리
    print("1. 신규 문서 테스트")
    result = manager.is_processed("DOC001", "hash123")
    print(f"   처리 여부: {result['processed']}")  # False
    
    manager.mark_processed(
        doc_id="DOC001",
        doc_hash="hash123",
        status='success',
        drafter="홍길동",
        department="생산팀"
    )
    
    # 2. 중복 문서 감지
    print("\n2. 중복 문서 테스트")
    result = manager.is_processed("DOC001", "hash123")
    print(f"   처리 여부: {result['processed']}")  # True
    print(f"   수정본: {result['modified']}")      # False
    
    # 3. 수정본 감지
    print("\n3. 수정본 테스트")
    result = manager.is_processed("DOC001", "hash456")
    print(f"   처리 여부: {result['processed']}")  # True
    print(f"   수정본: {result['modified']}")      # True
    
    # 4. 통계
    print("\n4. 통계")
    stats = manager.get_statistics()
    print(f"   전체: {stats['total']}, 성공: {stats['success']}, 성공률: {stats['success_rate']}%")
    
    # 정리
    test_db.unlink()
    print("\n✅ 테스트 완료")
