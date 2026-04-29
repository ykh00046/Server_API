# 빌드 가이드 (Build Guide)

> INTEROJO 포털 자동화 시스템 v3.1.0
> 최종 업데이트: 2025-12-03

---

## 📋 목차

1. [빌드 개요](#빌드-개요)
2. [왜 이렇게 빌드하는가?](#왜-이렇게-빌드하는가)
3. [빌드 전 준비사항](#빌드-전-준비사항)
4. [빌드 실행 방법](#빌드-실행-방법)
5. [빌드 검증](#빌드-검증)
6. [문제 해결](#문제-해결)
7. [주의사항](#주의사항)

---

## 빌드 개요

### 빌드 결과물
- **실행 파일**: `interojo_automation.exe` (9.5 MB)
- **전체 크기**: 약 99 MB (numpy 포함)
- **배포 방식**: `dist/interojo_automation/` 폴더 전체 압축

### 빌드 환경
- **Python**: 3.13.0 (3.8+ 호환)
- **PyInstaller**: 6.16.0
- **OS**: Windows 11 (Windows 10+ 호환)

---

## 왜 이렇게 빌드하는가?

### 1️⃣ build.py를 사용하지 않는 이유

**문제점**:
```python
# build.py의 의존성 체크 코드
__import__(package.replace('-', '_'))
```

**발생하는 오류**:
- ❌ 특수문자(✓, ✗) Windows 콘솔 인코딩 오류 (`UnicodeEncodeError`)
- ❌ PyInstaller 모듈 체크 실패 (실제로는 설치되어 있음)

**해결 방법**:
- ✅ PyInstaller를 **직접 실행**
- ✅ `automation.spec` 파일 사용

---

### 2️⃣ numpy를 포함해야 하는 이유

**문제**:
```
ModuleNotFoundError: No module named 'numpy'
```

**원인**:
- `openpyxl`이 내부적으로 `numpy`에 의존
- 빌드 최적화를 위해 numpy를 제외하면 실행 시 오류 발생

**해결**:
```python
# automation.spec
excludes = [
    'matplotlib',
    # 'numpy',  ❌ 제외하면 안 됨!
    'pandas',
    'scipy',
]
```

**결과**:
- ✅ 빌드 크기 증가 (+29 MB)
- ✅ 정상 작동 보장

---

### 3️⃣ automation.spec 파일이 필요한 이유

**spec 파일의 역할**:
1. 프로젝트 구조 명시 (`src/` 폴더)
2. 필수 모듈 지정 (`hiddenimports`)
3. 데이터 파일 포함 (`config.json` 등)
4. 제외 모듈 관리
5. GUI 모드 설정 (콘솔 숨김)

**spec 파일 없이 빌드하면**:
- ❌ 모듈 누락 가능성
- ❌ 데이터 파일 미포함
- ❌ 불필요한 모듈 과다 포함

---

## 빌드 전 준비사항

### ✅ 체크리스트

#### 1. Python 환경 확인
```bash
python --version
# 출력: Python 3.13.0 (또는 3.8+)
```

#### 2. 필수 패키지 설치 확인
```bash
pip list | grep -E "pyinstaller|selenium|gspread|openpyxl|numpy"
```

**확인해야 할 패키지**:
- pyinstaller >= 6.0
- selenium >= 4.0
- openpyxl >= 3.0
- gspread >= 5.0
- google-auth >= 2.0
- numpy (자동 설치됨)

#### 3. automation.spec 파일 존재 확인
```bash
ls automation.spec
# 파일이 없으면 생성 필요
```

#### 4. 필수 소스 파일 확인
```bash
ls -la src/
# core/, services/, gui/, config/, utils/ 폴더 확인
```

---

## 빌드 실행 방법

### 🚀 권장 방법 (PyInstaller 직접 실행)

#### 1. 이전 빌드 정리
```bash
cd /c/X/PythonProject/PythonProject5-pdf
rm -rf build dist
```

#### 2. 빌드 실행
```bash
python -m PyInstaller automation.spec --noconfirm --clean
```

**옵션 설명**:
- `automation.spec`: 빌드 설정 파일
- `--noconfirm`: 기존 파일 덮어쓰기 확인 생략
- `--clean`: 캐시 정리 후 빌드

#### 3. 빌드 진행 확인
빌드는 약 1-2분 소요됩니다.

**진행 단계**:
1. `INFO: Analyzing modules...` - 모듈 분석
2. `INFO: Building PYZ...` - Python 아카이브 생성
3. `INFO: Building PKG...` - 패키지 생성
4. `INFO: Building EXE...` - 실행 파일 생성
5. `INFO: Building COLLECT...` - 파일 수집
6. `INFO: Build complete!` - 완료

#### 4. 결과 확인
```bash
ls -lh dist/interojo_automation/
# interojo_automation.exe (9.5 MB)
# _internal/ (라이브러리)
```

---

### ⚠️ build.py 사용 시 (권장하지 않음)

만약 build.py를 꼭 사용해야 한다면:

```bash
# 의존성 체크 건너뛰기
python build.py --skip-deps
```

**주의**:
- 인코딩 오류 발생 가능
- 불안정할 수 있음

---

## 빌드 검증

### 1️⃣ 파일 존재 확인
```bash
cd dist/interojo_automation/
ls -lh

# 확인할 파일:
# - interojo_automation.exe (9.5 MB)
# - _internal/ (폴더)
# - README.txt (선택사항)
```

### 2️⃣ 크기 확인
```bash
du -sh dist/interojo_automation/
# 약 99MB (numpy 포함)
```

### 3️⃣ 실행 테스트

#### 방법 1: GUI 시작 테스트
```bash
cd dist/interojo_automation/
./interojo_automation.exe
# GUI 창이 열리면 성공
```

#### 방법 2: 로그 확인
```bash
# 실행 후 logs 폴더 확인
ls -la logs/
cat logs/automation_*.log
```

#### 방법 3: 간단한 기능 테스트
1. 실행 파일 더블클릭
2. "설정" 버튼 클릭 → 설정 창 열림 확인
3. 창 닫기 → 프로그램 종료 확인

---

## 문제 해결

### ❌ 문제 1: ModuleNotFoundError: No module named 'numpy'

**원인**: numpy가 빌드에서 제외됨

**해결**:
```python
# automation.spec 수정
excludes = [
    'matplotlib',
    # 'numpy',  ← 이 줄 제거 또는 주석 처리
    'pandas',
]
```

**재빌드**:
```bash
rm -rf build dist
python -m PyInstaller automation.spec --noconfirm --clean
```

---

### ❌ 문제 2: UnicodeEncodeError (build.py 사용 시)

**오류 메시지**:
```
UnicodeEncodeError: 'cp949' codec can't encode character '\u2717'
```

**원인**: Windows 콘솔이 특수문자를 지원하지 않음

**해결**: PyInstaller 직접 실행 방법 사용

---

### ❌ 문제 3: PyInstaller 모듈 체크 실패

**오류 메시지**:
```
ModuleNotFoundError: No module named 'pyinstaller'
```

**원인**: build.py의 모듈 체크 로직 문제

**해결**:
```bash
# 의존성 체크 건너뛰기
python build.py --skip-deps

# 또는 PyInstaller 직접 실행 (권장)
python -m PyInstaller automation.spec --noconfirm --clean
```

---

### ❌ 문제 4: 실행 파일이 생성되지 않음

**원인**: 경로 문제 또는 권한 문제

**확인사항**:
1. 프로젝트 루트 경로에서 실행했는지 확인
2. 관리자 권한으로 실행하지 말 것 (불필요)
3. 바이러스 백신 확인 (빌드 중단 가능성)

**해결**:
```bash
# 경로 확인
pwd
# /c/X/PythonProject/PythonProject5-pdf

# 권한 확인
ls -la automation.spec
```

---

### ❌ 문제 5: 빌드는 되는데 실행 안 됨

**증상**: 더블클릭해도 아무 반응 없음

**확인**:
```bash
# 콘솔에서 직접 실행하여 에러 확인
cd dist/interojo_automation/
./interojo_automation.exe
```

**일반적인 원인**:
1. 필수 DLL 누락 → `_internal/` 폴더 확인
2. Python 모듈 누락 → 로그 확인
3. 환경 변수 문제 → .env 파일 확인

---

## 주의사항

### ⚠️ 중요한 사항

#### 1. numpy는 반드시 포함
```python
# ❌ 잘못된 예
excludes = ['numpy']

# ✅ 올바른 예
excludes = ['matplotlib', 'pandas', 'scipy']
# numpy는 제외 목록에 없음
```

#### 2. automation.spec 파일 유지
```bash
# ❌ 삭제하면 안 됨
rm automation.spec

# ✅ 버전 관리에 포함
git add automation.spec
git commit -m "Add PyInstaller spec file"
```

#### 3. build.py보다 PyInstaller 직접 실행 권장
```bash
# ✅ 권장
python -m PyInstaller automation.spec --noconfirm --clean

# ⚠️ 비권장 (문제 발생 가능)
python build.py
```

#### 4. 관리자 권한으로 실행하지 말 것
```
DEPRECATION: Running PyInstaller as admin is not necessary
```
→ 일반 사용자 권한으로 빌드하세요.

#### 5. 가상환경 사용 권장 (선택사항)
```bash
# 가상환경 생성
python -m venv .venv

# 활성화 (Windows)
.venv\Scripts\activate

# 패키지 설치
pip install -r requirements_service.txt

# 빌드
python -m PyInstaller automation.spec --noconfirm --clean
```

---

## 빠른 참조

### 한 번에 빌드하기

```bash
# 프로젝트 루트로 이동
cd /c/X/PythonProject/PythonProject5-pdf

# 이전 빌드 정리
rm -rf build dist

# 빌드 실행
python -m PyInstaller automation.spec --noconfirm --clean

# 결과 확인
ls -lh dist/interojo_automation/

# 크기 확인
du -sh dist/interojo_automation/

# 테스트
cd dist/interojo_automation/
./interojo_automation.exe
```

---

## 배포 준비

### 1. README.txt 생성 (선택사항)
```bash
# 사용자 가이드 작성
vi dist/interojo_automation/README.txt
```

### 2. 압축 파일 생성
```bash
# Windows 탐색기에서:
dist/interojo_automation/ 폴더 → 마우스 우클릭 → "압축"

# 또는 명령줄:
cd dist
7z a interojo_automation_v3.1.0.zip interojo_automation/
```

### 3. 배포
- ZIP 파일을 대상 PC에 복사
- 압축 해제
- `interojo_automation.exe` 실행

---

## 체크리스트

빌드 전 확인:
- [ ] Python 3.8+ 설치됨
- [ ] 필수 패키지 설치됨 (`requirements_service.txt`)
- [ ] automation.spec 파일 존재
- [ ] src/ 폴더 구조 확인
- [ ] 이전 빌드 정리 (`build/`, `dist/` 삭제)

빌드 후 확인:
- [ ] `interojo_automation.exe` 생성됨 (9.5 MB)
- [ ] 전체 크기 약 99 MB
- [ ] 실행 파일 더블클릭 시 GUI 열림
- [ ] 설정 창 정상 작동
- [ ] README.txt 포함 (선택)

배포 전 확인:
- [ ] 다른 PC에서 실행 테스트
- [ ] .env 파일 자동 생성 확인
- [ ] 로그인 기능 테스트
- [ ] 문서 검색 기능 테스트

---

## 추가 정보

### 빌드 시간
- **일반적**: 1-2분
- **첫 빌드**: 2-3분 (캐시 생성)
- **재빌드** (변경 없음): 30초-1분

### 빌드 크기 비교
| 항목 | 크기 | 설명 |
|------|------|------|
| EXE 파일 | 9.5 MB | 실행 파일 |
| _internal | ~90 MB | 라이브러리 (numpy 포함) |
| **전체** | **99 MB** | 배포 파일 |

### 주요 포함 라이브러리
- ✅ numpy (29 MB) - openpyxl 의존성
- ✅ Selenium (Chrome WebDriver)
- ✅ openpyxl (Excel)
- ✅ gspread + google-auth (Google Sheets)
- ✅ tkinter (GUI)
- ✅ schedule, psutil, colorama

---

## 문의

빌드 관련 문제가 있으면:
1. 이 문서의 "문제 해결" 섹션 확인
2. `logs/` 폴더의 로그 확인
3. IT 담당자에게 문의

---

**작성일**: 2025-12-03
**버전**: 3.1.0
**작성자**: INTEROJO IT Team
