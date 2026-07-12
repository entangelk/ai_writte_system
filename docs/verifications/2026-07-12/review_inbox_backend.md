# 검증 기록 — Phase 6 Review Inbox 백엔드 (SoT v1.6.64)

## Subject metadata

- **날짜**: 2026-07-12
- **요청자**: 오너(사용자). 요청: "Phase 6 Review Inbox 백엔드 완료. GET /review-inbox(미승격 needs_review + candidate별 open conflict 개수 + 직접 승격 legacy 중복 억제)·GET /review-inbox/{cid}(payload + source ref 정본 pointer + matched canonical + 결정적 field diff·유실 ref는 status=missing·confirmed/reconciled 제거·cross-project·non-review 404). 검증해줘."
- **검증자**: Claude(독립 감사 — 구현 작업자 아님)
- **대상 slice/artifact**: Phase 6 Review Inbox 백엔드. 구현 `services/application/app/analysis/review_inbox.py`(신규)·`main.py`(route 2개 + helper + wiring). 회귀 `tests/test_analysis_apply_api.py::ReviewInboxApiTest`(신규 4). 계약 갱신 SoT v1.6.64·브리프 `plans/06-review-inbox-backend-decisions.md`(신규)·`plans/06-review-ui.md`(checkbox 2건 갱신).
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.64(버전 테이블 line 36). 선행: candidate 상태 전이 v1.6.61·review queue v1.6.59·승격 dedup v1.6.60·merge/split reconciliation v1.6.63.
- **소스**: working tree, uncommitted(`a74c4c7` v1.6.63 위).

## Scope

1. **계약 자체 일관성** — SoT v1.6.64 ↔ 브리프 D1~D5 ↔ 선행 v1.6.60 dedup·v1.6.61 전이·v1.6.63 reconcile 정합. read-only 경계(D4).
2. **list 구현** — needs_review 통합·candidate별 open conflict 중첩·직접 승격 legacy 억제(v1.6.60 dedup 계승).
3. **detail 구현** — payload·source ref 정본 pointer·matched canonical·결정적 field-level diff.
4. **status=missing 마커** — 유실 source ref의 가짜 pointer 회피, NotFound 라우팅.
5. **404 경계** — cross-project·needs_review 아님·confirmed/reconciled 제거.
6. **의존 서비스 메서드 실재 + signature** — `get_source_ref`·`list_needs_review_candidates`·`is_candidate_promoted`·`list_open`·`get_memory`.
7. **회귀 품질** — ReviewInboxApiTest 4종 under/over-strict.
8. **전체 suite 재현** — 771/48 독립 재실행(작업 AI 이번엔 명시적 green 보고).
9. **문서 갱신 정확** — SoT·HANDOFF·CHANGELOG·work_log·06-review-ui checkbox.
10. **적대적** — field diff 결정성·source pointer envelope 절반(missing vs resolved) 커버리지·중복 억제 이중 필터 관계.

## Methodology

```bash
# 1. 변경 범위
git status; git diff --stat

# 2. 계약/구현 원문 교차 읽기
git diff docs/system-contract-sot.md                       # v1.6.64
# Read plans/06-review-inbox-backend-decisions.md (D1~D5)
# Read services/application/app/analysis/review_inbox.py (전체)
git diff services/application/app/main.py                  # route + helper + wiring

# 3. 의존 메서드 실재 + signature (추측 금지)
grep -rn "def get_source_ref\|def list_needs_review_candidates\|def is_candidate_promoted" services/application/app/
sed -n '400,412p' services/application/app/core_sot/service.py   # get_source_ref raise vs None + cross-project
sed -n '66,80p' services/application/app/core_sot/models.py      # SourceRef 필드(quote 포함)

# 4. 회귀 원문 + 헬퍼
git diff tests/test_analysis_apply_api.py
sed -n '440,500p' tests/test_analysis_apply_api.py               # _open_conflict 헬퍼(payload/source_ref 세팅)

# 5. ★ 전체 suite 독립 재실행
timeout 200 python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider > /tmp/pytest_p6.log 2>&1
echo "EXIT: $?"; tail -3 /tmp/pytest_p6.log
python3 -m pytest -q tests/test_analysis_apply_api.py::ReviewInboxApiTest   # focused 4

# 6. route 등록 + envelope 확인 (app introspection)
python3 -c "import services.application.app.main as m; app=m.create_app(); \
  print(sorted(p for p in app.openapi()['paths'] if 'review-inbox' in p))"

# 7. 서식
git diff --check
```

