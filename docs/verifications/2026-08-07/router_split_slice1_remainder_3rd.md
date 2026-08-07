# 검증 기록 — 라우터 분해 Slice 1 잔여 3차 (analysis)

- **날짜**: 2026-08-07
- **요청자**: 오너 ("다음작업 검증해줘")
- **검증자**: Claude Code (독립 검증 — 피검증 슬라이스 비생산)
- **검증 대상**: 커밋 `70584c2`(이동) · `81aa52d`(기록). 작업 로그
  [`docs/daily_logs/2026-08-07/work_log.md`](../../daily_logs/2026-08-07/work_log.md) Task 5.
- **정본 사양**: 이 슬라이스의 계약은 "행위 무변"이다(내부 이동). 정본은
  [`docs/verifications/2026-08-05/repro_router_split.py`](../2026-08-05/repro_router_split.py) 가 정의하는
  공개 표면 지문 + 이동 정의의 byte-동일.
- **소스**: `main` 브랜치 HEAD(`81aa52d`), 작업 트리 clean.

## Scope

1. **계약(행위 무변)** — `create_app()` 공개 표면. 비교 기준 두 개: 작업자 기준 `5aaf202`(3차 직전) 와
   **`9bc06e3`(분해 이전)** — 후자는 1·2·3차 전체가 한 diff 로 증명되는 가장 강한 검사.
2. **이동 정의 byte-동일** — 36종(handler 21 + 직렬화기 13 + 헬퍼 1 + 공유 `_analysis_job_payload`).
   작업자가 [`repro_byte_identical_3rd.py`](repro_byte_identical_3rd.py) 를 커밋했으나, **검증자가 전수 추출로
   타깃 누락이 없는지 교차확인**한다.
3. **결합도 주장** — "유일 공유 = `_analysis_job_payload`" 를 main.py(writing 잔류)의 참조로 독립 실측.
4. **orphan 안전** — 이동으로 미사용이 된 import 40개 제거가 참조 중인 이름을 지우지 않았는지(PEP 563).
5. **전수 회귀** — backend 풀스위트(test-mongo ON). 작업자 기준선 2200/1/2165.
6. **뮤테이션 N1-N5** — 작업자 [`repro_mutations_3rd.py`](repro_mutations_3rd.py) 실행 + **N3 의 writing 반쪽을
   검증자가 직접 시위**(작업자 repro 은 analysis 테스트만 돌림).
7. **잡동사니** — `_require_project_exists` 보존 판단 · 패치 타깃 · 조립 골격 · register 배선 · **2차 hardening 2건의
   폐쇄 확인**.

## Methodology

- **(1) 행위 무변**: `5aaf202` 와 `9bc06e3` 각각을 워크트리로 만들어 repro 를 돌리고, HEAD 와 지문을 `diff`.
- **(2) byte-동일**: 작업자 repro 실행 + 검증자 전수 추출(`5aaf202:main.py` 와 HEAD `analysis.py`+`payloads.py`
  의 funcdef 전부를 이름별 `ast.unparse` 비교).
- **(3) 결합도**: `grep` 로 main.py(writing 잔류) 가 2·3차 이동 직렬화기 중 무엇을 참조하는지.
- **(4) orphan 안전**: `python3 -m pyflakes` 로 **F821(undefined name)=0** 확인(PEP 563 하 주석 전용 이름까지).
- **(5) 전수 회귀**: `docker compose -f docker-compose.test.yml up -d` → health 대기 → `python3 -m pytest -q`.
- **(6) 뮤테이션**: 작업자 repro(N1-N5, self-restoring) 실행 + N3 변이(`payloads.py` 에서 `failure_detail` 제거)를
  `test_writing_accept.py` 에 직접 적용해 writing 반쪽 시위. clean 게이트 → mutate → focused → `git checkout` 원복.
- **(7) 정적**: `_require_project_exists` 사용처 · patch 타깃 grep · `git show 70584c2` 골격 스윕 · 13b673e(2차 hardening 폐쇄) 확인.

## Findings

### (1) 행위 무변 — IDENTICAL (두 기준 모두)

`diff` 출력 없음. HEAD 지문 `route_count=76`·`order_sensitive_pairs=[]`(0)·
`openapi_sha256=f8b42ef191d95a2341debb0c879805b31ebc5c351dac1ca3c4ee51b2f809cfa1`.
- **HEAD == `5aaf202`**(작업자 기준) IDENTICAL.
- **HEAD == `9bc06e3`**(분해 이전) IDENTICAL — **1·2·3차 전체가 원래 분해 전과 같은 공개 표면**임이 한 diff 로 증명.
stderr 의 `in-routers` 만 12→63 으로 다르고, 이 값은 repro 가 **의도적으로 지문에서 뺀** `endpoint.__module__` 이다.

### (2) 이동 정의 byte-동일 — 36/36 (작업자 repro + 독립 교차)

