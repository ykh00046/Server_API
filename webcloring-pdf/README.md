# INTEROJO 포털 자동화 시스템

> **버전**: 3.4 | **최종 업데이트**: 2026-01-29

## 개요

INTEROJO 포털에서 자재 요청 문서를 자동으로 검색하고, PDF로 저장하며, Excel 파일로 데이터를 정리하는 자동화 시스템입니다. **GUI 인터페이스**, **Google Sheets 자동 백업**, **이메일 알림**, **헬스 체크**를 지원하여 안정적이고 사용자 친화적인 관리가 가능합니다.

## 📚 문서

- **[USER_GUIDE.md](docs/USER_GUIDE.md)** - 사용자 가이드 (설정 및 사용법)
- **[DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md)** - 배포 체크리스트
- **[BUILD_GUIDE.md](BUILD_GUIDE.md)** - 실행 파일 빌드 가이드
- **[CHANGELOG.md](CHANGELOG.md)** - 변경 이력
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - 개발자 가이드

## 🆕 v3.4 주요 기능

### ✅ 데이터 무결성

- **영속적 처리 이력**: SQLite 기반, 프로그램 재시작 후에도 중복 방지
- **수정본 자동 감지**: 문서 수정 시 해시 변경 감지 및 재처리
- **원자적 파일 쓰기**: 저장 중 오류 발생해도 기존 파일 보호

### 📊 모니터링 & 알림

- **실시간 메트릭 수집**: 처리 통계, 성능 지표, 리소스 사용량
- **이메일 알림**: 자동화 완료/실패 시 HTML 리포트 발송
- **헬스 체크**: 자동화 시작 전 시스템 상태 점검 (포털, 디스크, 권한)

### 🔁 안정성 향상

- **자동 재시도**: 일시적 오류 자동 복구 (Exponential Backoff)
- **페이지네이션**: 다중 페이지 자동 처리 (최대 100페이지)
- **에러 핸들링**: 상세 로그 및 스크린샷

## 주요 기능 (기존)

- **GUI 관리 인터페이스**: 설정 변경, 실행 상태 확인, 로그 모니터링
- **포털 자동 로그인**: INTEROJO 포털에 자동으로 로그인
- **스마트 문서 검색**: "자재" 키워드로 완료문서함에서 문서 검색
- **동적 필터링**: 마지막 처리 문서 날짜부터 자동 검색 (중복 최소화)
- **PDF 자동 저장**: Chrome DevTools Protocol을 사용한 고품질 PDF 생성
- **Excel 데이터 정리**: 자재 정보를 구조화된 Excel 파일로 저장
- **Google Sheets 자동 백업**: 자동화 완료 시 자동으로 백업 (배치 처리)
- **실시간 자동 스케줄링**: GUI 내장 스케줄러로 설정 시간에 자동 실행

## 🚀 빠른 시작

### 간편 실행 (배치 파일)

프로젝트 폴더에서 원하는 .bat 파일을 더블클릭하세요:

#### 1. `실행.bat`

GUI 모드로 프로그램 실행 (권장)

```
더블클릭 → GUI 창 열림
```

#### 2. `자동화실행.bat`

GUI 없이 자동화만 실행 (콘솔 모드)

```
더블클릭 → 자동화 실행 → 완료
```

#### 3. `빌드.bat`

실행 파일(.exe) 생성

```
더블클릭 → dist/ 폴더에 .exe 생성
```

#### 4. `패키지설치.bat`

처음 설치 시 필요한 패키지 설치

```
더블클릭 → 자동 설치
```

### 첫 실행 순서

1. `패키지설치.bat` 더블클릭 (최초 1회)
2. `실행.bat` 더블클릭
3. GUI에서 "설정" → 로그인 정보 입력
4. "지금 실행하기" 클릭

## 프로젝트 구조

