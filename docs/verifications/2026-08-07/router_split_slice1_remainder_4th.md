# 검증 기록 — 라우터 분해 Slice 1 잔여 4차 (writing) · Slice 1 완료

- **날짜**: 2026-08-07
- **요청자**: 오너 ("다음작업 검증해줘")
- **검증자**: Claude Code (독립 검증 — 피검증 슬라이스 비생산)
- **검증 대상**: 커밋 `c289bce`(이동) · `9833606`(기록). 작업 로그
  [`docs/daily_logs/2026-08-07/work_log.md`](../../daily_logs/2026-08-07/work_log.md) Task 7.
- **정본 사양**: 이 슬라이스의 계약은 "행위 무변"이다(내부 이동). 정본은
  [`docs/verifications/2026-08-05/repro_router_split.py`](../2026-08-05/repro_router_split.py) 가 정의하는
  공개 표면 지문 + 이동 정의의 byte-동일.
- **소스**: `main` 브랜치 HEAD(`9833606`), 작업 트리 clean.

## Scope

1. **계약(행위 무변)** — 비교 기준 두 개: `2a5a52c`(4차 직전) 와 **`9bc06e3`(Slice 1 착수 전)**.
   후자는 **모놀리스 `main.py`(76 op 인라인) → 11 라우터 모듈(76 op 전부)** 이동 전체가 한 diff 로
   증명되는 가장 강한 검사(Slice 1 완료의 모자).
2. **이동 정의 byte-동일** — 25종(handler 13 + 직렬화기 9 + 헬퍼 3). 작업자 repro + **독립 전수 추출**.
3. **`_require_project_exists` 삭제** — 순수 이동이 아닌 **실제 정의 제거**(writing 이 마지막 사용). 잔류 참조 없는지.
4. **AST 자동 생성 import** — 작업자가 ast.walk 로 import 문을 자동 생성(asname 함정·본문 참조 누락을 F821 로 보완).
   F821/F401 로 정확성.
5. **전수 회귀** — backend 풀스위트(test-mongo ON). 작업자 기준선 2200/1/2167.
6. **뮤테이션 N1-N5** — 작업자 [`repro_mutations_4th.py`](repro_mutations_4th.py). 특히 **N3 partial envelope**
   (3차 검증이 예고한 추가 의심축).
7. **잡동사니** — 공유 직렬화기 import · 조립 골격 · register 배선 · Slice 1 전체 규모 · 3차 hardening 폐쇄 확인.

## Methodology

- **(1) 행위 무변**: `2a5a52c`·`9bc06e3` 각각 워크트리로 repro 돌려 HEAD 와 `diff`.
- **(2) byte-동일**: 작업자 [`repro_byte_identical_4th.py`](repro_byte_identical_4th.py) 실행 + 검증자 전수 추출
  (`2a5a52c:main.py` 와 HEAD `writing.py` funcdef 전부 `ast.unparse` 비교).
- **(3) 삭제**: `grep` 로 main.py 의 `_require_project_exists` 참조 수 · writing.py 의 factory 사용.
- **(4) AST import**: `python3 -m pyflakes writing.py` 로 F821(정의 미사용→undefined)·F401(과잉 import) 확인.
- **(5) 전수 회귀**: `docker compose -f docker-compose.test.yml up -d` → health(`docker ps` 로 확인; 이 셸에선
  `docker inspect` 가 찰가 "no such object" 를 뱹니다 — WSL2 데몬 불량, 컨테이너 자체는 healthy) → `python3 -m pytest -q`.
- **(6) 뮤테이션**: 작업자 repro(N1-N5, self-restoring) 실행.
- **(7) 정적**: 공유 직렬화기 import grep · `git show c289bce` 골격 스윕 · main.py 궤적 · f9b5e45(3차 hardening 폐쇄) 확인.

## Findings

### (1) 행위 무변 — IDENTICAL (두 기준 모두) · ★ Slice 1 완료

`diff` 없음. HEAD 지문 `route_count=76`·`order_sensitive_pairs=[]`(0)·
`openapi_sha256=f8b42ef191d95a2341debb0c879805b31ebc5c351dac1ca3c4ee51b2f809cfa1`.
- **HEAD == `2a5a52c`**(4차 직전) IDENTICAL.
- **HEAD == `9bc06e3`**(Slice 1 착수 전) IDENTICAL — **모놀리스 `main.py`(76 op 전부 인라인) → 11 라우터 모듈(76 op
  전부 이동) 의 4-슬라이스 리팩터 전체가 원래와 같은 공개 표면**임이 한 diff 로 증명. `in-routers=76`, main.py 인라인
  라우트 **0**. stderr 의 `in-routers` 만 12→76 으로 다르고, 이 값은 repro 가 **의도적으로 지문에서 뺀** 값이다.

### (2) 이동 정의 byte-동일 — 25/25 (작업자 repro 24 + 독립 25)

