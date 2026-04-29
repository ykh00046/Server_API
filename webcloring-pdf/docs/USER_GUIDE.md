# INTEROJO 자동화 사용자 가이드

> **버전**: v3.4  
> **최종 업데이트**: 2026-01-29

---

## 📋 목차

1. [시작하기](#시작하기)
2. [기본 사용법](#기본-사용법)
3. [고급 설정](#고급-설정)
4. [모니터링 및 알림](#모니터링-및-알림)
5. [트러블슈팅](#트러블슈팅)

---

## 시작하기

### 시스템 요구사항

- **Python**: 3.8 이상
- **Chrome**: 최신 버전
- **OS**: Windows 10/11
- **디스크 공간**: 최소 1GB (권장 10GB)

### 설치

#### 1. Python 의존성 설치

```bash
pip install -r requirements.txt
```

#### 2. 설정 파일 수정

**`src/config/settings.py`** (필수):

```python
# 포털 로그인 정보
PORTAL_ID = "your_id"
PORTAL_PASSWORD = "your_password"

# WorksMobile 로그인 (2FA)
WORKSMOBILE_ID = "your_id"
WORKSMOBILE_PASSWORD = "your_password"
```

**`src/config/config.json`** (선택):

- 검색 기간 조정
- 이메일 알림 설정
- 페이지 제한 설정

#### 3. 첫 실행

```bash
python main.py
```

GUI 창이 열리면 "▶️ 수동 실행" 버튼을 클릭하세요.

---

## 기본 사용법

### GUI 모드 (권장)

```bash
python main.py
```

**주요 기능**:

- ✅ 설정 수정 (로그인 정보, 검색 기간)
- ✅ 수동 실행 (즉시 실행)
- ✅ 자동 실행 (스케줄 설정)
- ✅ 로그 모니터링 (실시간 로그)
- ✅ Google Sheets 백업

### 콘솔 모드 (백그라운드)

```bash
python automation.py
```

**특징**:

- GUI 없이 실행
- 백그라운드 실행 가능
- 스케줄러 연동 용이

---

## 고급 설정

### 동적 필터링

최근 처리된 문서를 기준으로 자동 검색:

**`settings.py`**:

```python
# 동적 필터링 활성화
ENABLE_DYNAMIC_FILTERING = True

# 최종 처리일 - N일부터 검색
DAYS_BACK = 3
```

**동작 방식**:

1. Excel 파일에서 가장 최근 처리일 확인
2. `최근 처리일 - 3일`을 시작일로 설정
3. 자동 검색

### 페이지 제한

대량 문서 처리 시 최대 페이지 수 설정:

**`config.json`**:

```json
{
  "pagination": {
    "max_pages": 50,
    "page_size": 50
  }
}
```

- `max_pages`: 최대 처리 페이지 (무한 루프 방지)
- `page_size`: 페이지당 문서 수 (50 권장)

### 처리 이력 관리

SQLite 기반 영속적 처리 이력:

```python
from src.utils.processed_document_manager import ProcessedDocumentManager

manager = ProcessedDocumentManager()

# 통계 확인
stats = manager.get_statistics()
print(f"총 처리: {stats['total']}건")
print(f"성공률: {stats['success_rate']}%")

# 최근 처리 문서
recent = manager.get_recent_documents(limit=10)
for doc in recent:
    print(f"{doc['doc_id']} - {doc['status']}")

# 실패 문서 확인
failed = manager.get_failed_documents()
for doc in failed:
    print(f"{doc['doc_id']}: {doc['error_message']}")

# CSV 내보내기
manager.export_to_csv(Path("처리이력.csv"))
```

---

## 모니터링 및 알림

### 이메일 알림 설정

#### Gmail 사용 시

1. **앱 비밀번호 생성**:
   - Google 계정 → 보안
   - 2단계 인증 활성화
   - "앱 비밀번호" 생성 (메일 → 기타)
   - 16자리 비밀번호 복사

2. **config.json 설정**:

```json
{
  "notification": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "your@gmail.com",
    "sender_password": "xxxx xxxx xxxx xxxx",
    "recipient_emails": ["team1@example.com", "team2@example.com"],
    "notify_on_success": true,
    "notify_on_failure": true
  }
}
```

3. **테스트**:

```python
from src.services.notification_service import NotificationService

service = NotificationService()
if service.test_connection():
    print("✅ 연결 성공")
```

### 헬스 체크

자동화 시작 전 시스템 상태 자동 점검:

**점검 항목**:

- ✅ 포털 접속 가능 여부
- ✅ Google Sheets 연결 상태
- ✅ 디스크 여유 공간 (최소 1GB)
- ✅ Excel 파일 쓰기 권한

**결과**:

- 모든 점검 통과 → 자동화 진행
- 포털 접속 불가 → **자동화 중단**
- 기타 경고 → 경고 표시 후 진행

### 메트릭 확인

실행 후 통계 확인:

```python
from src.core.portal_automation import PortalAutomation

automation = PortalAutomation()
automation.run_automation()

# 메트릭 요약
summary = automation.metrics.get_summary()
print(f"총 처리: {summary['total_documents']}건")
print(f"성공률: {summary['success_rate']}%")
print(f"평균 처리 시간: {summary['avg_processing_time']}초")
print(f"메모리 사용: {summary['avg_memory_mb']}MB")
```

---

## 트러블슈팅

### 포털 로그인 실패

**증상**: "로그인 실패" 오류

**해결**:

1. `settings.py`에서 ID/비밀번호 확인
2. 포털에 직접 로그인 테스트
3. 2FA 설정 확인 (WorksMobile)

### Excel 저장 실패

**증상**: "Excel 저장 오류"

**해결**:

1. 파일 읽기 전용 확인:
   ```bash
   # 읽기 전용 해제
   attrib -r "data/excel/Material_Release_Request.xlsx"
   ```
2. 디스크 공간 확인:
   ```python
   import psutil
   disk = psutil.disk_usage('.')
   print(f"여유 공간: {disk.free / 1024**3:.2f}GB")
   ```

### Google Sheets 연결 실패

**증상**: "Google Sheets 연결 오류"

**해결**:

1. `credentials.json` 파일 확인
2. Google Cloud Console에서 API 활성화 확인
3. OAuth 동의 화면 설정

### 헬스 체크 실패

**증상**: "❌ 포털 접속 불가능"

**해결**:

1. 인터넷 연결 확인
2. 포털 URL 확인 (`config.json`)
3. 방화벽/프록시 설정 확인

### Chrome 드라이버 오류

**증상**: "WebDriver 오류"

**해결**:

1. Chrome 브라우저 업데이트
2. webdriver-manager가 자동으로 처리하지만, 수동 설치 가능:
   ```bash
   pip install --upgrade webdriver-manager
   ```

### 중복 처리

**증상**: 동일 문서가 중복 처리됨

**확인**:

```python
from src.utils.processed_document_manager import ProcessedDocumentManager

manager = ProcessedDocumentManager()
stats = manager.get_statistics()
print(f"중복률: {stats.get('duplicate_rate', 0)}%")
```

**해결**:

- 정상: 중복률 0%
- 비정상: DB 파일 확인 (`data/state/processed_documents.db`)

### 이메일 발송 실패

**증상**: "SMTP 인증 실패"

**해결**:

1. 앱 비밀번호 재생성
2. SMTP 서버/포트 확인
3. 2단계 인증 활성화 확인

---

## 로그 파일 위치

- **자동화 로그**: `logs/automation.log`
- **에러 스크린샷**: `screenshots/error_*.png`
- **처리 이력 DB**: `data/state/processed_documents.db`

---

## 추가 도움말

### 커뮤니티 지원

- GitHub Issues: [프로젝트 링크]
- 이메일: support@example.com

### 업데이트

최신 버전 확인:

```bash
git pull origin main
pip install -r requirements.txt --upgrade
```

---

**문서 버전**: 1.0  
**작성일**: 2026-01-29