```
PythonProject5-pdf/
├── src/                        # 소스 코드
│   ├── core/                   # 핵심 로직
│   │   ├── portal_automation.py    # 포털 자동화
│   │   ├── excel_manager.py        # Excel 관리
│   │   ├── scheduler.py            # 스케줄러
│   │   └── document_monitor.py     # 문서 모니터링
│   ├── services/               # 외부 서비스
│   │   ├── google_sheets_manager.py    # Google Sheets 백업
│   │   ├── health_check.py
│   │   └── notification_service.py
│   ├── gui/                    # GUI
│   │   ├── main_window.py          # 메인 윈도우
│   │   ├── settings_dialog.py      # 설정 창
│   │   └── google_sheets_dialog.py # Google Sheets 설정
│   ├── utils/                  # 유틸리티
│   │   ├── logger.py
│   │   ├── error_handler.py
│   │   └── exceptions.py
│   └── config/                 # 설정
│       ├── settings.py             # 설정 로더
│       ├── config.json             # 중앙 설정
│       └── google_sheets_settings.json
├── data/                       # 데이터 출력
│   ├── PDF/                    # PDF 파일
│   └── excel/                  # Excel 파일
│       └── Material_Release_Request.xlsx
├── docs/                       # 문서
│   └── archive/                # 이전 버전 문서
├── logs/                       # 로그 파일
├── main.py                     # 진입점
├── .env                        # 환경 변수
├── README.md                   # 사용자 가이드
├── CHANGELOG.md                # 변경 이력
├── DEVELOPMENT.md              # 개발 문서
├── requirements_service.txt    # 패키지 의존성
├── 실행.bat                    # GUI 실행
├── 자동화실행.bat              # 콘솔 실행
├── 빌드.bat                    # 빌드
└── 패키지설치.bat              # 패키지 설치
```

## 설치 및 실행

### 개발 환경 (PyCharm)

#### 1. 가상환경 설정

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
```

#### 2. 의존성 설치

```bash
pip install -r requirements_service.txt
```

#### 3. 환경 변수 설정

`.env` 파일 생성:

```env
PORTAL_USERNAME=your_username
PORTAL_PASSWORD=your_password
PORTAL_URL=http://portal.interojo.com/portal/main/portalMain.do
APPROVAL_URL=http://portal.interojo.com/approval/main/approvalMain.do
SEARCH_START_DATE=2025.07.24
DEBUG_MODE=false

# 자동 실행 스케줄 설정
SCHEDULE_TIME=09:00
AUTO_ENABLED=True
WEEKDAYS_ONLY=False

# 스마트 필터링 설정
DYNAMIC_FILTERING=True
DAYS_BACK=0
```

#### 4. 실행

```bash
# GUI 모드 (기본)
python main.py