## Findings

### 1. 계약 자체 일관성 — PASS

- 브리프 D1~D5(`plans/06-review-inbox-backend-decisions.md`)와 SoT v1.6.64(버전 테이블 line 36) 정합.
- **read-only 경계(D4)**: 이 slice는 list/detail만. 기존 confirm/reject/merge/split 단건 API 재사용. 부분 승인·edit·Gate finding은 제외(브리프 line 12-13, 22-26). 구현이 write를 발생시키지 않음 확인.
- v1.6.60 (e) dedup 계승: "legacy 직접 승격 candidate는 canonical 경로로만"(브리프 D1) → `is_candidate_promoted` 필터로 실현.

### 2. list 구현 — PASS

- `review_inbox.py:47-61`: `list_needs_review_candidates` → `is_candidate_promoted` 필터(직접 승격 legacy 억제) → `list_open`을 candidate별 그룹 → `_item`.
- candidate 한 행 + open conflict 중첩(D1 "conflict만 별도 중복 행으로 만들지 않는다"). conflict 정렬 `sorted(entries, key=lambda v: v.id)`(결정적).
- **이중 필터 아님(필수 필터)**: `list_needs_review_candidates`는 needs_review status만 반환. 직접 promote(memory만 만들고 candidate status는 needs_review 유지 — v1.6.60 맥락) candidate는 여전히 needs_review라 list에 포함 → `is_candidate_promoted`로 억제. reconcile(c-2)/confirm(v1.6.61)은 candidate를 CONFIRMED로 전이하므로 status 필터로 제거. 두 경계 모두 커버.

### 3. detail 구현 — PASS

- `review_inbox.py:63-88`: `get_item`이 list에서 candidate_id 탐색 → 없으면 `ReviewInboxNotFound`. `_conflict`가 `entry.matched_memory_id`로 canonical 조회(MemoryNotFound 시 None) → memory 있으면 `_payload_diff(before=memory.payload, after=candidate_payload)`, 없으면 diff=().
- `_payload_diff`(91-96): `sorted(set(before)|set(after))`에서 `before.get(field) != after.get(field)`인 field만 → **결정적**(field명 정렬, 값 동일 제외, 새/제거 field 모두 포함).
- main.py `_review_inbox_payload`(1670-1709): include_detail=False(list)는 candidate_id/job_id/candidate_type/status/confidence/provenance/conflict_count; True(detail)는 payload·source_refs·conflicts(entry_id/action/rationale/matched_memory/diff) 추가.

### 4. status=missing 마커 — PASS

- main.py `_review_source_pointer`(1667-1683): `core_sot.get_source_ref(project_id, source_ref_id)`. NotFound except → `{"source_ref_id":..., "status":"missing"}`(가짜 pointer 없음). 정상 시 `status=resolved` + snapshot_id/block_id/start_offset/end_offset/quote/content_hash.
- `get_source_ref`(`core_sot/service.py:407-411`): `repo.get_source_ref(source_ref_id)` → None이거나 `source_ref.project_id != project_id`면 **NotFound raise**(cross-project 격리 포함). main.py except NotFound 정합.
- `SourceRef` 모델(`models.py:68-76`)에 `quote` 필드 존재 → main.py `ref.quote` 안전(초기 의심 해소).

### 5. 404 경계 — PASS

- project 누락: `_require_project_exists` NotFound → 404(main.py list/detail 양쪽).
- cross-project / needs_review 아님 / confirmed·reconciled: `get_item`이 `list_items(project_id)`에서만 탐색 → 해당 candidate 없으면 `ReviewInboxNotFound` → 404. 브리프 line 19 정합.
- test_confirmed_leaves: reconcile split 후 candidate CONFIRMED 전이 → list=[] · detail 404. test_404: missing project 404 · cross-project candidate 404. 양방향 검증.

