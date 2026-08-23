# Phase 8.5 (quota 관리자 운영 API) + docs 비공개 + SoT v1.8.0 등재 — 독립 검증

## Subject metadata

- 날짜: 2026-08-23 (검증 세션 3차 — 구현 세션 9~11과 다른 AI 세션; 같은 날 폴백·extractor
  검증 기록 2건의 작성자가 이어 받음)
- 요청자: 오너 — *"다음작업 검증해줘. 오늘 슬라이스들 검증해줘."* (구현 세션 종료 권고
  *"오늘 구현 분량이 많아 반증 가치가 큽니다"* 에 따름).
- 대상:
  - **8.5-a** `d20cb67`(조회 2종)·`5d89484`(에러 선언 가드) — SoT **v1.8.1**
  - **8.5-b** `0a75c5e`(변경·정지/해제 3종 + 감사)·`44ffb47`(활동 분류표 등재) — SoT **v1.8.2**
  - 곁들임: **docs 비공개** `14e9904`(/docs·/redoc·/openapi.json — SoT v1.7.98, 오늘 아침
    슬라이스로 미검증이었음)·**SoT v1.8.0 등재** `e0b9995`(폴백 taxonomy 부채 폐쇄 + D-g 보충).
  - HEAD(`52431f7`) 클린 트리에서 검증.
- 정규 스펙: [`plans/08-5-usage-admin-cms-decisions.md`](../../plans/08-5-usage-admin-cms-decisions.md)
  (D1=ⓒ·D2=ⓐ·D3=ⓑ, 오너 2026-08-23 — 재작성판 선택지 표) + SoT v1.7.98·v1.8.0~v1.8.2 변경이력.
- 소스: 위 커밋 + `daily_logs/2026-08-23/work_log.md` 세션 9~11.

## Scope

- 계약: 브리프 §5를 경계 행렬로 먼저 세웠다 — endpoint 5종(ADMIN 11→16, operation 84→87)·
  목록의 **정책 행 없는 활성 회원 포함**·상세의 **effective/stored/pending 분리**(H2)·
  P6 발효(완화 즉시·축소 예약)·`POST limits` 400(음수·**비정수**·둘 다 미지정)·
  사유 필수·정지/해제 **즉시**(set_status 신규)·suspended 의 한도 변경이 정지를 안 풀기·
  감사(D3=ⓑ — `member_quota_policy`·`target_user_id`·`detail`·변경만·fail-closed)·
  `/me/quota` 와 같은 snapshot 산식·비활성화(D6)와 별개 축.
- ★ 최우선 의심 축: (i) P6 경계를 API 층이 우회하는가(완화/축소·status 유지) (ii) 감사
  fail-closed 가 실제로 전파되는가·읽기 오염은 없는가 (iii) **비정수 400 조항의 실제
  거동** (iv) 정지 즉시성·activate 복원 (v) H2(만료 pending 표시).
- 구현: `routers/admin.py`(quota 절 전체)·`quota/policy.py`(`policy_row`·`set_status`)·
  `quota/enforcement.py`(`policy` 위임)·`auth/admin_audit.py`(+mongo)·`api/models.py`·
  `api/errors.py`·`main.py`(docs 차단).
- 회귀셀: `AdminQuotaPolicyApiTest` 5셀·`AdminQuotaPolicyChangeApiTest` 6셀·tier/에러선언
  전수 갱신·활동 분류표 등재 — 감사의 대상으로 전수 정독.
- 전수 수트: HEAD에서 독립 재실측(2504/0/2805 검산).

## Methodology

재현 환경: 같은 날 앞선 두 검증 기록과 동일(WSL2·메인 스택 기동·test-mongo 기동·mypy
설치·`.env` 14키). 뮤테이션 절차 동일(tree clean 게이트 → Edit 변이 → 요약 count 줄 +
`FAILED|SUBFAILED` 판독 → `git checkout --` → 클린 확인).

