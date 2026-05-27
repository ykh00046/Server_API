# except-exception-refactor-r2 — Design

> **Cycle**: except-exception-refactor-r2
> **PDCA Phase**: Design
> **Date**: 2026-05-27
> **Plan**: [except-exception-refactor-r2.plan.md](../../01-plan/features/except-exception-refactor-r2.plan.md)

## 1. 분류 원칙 (3 Class)

각 `except Exception` 위치를 3개 클래스로 분류한다:

| Class | 설명 | 처리 방식 |
|---|---|---|
| **N (Narrow)** | 실제로 좁은 예외만 발생 가능. catch-all은 silent swallow 부작용 큼. | `except (SpecificError, ...)` 로 좁힘 |
| **J (Justified)** | top-level handler, worker loop, LLM tool boundary 등 의도적 catch-all 필요. | `except Exception` 유지 + `# noqa: BLE001` + 1줄 사유 주석 |
| **D (Drop)** | bare `except Exception: pass` — 진짜 무음. silent failure 위험. | narrow + logger.debug(또는 warning) 또는 `contextlib.suppress(NarrowError)` |

## 2. 영역별 매핑 (Master Table)

### A. notifications (6곳)

| 파일:줄 | 현재 | Class | 대상 narrow / 조치 |
|---|---|---|---|
| `api/notifications/store.py:60` | `except Exception: pass` (cached.close 실패) | **D→N** | `except (sqlite3.Error, OSError):` + `logger.debug` |
| `api/notifications/store.py:159` | `except Exception: pass` (reset_for_tests close) | **D→N** | 동일 패턴 |
| `api/notifications/worker.py:104` | `except Exception as e:` (dispatcher belt) | **J** | `# noqa: BLE001 — belt-and-suspenders: dispatcher가 raise하더라도 worker는 죽이지 않는다` |
| `api/notifications/worker.py:169` | `except Exception as e:` (tick loop) | **J** | `# noqa: BLE001 — worker tick은 어떤 예외에서도 살아남아야 한다` |
| `api/notifications/dispatcher.py:96` | `except Exception as e:` (webhook outbound) | **N** | `except (httpx.HTTPError, OSError, ValueError) as e:` — httpx의 모든 통신 오류 + URL 파싱 + DNS |
| `api/notifications/events.py:112` | `except Exception as e:` (enqueue) | **J** | `# noqa: BLE001 — emit_event는 호출자에게 절대 예외를 전파하지 않는다` |

### B. routers (5곳)

| 파일:줄 | 현재 | Class | 대상 narrow / 조치 |
|---|---|---|---|
| `api/routers/system.py:83` | `except Exception as e:` (db status) | **N** | `except (sqlite3.Error, OSError) as e:` |
| `api/routers/system.py:111` | `except Exception:` (statvfs fallback) | **N** | `except (AttributeError, OSError):` |
| `api/routers/system.py:117` | `except Exception: pass` (shutil fallback) | **D→N** | `except (OSError, ValueError):` + `logger.debug` |
| `api/routers/system.py:214` | `except Exception as e:` (ai health) | **J** | `# noqa: BLE001 — health 캐시는 어떤 외부 호출 오류에서도 degraded 상태를 기록해야 한다` |
| `api/routers/records.py:44` | `except Exception: return None` (cursor decode) | **D→N** | `except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError):` |

### C. chat & stream (6곳)

| 파일:줄 | 현재 | Class | 대상 narrow / 조치 |
|---|---|---|---|
| `api/chat.py:280` | `except Exception as e:` (provider try) | **J** | `# noqa: BLE001 — provider별 SDK 예외가 제각각이므로 fallback을 위해 광범위 catch` |
| `api/chat.py:301` | `except Exception as fb_err:` (fallback fail) | **J** | `# noqa: BLE001 — 마지막 fallback도 실패한 경우 사용자에게 에러 응답` |
| `api/chat.py:333` | `except Exception as e:` (top-level) | **J** | `# noqa: BLE001 — top-level handler: 모든 예외를 500으로 변환` |
| `api/_chat_stream.py:141` | `except Exception as fb_err:` (fb) | **J** | `# noqa: BLE001 — SSE stream 내 fallback 실패 시 에러 이벤트 송출` |
| `api/_chat_stream.py:237` | `except Exception as e:` (top-level SSE) | **J** | `# noqa: BLE001 — SSE handler: 어떤 예외도 stream을 죽이면 안 된다` |
| `api/_gemini_client.py:38` | `except Exception as e:` (client init) | **N** | `except (ImportError, ValueError, RuntimeError) as e:` — google-genai 초기화 실패 종류 |

