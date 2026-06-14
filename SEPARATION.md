# webcloring-pdf — submodule 분리 절차서

> **상태**: 준비 완료, **outward 단계는 미실행** (사용자 실행 대기)
> **결정**: 2026-05-19 (git submodule 방식), 준비: 2026-06-15 (webcloring-pdf-separation 사이클)
> **대상**: `webcloring-pdf/` (INTEROJO 포털 자동화, 독립 PySide6 앱)

이 문서는 `webcloring-pdf/`를 별도 git 저장소로 떼어내 부모(`Server_API`)에 **submodule**로 다시 붙이는, 되돌리기 어려운 외부 작업의 실행 순서다. 코드 준비(requirements 정리·lock 재생성)는 이미 완료됐다. 아래 단계만 실행하면 된다.

## 왜 submodule이고 폴더는 제자리인가

- `manager.py`가 `BASE_DIR/"webcloring-pdf"` 경로를 하드코딩해 webcloring-pdf를 **하위 프로세스**로 실행(`main.py --schedule/--auto`). 코드 import 결합은 없음.
- 폴더를 물리적으로 옮기면 manager Portal 패널이 깨진다. → submodule로 폴더를 `Server_API/webcloring-pdf/` **제자리 유지** → manager 무수정.
- 루트 `portal_settings_dialog.py`는 manager가 `webcloring-pdf/.env`를 편집하는 브리지 → Server_API에 잔류.

## 사전 조건

- 작업 트리 클린(미커밋 변경 없음). 이 사이클의 requirements/lock/문서 커밋이 먼저 들어가 있어야 함.
- `gh` CLI 로그인 상태(`gh auth status`)이고 대상 owner에 repo 생성 권한 보유.
- 대상 저장소 위치/공개여부 결정(예: `<owner>/webcloring-pdf`, private 권장 — 내부 포털 자동화).

## 실행 순서 (PowerShell 기준)

### 1. webcloring-pdf를 독립 repo로 초기화
```powershell
cd C:\X\Server_API\webcloring-pdf
git init -b main
git add -A          # .gitignore가 data/logs/build/dist/.env/google키 제외 — 확인:
git status          # 트래킹 목록에 .env / *-*.json / dist / build 없어야 함
git commit -m "chore: webcloring-pdf 독립 저장소 초기화 (Server_API에서 분리)"
```

> ⚠️ `git add -A` 전 `git status`로 `.env`·Google 키(`*-*.json`)·`dist/`·`build/`·`data/PDF` 등이 **제외**됐는지 반드시 확인. webcloring-pdf/.gitignore가 처리하지만 push 전 육안 검증.

### 2. 원격 저장소 생성 + push
```powershell
gh repo create <owner>/webcloring-pdf --private --source . --remote origin --push
# 또는 수동:
#   gh repo create <owner>/webcloring-pdf --private
#   git remote add origin https://github.com/<owner>/webcloring-pdf.git
#   git push -u origin main
```

### 3. 부모(Server_API)에서 폴더를 트래킹 해제
```powershell
cd C:\X\Server_API
git rm -r --cached webcloring-pdf      # 워킹트리 파일은 유지, 인덱스에서만 제거
# 이 시점에 webcloring-pdf/는 부모 입장에서 untracked가 됨
```

### 4. submodule로 다시 추가 (폴더 제자리)
```powershell
git submodule add https://github.com/<owner>/webcloring-pdf.git webcloring-pdf
# .gitmodules 생성됨. 폴더 경로 동일 → manager.py 무수정
git commit -m "chore: webcloring-pdf를 submodule로 전환 (폴더 경로 유지)"
git push origin main
```

### 5. 검증
```powershell
# 부모 repo
git submodule status                    # webcloring-pdf 커밋 해시 출력
Test-Path .gitmodules                   # True
# manager Portal 패널 동작 (폴더 경로 불변이므로 정상이어야 함)
python manager.py                       # Portal 패널에서 webcloring-pdf 실행 확인
# 클린 체크아웃 재현
#   git clone --recurse-submodules <Server_API-url> 또는
#   기존 클론에서: git submodule update --init --recursive
```

## 롤백 (submodule 추가 전까지만 쉬움)

- 3단계까지만 했고 되돌리려면: `git reset --hard HEAD` (부모), webcloring-pdf/ 그대로.
- 4단계(submodule add) 후 되돌리려면:
  ```powershell
  git submodule deinit -f webcloring-pdf
  git rm -f webcloring-pdf
  rm -r -force .git\modules\webcloring-pdf
  git checkout -- .gitmodules   # 또는 .gitmodules 편집/삭제
  ```
  그 후 webcloring-pdf를 일반 폴더로 되돌리려면 원격에서 다시 받거나 백업 복원.

## 분리 후 일상 작업

- webcloring-pdf 수정: `cd webcloring-pdf` 후 자체 repo로 커밋·push → 부모에서 `git add webcloring-pdf && git commit`(포인터 갱신).
- 클론 시: `git clone --recurse-submodules ...` 또는 클론 후 `git submodule update --init`.
- 의존성: webcloring-pdf는 자체 `requirements.txt` 사용. 부모 `requirements.txt`에는 portal 의존성 없음(psutil만 잔류 — manager 프로세스 관리용).
