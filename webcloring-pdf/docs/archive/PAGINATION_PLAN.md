# INTEROJO 포털 자동화 페이지네이션 개선 계획 (v2.0)

## 📌 변경 이력
- **v1.0** (2025-11-XX): 초기 계획 작성
- **v2.0** (2025-12-01): 상세 검토 및 개선 사항 반영
  - XPath 문법 오류 수정
  - 무한 루프 방지 (MAX_PAGES 추가)
  - 프레임 전환 예외 처리 개선
  - Stale Element 처리 추가
  - 페이지 이동 로직 메서드 분리
  - 연속 오류 처리 추가
  - 로그 메시지 강화

---

## 1. 개요

### 목표
문서 검색 결과가 50건을 초과할 경우, 자동으로 다음 페이지로 이동하여 모든 문서를 처리하도록 개선.

### 검증 결과
별도 테스트(`test_pagination.py`)를 통해 JavaScript 클릭(`execute_script`) 방식을 사용하면 페이지 이동이 정상적으로 수행됨을 확인.

### 수정 대상
`src/core/portal_automation.py`

### 주요 개선 사항
1. **안정성**: 무한 루프 방지, 연속 오류 처리, Stale Element 처리
2. **확장성**: 10페이지 단위 이동, 최대 100페이지 처리
3. **유지보수성**: 페이지 이동 로직을 별도 메서드로 분리
4. **가시성**: 상세한 로그 메시지 및 진행률 표시

---

## 2. 상세 수정 계획

### A. `change_page_size` 메서드 강화

**목적**: 페이지당 글 수를 50개로 변경하고, iframe 컨텍스트 유실 방지

**개선 사항**:
- iframe 존재 여부 확인 후 전환
- 명시적인 예외 타입 지정
- 페이지 크기 변경 후 테이블 리로드 확인

```python
@handle_selenium_errors(default_return=False, log_error=True)
def change_page_size(self):
    """페이지당 표시 글 수를 50개로 변경"""
    try:
        logger.info("페이지당 글 수 변경 시작...")

        # 1. 프레임 재진입 (안전장치)
        self.driver.switch_to.default_content()

        # iframe 존재 여부 확인 후 전환
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                self.driver.switch_to.frame(iframes[0])
                logger.debug("iframe으로 전환 완료")
            else:
                logger.debug("iframe 없음, 메인 프레임에서 진행")
        except Exception as e:
            logger.warning(f"iframe 전환 중 오류 (메인 프레임 유지): {e}")

        # 2. 50개 보기 선택
        page_size_select = self.wait.until(
            EC.element_to_be_clickable((By.NAME, "pagePerRecord"))
        )

        # 이미 50개로 설정되어 있으면 스킵
        if page_size_select.get_attribute('value') == '50':
            logger.info("페이지 크기가 이미 50입니다.")
            return True

        Select(page_size_select).select_by_value('50')
        logger.debug("페이지 크기 50 선택 완료")

        # 3. 변경 완료 대기
        self.wait.until(
            lambda d: d.find_element(By.NAME, "pagePerRecord").get_attribute('value') == '50'
        )
        time.sleep(1)  # 안정성을 위한 짧은 대기

        # 4. 테이블 리로드 대기
        self.wait.until(EC.presence_of_element_located((By.ID, "listTable")))

        logger.info("✅ 페이지 크기 변경 완료 (50개로 설정)")
        return True

    except TimeoutException as e:
        logger.error(f"페이지 크기 변경 시간 초과: {e}")
        return False
    except Exception as e:
        logger.error(f"페이지 크기 변경 실패: {e}")
        return False
```

---

### B. 페이지 이동 로직을 별도 메서드로 분리

**목적**: 코드 재사용성 향상, 테스트 용이성 증대

#### B-1. `_move_to_next_page` 메서드 (신규 추가)