```bash
git status --short                                        # 빈 것 확인
python3 -m pytest -q tests/test_auth_api.py               # 129 passed, 853 subtests
python3 -m pytest -q tests/test_admin_surface_separation.py  # 11 passed, 89 subtests
# V7 탐침(비정수 실측 — 변이 아님):
#   TestClient 로 POST limits 에 {"daily_limit": "77"} / true / 2.5 — 아래 Findings 2
# operation 수 검산: client.app.openapi() 경로·메서드 전수 = 87, /admin/* = 16
docker compose -f docker-compose.test.yml up -d           # healthy 대기
python3 -m pytest -q                                      # (아래 Findings 4)
docker compose -f docker-compose.test.yml down
```

## Findings

### 1. 정본 ↔ 구현 대조 — 브리프 §5 전 항 일치 (비정수 단 한 곳 제외)

| 계약 조항 | 코드 좌표 | 판정 |
|---|---|---|
| D1ⓒ endpoint 5종 | `routers/admin.py` — 목록·상세(8.5-a) + limits·suspend·activate(8.5-b). **operation 87·ADMIN 16 실측 일치** | 일치 |
| 정책 행 없는 활성 회원 포함 | `list_quota_policies` 전 사용자 순회(`if user.is_active`) — 비활성 제외는 상세로 보는 길 유지 | 일치 |
| H2 effective/stored/pending 분리 | `_quota_detail`(stored_* 별도 필드) + `_pending_payload`가 `effective_at <= now` 만료 예약 거르기 | 일치 |
| P6(D2=ⓐ) 발효 | 라우터는 `set_limits` 재사용만 — 완화 즉시·축소 예약 셀 둘 다 존재 | 일치 |
| status 유지(정밀화 ①) | `target=QuotaLimits(…, status=effective.status)` — set_limits 의 ACTIVE 기본 해석을 못 타게 | 일치 |
| 정지 즉시(정밀화 ②) | 신규 `QuotaPolicyService.set_status`(한도·pending 무변경, 행 없으면 기본 행 생성) | 일치 |
| D3=ⓑ 감사 | `record_member_quota_change`(action `member_quota_policy`·`target_type "user"`·`target_user_id`·`detail` 변경 요약·reason strip) — purge 필드 재사용 없음·읽기 미기록·호출부가 예외 안 삼킴 | 일치 |
| 같은 snapshot 산식 | `_quota_policy_payload`가 `/me/quota` 와 같은 `quota.snapshot` — 두 표면 직접 비교 셀 | 일치 |
| 400(둘 다 미지정·음수·공백 사유)·404·403 | `change_quota_limits` 검증 순서(본문 → 404)·`_toggle_status` | 일치 |
| **400(비정수)** | **미시행 — 아래 B1** | **불일치** |

tier 87·에러 선언(ADMIN 16)·활동 분류표 `admin_audited` 3종 등재도 전수 가드로 확인.

### 2. ★ B1 — 브리프 §5 "비정수 → 400"이 시행되지 않았고, 정본 셋(브리프·SoT·work_log)이 서로 다른 말을 한다

실측(V7 탐침, 관리자 세션에서 `POST …/limits`):

| 입력 | 실제 거동 |
|---|---|
| `"77"`(숫자 문자열) | **200 — 77로 강제 변환돼 적용**(`stored_daily_limit=77` 실측) |
| `true`(불) | **200 — 1로 변환돼 적용**(77 유지 + 1로의 축소 **예약까지 생성**) |
| `2.5`(소수) | 422(pydantic 형태 오류) |
| 그 어느 것도 | **400이 아니다** |