# 자동화만 실행
python main.py --auto
```

## 핵심 컴포넌트

### PortalAutomation 클래스

- 웹드라이버 초기화 및 관리
- 포털 로그인 자동화
- 동적 필터링 기반 문서 검색
- PDF 생성 및 저장

### ExcelManager 클래스

- Excel 파일 생성 및 관리
- 중복 데이터 방지
- 자동 저장 및 Google Sheets 백업

### GoogleSheetsManager 클래스 (v3.0)

- 배치 처리 방식 자동 백업
- API 호출 최적화 (98% 감소)
- Rate Limiting 및 Fail-Safe

**더 자세한 정보는 [DEVELOPMENT.md](DEVELOPMENT.md)를 참조하세요.**

## Excel 출력 형식

| 순번 | 자재코드 | 품명        | 요청수량(g단위) | 사유   | 요청부서 | 기안자 | 문서번호     | 처리일시            |
| ---- | -------- | ----------- | --------------- | ------ | -------- | ------ | ------------ | ------------------- |
| 1    | AC0064   | Omnirad2100 | 3000            | 생산용 | 생산팀   | 홍길동 | 20250728P001 | 2025-07-28 14:30:00 |
| 2    | AC0041   | Omnirad819  | 32.00           | 연구용 | R&D팀    | 김연구 | 20250728P002 | 2025-07-28 14:31:00 |

**파일 위치**: `data/excel/Material_Release_Request.xlsx`

## GUI 시스템 특징

### 메인 GUI 창 기능

- **현재 상태 표시**: 실행 상태, 마지막 실행 시간, 다음 실행 시간 (실시간 업데이트)
- **즉시 실행**: "지금 실행하기" 버튼으로 수동 실행
- **스마트 자동 모드**: 내장 스케줄러로 설정 시간에 백그라운드 자동 실행
- **설정 관리**: GUI로 모든 옵션 통합 관리
- **실시간 로그 모니터링**: GUI 내 로그 출력 및 로그 폴더 바로 열기
- **결과 확인**: Excel 파일 바로 열기

### 설정 다이얼로그 기능 (완전 개선)

- **로그인 정보**: 사용자명/비밀번호 입력 및 저장
- **스마트 검색 설정**:
  - 동적 필터링 (마지막 문서 날짜부터 자동 검색)
  - 수동 날짜 설정 (고정 날짜 사용)
  - 여분 날짜 설정 (놓칠 수 있는 문서 고려)
- **자동 실행 스케줄**: 시간 설정, 평일만 옵션
- **연결 테스트**: 설정 저장 전 로그인 테스트 기능

### 실행 모드

```bash
# GUI 모드 (기본) - 더블클릭 또는
interojo_automation.exe

# 자동화 모드 (Windows 스케줄러용)
interojo_automation.exe --auto

# 테스트 모드 (설정 확인)
interojo_automation.exe --test
```

## 최근 업데이트

### v3.1 (2025-12-03)

- **문서 정리**: CHANGELOG.md, DEVELOPMENT.md 추가
- **설정 통합**: config.json으로 하드코딩 제거
- **프로젝트 최적화**: 크기 445MB → 3.7MB (99% 감소)
- **버그 수정**: GUI 백업 버튼 오류 수정
- **디버그 모드**: 자동 종료 설정 (DEBUG_MODE=false)

### v3.0 (2025-12-02)

- **Google Sheets 통합**: 배치 처리 방식 자동 백업
- **API 최적화**: API 호출 98% 감소
- **Lazy Loading**: 초기 로딩 시간 단축
- **Threading**: GUI 프리징 방지

### v2.0 (2025-07-28)

- **스마트 필터링**: 동적 검색으로 효율성 극대화
- **품명 파싱 개선**: 숫자 포함 품명 정확 처리
- **자동 스케줄링**: GUI 내장 스케줄러

**전체 변경 이력은 [CHANGELOG.md](CHANGELOG.md)를 참조하세요.**

## 사용법

### GUI 모드 사용법

#### 1. 첫 실행 설정 (완전 개선)

1. `interojo_automation.exe` 더블클릭하여 GUI 실행
2. **설정** 버튼 클릭
3. **로그인 정보** 입력 (사용자명, 비밀번호)
4. **스마트 검색 설정**:
   - ✅ **스마트 필터링 사용** (권장): 마지막 문서 날짜부터 자동 검색
   - 여분 검색 일수: 0일 (놓칠 수 있는 문서 고려)
   - 또는 수동 날짜 설정 선택
5. **자동 실행 스케줄**: 원하는 시간 설정 (예: 14:30)
6. **연결 테스트** 버튼으로 로그인 확인
7. **저장** 버튼 클릭

#### 2. 수동 실행

- **지금 실행하기** 버튼 클릭
- 하단 로그 영역에서 실행 상황 실시간 확인
- 완료 후 **Excel 열기** 버튼으로 결과 확인

#### 3. 스마트 자동 모드 (신기능)

- **자동 모드 시작** 버튼 클릭
- 설정된 시간에 백그라운드에서 자동 실행
- 실시간으로 다음 실행 시간 표시
- **자동 모드 정지** 버튼으로 언제든 중단 가능

### Windows 작업 스케줄러 연동

```bash
# 작업 스케줄러에서 다음 명령으로 등록
C:\path\to\interojo_automation.exe --auto
```

## 처리 결과 예시

### GUI 실행 화면

```
INTEROJO 자동화 관리 시스템 v2.0
═══════════════════════════════════
상태: 🟢 자동 모드 활성 (매일 14:30)
마지막 실행: 2025-07-28 14:30
다음 실행: 2025-07-29 14:30

