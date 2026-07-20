# Verification — 미채택 Writing candidate 복구 안전망 (scratch)

> **Closure note (2026-07-20, 구현자 후속 — 검증자 판정 이후 추가)**
> 본 기록의 판정은 **조건부 합격(조건: B-1)**이었다. 아래는 그 조건과 hardening에 대한 대응 결과이며, **원 검증 본문은 수정하지 않았다**(감사 이력 보존).
>
> - **B-1 (blocking) — 닫힘**: `tests/test_writing_scratch_mongo.py` 추가(6건). 검증자가 지목한 선례(`test_writing_loop_audit_mongo.py`)의 `_Collection`/`_Cursor` fake 패턴을 복제하되, scratch가 **mutable**이라는 차이를 반영해 `delete_many`(+`$in`) 경로까지 fake에 구현했다. **mutation 6/6 bite로 실효성 실증**: `candidate_text`→`candidiate_text` 오타, `_doc`에서 `intent` 누락, newest-first→oldest-first sort 반전, index name 변경, empty-ids 가드 제거, `delete_for_draft`가 `draft_id` 무시(프로젝트 전체 wipe) — 각각 해당 테스트가 실패했다.
> - **H-2 — (a)로 잠금**: cleanup을 `_clear_scratch_for_saved_accept()` 헬퍼로 뽑아 **502 partial 경로에서도 호출**하도록 코드를 정합화하고(브리프 rationale과 일치), 브리프 "잠정 보존/만료 정책"에 세 분기(200 정리 / 502 partial 정리 / 비-PASS 미정리)를 명시했다. 회귀 `test_partial_analysis_failure_still_clears_scratch` 추가, mutation bite 확인.
> - **H-1/H-4 — 선제 추가**: `_ExplodingScratch`(save/clear 모두 raise)로 generate·accept가 여전히 200인지 pin, generate 실패(400) 시 scratch 0건 pin. 검증자 권고대로 **오너 SoT 승격 전에** 넣어 승격 순간 empty cell이 되지 않게 했다. mutation bite 확인(격리 제거 시 각각 실패).
> - **H-3 — 근거 기록**: 브리프 Follow-up에 `next_unit` 제외 근거(generate 시점 부재 → 항상 None 필드 선점은 Simplicity First 역행, Phase 7에서 `intent`와 동반 추가)를 명시했다.
> - **재실행**: backend **1222 passed / 70 skipped / 297 subtests**(+10: Mongo 6 + H-1/H-2/H-4 4), frontend 159 passed / 11 files(무변), tsc clean.
> - **판정 갱신**: B-1 closure로 **합격(pass)** 조건 충족. 최종 재검증은 오너/검증자 몫이다.

## Subject metadata

- **Date**: 2026-07-20
- **Requester**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **Verifier**: Claude (독립 검증, 구현 미관여)
- **Target slice**: 미채택 Writing candidate 영속 — `generate` 안전망 저장 + `accept` 정리 + `GET/DELETE .../writing/scratch` + `ScratchRecovery` 프론트 배너
- **Canonical spec reference**: [`docs/plans/unaccepted-candidate-persistence-decisions.md`](../../plans/unaccepted-candidate-persistence-decisions.md) (상태: `결정 확정 (2026-07-20) — D0=B / D1=B / D2=A, 구현 착수`)
- **Source of work being verified**: working tree, uncommitted (`git status` — M main.py·client.ts·schema.d.ts·DraftEditor.tsx·DraftEditor.test.tsx·App.test.tsx·HANDOFF.md·CHANGELOG.md·브리프, ?? scratch.py·scratch_mongo.py·test_writing_scratch.py·ScratchRecovery.tsx·ScratchRecovery.test.tsx·work_log.md)
- **작업 AI self-claim**: backend 1212 passed/70 skipped(+11), frontend 159 passed/11 files(+4), tsc clean, build OK, gen:api scratch path 2개 additive, in-process smoke seed→list→accept→cleanup 왕복 확인