원인: `AdminQuotaLimitsChangeRequest.daily_limit: int | None` — pydantic lax 모드가
숫자 문자열·불을 정수로 강제 변환한다. 브리프 §5 상태코드 행은 "400(잘못된 한도 값 —
음수·**비정수**·둘 다 미지정)"으로 못박았는데 ① 코드에는 이 분기가 없고 ② 이 축의
셀도 없으며 ③ SoT v1.8.2("400(음수/둘 다 미지정/공백 사유)")와 work_log 세션 11도
**비정수를 결정 기록 없이 뺐다** — 정본 내부 불일치. `true`가 조용히 한도 1 예약을
만드는 것은 "관리자 전용이라 위험 낮음"으로 정당화하기 어려운, 계약이 못박은 거부
분기의 미시행이다. 화소는 오너 결정: ⓐ **strict 검증 구현**(예: 모델을 `StrictInt |
None`로 하거나 `field_validator` 로 bool/문자열 명시 거부) + 비정수 400 셀 추가,
또는 ⓑ 강제 변환 수용을 결정하고 브리프 §5·SoT 를 그렇게 개정(권장하지 않음 —
`true`→1 은 운용 사고를 조용히 만든다).

### 3. 뮤테이션 8종 — 브리프가 못박은 축은 전부 잠금 확인

| id | 적용한 diff | 물린 셀 |
|---|---|---|
| V1 | `admin.py` 라우터 `status=effective.status` → `status=QuotaStatus.ACTIVE` | 1셀 `test_a_limits_change_does_not_lift_a_suspension` |
| V2 | `_audit_quota_change` 본문을 `try: … except Exception: pass`로(삼킴) | 1셀 `test_audit_failure_fails_the_request_closed` |
| V3 | `_toggle_status` 의 `quota.policy.set_status(…)` 호출 삭제 | 2셀 status-유지(선행 suspend 실패로 연쇄)·suspend/activate |
| V4 | `_pending_payload` 의 만료 거르기 2줄 삭제 | 1셀 `test_detail_splits_effective_from_stored_and_hides_expired_pending` |
| V5 | 목록 `if user.is_active` 제거 | 1셀 `test_list_includes_members_without_a_policy_row` |
| V6 | 음수 검사 루프 삭제 | 1셀 `test_validation_and_target_errors` |
| V9 | `read_quota_policy` 에 감사 호출 추가(읽기 감사 = over-strict) | 1셀 `test_changes_are_audited_with_reason_but_reads_are_not` |
| W1 | `main.py` `docs_url/redoc_url/openapi_url=None` 3행 삭제(docs 재공개) | 1셀 `test_the_interactive_docs_are_not_served_on_any_surface` |

전 뮤테이션 후 `git status --short` 빈 것 확인(8회 복구·클린).

### 4. 정량 클레임 — 전수 재실측

| 클레임 | 실측 | 판정 |
|---|---|---|
| 전수 2504 / 0 failed / 2805 subtests | **2504 passed / 4 skipped / 2806 subtests (237.1초, exit 0, 실패 0건)** — 셀 검산 2493 + 8.5-a 5 + 8.5-b 6 = 2504 일치·수집 2508(`--collect-only`) 대조. subtest 2806 = 주장 2805 + 본 기록 등재분 판정 열 +1(문서화된 규칙) | 일치(2805→2806은 본 기록분) |

**측정 순서 실수 기록(재현성 경고)**: 첫 전수는 본 기록 파일을 인덱스 등재 **전**에
둔 채로 돌아 `test_docs_indexes` 계열 8실패(건수·분포·행 구조 셀 — 전부 본 기록
미등재 아티팩트)로 오염됐다. 색인 정합 후 재측정한 위 값이 확정이다. 교훈: **검증
기록을 쓰는 세션의 전수는 기록 등재·색인 갱신 뒤에 잰다.**
| tier 87·ADMIN 11→16·에러 선언 등재 | openapi 전수 87·/admin 16 실측·전수 가드 green | 일치 |
| 활동 분류표 3종 등재(가드가 잡은 누락) | `actions.py` EXCLUDED 3행 확인 + 전수 가드 | 일치 |
| 신규 6셀(8.5-b) | 셀 수 실측 일치 | 일치 |

### 5. docs 비공개(14e9904)·SoT v1.8.0(e0b9995)

- `/docs`·`/redoc`·`/openapi.json` → TestClient 실측 전부 **404**, `/health` 200(양방향).
  세 factory 한 본문 차단 구조 확인, W1 뮤테이션 재실패 — 가드 유효.