```python
def _move_to_next_page(self, target_page: int) -> bool:
    """
    다음 페이지로 이동

    Args:
        target_page: 이동할 페이지 번호

    Returns:
        bool: 이동 성공 여부
    """
    try:
        # 1. 숫자 버튼으로 이동 시도 (예: '2', '3', '4' 버튼)
        xpath_next_btn = f"//div[contains(@class, 'paging')]//a[contains(text(), '{target_page}')]"

        try:
            next_btn = self.driver.find_element(By.XPATH, xpath_next_btn)
            logger.info(f"➡️  페이지 {target_page} 버튼 발견")

            # 스크롤 및 JavaScript 클릭 (검증된 방식)
            self.driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", next_btn)

            # 페이지 로딩 확인
            self._wait_for_page_load(target_page)

            logger.info(f"✅ 페이지 {target_page} 로딩 완료")
            return True

        except NoSuchElementException:
            # 2. 숫자 버튼이 없으면 10페이지 단위 이동 시도
            logger.debug(f"페이지 {target_page} 버튼 없음, 10페이지 단위 이동 시도")
            return self._move_to_next_page_group()

    except TimeoutException as e:
        logger.error(f"페이지 {target_page} 로딩 시간 초과: {e}")
        return False
    except Exception as e:
        logger.error(f"페이지 이동 실패: {e}")
        return False


def _move_to_next_page_group(self) -> bool:
    """
    10페이지 단위로 이동 ('다음 10페이지' 버튼 클릭)

    Returns:
        bool: 이동 성공 여부
    """
    try:
        # '다음 10페이지' 버튼 찾기
        next_group_btn = self.driver.find_element(
            By.XPATH,
            "//div[contains(@class, 'paging')]//a[contains(@class, 'next')]"
        )
        logger.info("➡️  '다음 10페이지' 버튼 발견")

        # 스크롤 및 JavaScript 클릭
        self.driver.execute_script("arguments[0].scrollIntoView(true);", next_group_btn)
        time.sleep(0.5)
        self.driver.execute_script("arguments[0].click();", next_group_btn)

        # 페이지 로딩 대기 (단순 대기 후 테이블 확인)
        time.sleep(2)
        self.wait.until(EC.presence_of_element_located((By.ID, "listTable")))

        logger.info("✅ 10페이지 단위 이동 완료")
        return True

    except NoSuchElementException:
        logger.info("🏁 더 이상 다음 페이지 없음 (마지막 페이지)")
        return False
    except Exception as e:
        logger.error(f"10페이지 단위 이동 실패: {e}")
        return False


def _wait_for_page_load(self, expected_page: int):
    """
    페이지 로딩 완료 대기 (Stale Element 처리 포함)

    Args:
        expected_page: 로딩을 기다릴 페이지 번호
    """
    # 1. 활성 페이지 번호 확인 (fColor 클래스)
    xpath_active_page = (
        f"//div[contains(@class, 'paging')]//a"
        f"[contains(@class, 'fColor') and contains(text(), '{expected_page}')]"
    )
    self.wait.until(EC.presence_of_element_located((By.XPATH, xpath_active_page)))

    # 2. 기존 테이블이 사라질 때까지 대기 (Stale Element 처리)
    try:
        old_table = self.driver.find_element(By.ID, "listTable")
        self.wait.until(EC.staleness_of(old_table))
        time.sleep(0.5)  # 짧은 대기
    except:
        # 기존 테이블을 찾지 못한 경우 (이미 사라짐)
        pass

    # 3. 새 테이블 로딩 확인
    self.wait.until(EC.presence_of_element_located((By.ID, "listTable")))

    # 4. 테이블 내용 로딩 완료 확인 (tbody 내 tr 존재)
    self.wait.until(
        EC.presence_of_element_located((By.XPATH, "//table[@id='listTable']//tbody/tr"))
    )

    logger.debug(f"페이지 {expected_page} 로딩 확인 완료")


def _get_current_page_number(self) -> int:
    """
    현재 활성화된 페이지 번호 확인

    Returns:
        int: 현재 페이지 번호, 확인 실패 시 -1
    """
    try:
        active_page_elem = self.driver.find_element(
            By.XPATH,
            "//div[contains(@class, 'paging')]//a[contains(@class, 'fColor')]"
        )
        current_page = int(active_page_elem.text.strip())
        return current_page
    except Exception as e:
        logger.warning(f"현재 페이지 번호 확인 실패: {e}")
        return -1
```