## Scope

계약 스코프는 브리프에서 다음 anchor로 한정했다(관련 없는 Phase 7/W4/export는 제외):

1. **브리프 본문** — D0/D1/D2 확정절, "잠정 보존/만료 정책" 절(키·append·cap 20·accept 즉시 삭제·명시 버리기·시간 만료 없음·best-effort 격리), Follow-up(schema seam), Deferred.
2. **구현 코드** — `services/application/app/writing/scratch.py`, `scratch_mongo.py`, `main.py`의 generate/accept 훅 + HTTP 2 endpoint.
3. **회귀 테스트** — `tests/test_writing_scratch.py`(11건) + `frontend/src/writing/ScratchRecovery.test.tsx`(4건).
4. **공개 envelope** — `schema.d.ts`(gen:api 결과), `api/client.ts` hand-declared 타입, `HANDOFF.md`·`CHANGELOG.md`·`work_log.md`.

## Methodology

독립 재유도 — 작업 AI의 수치를 신뢰하지 않고 직접 재실행. 인용된 모든 명령은 아래 재현 절에서 재실행 가능.

1. **계약 읽기**: 브리프 전문 + work_log 독독 → boundary matrix 구축(아래 Findings 첫 표).
2. **코드 감사**: `scratch.py`·`scratch_mongo.py` 전문, `main.py` generate(`2941-3026`)/accept(`3537-3640`) 핸들러 전문, 프론트 `ScratchRecovery.tsx`·`DraftEditor.tsx` diff.
3. **테스트 코드 감사**: 11+4건 각 assertion이 계약을 pin 하는지(under-strict/over-strict 양방향), parametrize 경계값 coverage.
4. **재실행**:
   - `python3 -m pytest tests/test_writing_scratch.py -v -p no:cacheprovider`
   - `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` (전체 backend)
   - `cd frontend && npx vitest run` (전체 frontend)
   - `cd frontend && npx tsc --noEmit && npm run build`
   - `cd frontend && cp src/api/schema.d.ts /tmp/schema.before.d.ts && npm run gen:api && diff -u /tmp/schema.before.d.ts src/api/schema.d.ts` (gen:api idempotency / drift)
5. **선례 대조**: `tests/test_writing_loop_audit_mongo.py`(작업 AI가 인용한 loop_audit 선례)의 Mongo 어댑터 검증 방식과 scratch_mongo의 coverage 차이.

## Findings

### Boundary matrix (canonical — owner-confirmed D0=B/D1=B/D2=A + 브리프 구조 요구)

| # | 계약 요구 분기 | 기대 | 회귀 테스트 | 상태 |
|---|---|---|---|---|
| 1 | generate 성공 + `current_position` → scratch 저장 | fire | `test_generate_with_position_persists_scratch` | ✅ |
| 2 | generate 성공, `current_position` 없음 → 미저장 | NOT fire | `test_generate_without_position_does_not_persist` | ✅ |
| 3 | accept `result.accepted=true` → draft scratch 정리 | fire | `test_saved_accept_clears_scratch` | ✅ |
| 4 | accept `result.accepted=false`(REVISE) → 정리 안 함 | NOT fire | `test_non_pass_accept_keeps_scratch` | ✅ |
| 5 | 명시 버리기(DELETE) → 전체 삭제 + count | fire | `test_discard_clears_and_reports_count` | ✅ |
| 6 | UI "버리기" confirm 거부 → DELETE 미발생 | NOT fire | `ScratchRecovery: does not discard when declined` | ✅ |
| 7 | 미존재 project GET/DELETE → 404 | fire | `test_list_and_discard_unknown_project_are_404` | ✅ |
| 8 | per-draft cap → **오래된 것**부터 삭제, 최신 보존 | fire(정확히 오래된 것) | `test_history_is_capped_dropping_oldest`(cap=3, 4건→초안0 삭제 단언) | ✅ |
| 9 | `(project_id, draft_id)` 격리 | — | `test_isolation_by_project_and_draft` | ✅ |
| 10 | HTTP list envelope exact-key set | — | `test_list_returns_items_newest_first_with_keys`(`set(first)=={9키}`) | ✅ |
| 11 | Core SOT(version/snapshot) 무오염 | 구조적 | 별도 collection·별도 repo class — 직접 assertion은 없으나 구조적으로 보장 | ~ |
| 12 | **Mongo 어댑터 `_doc`↔`_entry` field round-trip** | fire | **(없음)** | ❌ |
| 13 | **best-effort: scratch 실패 → 본 흐름 영향 없음** | NOT fail | **(없음)** | ❌(잠정 정책) |
| 14 | **accept 502 partial(saved=True) → 정리?** | 모호 | **(없음)**, 코드도 미정리 | ❌(잠정/계약 인접) |

