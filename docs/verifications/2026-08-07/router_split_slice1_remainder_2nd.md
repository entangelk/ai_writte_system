# 검증 기록 — 라우터 분해 Slice 1 잔여 2차 (projects·drafts·source-refs)

- **날짜**: 2026-08-07
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude Code (독립 검증 — 피검증 슬라이스 비생산)
- **검증 대상**: 커밋 `131bc2a`(이동) · `c721aa4`(기록). 작업 로그
  [`docs/daily_logs/2026-08-07/work_log.md`](../../daily_logs/2026-08-07/work_log.md) Task 3.
- **정본 사양**: 이 슬라이스의 계약은 "행위 무변"이다(내부 이동). 정본은
  [`docs/verifications/2026-08-05/repro_router_split.py`](../2026-08-05/repro_router_split.py) 가 정의하는
  공개 표면 지문 + 이동 정의의 byte-동일.
- **소스**: `main` 브랜치 HEAD(`c721aa4`), 작업 트리 clean.

## Scope

1. **계약(행위 무변)** — `create_app()` 공개 표면: (path,method) 76 · 해석된 dependency 트리 ·
   status_code/response_model/responses · `app.openapi()` sha256 · order-sensitive pair 수.
   비교 기준은 세션 착수 시점 `9bc06e3`(1차·hardening·2차 이전)이라 **하루치 전체**가 한 diff 에 든다.
2. **이동 정의 byte-동일** — 옮겨간 정의 30종(handler 25 + 직렬화기 5)의 본문. 1차 repro 스크립트가
   이 축을 안 덮어서(아래 Hardening) **검증자가 직접 AST 비교로 채웠다.**
3. **카운트 정합** — 25 operation · 30 정의 · 직렬화기 5 · in-routers 17→42 · main.py 잔류 인라인 34.
4. **orphan 안전** — 이동으로 미사용이 된 import 38개 제거가 참조 중인 이름을 지우지 않았는지.
   (`main.py` 가 `from __future__ import annotations`(PEP 563)를 쓰므로 import-time 통과만으론 부족.)
5. **전수 회귀** — backend 풀스위트(test-mongo ON). 작업자 기준선 2200/1/2163.
6. **뮤테이션 N1 재현** — 작업자가 "이 슬라이스에서 가장 값진 결과"로 꼽은 것(순환 복귀 → 글롭 가드가
   신규 `routers.projects` 를 잡는지).
7. **잡동사니 주장** — 패치 타깃 0건 · 조립 골격 무터치 · register 배선 · subtest +3 근거 · 미사용 import 카운트.

## Methodology

- **(1) 행위 무변**: 슬라이스 직전 `9bc06e3` 을 워크트리로 만들어 repro 를 돌리고, HEAD 와 지문을 `diff`.
  ```bash
  git worktree add --detach /tmp/wt_pre 9bc06e3
  (cd /tmp/wt_pre && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/fp_pre.json)
  python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/fp_head.json
  diff /tmp/fp_pre.json /tmp/fp_head.json && echo IDENTICAL
  ```
- **(2) byte-동일**: `git show 9bc06e3:main.py` 와 HEAD 의 `routers/{projects,drafts,source_refs}.py` 에서
  30 정의를 AST 로 이름별 추출해 `ast.unparse` 비교(들여쓰기 정규화, 리터럴/키/속성/호출인자 보존).
  1차 `repro_byte_identical.py` 의 TARGETS 가 12개(1차분만)라 같은 기법으로 2차 30개를 별도 측정.
- **(3) 카운트**: 라우터 3파일의 funcdef 수 · main.py 잔류 `@app.<verb>` 수 · repro stderr 의 in-routers 수.
- **(4) orphan 안전**: `pip install pyflakes` 후 `python3 -m pyflakes` 로 **F821(undefined name) = 0** 확인.
  PEP 563 하에서 주석으로만 쓰인 이름도 잡기 위해 정적 분석기 사용.
- **(5) 전수 회귀**: `docker compose -f docker-compose.test.yml up -d` → health 대기 → `python3 -m pytest -q`.
  skip 수=1 이면 test-mongo 사용 확정(작업자 자기 신고 실수 2087/114 와 구분).