### 6. 의존 메서드 실재 — PASS

`get_source_ref`(core_sot/service.py:407)·`list_needs_review_candidates`(analysis/service.py:500)·`is_candidate_promoted`(memory/service.py:134)·`list_open`(review_queue)·`get_memory`(memory) 전부 실재·signature 일치. 추측 아닌 grep+원문 확인.

### 7. 회귀 품질 — PASS (비차단 관찰 1~4, 아래 Issues)

`ReviewInboxApiTest` 4종:
- `test_list_unifies_candidate_with_open_conflict`: conflict_count=1·status=needs_review·list에 payload 없음(include_detail=False). under-strict.
- `test_detail_returns_payload_source_status_memory_and_field_diff`: payload·source_refs=[{missing}]·matched_memory.id·diff=[{name, before=Ariel, after=Song}]. under/over-strict(diff 정확성).
- `test_confirmed_candidate_leaves_inbox`: reconcile split 후 list=[] · detail 404. over-strict.
- `test_missing_project_and_cross_project_candidate_return_404`: missing project 404 · cross-project 404. over-strict.
- **정직성 catch**: work_log에 *"최초 테스트 클래스 상속이 기존 4개를 중복 수집해 775로 보인 것을 발견하고 helper-only 재사용으로 교정"* — `ReviewInboxApiTest`가 `CharacterReconciliationApiTest`를 상속하면 unittest가 test_ 메서드를 부모+자식 중복 수집(775 잘못 카운트)하는 버그를 작업 AI가 스스로 포착·교정(helper 호출 패턴). 771이 정확.

### 8. 전체 suite 재현 — PASS