작업자 [`repro_byte_identical_3rd.py`](repro_byte_identical_3rd.py): **36/36 AST-동일**.
검증자 전수 추출: HEAD `analysis.py`+`payloads.py` 의 비-register funcdef 39개 중 **36이 `5aaf202:main.py` 와 동일**,
나머지 3(`_memory_payload`·`_project_brief_payload`·`_scope_payload`)은 **1차에 이미 `payloads.py` 로 내려간 직렬화기**라
`5aaf202` 시점 main.py 에 없는 것(정상). **타깃 누락 0**, 작업자 TARGETS(36) 완전.

### (3) 결합도 — "유일 공유 = `_analysis_job_payload`" 독립 입증

main.py(writing 잔류)가 2·3차 이동 직렬화기 14종 중 참조하는 것은 **오직 `_analysis_job_payload`** ([`main.py:1589`](../../services/application/app/main.py#L1589) import · [`:3049`](../../services/application/app/main.py#L3049) `POST /writing/accept` 응답의 `analysis_job` 직렬화). 나머지 13종(`_draft_payload`·`_analysis_candidate_payload`·`_gate_finding_payload`·…)은 **0 참조** → 도메인 전용.
HANDOFF 가 "_draft_payload 공유 후보"로 예고한 것은 **추측이었음**이 실측으로 확인(작업자 근거 부합). 그래서 `_analysis_job_payload` 만 `api/payloads.py` 로 내리고, writing 은 `from .api.payloads import` 로 가져온다.

### (4) orphan 안전 — F821 0건

`python3 -m pyflakes main.py routers/analysis.py api/payloads.py` → **undefined name 0건**. PEP 563(`main.py:3`)
하에서도 제거 40개가 참조 중인 이름을 지운 자리는 없다. main.py 잔류 unused(F401)=**21건**(13b673e 정정값과 일치).

### (5) 전수 회귀 — 2200/1/2165

`2200 passed, 1 skipped, 2165 subtests passed in 929.44s`. 작업자 기준선(2200/1/2165, 937s)과 **셀·subtest·skip 전부 일치**.
**skip=1** = test-mongo 전 구간 사용(구조적 live-Chroma 1건). `70584c2` 가 테스트를 한 줄도 안 건드렸으므로 셀 증감 0 은
"테스트를 고쳐서 통과시킨 것이 아니다"의 실측. **subtest +2** 는 작업자 설명대로 +1(글롭 가드 routers 9→10) +1(2차 검증 기록 `d9ecdd1`,
HANDOFF 가 예고한 것).

### (6) 뮤테이션 N1-N5 — 전부 물림 (+ N3 writing 반쪽 시위)

작업자 [`repro_mutations_3rd.py`](repro_mutations_3rd.py) 로 N1-N5 재현, 5종 전부 FAIL, 원복 clean:

| # | 뮤테이션 | 결과(재실측) |
|---|---|---|
| N1 | `routers/analysis.py` → `from ..main import`(순환 복귀) | `SUBFAILED(module='…routers.analysis')` — 글롭 가드가 3차 신규 모듈을 **구체적으로** 지목. 1차 글롭 처방이 3차까지 자동 범위화. |
| N2 | `register_analysis` 호출 삭제 | tier 전수 가드 FAIL `len(by_tier["project"]), 61`. |
| N3 | 공유 `_analysis_job_payload` 에서 `failure_detail` 제거 | analysis 셀 FAIL. **★ 검증자가 writing 반쪽을 추가 시위**: 같은 변이로 `test_writing_accept.py` **8 cells 재실패**(WritingAcceptEnvelopeKeyTest·WritingIntentApiTest·StartNextUnitLegacyDataTest) → **analysis·writing 양쪽 모두 같은 정의 하나에 의존**함을 양쪽 테스트로 입증. |
| N4 | `_REQUIRE_PROJECT_OWNER_BILLABLE` 소유권·시행 순서 뒤집기 | **BILLABLE 9개 전수 SUBFAILED**(context-search·analysis run/compare·writing 6) — 공유 billable 상수가 analysis 신규 라우트까지 올바르 적용. |
| N5 | `POST /analysis/jobs` 의 `dependencies=_REQUIRE_PROJECT_OWNER` 제거 | auth 가드 `SUBFAILED(path='/projects/{project_id}/analysis/jobs', method='post')`. |

### (7) 잡동사니 주장

- **`_require_project_exists` 보존**: main.py 에 **14곳** 사용(1 정의 + 13 writing 호출 추정). analysis 는 factory
  `project_existence_check(core_sot)` 를 대신 씀([`analysis.py:70·137`](../../services/application/app/routers/analysis.py#L70)).
  보존 결정은 정당(14 > 0). 다만 작업자 근거 "33곳" 은 실측 14 로 **과추정** — 결론은 그대로.
- **패치 타깃 0건**: 이동 심볼 37종을 `app.main.<…>` 로 patch 하는 테스트 **0건**.
- **조립 골격 무터치**: `70584c2` 의 main.py diff 에서 `add_middleware`·`exception_handler`·`on_event`·`add_event_handler` 전부 무변.
- **register 배선**: [`main.py:1906-1920`](../../services/application/app/main.py#L1906) — 14 협력자(core_sot·analysis·memory·runner·analysis_context·compare·apply_service·review_queue·character_reconciliation·review_inbox·gate_findings·llm_call_audit·candidate_review).
- **★ 2차 hardening 2건이 폐쇄됨**: 2차 검증(`d9ecdd1`)이 올린 ①2차 repro 미커밋 ②미사용 import 22→21 가 `13b673e` 로
  둘 다 닫혔고, **3차는 repro 2종을 처음부터 커밋**. 검증 루프가 과정을 개선했다.

## Issues / Risks

### Blocking (계약 의무)

없음.

### Hardening recommendations (비차단)

- **N3 repro 가 자기 주장보다 시위가 좁다.** docstring 은 *"analysis·writing 양쪽 셀이 같이 물린다"* 고 쓰나,
  repro 은 `test_application_api.py -k analysis` 만 돌린다. **양쪽이 물리는 것은 사실**이다 — 검증자가 같은 변이로
  `test_writing_accept.py` 8 cells 재실패를 확인했다. repro 에 `test_writing_accept.py` 를 추가하면 서술과 시위가 일치한다
  (공유 자체는 (3) 의 import 구조로 이미 증명되므로 슬라이스 판정엔 영향 없음).
- **`_require_project_exists` 보존 근거 "33곳" vs 실측 14**. 결론(4차 writing 이동까지 보존)은 정당하나, 사유의 숫자가 과추정.
  오너가 4차에서 writing 이동 후 이 클로저를 정리할 때 14 가 정확한 출발값.

## Verdict

**합격** — 행위 무변이 **두 기준(`5aaf202`·`9bc06e3`) 모두** repro 지문 IDENTICAL(route 76·pairs 0·openapi sha
`f8b42ef1…`·dependency 트리) 로 입증됐고(후자는 1·2·3차 전체가 한 diff), 이동 정의 36/36 AST-동일, "유일 공유 =
`_analysis_job_payload`" 결합도 주장을 독립 실측, orphan 제거 F821 0건(PEP 563), 전수 회귀 2200/1/2165 재현(test-mongo
사용), 뮤테이션 N1-N5 전부 가드 작동(N1 이 신규 `routers.analysis` 순환을 글롭으로 지목·N3 양쪽 시위·N4 BILLABLE 9개 전수).
2차 hardening 2건이 작업자에 의해 폐쇄됐고 3차는 repro 를 처음부터 커밋했다. 비차단 2건(N3 repro 시위 확장·보존 근거 숫자)은
모두 슬라이스 판정 밖이다.

## Outstanding items

- test-mongo 회수함(검증자가 기동한 것 회수 — dev stack 본체는 건드리지 않음).
- 슬라이스는 그대로 둔다(차단 발견 없음). 작업자가 별도 슬라이스로 올린 보류 사항 — **4차: writing(13 operation)**.
  `_analysis_job_payload` 는 이미 공유로 내려갔으므로 import 만 하면 된다(partial envelope 5곳·유료 6경로·헬퍼/상수 다수).
  그 후 `_require_project_exists` 정리(14 사용처).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# (1) 행위 무변 — HEAD vs 5aaf202(3차 직전) AND vs 9bc06e3(분해 이전, 전체 사슬)
git worktree add --detach /tmp/wt_a 5aaf202
(cd /tmp/wt_a && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/fp_a.json 2>/dev/null)
git worktree add --detach /tmp/wt_b 9bc06e3
(cd /tmp/wt_b && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/fp_b.json 2>/dev/null)
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/fp_head.json 2>/dev/null
diff /tmp/fp_a.json /tmp/fp_head.json && echo "HEAD==5aaf202 IDENTICAL"
diff /tmp/fp_b.json /tmp/fp_head.json && echo "HEAD==9bc06e3 IDENTICAL (whole split)"
git worktree remove /tmp/wt_a --force; git worktree remove /tmp/wt_b --force

# (2) byte-동일(36) — 작업자 repro + 검증자 전수 추출(본 기록 §Methodology (2))
python3 docs/verifications/2026-08-07/repro_byte_identical_3rd.py   # 36/36

# (3) 결합도: main.py(writing 잔류)가 이동 직렬화기 중 참조하는 것
grep -nE "_analysis_job_payload|_draft_payload|_analysis_candidate_payload" services/application/app/main.py

# (4) orphan 안전 (PEP 563 포함)
python3 -m pyflakes services/application/app/main.py services/application/app/routers/analysis.py \
  services/application/app/api/payloads.py 2>&1 | grep "undefined name" || echo "F821=0 OK"

# (5) 전수 회귀 (skip=1 이 test-mongo 사용의 증거)
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_witte_system-test-mongo-1)" = healthy ]; do sleep 2; done
python3 -m pytest -q --no-header    # 기대: 2200 passed, 1 skipped, 2165 subtests
docker compose -f docker-compose.test.yml down

# (6) 뮤테이션 N1-N5 (self-restoring) + N3 writing 반쪽
python3 docs/verifications/2026-08-07/repro_mutations_3rd.py
# N3 writing 반쪽 시위:
#   sed -i '/"failure_detail": job.failure_detail,/d' services/application/app/api/payloads.py
#   python3 -m pytest tests/test_writing_accept.py -q   # 기대: 8 failed
#   git checkout -- services/application/app/api/payloads.py
```