---

### C. `process_document_list` 메서드 전면 개편 (페이지네이션 추가)

**목적**: 단일 페이지 처리를 다중 페이지 처리로 확장

**개선 사항**:
- 무한 루프 방지 (최대 100페이지)
- 연속 오류 처리 (3회 연속 실패 시 중단)
- 페이지별 처리 통계
- driver.back() 후 프레임 재진입 개선
- 상세한 로그 메시지

```python
def process_document_list(self):
    """
    문서 목록 처리 (다중 페이지 지원)

    처리 흐름:
    1. 현재 페이지의 문서 목록 수집
    2. 각 문서 처리 (상세 페이지 진입 → 데이터 추출 → 뒤로가기)
    3. 다음 페이지로 이동
    4. 1~3 반복 (최대 100페이지 또는 마지막 페이지까지)

    Returns:
        bool: 처리 성공 여부
    """
    try:
        logger.info("=" * 60)
        logger.info("문서 목록 처리 시작 (다중 페이지 지원)")
        logger.info("=" * 60)

        # 설정
        MAX_PAGES = 100  # 최대 처리 페이지 수
        MAX_CONSECUTIVE_ERRORS = 3  # 최대 연속 오류 허용 횟수

        # 상태 변수
        current_page = 1
        total_processed = 0
        consecutive_errors = 0

        # 페이지 처리 루프
        while current_page <= MAX_PAGES:
            logger.info("")
            logger.info(f"{'='*60}")
            logger.info(f"📄 현재 페이지: {current_page}/{MAX_PAGES}")
            logger.info(f"{'='*60}")

            try:
                # 1. 현재 페이지의 문서 목록 수집
                doc_list = self.collect_document_list()

                if not doc_list and current_page == 1:
                    logger.info("❌ 처리할 문서가 없습니다.")
                    return True

                if not doc_list:
                    logger.warning(f"⚠️  페이지 {current_page}에 문서 없음 (비정상 상태)")
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.error("❌ 연속 오류 한계 도달, 처리 중단")
                        break
                    continue

                # 2. 문서 처리
                page_processed = 0
                for i, doc_info in enumerate(doc_list, 1):
                    try:
                        logger.info(f"📄 [{current_page}페이지] 문서 {i}/{len(doc_list)} 처리 중: {doc_info['title'][:50]}...")

                        # 문서 링크 클릭 (JavaScript 클릭)
                        link_xpath = f"//a[contains(@href, \"getApprDetail('{doc_info['id']}')\")]"
                        doc_link = self.wait.until(
                            EC.element_to_be_clickable((By.XPATH, link_xpath))
                        )
                        self.driver.execute_script("arguments[0].click();", doc_link)

                        # 문서 상세 처리
                        self.process_document(doc_info)

                        # 뒤로가기 및 프레임 재진입
                        self._return_to_document_list()

                        page_processed += 1
                        total_processed += 1

                        logger.info(f"✅ [{current_page}페이지] 문서 {i} 처리 완료 (총 처리: {total_processed})")

                    except Exception as e:
                        logger.error(f"❌ 개별 문서 처리 실패: {doc_info['title'][:50]} - {e}")

                        # 복구 시도: 문서 목록 페이지로 복귀
                        try:
                            self._recover_to_document_list()
                        except Exception as recover_error:
                            logger.error(f"복구 실패: {recover_error}")
                            consecutive_errors += 1
                            break

                logger.info(f"📊 페이지 {current_page} 처리 완료: {page_processed}/{len(doc_list)}건")

                # 성공 시 연속 오류 카운터 리셋
                consecutive_errors = 0

                # 3. 다음 페이지 이동
                next_page = current_page + 1

                if not self._move_to_next_page(next_page):
                    # 이동 실패 = 마지막 페이지
                    logger.info("🏁 마지막 페이지 도달, 모든 처리 완료")
                    break

                # 10페이지 단위 이동 후 현재 페이지 번호 확인
                actual_page = self._get_current_page_number()
                if actual_page > 0:
                    current_page = actual_page
                else:
                    current_page = next_page

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"❌ 페이지 {current_page} 처리 중 오류 ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}")
                take_error_screenshot(self.driver, f"page_{current_page}_error")

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.error("❌ 연속 오류 한계 도달, 처리 중단")
                    break

                # 복구 시도
                time.sleep(2)
                try:
                    self._recover_to_document_list()
                except:
                    break

                # 다음 페이지로 건너뛰기
                current_page += 1

        # 처리 완료 후 최대 페이지 경고
        if current_page > MAX_PAGES:
            logger.warning(f"⚠️  최대 페이지({MAX_PAGES}) 도달, 더 많은 페이지가 있을 수 있습니다")

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"✅ 문서 목록 처리 완료")
        logger.info(f"   - 총 처리 문서: {total_processed}건")
        logger.info(f"   - 처리 페이지: {current_page}페이지")
        logger.info(f"   - 연속 오류: {consecutive_errors}회")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"❌ 문서 목록 처리 실패: {e}")
        take_error_screenshot(self.driver, "process_document_list_failure")
        return False


def _return_to_document_list(self):
    """
    문서 상세 페이지에서 문서 목록 페이지로 복귀

    driver.back() 후 프레임 재진입 및 테이블 로딩 확인
    """
    try:
        # 뒤로가기
        self.driver.back()
        time.sleep(0.5)  # 페이지 전환 안정화

        # 프레임 재진입
        self.driver.switch_to.default_content()
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                self.driver.switch_to.frame(iframes[0])
                logger.debug("iframe 재진입 완료")
        except Exception as e:
            logger.warning(f"iframe 재진입 실패 (메인 프레임 유지): {e}")

        # 문서 목록 페이지 로딩 확인
        self.wait.until(EC.presence_of_element_located((By.ID, "listTable")))
        logger.debug("문서 목록 페이지로 복귀 완료")

    except Exception as e:
        logger.error(f"문서 목록 복귀 실패: {e}")
        raise


def _recover_to_document_list(self):
    """
    오류 발생 시 문서 목록 페이지로 복구

    페이지 새로고침 후 프레임 재진입
    """
    try:
        logger.info("🔄 문서 목록 페이지로 복구 시도...")

        # 현재 URL 새로고침
        self.driver.refresh()
        time.sleep(1)

        # 프레임 재진입
        self.driver.switch_to.default_content()
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                self.driver.switch_to.frame(iframes[0])
        except Exception as e:
            logger.warning(f"iframe 재진입 실패: {e}")

        # 테이블 로딩 확인
        self.wait.until(EC.presence_of_element_located((By.ID, "listTable")))

        logger.info("✅ 복구 완료")

    except Exception as e:
        logger.error(f"복구 실패: {e}")
        raise
```