- **(6) 뮤테이션 N1**: clean 게이트 → `routers/projects.py:52` 의 `from ..api.payloads import` → `from ..main import`
  (순환 복귀) → `pytest tests/test_app_import_paths.py` → `git checkout -- <path>` 원복 → 원복 clean + byte-동일 확인.
- **(7) 정적**: `grep` 패치 타깃 · `git show 131bc2a` 골격(middleware/exception/on_event) 스윕 · register 호출 인자.

## Findings

### (1) 행위 무변 — IDENTICAL

`diff /tmp/fp_pre.json /tmp/fp_head.json` 출력 없음. 양쪽 `route_count=76`, `order_sensitive_pairs=[]`(0),
`openapi_sha256=f8b42ef191d95a2341debb0c879805b31ebc5c351dac1ca3c4ee51b2f809cfa1` 동일, route 별
`deps`/`status_code`/`response_model`/`responses` 동일. stderr 의 이동 현황만 다르다(pre `in-routers=12` →
post `in-routers=42`) — `endpoint.__module__` 은 repro 가 **의도적으로 지문에서 뺀** 유일한 값이다.
**이 sha 는 repro docstring(2026-08-05 최초 분해)이 기록한 값과도 일치** — 1차·hardening·2차 전부가 최초
분해 때와 같은 OpenAPI 를 생산한다. 기록된 sha 를 믿지 않고 두 상태에서 직접 찍어 비교했다.

### (2) 이동 정의 byte-동일 — 30/30

`projects.py`(12: `_project_payload` + handler 11) · `drafts.py`(12: `_draft_payload`·`_version_meta_payload`
+ handler 10) · `source_refs.py`(6: `_source_ref_payload`·`_rebuild_source_block_index_payload` + handler 4).
register_* 3종은 신규 배선이라 제외. **30/30 `ast.unparse` 동일.** repro 지문이 `dict[str, object]` 응답의
직렬화기 본문을 못 보는 빈칸(1차 검증이 지적한 것과 같은 자리)을 이 측정이 닫는다.

### (3) 카운트 — 전부 주장과 일치

operation 25(projects 11 · drafts 10 · source_refs 4) · 이동 정의 30(handler 25 + 직렬화기 5) ·
in-routers 17→42 · main.py **4,534→3,924줄**(`9bc06e3` 은 4,808) · main.py 잔류 인라인 `@app.<verb>` **34** =
analysis(21)+writing(13). 직렬화기 5종은 전부 도메인 전용이라 `api/payloads.py` 로 내리지 않았음을 확인(커밋 메시지 부합).

### (4) orphan 안전 — F821 0건

`python3 -m pyflakes main.py routers/{projects,drafts,source_refs}.py` → **undefined name 0건**. PEP 563
(`from __future__ import annotations`, `main.py:3`) 하에서 주석으로만 쓰인 제거 import 도 없다 —
"create_app() 이 import 된다"보다 강한 증거. 신규 라우터 3파일은 pyflakes 완전 clean.
main.py 잔류 unused import(F401)는 **21건** — 작업자가 "기존 부채 22개 손대지 않음"이라 한 것과 근사
(차이는 아래 Hardening). 제거 38개가 참조 중인 이름을 지운 자리는 0건.

### (5) 전수 회귀 — 2200/1/2163

`2200 passed, 1 skipped, 2163 subtests passed in 965.51s`. 작업자 기준선(2200/1/2163, 829s)과
**셀·subtest·skip 전부 일치**(시간 차이는 머신 부하). **skip=1** = test-mongo 를 전 구간 사용했다는 확정
(구조적 live-Chroma 1건만 skip). `131bc2a` 가 테스트를 한 줄도 안 건드렸으므로(`git show --stat 131bc2a`
→ tests/ 0건) 셀 증감 0 은 "테스트를 고쳐서 통과시킨 것이 아니다"의 실측이다.

### (6) 뮤테이션 N1 — 주장대로 물림 (가장 값진 결과 재현)

