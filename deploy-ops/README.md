# 운영 PC 서비스 실행 + git 자동 배포

운영 PC는 Windows 11 Home이라 업데이트 재부팅을 막을 수 없고 자동 로그인도 꺼져 있다. 예전에는 `manager.py`를 사람이 띄워야 API가 살아났기 때문에, 재부팅 뒤에는 로그인해서 매니저를 켤 때까지 8000이 내려가 있었다. 이 폴더는 서비스를 작업 스케줄러(SYSTEM, 부팅 시)로 옮기고, 개발 PC에서 `git push`만 하면 10분 안에 반영되게 한다. 유량계 대시보드(`daily-flow-app/deploy-ops`)와 같은 패턴이다.

## 작업 4개

| 작업 이름 | 계정 · 시점 | 하는 일 |
|---|---|---|
| `ProductionHubApi` | SYSTEM · 부팅 | `uvicorn api.main:app` 8000 |
| `ProductionHubPortal` | SYSTEM · 부팅 | 포털 봇 스케줄러 (`webcloring-pdf/main.py --schedule`) |
| `ProductionHubWatcher` | SYSTEM · 부팅 | DB 워처 (`tools/watcher.py --daemon`, 1시간 간격) |
| `ProductionHubUpdate` | 설치한 사용자 · 10분마다 | 감시 + 자동 배포 (`ops-update.ps1`) |

서비스 작업 3개는 실행 시간 제한 없음(PT0S), 배터리 중지 없음, 실패 시 1분 간격 3회 재시작으로 등록된다.

## 최초 1회 설치

1. 매니저를 트레이에서 완전히 종료한다(8000을 매니저가 잡고 있으면 서비스가 뜨지 못한다).
2. `deploy-ops\ops-install.bat`을 **관리자 권한으로** 실행한다.
   - `.venv`가 없으면 만든다(Python 3.12 우선). 의존성(`requirements.lock.txt` + 봇 `requirements.txt`)을 설치한다.
   - 작업 4개와 방화벽 규칙(8000)을 등록하고 `deploy-ops\.service-mode` 표식을 만든다.
3. `http://localhost:8000/healthz` 확인.
4. **포털 봇 첫 실행 확인**(아래).

다시 실행해도 안전하다(같은 이름으로 덮어 등록).

### 포털 봇 첫 실행 확인 (필수)

봇은 Chrome을 띄워 포털에 로그인한다. 지금까지는 로그인한 사용자 화면에서 돌았고, 이제는 화면이 없는 SYSTEM 계정에서 돈다. 개발 PC에서는 이 조건을 검증하지 못했다. 설치 직후 관리자 PowerShell에서 한 번 돌려 본다.

```powershell
powershell -ExecutionPolicy Bypass -File deploy-ops\test-portal-as-system.ps1
```

SYSTEM 계정으로 봇을 1회 실행(`main.py --auto`, 매니저의 Run Now와 같은 동작)하고 로그 끝 40줄을 보여 준다. 로그인·다운로드·백업 전송이 끝까지 가는지 본다. 실패하면:

- 먼저 매니저 **Settings**에서 헤드리스 모드를 켜고(`HEADLESS_MODE=True`) 다시 시험한다.
- 그래도 안 되면 포털 작업만 사용자 계정으로 돌린다. 이 경우 로그인해 있을 때만 돈다.
  ```powershell
  schtasks /Change /TN ProductionHubPortal /RU <사용자> /IT
  ```
- Chrome 드라이버는 SYSTEM 프로필에 처음 한 번 내려받는다. 인터넷이 막혀 있으면 여기서 멈춘다.

## 이후 배포

개발 PC에서 push하면 끝이다. `ProductionHubUpdate`가 10분마다:

1. 서비스 작업의 실행 시간 제한을 확인한다(바뀌었으면 1회 재시작).
2. `/healthz`가 두 번 연속(15초 간격) 응답이 없으면 API를 재시작한다. 포털·워처 작업이 멈춰 있으면 다시 띄운다.
3. `git fetch` → 새 커밋이 있으면 `git pull --ff-only` → 서브모듈 → 의존성(요구 파일이나 봇 리비전이 바뀐 경우만) → 바뀐 역할만 재시작한다.
   - `api/`·`shared/` 변경 → API, `tools/`·`shared/` 변경 → 워처, 봇 리비전·의존성 변경 → 포털.
   - 문서·테스트만 바뀌면 아무것도 재시작하지 않는다.

결과는 `deploy-ops\update.log`에 남는다. 확인할 줄: `API restart verified health=200`.

실패하면 돌던 프로세스를 그대로 둔다: `GIT PULL FAILED`(운영 PC에 추적 파일 로컬 변경), `SUBMODULE UPDATE FAILED`, `PIP INSTALL FAILED`.

주의:
- 봇이 문서를 내려받는 중에 봇 리비전이 바뀌는 push를 하면 그 실행이 중간에 끊긴다. 봇 변경은 예약 시각을 피해 push한다.
- `ProductionHubUpdate`는 설치한 사용자의 git 자격으로 돈다. 그 사용자가 로그인해 있지 않으면 배포는 다음 로그인까지 밀린다. 서비스 자체는 SYSTEM이라 영향이 없다.
- DB 스키마가 바뀌는 변경은 자동 배포에 태우지 말고 사람이 지켜보며 반영한다.

## 매니저(manager.py)와의 관계

`deploy-ops\.service-mode`가 있으면 매니저는 **관찰만** 한다.

- 상단 뱃지: API는 8000 포트, 포털·워처는 `deploy-ops\logs\<역할>.pid`로 생존을 본다.
- Start/Stop 버튼은 동작하지 않고 `schtasks` 명령을 안내한다. 매니저를 켜고 끄는 것은 서비스에 영향이 없다.
- 포털 **Settings**, 작업(키워드·시각) 편집, **Run Now**는 그대로 쓴다. 스케줄(작업 시각)을 바꾼 뒤에는 포털 작업을 한 번 재시작해야 반영된다: `schtasks /End /TN ProductionHubPortal` 후 `schtasks /Run /TN ProductionHubPortal`(관리자).
- `update.bat`은 서비스 모드에서 실행하면 안내만 하고 끝난다(서비스를 죽이고 꺼 둔 채 끝나는 것을 막는다).

매니저 방식으로 되돌리려면 작업 4개를 지우고 `.service-mode`를 지운다.

## 로그 (운영 PC, git 밖)

- `deploy-ops\logs\api.log` / `portal.log` / `watcher.log` — 각 역할의 표준 출력. 시작 때 10MB를 넘으면 `.1~.3`으로 넘긴다.
- `deploy-ops\update.log` — 감시·배포 기록.
- `logs\app.log` — API 자체 회전 로그(기존과 같음).

## 수동 조작 (관리자 권한 창)

```bat
schtasks /Run /TN ProductionHubApi
schtasks /End /TN ProductionHubApi
deploy-ops\ops-update.bat
```