---

## 3. 기대 효과

### 3.1 완전 자동화
- 문서 양이 많아도(50개 이상, 최대 5000개) 사용자 개입 없이 끝까지 처리 가능
- 10페이지 단위 이동까지 지원하여 대량 데이터 처리 가능

### 3.2 안정성 향상
- **무한 루프 방지**: 최대 100페이지 제한
- **연속 오류 처리**: 3회 연속 실패 시 자동 중단
- **Stale Element 처리**: 페이지 전환 시 발생하는 DOM 변경 대응
- **프레임 관리**: iframe 컨텍스트 유실 방지

### 3.3 확장성
- 페이지 이동 로직을 별도 메서드로 분리하여 재사용 가능
- 다양한 페이지네이션 패턴에 대응 가능 (숫자 버튼, 10페이지 단위)

### 3.4 가시성
- 상세한 로그 메시지로 처리 현황 추적 용이
- 페이지별, 문서별 처리 통계 제공
- 오류 발생 시 스크린샷 자동 저장

---

## 4. 테스트 계획

### 4.1 단위 테스트
- [ ] `_move_to_next_page()` - 숫자 버튼 클릭 테스트
- [ ] `_move_to_next_page_group()` - 10페이지 단위 이동 테스트
- [ ] `_wait_for_page_load()` - 페이지 로딩 대기 테스트
- [ ] `_get_current_page_number()` - 현재 페이지 번호 확인 테스트
- [ ] `_return_to_document_list()` - 뒤로가기 테스트
- [ ] `_recover_to_document_list()` - 복구 로직 테스트