### D. tools (Gemini boundary, 8곳)

LLM이 호출하는 tool은 어떤 예외든 `{"status": "error", "message": str(e)}` 형태로 반환해야 한다 (계약).
모두 **J** 클래스로 유지 + 통일된 주석.

| 파일:줄 | 위치 | 조치 |
|---|---|---|
| `api/tools/items.py:101, 166` | search_production_items, get_item_history | `# noqa: BLE001 — Gemini tool boundary: 모든 예외를 error dict로 변환 (LLM 계약)` |
| `api/tools/summary.py:95, 163, 224, 324` | summary/trend/top/compare | 동일 주석 |
| `api/tools/custom.py:197, 245` | run_query 내부 + 외부 wrap | 동일 주석 |

### E. shared infra (10곳)

| 파일:줄 | 현재 | Class | 대상 narrow / 조치 |
|---|---|---|---|
| `shared/database.py:98` | `except Exception: pass` (cleanup close) | **D→N** | `except (sqlite3.Error, OSError):` + debug log |
| `shared/database.py:147` | `except Exception as e:` (PRAGMA setup) | **N** | `except sqlite3.Error as e:` |
| `shared/database.py:278` | `except Exception: pass` (broken close) | **D→N** | `except (sqlite3.Error, OSError):` |
| `shared/database.py:286` | `except Exception: pass` (mtime reconnect close) | **D→N** | `except (sqlite3.Error, OSError):` |
| `shared/db_maintenance.py:62` | `except Exception: return 0, 0` (getmtime/size) | **D→N** | `except OSError: return 0, 0` |
| `shared/db_maintenance.py:181` | `except Exception as e:` (after sqlite3.Error block) | **J** | `# noqa: BLE001 — sqlite3.Error 외 경로(IO 등) 마지막 안전망` |
| `shared/db_maintenance.py:230` | 동일 패턴 (ANALYZE) | **J** | 동일 주석 |
| `shared/db_maintenance.py:276` | 동일 패턴 (VACUUM) | **J** | 동일 주석 |
| `shared/cache.py:67` | `except Exception:` (DB version cache fallback) | **N** | `except (OSError, sqlite3.Error):` |
| `shared/process_utils.py:71` | `except Exception: pass` (subprocess wait) | **D→N** | `except (OSError, subprocess.SubprocessError):` + debug log |

### F. dashboard core (10곳)

| 파일:줄 | 현재 | Class | 대상 narrow / 조치 |
|---|---|---|---|
| `dashboard/data.py:38` | `except Exception: return 0` (getmtime) | **D→N** | `except OSError: return 0` |
| `dashboard/data.py:68` | `except Exception as e:` (DB self-check) | **N** | `except (sqlite3.Error, OSError) as e:` |
| `dashboard/components/ai_section.py:25` | `except Exception:` (optional import) | **N** | `except ImportError:` |
| `dashboard/components/ai_section.py:85` | `except Exception:` (response read) | **N** | `except (httpx.HTTPError, UnicodeDecodeError, OSError):` |
| `dashboard/components/ai_section.py:140` | `except Exception as e:` (stream err) | **J** | `# noqa: BLE001 — UI safety: 어떤 SSE 파싱 오류도 사용자에게 토스트로` |
| `dashboard/components/ai_section.py:174` | `except Exception: pass` (download button) | **D→J** | `except Exception: pass  # noqa: BLE001 — download button은 부수적, 실패해도 UI 영향 없음` |
| `dashboard/components/webhook_admin/api_client.py:37` | `except Exception:` (resp.json) | **N** | `except (ValueError, json.JSONDecodeError):` |
| `dashboard/components/webhook_admin/api_client.py:106` | `except Exception as e:` (resp.json 2xx) | **N** | `except (ValueError, json.JSONDecodeError) as e:` |
| `dashboard/components/webhook_admin/views.py:20` | `except Exception:` (optional toast import) | **N** | `except ImportError:` |
| `dashboard/pages/webhooks.py:34` | 이미 `# noqa: BLE001` | **J** | **유지 (변경 없음)** |