[지금 실행하기] [자동 모드 정지]
[설정] [로그 보기] [Excel 열기]

실행 로그:
[14:30:15] 🤖 자동 실행 시작
[14:30:18] 스마트 필터링 모드: 2025.07.27 (여분 0일)
[14:30:21] 포털 로그인 성공
[14:30:24] 문서 검색 완료: 2개 발견 (중복 0개)
[14:30:35] HTML 테이블에서 추출: ['1', 'AC0064', 'Omnirad2100', '3000', '생산용']
[14:30:41] 문서 처리 완료: 20250728P001
[14:30:52] ✅ 자동화 완료 (처리: 2건, 효율성: 100%)
```

### 파일 결과 구조

```
실행파일폴더/
├── interojo_automation.exe
├── .env (설정 저장)
├── excel/
│   ├── Material_Release_Request.xlsx (결과 파일)
│   └── backup/ (백업 파일들)
├── PDF/ (저장된 PDF 문서들)
└── logs/ (실행 로그들)
```

## 주요 특징

### ✅ 완료된 기능

- **스마트 필터링**: 마지막 문서 날짜 기반 동적 검색
- **Google Sheets 백업**: 자동화 종료 시 배치 백업 (API 호출 98% 감소)
- **GUI 관리**: 직관적인 인터페이스와 실시간 상태 모니터링
- **자동 스케줄링**: 설정 시간에 백그라운드 자동 실행
- **중복 방지**: 처리된 문서 재처리 방지

### 🚀 성능

- **프로젝트 크기**: 99% 감소 (445MB → 3.7MB)
- **API 호출**: 98% 감소 (100회 → 2회)
- **처리 시간**: 문서당 평균 30-60초

## 향후 계획

- **페이지네이션**: 다중 페이지 자동 처리 (최대 100페이지)
- **Incremental Update**: Google Sheets 신규 데이터만 추가
- **단위 테스트**: 코드 안정성 검증
- **알림 시스템**: 이메일/슬랙 연동

**자세한 내용은 [CHANGELOG.md](CHANGELOG.md)를 참조하세요.**

## 문제 해결

### GUI 관련 문제

1. **GUI 창이 안 열림**: tkinter 설치 확인, Python 환경 확인
2. **설정이 저장 안됨**: 실행파일 위치에 쓰기 권한 확인
3. **자동 모드 작동 안함**: Windows 작업 스케줄러 설정 확인

### 자동화 관련 문제

1. **로그인 실패**: GUI에서 **연결 테스트** 후 설정 확인
2. **PDF 저장 실패**: Chrome 브라우저 최신 버전 설치
3. **Excel 저장 안됨**: `excel/` 폴더 권한 확인
4. **문서 검색 안됨**: 검색 시작 날짜 및 포털 접속 상태 확인

### 성능 최적화

- **메모리 사용량**: GUI 대기 시 20-30MB, 실행 시 100-200MB
- **실행 시간**: 문서 1개당 평균 30-60초
- **백그라운드 모드**: 자동 모드 시 최소 리소스 사용

**더 자세한 문제 해결 방법은 [DEVELOPMENT.md](DEVELOPMENT.md)를 참조하세요.**

---

## 라이선스

이 프로젝트는 INTEROJO 내부 사용을 위해 개발되었습니다.

**버전**: 3.1 | **최종 업데이트**: 2025-12-03