작업자 [`repro_byte_identical_4th.py`](repro_byte_identical_4th.py): 24/24 AST-동일(직렬화기 9 + **헬퍼 2** + handler 13).
검증자 전수 추출: HEAD `writing.py` 비-register funcdef **25개 전부** `2a5a52c:main.py` 와 동일.
**차이 1**: writing.py 헬퍼는 **3종**(`_record_loop_audit`·`_clear_scratch_for_saved_accept`·`_derive`)인데
작업자 TARGETS(24)·커밋 메시지("헬퍼 2종")는 `_derive` 1개를 빠뜨렸다. **이동 자체는 완전**하다 — `_derive` 포함 25/25 동일을
독립 추출로 확인(아래 Hardening).

### (3) `_require_project_exists` 삭제 — 잔류 참조 0

main.py 의 `_require_project_exists` 참조 **0건**(정의·사용 전부 삭제). writing.py 는 factory
`project_existence_check(core_sot)` 를 **2곳**에서 쓴다. **F821 0건**(아래)이 삭제된 이름을 다시 보는 곳이 없음을
확인 — 순수 이동이 아닌 실제 정의 제거가 안전함.

### (4) AST 자동 생성 import — pyflakes 완전 clean

`python3 -m pyflakes writing.py` → **F821(undefined) 0 · F401(unused) 0**. 작업자가 ast.walk 로 handler 참조 심볼을
수집해 import 문을 자동 생성하며 밟았다는 **asname 함정 2종·직렬화기 본문 참조 누락**을 F821 로 보완했다는 기법 메모가
실제로 작동함 — 과잉 import(F401)도 없고 누락(F821)도 없다. PEP 563(`main.py:3`) 하에서도 main.py F821 0건.

### (5) 전수 회귀 — 2200/1/2167

`2200 passed, 1 skipped, 2167 subtests passed in 973.78s`. 작업자 기준선(2200/1/2167, 843s)과 **셀·subtest·skip 전부 일치**.
**skip=1** = test-mongo 전 구간 사용(구조적 live-Chroma 1건). `c289bce` 가 테스트를 한 줄도 안 건드렸으므로 셀 증감 0.
**subtest +1** = 글롭 가드 routers 10→11(`test_a_router_module_loads_before_main`).

### (6) 뮤테이션 N1-N5 — 전부 물림 (N3 가 3차 예고축)

작업자 [`repro_mutations_4th.py`](repro_mutations_4th.py) 로 5종 재현, 전부 FAIL, 원복 clean:

| # | 뮤테이션 | 결과(재실측) |
|---|---|---|
| N1 | `routers/writing.py` → `from ..main import`(순환 복귀) | `SUBFAILED(module='…routers.writing')` — 글롭 가드가 11번째 모듈을 지목. |
| N2 | `register_writing` 호출 삭제 | tier 전수 가드 FAIL. |
| N3 | **accept partial envelope 502→500**(H3 분류 오염) | partial envelope 셀 FAIL — **3차 검증이 "partial envelope 을 추가 의심축으로" 예고한 자리를 정확히 잡음**. |
| N4 | `_REQUIRE_PROJECT_OWNER_BILLABLE` 소유권·시행 순서 뒤집기 | **BILLABLE 9개 전수 SUBFAILED**(context-search·analysis run/compare·writing 6). |
| N5 | `GET /writing/budget` 의 소유권 tier 제거 | auth 가드 `SUBFAILED(path='/projects/{project_id}/writing/budget')`. |

### (7) 잡동사니 주장

