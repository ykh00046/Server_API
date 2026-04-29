# 배포 체크리스트

> **버전**: v3.4  
> **대상**: INTEROJO 포털 자동화

---

## 📋 사전 준비

### 시스템 요구사항

- [ ] **Python 3.8+** 설치 확인

  ```bash
  python --version  # 3.8 이상
  ```

- [ ] **Chrome 브라우저** 최신 버전 설치
  - Chrome 설정 → 도움말 → Chrome 정보

- [ ] **디스크 공간** 확인
  - 최소: 1GB
  - 권장: 10GB 이상

### 의존성 설치

- [ ] **Python 패키지** 설치

  ```bash
  pip install -r requirements.txt
  ```

- [ ] 설치 확인
  ```bash
  pip list | grep selenium
  pip list | grep openpyxl
  pip list | grep psutil
  ```

---

## ⚙️ 설정

### 필수 설정

- [ ] **포털 로그인 정보** (`src/config/settings.py`)

  ```python
  PORTAL_ID = "your_id"
  PORTAL_PASSWORD = "your_password"
  WORKSMOBILE_ID = "your_id"
  WORKSMOBILE_PASSWORD = "your_password"
  ```

- [ ] **검색 설정** (`src/config/config.json`)
  ```json
  {
    "search": {
      "start_date": "2025.06.20",
      "keywords": ["자재", "접수"]
    }
  }
  ```

### 선택 설정

- [ ] **이메일 알림** (`src/config/config.json`)
  - Gmail 앱 비밀번호 생성
  - notification.enabled = true
  - sender_email, recipient_emails 설정

- [ ] **Google Sheets 백업**
  - credentials.json 파일 준비
  - OAuth 동의 화면 설정

---

## 🧪 테스트

### 1. 기본 기능 테스트

- [ ] **헬스 체크**

  ```python
  from src.services.health_checker import HealthChecker

  checker = HealthChecker()
  result = checker.run_all_checks()

  # 모든 항목 통과 확인
  assert result['overall_status'] == True
  ```

- [ ] **로그인 테스트**
  - GUI 실행 (`python main.py`)
  - "테스트 실행" 버튼 클릭
  - 로그인 성공 확인

- [ ] **문서 검색 테스트**
  - 검색 기간 1일로 설정
  - 문서 목록 표시 확인

### 2. 문서 처리 테스트

- [ ] **1개 문서 처리**

  ```bash
  # max_pages를 1로 설정
  python automation.py
  ```

  - PDF 저장 확인 (`data/PDF/`)
  - Excel 저장 확인 (`data/excel/`)
  - 로그 확인 (`logs/automation.log`)

- [ ] **중복 방지 확인**

  ```bash
  # 동일 검색 조건으로 2회 실행
  python automation.py
  python automation.py

  # 로그에서 "이미 처리됨 - 스킵" 확인
  ```

- [ ] **처리 이력 확인**

  ```python
  from src.utils.processed_document_manager import ProcessedDocumentManager

  manager = ProcessedDocumentManager()
  stats = manager.get_statistics()

  print(f"성공률: {stats['success_rate']}%")
  # 100% 확인
  ```

### 3. 알림 테스트 (설정 시)

- [ ] **이메일 알림**
  - notification.enabled = true
  - 자동화 실행
  - 완료 이메일 수신 확인

- [ ] **헬스 체크 경고**
  - 디스크 공간 부족 시뮬레이션 (어려움)
  - 또는 포털 URL 임시 변경
  - 경고 이메일 수신 확인

---

## 🗂️ 파일 및 권한 확인

### 디렉토리 구조

- [ ] **로그 디렉토리** 생성 및 권한

  ```bash
  mkdir logs
  # 쓰기 권한 확인
  ```

- [ ] **Excel 저장 경로** 권한

  ```bash
  # data/excel/ 디렉토리 쓰기 가능 확인
  ```

- [ ] **PDF 저장 경로** 권한

  ```bash
  # data/PDF/ 디렉토리 쓰기 가능 확인
  ```