행 1-10, 11: canonical 계약 분기는 **모두 양방향 guard와 함께 pin** 되어 있다. 행 12-14가 이 검증의 핵심 발견.

### 코드 감산 — 훅 배치 정합성 (positive)

- **generate 훅**(`main.py:3009-3025`): 모든 실패 경로가 `except`에서 `HTTPException`으로 빠지고 성공 경로는 단일 `return _writing_candidate_payload(candidate)`(3026)로 수렴 → scratch save는 이 단일 return 직전. **성공했는데 안전망이 안 켜지는 조기 return 빈칸 없음**. `if body.current_position is not None`(3013)로 키 없음 가드. bare `except Exception: pass`(3024)로 best-effort.
- **accept 훅**(`main.py:3621-3629`): `if result.accepted:` 가드 위에 `current_position.draft_id` 우선·`body.draft_id` fallback 키 정합성. generate 저장 키(`current_position.draft_id`)와 동일 키로 정리.
- **trim**(`scratch.py:129-135`): `list_for_draft`(newest-first)의 tail을 delete → 오래된 것 삭제. in-memory sort 키 `(created_at, id) reverse`(`scratch.py:67-72`)와 Mongo sort `(created_at DESC, _id DESC)`(`scratch_mongo.py:34-36`)가 동일 의미로 정렬. cap=3에서 4건 저장 시 `초안0` 삭제를 단언으로 pin.

### 재실행 — 수치 재현 (작업 AI self-claim과 정확 일치)

- backend scratch 단독: **11 passed** (`tests/test_writing_scratch.py`)
- backend 전체(`--ignore=tests/test_memory_mongo.py`): **1212 passed / 70 skipped / 297 subtests** — work_log "1212/70/297"과 정확 일치
- frontend 전체(`npx vitest run`): **159 passed / 11 files**(ScratchRecovery 4건 포함) — work_log "159/11"과 정확 일치
- `npx tsc --noEmit`: clean. `npm run build`: 101 modules, CSS 18.48 / JS 391.41 kB — work_log와 정확 일치
- `npm run gen:api` 재생성 후 `diff`: **NO_DRIFT** — committed `schema.d.ts`가 OpenAPI와 정합. additive 88줄(신규 path 1개 블록 + operation 2개), 기존 path 무변.

### 프론트 — 테스트 하네스 우회 감사 (positive)

`ScratchRecovery`가 편집기 마운트 시 fetch 1건을 추가해 `DraftEditor.test.tsx`의 순서 기반 `mockFetch`가 밀리는 것을, 두 파일 모두 `stubFetch` 래퍼로 `/writing/scratch` URL을 **기록된 mock 밖에서** 빈 목록 응답 처리(`DraftEditor.test.tsx` 5지점, `App.test.tsx` 1지점 — work_log "5곳+App 1건"과 일치). 기존 index/count 단언이 "편집기 자신의 요청만" 기술하도록 보존. ScratchRecovery 자체의 discard 동작은 독자 테스트 파일에서 proper mock으로 pin → 통합 지점은 "기존 흐름 안 깨뜨림"만 검증하는 구조로 타당.