### 4.2 통합 테스트
- [ ] 1~5페이지 처리 (일반적인 케이스)
- [ ] 11~20페이지 처리 (10페이지 단위 이동)
- [ ] 최대 페이지 제한 테스트 (100페이지 도달)
- [ ] 연속 오류 처리 테스트 (3회 연속 실패)
- [ ] 중간 오류 복구 테스트 (네트워크 지연, 타임아웃)

### 4.3 엣지 케이스
- [ ] 문서가 정확히 50개인 경우 (2페이지 경계)
- [ ] 문서가 1개만 있는 경우
- [ ] 문서가 전혀 없는 경우
- [ ] 페이지 이동 중 네트워크 오류 발생
- [ ] iframe이 없는 페이지 구조

---

## 5. 롤백 계획

개선 사항 적용 후 문제 발생 시 롤백 방법:

### 5.1 Git 커밋
변경 전 현재 상태를 Git에 커밋:
```bash
git add src/core/portal_automation.py
git commit -m "페이지네이션 개선 전 백업"
```

### 5.2 백업 파일
```bash
cp src/core/portal_automation.py src/core/portal_automation.py.backup
```

### 5.3 롤백 방법
```bash
# Git 사용 시
git checkout HEAD src/core/portal_automation.py

# 백업 파일 사용 시
cp src/core/portal_automation.py.backup src/core/portal_automation.py
```

---

## 6. 구현 체크리스트

### Phase 1: 기본 기능
- [ ] `change_page_size()` 메서드 개선
- [ ] `_move_to_next_page()` 메서드 추가
- [ ] `_wait_for_page_load()` 메서드 추가
- [ ] `process_document_list()` 기본 루프 구현

### Phase 2: 안정성 강화
- [ ] `_move_to_next_page_group()` 메서드 추가 (10페이지 단위)
- [ ] `_get_current_page_number()` 메서드 추가
- [ ] 무한 루프 방지 (MAX_PAGES)
- [ ] 연속 오류 처리 (MAX_CONSECUTIVE_ERRORS)

### Phase 3: 복구 로직
- [ ] `_return_to_document_list()` 메서드 추가
- [ ] `_recover_to_document_list()` 메서드 추가
- [ ] 오류 발생 시 스크린샷 저장

### Phase 4: 로그 및 통계
- [ ] 상세 로그 메시지 추가
- [ ] 페이지별 처리 통계
- [ ] 최종 처리 결과 요약

### Phase 5: 테스트
- [ ] 단위 테스트 실행
- [ ] 통합 테스트 실행
- [ ] 엣지 케이스 테스트
- [ ] 실제 포털에서 검증

---

## 7. 참고 자료