- [ ] **상태 DB 경로** 권한
  ```bash
  # data/state/ 디렉토리 생성 및 쓰기 가능
  ```

---

## 📊 운영 준비

### 백업 전략

- [ ] **Excel 파일 백업**
  - 자동 백업: `data/excel/backup/` (최근 10개 유지)
  - 수동 백업: 주간 단위 외부 저장소

- [ ] **처리 이력 DB 백업**
  ```bash
  # 월간 백업 권장
  cp data/state/processed_documents.db backup/processed_$(date +%Y%m).db
  ```

### 모니터링 설정

- [ ] **이메일 알림 활성화**
  - 매일 실행 결과 확인

- [ ] **로그 모니터링**
  - 로그 레벨: INFO
  - 에러 발생 시 즉시 확인

- [ ] **디스크 공간 모니터링**
  - 최소 1GB 여유 공간 유지
  - PDF 파일 정리 계획

---

## 🕐 스케줄 설정 (선택)

### Windows 작업 스케줄러

1. **작업 스케줄러 열기**
   - `Win + R` → `taskschd.msc`

2. **작업 만들기**
   - 이름: "INTEROJO 자동화"
   - 설명: "매일 자동 실행"

3. **트리거 설정**
   - 일정: 매일
   - 시작 시간: 01:00 (자정 이후)

4. **작업 설정**
   - 프로그램: `python.exe`
   - 인수: `C:\full\path\to\automation.py`
   - 시작 위치: `C:\full\path\to\project`

5. **조건 설정**
   - ☑️ AC 전원 사용 시에만 작업 시작
   - ☐ 컴퓨터를 AC 전원에서 사용 중인 경우 중지

6. **설정**
   - ☑️ 작업이 실행되지 않으면 가능한 빨리 시작
   - ☑️ 연속 실패 시 다시 시작 (3회까지)

### 수동 테스트

- [ ] 스케줄 작업 수동 실행
- [ ] 실행 이력 확인
- [ ] 로그 파일 생성 확인

---

## ✅ 최종 점검

### 기능 검증

- [ ] 로그인 성공
- [ ] 문서 검색 정상
- [ ] 문서 처리 정상 (PDF + Excel)
- [ ] 중복 방지 작동
- [ ] 수정본 감지 작동
- [ ] 헬스 체크 통과
- [ ] 이메일 알림 정상 (설정 시)

### 성능 확인

- [ ] 문서당 처리 시간 < 10초
- [ ] 메모리 사용량 < 500MB
- [ ] 디스크 I/O 정상

### 안정성 확인

- [ ] 3회 연속 정상 실행
- [ ] 에러 발생 시 자동 재시도 확인
- [ ] 로그 파일 정상 생성

---

## 📚 문서 확인

- [ ] **README.md** 최신 버전 확인
- [ ] **USER_GUIDE.md** 읽고 단계 따라하기
- [ ] **DEPLOYMENT_CHECKLIST.md** (본 문서) 모든 항목 체크

---

## 🚨 문제 발생 시

### 즉시 조치

1. **로그 파일 확인**
   - `logs/automation.log`
   - 마지막 오류 메시지 확인

2. **헬스 체크 실행**

   ```python
   from src.services.health_checker import HealthChecker
   checker = HealthChecker()
   result = checker.run_all_checks()
   print(result['summary'])
   ```

3. **처리 이력 확인**
   ```python
   from src.utils.processed_document_manager import ProcessedDocumentManager
   manager = ProcessedDocumentManager()
   failed = manager.get_failed_documents()
   ```

### 복구 절차

1. **설정 파일 재확인**
2. **의존성 재설치** (`pip install -r requirements.txt --force-reinstall`)
3. **Chrome 업데이트**
4. **시스템 재부팅**

---

## 📞 지원

- **문서**: `docs/USER_GUIDE.md`
- **이슈**: GitHub Issues
- **이메일**: support@example.com

---

**체크리스트 버전**: 1.0  
**최종 업데이트**: 2026-01-29