- SoT v1.8.0 등재 내용(literal 6종·쿨다운 3분류 ⓑ·env 파싱·`LLAMA_DEFAULT_MODEL` 함정
  명시)은 검증 완료된 폴백 구현과 문장 단위 일치 — 등재 슬라이스답게 **코드 무변**
  (`e0b9995` diff 문서 6파일). **D-2026-08-23-g 등재 확인** — 전 검증의 니트(ⓑ 결정
  Decisions 절 부재) 폐쇄 사실.

## Issues / Risks

### Blocking (계약 의무)

- **B1 — 위 Findings 2.** 브리프 §5의 "비정수 → 400" 미시행(실측: 문자열·불은 강제
  변환 **적용**, 소수는 422, 400은 부재) + 미추적 분기 + 브리프↔SoT v1.8.2↔work_log
  삼자 불일치(비정수를 결정 없이 삭제). 계약 필요 분기가 빈 칸인 상태로는 슬라이스를
  닫을 수 없다 — 화소 방향(ⓐ strict 구현+셀 권장 / ⓑ 개정)은 오너 결정.

### Hardening recommendations (비차단)

- **H1 — 관리자 자기 정지(self-suspend) 가드가 없다.** 브리프가 금지하지도 않았고
  구현도 막지 않는다 — 관리자가 자기 quota 를 정지해도 아무 검사가 없다(정책 행
  `limit=None` 관리자도 정지되면 403). 브리프가 침묵하는 축이라 blocking 은 아니나,
  1인 운영에서 셀프 잠금 사고의 문이 하나 열려 있다 — 금지(400)할지 오너 결정 권장.
- **H2 — 감사 실패 시 변경은 이미 적용된 상태로 요청만 죽는다.**(롤백 없음 —
  docstring 이 "변경은 동기적으로 완결되고 이 이벤트는 그 뒤"라고 서술.) 브리프가
  원자성을 요구하지 않아 위반은 아니지만, 재시도 시 감사에 두 번째 행이 남는다는
  운용 사실를 관리자 콘솔 문서에 남길 것.

## Verdict

**조건부 합격** — 브리프 §5 "비정수 → 400" 조항의 미시행·미추적·정본 삼자 불일치(B1)가
오너 결정으로 화해될 때까지.

근거: 브리프가 못박은 나머지 전 축(P6 발효·status 유지·정지 즉시·H2 분리·감사
fail-closed/읽기 미기록·포함 규칙·400/404/403·tier 87)은 구조·셀·뮤테이션 8종으로
전부 잠금 확인됐고 전수 2504/4/2805 도 독립 재현했다. B1 하나가 계약 문구와 실제
거동(강제 변환 적용)이 갈리는 빈 칸이다.

## Outstanding items

- B1 화소 방향 — 오너 결정 대기(ⓐ strict 검증+셀 / ⓑ 브리프·SoT 개정). 검증자는
  고치지 않는다.
- 배포 서버 동기화 — 8.5·docs 비공개·B1 폐쇄분 전부 미반영(서버는 extractor 슬라이스
  까지). 다음 서버 세션에서 번들 동기화 필요(오너 승인 대기).
- 8.6 결제 seam 브리프·8.7 Phase 8 전체 독립 검증 — 구현 세션 후보 목록 그대로.
- 다음 전수 기대값은 B1 폐쇄 형태에 따라 변동(ⓐ면 +1~2셀, 이 기록 등재로 subtest +1).

## Reproduction

```bash
git status --short                                  # 빈 것 확인
python3 -m pytest -q tests/test_auth_api.py tests/test_admin_surface_separation.py
# B1 탐침: TestClient 관리자 세션에서 POST limits 에 daily_limit="77"/true/2.5
#   → 200(77 적용)/200(1 예약)/422, 400은 부재
# 뮤테이션: Findings 3 표의 diff 를 그대로 Edit → 표적 클래스 pytest →
#   git checkout -- <path> → git status --short 빈 확인
docker compose -f docker-compose.test.yml up -d && \
  until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done
python3 -m pytest -q                                # 2504 / 4 / 2806
docker compose -f docker-compose.test.yml down
```