## Issues / Risks

### Blocking (계약 의무) — 1건

**B-1. `MongoWritingScratchRepository` field round-trip 회귀가 없다 (cited 선례 대비 empty cell).**

- **사실**: `MongoWritingScratchRepository`(`scratch_mongo.py`)는 `_doc`→`_entry` 직렬화/역직렬화(`scratch_mongo.py:50-77`), index 생성(`19-22`), sort(`34-36`)을 갖지만, 이 어댑터를 직접 검증하는 테스트가 **표준 suite에 전혀 없다** — `grep -rn "MongoWritingScratch" tests/`가 0건. 11건 회귀는 전부 `InMemoryWritingScratchRepository` 경로. smoke도 in-process(in-memory)라 Mongo 경로를 관통하지 않는다.
- **왜 차단 후보인가**: (1) D2=A의 존재 이유 자체가 "정본 무변 + **서버 신뢰성** 확보"이며, 그 서버 신뢰성의 실체가 `writing_drafts_scratch` Mongo collection이다. in-memory는 dev/no-infra fallback일 뿐 canonical durable 경로가 아니다. (2) 작업 AI가 `scratch_mongo.py` 주석·work_log에서 "loop_audit 선례를 따른다"고 명시했으나, **그 선례(`tests/test_writing_loop_audit_mongo.py`)는 fake collection(`_Collection`/`_Cursor`)으로 Mongo 어댑터의 `_doc`↔`_run` field drift·index·append-only·newest-first를 표준 suite에서 pin 하는 전용 테스트를 갖는다**. 즉 인용한 선례의 핵심 검증 관행을 복제하지 않았다. (3) field-name 오타(`candidate_text`↔`candidiate_text`)·`intent` 누락·sort 방향 오류가 있어도 in-memory 경로와 HTTP 테스트(in-memory 기반)로는 잡히지 않는다 — durable 모드(`CORE_SOT_MONGO_URI` 설정 시)에서만 폭발하고, 그때는 복구가 조용히 실패한다.
- **영향 범위**: 낙관적이지 않다 — 정확히 "잃지 않기"라는 슬라이스의 가치가 durable 모드에서 검증 없이 놓여 있다.
- **권고**: `test_writing_loop_audit_mongo.py`의 `_Collection`/`_Cursor` 패턴을 복제한 `tests/test_writing_scratch_mongo.py` 추가 — `_doc`↔`_entry` field-for-field round-trip(신규 field 추가 시 drift 감지), 안정적 index name, newest-first sort, mutable delete(delete_for_draft/delete_ids)를 pin. 이 선례 테스트 하나로 B-1은 닫힌다.

> **참고**: 작업 AI가 발견을 숨기지는 않았다 — 다만 Mongo coverage 누락을 명시적으로 인지/공개한 흔적이 work_log·브리프에 없다. 따라서 이것은 "기록된 한계"가 아니라 "미포착 empty cell"이며, 위 B-1 권고로 닫아야 conditional → pass로 승격 가능하다.

### Hardening recommendations (non-blocking)

**H-1. best-effort 격리가 회귀로 pin 되어 있지 않다 (잠정 정책 → SoT 승격 시 계약 lock으로 승격됨).**

- **사실**: 브리프 "잠정 보존/만료 정책" §best-effort("scratch 쓰기·삭제 실패는 본 흐름을 실패시키지 않는다")는 `try/except Exception: pass`(`main.py:3014-3025`, `3626-3629`)로 구현됐으나, save/clear_draft가 raise하는 repo를 주입해 generate/accept가 여전히 200을 반환하는지를 단언하는 테스트가 없다.
- **왜 non-blocking**: 해당 절은 브리프가 명시적으로 **"정본 계약이 아니며, 나중에 오너가 SoT로 승격·확정해야 한다"**고 규정한 잠정 정책이다. CLAUDE.md의 "empty cell = blocking" 규칙은 canonical 계약 의무에만 적용되므로, 현 시점에서는 hardening이다.
- **단, ★ 다음 작업(오너 SoT 승격) 직후 상태가 바뀐다**: 보존/만료 정책이 SoT로 오르는 순간 이 best-effort 분기는 canonical "should NOT fire"(scratch 실패 → 본 흐름 실패 아님)이 되고, 그때 regression이 없으면 empty cell이 된다. 승격 전에 미리 추가해 두는 것을 권장.