`routers/projects.py:52` `from ..api.payloads import _project_brief_payload` → `from ..main import`
(순환 복귀). `test_app_import_paths.py` **5 cells 재실패**, 그중
[`test_a_router_module_loads_before_main`](../../tests/test_app_import_paths.py#L90) 가
**`SUBFAILED(module='services.application.app.routers.projects')`** 로 범인을 정확히 지목 — 작업자 주장과
한 단어까지 일치. 에러: `ImportError: cannot import name '_project_brief_payload' from partially initialized
module 'app.main' (most likely due to a circular import)`.
이 셀은 목록을 `routers/*.py` **글롭**으로 읽으므로([`:103-108`](../../tests/test_app_import_paths.py#L103))
2차 의 신규 모듈 3종이 자동으로 범위에 들어왔다 — 1차 의 글롭 처방("사람이 갱신해야 하는 가드는 갱신을
잊는 쪽으로 약해진다")이 다음 슬라이스에서 실제로 값을 한 것. 가드가 여전히 하드코딩(admin·auth)이었다면
이 subtest 는 통과했을 것이고 순환은 배포에서만 터졌을 것이다. 원복 후 `projects.py` HEAD 와 byte-동일.

### (7) 잡동사니 주장

- **패치 타깃 0건**: 이동 심볼 33종(create_project·save_draft·_draft_payload·register_* 등)을
  `app.main.<…>` 로 patch 하는 테스트 **0건**. 1차 와 달리 patch 갱신이 필요한 자리가 애초에 없었다(작업자 주장 부합).
- **조립 골격 무터치**: `131bc2a` 의 main.py diff 에서 `add_middleware`·`add_exception_handler`·`on_event`·
  `add_event_handler` 전부 무변. 건드린 건 이동한 route 데커레이터 + import + register 호출 추가뿐.
- **register 배선**: [`main.py:1931-1938`](../../services/application/app/main.py#L1931) —
  `register_projects(app, core_sot, access_grants, sync_outbox)` ·
  `register_drafts(app, core_sot, sync_outbox)` ·
  `register_source_refs(app, core_sot, shared_vector_index, shared_embeddings, shared_backend)`.
  협력자가 work_log 표와 정확히 일치.
- **subtest +3 근거**: 글롭 가드가 6→9 모듈을 도므로 `test_a_router_module_loads_before_main` subtest 6→9.
  코드와 무관하게 오르는 자리(HANDOFF 가 경고한)의 재확인.

## Issues / Risks

### Blocking (계약 의무)

없음.

### Hardening recommendations (비차단)

- **★ 2차 의 byte-동일(30 def)·뮤테이션(N1-N5) 에 커밋된 repro 스크립트가 없다.** 1차 는
  [`repro_byte_identical.py`](repro_byte_identical.py)(12 def)·[`repro_mutations.py`](repro_mutations.py)(M1-M5)
  를 커밋했으나, 2차(`c721aa4`)는 HANDOFF·README·work_log 만 건드려 이 두 축의 재현 스크립트를 남기지 않았다.
  메모리 규칙 `verification-repro-scripts-must-be-committed` 와 대비되는 비대칭. **부하 증명(지문 IDENTICAL)은
  커밋된 `repro_router_split.py` 로 덮이므로 슬라이스 판정엔 영향 없다** — 다만 `repro_byte_identical.py` 의
  TARGETS 를 30개로 확장하고 N1-N5 repro 를 별도 커밋하면, 다음 검증자가 이 기록처럼 30 def 동일·뮤테이션을
  직접 재유도하지 않아도 된다. 본 검증은 검증자가 두 축을 직접 재현해 채웠다(위 (2)·(6)).
- **main.py 미사용 import 카운트: 작업자 22, 실측 21**(pyflakes F401). 단순 집계차이로 보이며(동일 import 문의
  다중 이름을 세는 단위 차이 가능), 작업자 의도 — "기존 부채는 손대지 않고 내 이동이 만든 orphan 만 지운다" — 는
  정확히 확인됨(orphan 제거 안전성은 (4) 로 이미 입증). 오너가 정리 슬라이스를 잡을 때 21 이 정확한 출발값.
- (화술적) 회귀 명령 시작 에코의 `docker inspect … test-mongo-1` 이 찰나에 `error: no such object` 를 반환했다.
  그러나 test-mongo-1 은 12:53:15 부터 컨테이너 ID 불변으로 연속 Up·healthy 였고, 로그가 직전 2분간 2,238줄,
  최종 skip=1 → pytest 가 실사용했음이 확정. 동시 `docker inspect` 경합/데몬 찰나 지연이 낸 허위 에코이며
  진짜 신호는 최종 skip 수다. 작업자가 회귀 명령줄에 healthcheck 를 붙인 것은 옳은 방향이나, 에코가 빈 값을
  반환해도 컨테이너가 실제로는 살아있을 수 있음을 함께 아는 것이 좋다.

## Verdict

**합격** — 하루치 전체(1차 + hardening + 2차)의 행위 무변이 repro 지문 IDENTICAL(경로 76 · pairs 0 ·
openapi sha · dependency 트리 전부 무변, `9bc06e3` 대 `c721aa4` 직접 비교) 로 입증됐고, 이동 정의 30/30 이
AST-동일이며, orphan 제거가 F821 0건으로 안전(PEP 563 포함)하고, 전수 회귀 2200/1/2163 이 재현됐으며
(test-mongo 사용 확정), N1 뮤테이션이 글롭 가드로 신규 `routers.projects` 순환을 정확히 잡아냈다.
유일한 비대칭(2차 byte-동일·뮤테이션 repro 미커밋)은 부하 증명이 커밋된 지문 repro 로 덮이므로 hardening 이지
이 슬라이스의 계약 위반이 아니다.

## Outstanding items

- test-mongo 회수함(검증자가 기동한 것 회수 — dev stack 본체는 건드리지 않음). 작업자 종료 상태("회수")에 맞춤.
- 슬라이스는 그대로 둔다(차단 발견 없음). 작업자가 별도 슬라이스로 올린 보류 사항 — 잔여 2 도메인
  (analysis 21 · writing 13, 공유 직렬화기 `_analysis_job_payload` 1개) 이동 → 그 다음 main.py 기존
  미사용 import 정리(오너 판단 순서).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# (1) 행위 무변 — 9bc06e3(세션 착수 전) 대 HEAD 지문 diff
git worktree add --detach /tmp/wt_pre 9bc06e3
(cd /tmp/wt_pre && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/fp_pre.json 2>/dev/null)
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/fp_head.json 2>/dev/null
diff /tmp/fp_pre.json /tmp/fp_head.json && echo IDENTICAL   # 기대: IDENTICAL, route 76 / pairs 0
git worktree remove /tmp/wt_pre --force

# (2) byte-동일(30 정의 AST 비교) — 1차 repro_byte_identical.py 가 안 덮는 2차 축.
#     git show 9bc06e3:main.py 와 routers/{projects,drafts,source_refs}.py 에서
#     이름별 ast.unparse 비교 → 30/30 동일. (본 기록 §Methodology (2) 의 inline 스크립트.)

# (3) 카운트
grep -cE '@app\.(get|post|put|patch|delete)' services/application/app/main.py   # 잔류 인라인 = 34

# (4) orphan 안전 (PEP 563 포함)
pip install --quiet pyflakes
python3 -m pyflakes services/application/app/main.py \
  services/application/app/routers/projects.py services/application/app/routers/drafts.py \
  services/application/app/routers/source_refs.py 2>&1 | grep "undefined name" || echo "F821=0 OK"

# (5) 전수 회귀 (skip=1 이 test-mongo 사용의 증거)
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done
python3 -m pytest -q --no-header    # 기대: 2200 passed, 1 skipped, 2163 subtests
# ^ 컨테이너 이름 오타(ai_witte_…) 를 2026-08-07 보강 패스가 고쳤다 — 오타면 위 until 이
#   'no such object' 로 영원히 돈다. 아래 Hardening ③ 의 '찰나의 허위 에코' 도 같은 뿌리로 보인다.
docker compose -f docker-compose.test.yml down

# (6) 뮤테이션 N1 — clean 게이트 → mutate → focused → git checkout 원복 → byte-동일 확인
git status --short                  # must be empty
sed -i 's/from \.\.api\.payloads import _project_brief_payload/from ..main import _project_brief_payload/' \
  services/application/app/routers/projects.py
python3 -m pytest tests/test_app_import_paths.py -q   # 기대: 5 failed, SUBFAILED(module='…routers.projects')
git checkout -- services/application/app/routers/projects.py
git diff --quiet && echo "restored byte-identical to HEAD"
```