### 7.1 Selenium 공식 문서
- **WebDriverWait**: https://www.selenium.dev/documentation/webdriver/waits/
- **Expected Conditions**: https://www.selenium.dev/selenium/docs/api/py/webdriver_support/selenium.webdriver.support.expected_conditions.html
- **Stale Element**: https://www.selenium.dev/documentation/webdriver/troubleshooting/errors/#stale-element-reference-exception

### 7.2 XPath 참고
- **XPath 문법**: https://www.w3schools.com/xml/xpath_syntax.asp
- **contains() 함수**: https://www.w3schools.com/xml/xpath_functions.asp

### 7.3 프로젝트 관련
- `src/core/portal_automation.py`: 현재 코드 (Line 399-424)
- `src/utils/error_handler.py`: 에러 핸들링 유틸리티
- `src/utils/logger.py`: 로깅 유틸리티

---

## 8. 변경 영향 분석

### 8.1 변경되는 메서드
- `change_page_size()` - 개선
- `process_document_list()` - 전면 개편

### 8.2 신규 추가 메서드
- `_move_to_next_page(target_page)`
- `_move_to_next_page_group()`
- `_wait_for_page_load(expected_page)`
- `_get_current_page_number()`
- `_return_to_document_list()`
- `_recover_to_document_list()`

### 8.3 영향받는 메서드
- `run_automation()` - 호출 체인 동일 (영향 없음)
- `collect_document_list()` - 변경 없음 (재사용)
- `process_document()` - 변경 없음 (재사용)

### 8.4 의존성
- 추가 import 필요 없음 (기존 import 충분)
- 외부 라이브러리 추가 불필요

---

## 9. 성능 예상

### 9.1 처리 시간
- **기존**: 1페이지 (최대 50건) = 약 5분
- **개선 후**: 10페이지 (최대 500건) = 약 50분
- **최대**: 100페이지 (최대 5000건) = 약 8시간

### 9.2 메모리 사용
- 페이지 단위 처리로 메모리 부담 최소화
- 문서 데이터는 Excel에 즉시 저장 (메모리 누적 없음)

### 9.3 네트워크 요청
- 페이지당 약 50~60회 요청 (문서 상세 페이지)
- 과도한 요청 방지를 위한 `time.sleep()` 포함

---

## 10. 주의사항

### 10.1 포털 정책
- 과도한 자동화는 포털 정책 위반 가능성
- 업무 시간대 이외 실행 권장
- 필요 시 `time.sleep()` 증가하여 부하 경감

### 10.2 데이터 중복
- `ExcelManager.is_document_processed()` 메서드로 중복 방지
- 동일 문서 재처리 시 자동 스킵

### 10.3 오류 처리
- 3회 연속 오류 발생 시 자동 중단
- 오류 발생 시 스크린샷 자동 저장 (`data/screenshots/`)
- 로그 파일 확인 필수 (`logs/automation_YYYYMMDD.log`)

---

## 부록: 주요 XPath 참고

### A. 페이지네이션 관련 XPath

```xpath
# 현재 활성화된 페이지 (fColor 클래스)
//div[contains(@class, 'paging')]//a[contains(@class, 'fColor')]

# 특정 페이지 번호 버튼
//div[contains(@class, 'paging')]//a[contains(text(), '3')]

# 다음 10페이지 버튼 (next 클래스)
//div[contains(@class, 'paging')]//a[contains(@class, 'next')]

# 이전 10페이지 버튼 (prev 클래스)
//div[contains(@class, 'paging')]//a[contains(@class, 'prev')]
```

### B. 문서 목록 관련 XPath

```xpath
# 문서 목록 테이블
//table[@id='listTable']

# 문서 제목 링크 (4번째 td 안의 a 태그)
//tbody/tr//td[4]/a

# 특정 문서 링크 (ID 기반)
//a[contains(@href, "getApprDetail('123456')")]
```

---

**작성일**: 2025-12-01
**작성자**: AI Assistant
**검토자**: (검토 후 기입)
**승인자**: (승인 후 기입)
**버전**: v2.0