**H-2. accept 502 partial(saved=True, analysis 실패) 경로가 scratch를 정리하지 않는다 — 브리프 rationale과 충돌, disclosure가 work_log에만 있다.**

- **사실**: `WritingAcceptAnalysisError` catch가 `JSONResponse(502, {accepted: True, saved: ...})`로 **return**(`main.py:3600-3607`)하고, 이 return은 cleanup 훅(`3621-3629`) **직전**이다. 따라서 version은 저장됐지만 analysis가 실패한 502 partial에서는 scratch가 남는다.
- **왜 의미 있다**: 브리프 rationale은 "사용자가 정본을 확정했으므로 미채택 이력은 무의미 → accept 시 즉시 삭제"다. 502 partial은 `saved`가 존재(=정본 확정)하므로 rationale상 **정리 대상**이나, 코드는 정리하지 않는다 → rationale↔코드 불일치. 작업 AI는 work_log "알려진 한계(비차단)"로 공개했으나 **브리프 자체에는 반영되지 않았다** → 계약 문서 수준에서는 여전히 unlocked.
- **권고(둘 중 하나)**: (a) cleanup 훅을 두 accept-success return 모두를 덮도록 502 partial return 직전으로 이동(가장 적은 코드, rationale과 정합), 또는 (b) 브리프 "잠정 보존/만료 정책"에 "502 partial은 정리 제외"를 명시하고 해당 동작을 regression으로 pin. 어느 쪽이든 **잠금 없이 남기지 않는다**(CLAUDE.md "picking silently leaves the boundary unlocked").
- **영향**: 낮음(상한 20 + 다음 성공 accept에서 수렴). 작업 AI 평가와 일치. 단 UX 미세 부조화(정본 저장됐는데 복구 배너 잔존)는 (a)로 소거 가능.

**H-3. scratch schema에 `next_unit`이 없다 (브리프 Follow-up 명시 항목).**

- **사실**: 브리프 Follow-up이 "candidate 식별(`request_id`/`intent`/`next_unit`)을 그대로 싣되"라고 명시하나, `ScratchCandidate`(`scratch.py:31-45`)는 `request_id`·`intent`(nullable)만 싣고 `next_unit`은 스키마에서 제외됐다. work_log는 "intent/next_unit은 generate 시점에 알 수 없다"고 한다.
- **왜 non-blocking**: `WritingCandidate`(`writing/models.py:189-208`)의 `next_unit`은 기본 `None`이고 generate 시점에 의미 있는 값이 없다 — 그래서 "항상 None인 field를 nullable로 추가"는 Simplicity First에 역행. work_log의 `intent` nullable seam 논리를 `next_unit`에까지 대칭 적용하지 않은 것은 방어 가능한 선택이다.
- **단, 계약 인접**: 브리프가 "식별자 3종"을 명시했으므로, Phase 7 `conversation_turn` 흡수 시 next_unit seam이 필요해지면 스키마 변경이 발생한다(Follow-up이 "스키마 변경 없이"를 목표로 했던 것과 어긋). 브리프 Follow-up에 next_unit 제외 근거를 한 줄 남겨 두면 이 정합성도 닫힌다.

**H-4. generate-failure → no-scratch 분기 미테스트 (구조 보장).**