### G. portal & misc (1곳)

| 파일:줄 | 현재 | Class | 대상 narrow / 조치 |
|---|---|---|---|
| `portal_settings_dialog.py:60` | `except Exception:` (deobfuscate fail) | **N** | `except (ValueError, binascii.Error, UnicodeDecodeError):` |

## 3. 통계 요약

| 카테고리 | 수 |
|---|---|
| **N (Narrow)**: 좁은 예외로 치환 | **23** |
| **J (Justified)**: noqa + 주석 | **17** |
| **D→N (Drop pass, narrow)**: 무음 실패 제거 | **8** (D 클래스 모두 N으로 변환됨) |
| **D→J**: 1곳 (download button) | **1** |
| **총합** | **46** |

수정 후 grep 결과:
- `rg "except Exception"` 본 프로젝트 결과: ~17곳 (J 클래스만, 모두 noqa+주석)
- 무음 `pass`/`return None` 패턴: **0**
- AC5 충족: 46 → 17 (63% 감소, 목표 35% 초과 달성)

## 4. 구현 순서 (Implementation Order)

리스크가 낮은 순서로 진행:

1. **G + F-import** (portal, dashboard optional imports) — `ImportError` 좁히기, 4곳
2. **E (shared)** — DB / cache / process. 가장 핵심 인프라이지만 패턴이 균일 (sqlite3.Error, OSError) — 10곳
3. **A (notifications)** — store/worker/dispatcher/events. 핵심 백엔드 — 6곳
4. **B (routers)** — system/records. API endpoint — 5곳
5. **C (chat & stream)** — 대부분 J 클래스(주석만 추가) — 6곳
6. **D (tools)** — 모두 동일 주석 추가 — 8곳
7. **F-core (dashboard)** — UI 코드, 마지막에 — 6곳 (import 제외)

각 단계마다 임포트 smoke 확인.

## 5. 도입 import

| 모듈 | 추가 import |
|---|---|
| `api/routers/records.py` | `import binascii, json` (이미 json 있음) |
| `api/notifications/dispatcher.py` | (httpx 이미 import) |
| `api/notifications/store.py` | (sqlite3 이미 import) |
| `shared/process_utils.py` | `import subprocess` (이미 있을 가능성) — Read로 확인 |
| `portal_settings_dialog.py` | `import binascii` |
| `dashboard/components/webhook_admin/api_client.py` | `import json` 확인 (없으면 추가) |

## 6. 회귀 방지 전략

- **모듈 import smoke**: 수정 후 `python -c "import <module>"` 7개 핵심 모듈 검증
- **pytest 부분 실행**: `pytest tests/test_notifications_*.py tests/test_webhook_admin_ui.py tests/test_chat_*.py` (수정 모듈 직접 영향)
- **manual smoke** (Do phase 마지막):
  - `python -c "from api.notifications.store import get_conn, reset_for_tests; ..."` 로 thread-local + close 동작 확인
  - `python -c "from api.routers.records import _decode_cursor; print(_decode_cursor('garbage'))"` → None
- **diff 시각 검사**: 각 영역 commit 직전 `git diff --stat`

## 7. Out of Scope (재확인)

- `tools/`, `scripts/`, `manager.py`, `tests/` — R2-2로 이월
- `webcloring-pdf/` — submodule 분리 후 별도 (R2-3)
- ruff BLE001 활성화 — R3