`timeout 200 python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **771 passed, 48 skipped, 3 warnings, 99 subtests passed in 12.25s, exit 0**. 작업 AI 보고(771/48/99)와 정확히 일치. focused `ReviewInboxApiTest` 4 passed.

### 9. 문서 갱신 — PASS

- SoT v1.6.64(버전 테이블 line 36, 역순 최상단). HANDOFF(Current Status v1.6.64·Memory 레이어 v1.6.62~64 요약·Verification 771·project 구조 SoT 버전 정정). CHANGELOG 최상단. work_log(Goals·Completed·Decisions + 중복 수집 교정 기록). `06-review-ui.md` checkbox 2건 [x] 갱신(Gate finding 통합 결정·source deep link 결정).
- `git diff --check` exit 0.

## Issues / Risks

**차단 이슈: 없음.** 계약 위반·쓰기 발생·의존 메서드 부재·source ref 누출·빈 boundary cell 전부 발견 안 됨.

**비차단 관찰**:

- **Obs1 — `status=resolved` source ref 경로 미커버(보강 가치 가장 큼)**. ReviewInboxApiTest의 모든 source_refs assertion이 `[{"source_ref_id": "source-ref-1", "status": "missing"}]`(정본 미등록 ref). `_review_source_pointer`의 **resolved 분기**(`status=resolved` + snapshot_id/block_id/start_offset/end_offset/quote/content_hash field 매핑)가 회귀로 잠기지 않음. missing 분기(NotFound→404 라우팅)는 잠겨 있으나, public envelope의 resolved 형태가 보장되지 않음. SourceRef 필드명·매핑이 단순하므로 위험 낮으나, 추천: 정본에 source ref를 등록한 fixture로 resolved 경로 회귀 추가(snapshot_id/quote/content_hash 등 assertion).
- **Obs2 — 직접 승격 legacy candidate 억제 미커버**. test_confirmed는 reconcile(CONFIRMED 전이) 경로만. `list_items:53`의 핵심 필터 `is_candidate_promoted`가 direct promote(memory만 만들고 status는 needs_review 유지) candidate를 억제하는 시나리오가 inbox 컨텍스트에서 직접 테스트 안 됨. v1.6.60 (e) dedup 자체 테스트에 위임 가능하나, inbox read surface에서의 억제는 미커버. 추천: direct-promote candidate를 inbox list에서 빠지는 회귀.
- **Obs3 — matched_memory 없는 conflict (diff 빈) 미커버**. `matched_memory_id=None` conflict(중복 canonical conflict, `compare.py` matches>1 경로)의 `diff=()` 분기(`_conflict:87` memory=None → diff=())가 테스트 안 됨. 빈 envelope 보장.
- **Obs4 — 다중 conflict 정렬 미커버**. 한 candidate에 여러 open conflict일 때 `sorted(entries, key=lambda v: v.id)` 결정적 정렬이 단일 conflict 케이스로만 검증. 다중 시 결정성 보장 회귀 권장.
- **Obs5 — field diff nested 미지원**. `_payload_diff`가 1-depth 평면 비교만. character{name,observation}·event·open_question payload가 평면이라 현재 OK. 향후 nested payload 도입 시 재귀 확장 필요(이 slice 범위 밖).

## Verdict

**PASS (조건 없음).**

적대적·독립 재검증 결과:
- 계약(SoT v1.6.64·브리프 D1~D5) ↔ 구현 ↔ 테스트 정합. read-only 경계 준수(write 발생 없음).
- list(needs_review 통합 + candidate별 open conflict 중첩 + 직접 승격 억제)·detail(payload + source pointer + matched canonical + 결정적 field diff)·status=missing(가짜 pointer 회피 + cross-project 격리)·404 경계(cross-project/needs_review 아님/confirmed·reconciled) 전부 구현·검증.
- 의존 메서드 5종 실재·signature 일치(추측 아닌 원문 확인). 특히 `get_source_ref` NotFound raise + project_id 스코핑, `SourceRef.quote` 존재 확인.
- **전체 suite 771/48/99/12.25s/exit 0 독립 재현**(작업 AI 보고와 정확히 일치 — 이번엔 명시적 green 보고).
- 작업 AI가 테스트 중복 수집 버그(775 잘못 카운트)를 스스로 포착·교정한 정직성 확인.
- `git diff --check` clean.

비차단 관찰 5건은 회귀 보강 권장(public envelope/resolved 경로 등) 또는 향후 확장 대상이며 합격 조건이 아님. **Obs1(resolved source ref 경로)·Obs2(direct 승격 억제)가 보강 가치가 가장 큼** — c-2 이후 검증에서 Obs2/Obs4를 회귀로 보강한 선례(`HANDOFF` "독립 감사 Obs2/Obs4 HTTP 보강")와 동일한 리듬으로 자연스럽게 닫을 수 있음.

## Outstanding items

- **작업 미커밋**: 본 slice는 working tree에만(`a74c4c7` v1.6.63 위). 오너 커밋 승인 대기.
- **Obs1~4 회귀 보강**: 특히 Obs1(resolved source ref envelope)·Obs2(direct 승격 inbox 억제). 후속 보강 권장.
- **Phase 6 UI 잔여(이 slice 범위 밖)**: 부분 승인/부분 retry 정책·candidate edit/version 정책·Gate finding 영속화 및 inbox additive 통합·frontend(framework 미확정 보류).
- **이후**: Phase 5 Writing AI·Phase 7 Conversational Authoring(HANDOFF Next Tasks 추적).

## Reproduction

```bash
# 전체 suite
timeout 200 python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# 기대: 771 passed, 48 skipped, 99 subtests (약 12초)

# 이 slice 회귀
python3 -m pytest -q tests/test_analysis_apply_api.py::ReviewInboxApiTest
# 기대: 4 passed
python3 -m pytest -q tests/test_analysis_apply_api.py
# 기대: 22 passed (작업 AI "focused API 22" = 파일 전체)

# route 등록 + envelope (app introspection)
python3 -c "import services.application.app.main as m; app=m.create_app(); \
  print(sorted(p for p in app.openapi()['paths'] if 'review-inbox' in p))"
# 기대: ['/projects/{project_id}/analysis/review-inbox',
#        '/projects/{project_id}/analysis/review-inbox/{candidate_id}']

# 의존 메서드 실재 + source ref cross-project 격리
grep -n "def get_source_ref" services/application/app/core_sot/service.py  # :407 (project_id 버전)
sed -n '407,411p' services/application/app/core_sot/service.py             # NotFound raise + project_id check
sed -n '68,76p' services/application/app/core_sot/models.py                # SourceRef (quote 포함)

# 서식
git diff --check   # exit 0
```