- scratch save가 generate 실패를 처리하는 try/except **이후**에 있어, 실패 시 HTTPException 전파로 save 미실행이 구조적으로 보장된다. 회귀가 없어도 실질 위험은 낮으나, belt-and-suspenders로 "generate 400/502 시 scratch 0건" 단언을 추가하면 H-1과 함께 격리 축을 한 번에 pin.

## Verdict

**조건부 합격 (conditional pass)** — 조건: **B-1 closure**.

이유:
- Canonical 계약 분기(matrix 행 1-10)는 **전부 양방향 guard와 함께 회귀로 pin** 되어 있고, envelope(exact-key set)·gen:api drift·tsc/build·재실행 수치가 작업 AI self-claim과 **정확히 일치**한다. 슬라이스의 기능적 정확성과 scope discipline(Core SOT 무변·추측 field 최소화·잠정 정책의 비-canonical 명시)은 확인했다.
- **유일한 차단 조건 B-1**: D2=A의 존재 이유인 durable Mongo 경로의 직렬화 round-trip이 **cited 선례(`test_writing_loop_audit_mongo.py`)에도 불구하고 테스트 없다**. 이것은 "기능이 돌아간다"가 아니라 "durable 모드에서 복구가 조용히 실패할 수 있는 field drift가 잠금돼 있지 않다"다. 선례 테스트 1개 추가로 닫힌다.
- B-1을 닫으면 **합격**으로 승격. H-1~H-4는 잠정 정책/계약 인접 영역의 hardening으로, ★ 다음 작업(SoT 승격) 시점에 H-1·H-2는 자연히 canonical lock 후보가 되므로 그때까지 정리를 권한다.

"테스트 suite가 green이다" ≠ "계약이 요구하는 것을 suite가 검증한다". 본 검증은 B-1이 이 둘의 차이에 해당함을 명시한다.

## Outstanding items

- **미커밋**: 본 슬라이스 전체가 working tree(uncommitted). 오너 확인 후 커밋 예정이라 함.
- **B-1 미해결**: conditional pass 조건이 작업 AI에게 돌아감 — `tests/test_writing_scratch_mongo.py` 추가 후 재검증 필요.
- **★ 오너 액션 대기**: scratch 보존/만료 잠정 정책(per-draft 상한 20·accept 즉시 삭제·시간 만료 없음)의 SoT 승격. 승격 시 H-1(best-effort)·H-2(502 partial)가 canonical lock 후보로 승격되므로 regression 추가 권장.
- **H-2 회피 불가**: 502 partial scratch 동작은 (a)코드 이동 또는 (b)브리프 명시+회귀 중 하나로 명시적으로 잠가야 한다(work_log 공개만으로는 계약 문서가 unlocked 상태).

## Reproduction

```bash
# 1. backend scratch 회귀 (단독)
python3 -m pytest tests/test_writing_scratch.py -v -p no:cacheprovider

# 2. backend 전체 (작업 AI와 동일 명령)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
#   기대: 1212 passed, 70 skipped, 297 subtests

# 3. frontend 전체 + 타입 + 빌드
cd frontend
npx vitest run                    # 기대: 159 passed / 11 files
npx tsc --noEmit                  # 기대: clean
npm run build                     # 기대: 101 modules, JS 391.41 kB

# 4. gen:api drift (schema.d.ts가 OpenAPI와 정합인지)
cp src/api/schema.d.ts /tmp/before.d.ts
npm run gen:api
diff -u /tmp/before.d.ts src/api/schema.d.ts && echo NO_DRIFT

# 5. B-1 재현(선례 대조) — scratch Mongo 어댑터 coverage 부재 확인
cd ..
grep -rn "MongoWritingScratch" tests/           # 0건이어야 함(empty cell)
grep -rln "MongoWritingLoopAudit" tests/        # test_writing_loop_audit_mongo.py 존재(선례)

# 6. B-1 closure 후보 — 선례 테스트 패턴 확인
sed -n '1,60p' tests/test_writing_loop_audit_mongo.py   # _Collection/_Cursor fake pattern
```