- **공유 직렬화기**: writing.py 가 `_analysis_job_payload` 를 `from ..api.payloads import`([`writing.py:141`](../../services/application/app/routers/writing.py#L141))로 가져와
  `writing_accept_endpoint`([`:1290`](../../services/application/app/routers/writing.py#L1290)) 에서 씀 — 3차 에서 공유로 내린 정의를 올바르게 재사용.
- **조립 골격 무터치**: `c289bce` 의 main.py diff 에서 `add_middleware`·`exception_handler`·`on_event`·`add_event_handler` 전부 무변.
- **register 배선**: [`main.py:1839-1855`](../../services/application/app/main.py#L1839) — 15 협력자 + `return app`(`:1857`, `create_app` 종료).
- **★ Slice 1 규모(실측)**: main.py `2f20fbb~1`(prelude 추출 전)=**5,843줄** → HEAD=**1,860줄** = **약 68% 감소**. 작업자가 적은
  "6,145/70%" 은 시작점이 다소 과대(아래 Hardening).
- **★ 3차 hardening 2건이 폐쇄**: `f9b5e45`·`2a5a52c` 가 3차 검증의 ①N3 repro writing 시위 추가 ②`_require_project_exists` 33→14 정정
  을 닫았다. **지금까지 검증자가 올린 hardening 4건(2차 2·3차 2)이 전부 폐쇄**.

## Issues / Risks

### Blocking (계약 의무)

없음.

### Hardening recommendations (비차단)

- **작업자 byte-identical repro TARGETS=24 가 `_derive` 1개를 누락**. writing.py 헬퍼는 3종(`_record_loop_audit`·
  `_clear_scratch_for_saved_accept`·`_derive`)인데 작업자는 "헬퍼 2종"으로 세고 `_derive` 를 TARGETS 에 안 넣었다.
  **이동은 완전** — 검증자 전수 추출이 25/25 동일을 확인. 2차 때와 같은 패턴(손 관리 TARGETS 가끔 과소집계; 독립 전수 추출이 잡음).
  repro TARGETS 를 25로 늘리면 서술과 검사가 일치.
- **"원래 6,145줄/70%" 수사**: 실측 최대 출발점은 `2f20fbb~1`(prelude 추출 전) **5,843줄**, 감소율 **약 68%**. 작업자 수치는
  시작점이 다소 과대이나 리팩터 규모의 서술적 수사일 뿐 정확성엔 무영향.

## Verdict

**합격** — 행위 무변이 **두 기준 모두** repro 지문 IDENTICAL(route 76·pairs 0·openapi sha `f8b42ef1…`·dependency 트리) 로
입증됐고, 그중 **HEAD ≡ `9bc06e3`** 는 **Slice 1 전체 — 모놀리스 `main.py`(76 op 인라인) → 11 라우터 모듈(76 op 전부)
이동 — 가 원래와 같은 공개 표면**임을 증명한다(Slice 1 완료). 이동 정의 25/25 AST-동일(독립 전수 추출), `_require_project_exists`
**실제 정의 삭제**가 잔류 참조 0·F821 0 로 안전, AST 자동 생성 import 가 F821/F401 0 로 정확, 전수 회귀 2200/1/2167 재현
(test-mongo 사용), 뮤테이션 N1-N5 전부 가드 작동(N1 신규 `routers.writing` 순환 글롭 지목·**N3 partial envelope 502→500**·N4 BILLABLE 9개).
비차단 2건(TARGETS `_derive` 누락·6,145/70% 수사)은 모두 슬라이스 판정 밖이며, 독립 전수 추출이 첫 번째를, 실측이 두 번째를 보완한다.

## Outstanding items

- test-mongo 회수함(검증자가 기동한 것 회수 — dev stack 본체는 건드리지 않음).
- **Slice 1 완료** — 차단 발견 없음. 작업자가 올린 두 갈래: ①`main.py` 미사용 import 정리(출발 pyflakes F401=21,
  `_default_model_capabilities`·`seed_*` 조립 전용 잔류 심볼 포함) ②Slice 2(`create_admin_app()` — 이제 `routers.admin` 을
  그냥 import 가능, 선행 H-2 shim drift 가드).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# (1) 행위 무변 — HEAD vs 2a5a52c(4차 직전) AND vs 9bc06e3(★ Slice 1 전체)
git worktree add --detach /tmp/wt_a 2a5a52c
(cd /tmp/wt_a && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/fp_a.json 2>/dev/null)
git worktree add --detach /tmp/wt_b 9bc06e3
(cd /tmp/wt_b && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/fp_b.json 2>/dev/null)
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/fp_head.json 2>/dev/null
diff /tmp/fp_a.json /tmp/fp_head.json && echo "HEAD==2a5a52c IDENTICAL"
diff /tmp/fp_b.json /tmp/fp_head.json && echo "HEAD==9bc06e3 IDENTICAL (Slice 1 whole)"
git worktree remove /tmp/wt_a --force; git worktree remove /tmp/wt_b --force

# (2) byte-동일 — 작업자 repro + 검증자 전수 추출(본 기록 §Methodology (2))
python3 docs/verifications/2026-08-07/repro_byte_identical_4th.py   # 24/24 (검증자 전수는 25/25)

# (3) _require_project_exists 삭제 — main.py 잔류 참조 0
grep -cE "_require_project_exists" services/application/app/main.py   # 0

# (4) AST import 정확성 — writing.py pyflakes clean
python3 -m pyflakes services/application/app/routers/writing.py services/application/app/main.py 2>&1 | grep undefined || echo "F821=0 OK"

# (5) 전수 회귀 (skip=1 이 test-mongo 사용의 증거; 이 셸에선 docker inspect 가 찰가 안 되니 ps 로 확인)
docker compose -f docker-compose.test.yml up -d
until [ "$(docker ps --filter name=test-mongo --format '{{.Status}}' | grep -o healthy)" = healthy ]; do sleep 2; done
python3 -m pytest -q --no-header    # 기대: 2200 passed, 1 skipped, 2167 subtests
docker compose -f docker-compose.test.yml down

# (6) 뮤테이션 N1-N5 (self-restoring)
python3 docs/verifications/2026-08-07/repro_mutations_4th.py
```
