# 검증 기록 — 비동기 생성 + 결과 패드 슬라이스 증분 1 (D2=A + D7, scratch tier 패드 준비)

## Subject metadata

- **날짜**: 2026-07-21
- **요청자**: 오너 ("작업 AI 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? 증분 1 완료")
- **검증자**: 독립 검증 AI (Claude)
- **대상 슬라이스/아티팩트**: 비동기 생성 + 결과 패드 슬라이스 **증분 1** — scratch tier 패드 준비. 구현 내용: D2=A(accept 정리 draft 전체 → 채택 항목 단위), D7(scratch `version_id` additive nullable seam). SoT v1.7.24 → **v1.7.25**.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.25 (변경입항 line 36, §scratch 계약 line 262·265·267), 브리프 `docs/plans/async-generation-pad-decisions.md`(D1~D7 확정 2026-07-20, "구현 시 필수 사항"·검증 H1~H3 반영).
- **작업 출처**: working tree, **uncommitted**(커밋 미지시). `git diff --stat` = 9 files, +201/-32.

## Scope

정본 계약(SoT v1.7.25 해당 조항 + 버전로그)·브리프 적합성(D2=A/D7 + "구현 시 필수 사항")·구현 코드(`scratch.py`·`scratch_mongo.py`·`main.py` generate/accept/serialize/DELETE 경로)·회귀 테스트(`test_writing_scratch.py`·`test_writing_scratch_mongo.py`, 양방향 가드)·프론트엔드 타입 미러 + `gen:api` byte-identical·전체 suite green bar 재도출·`git diff --check`·변경 9파일 추적성. **비동기 실행 자체(job 테이블·worker LLM 루프·2048/4096 분기)와 §261 용도 문구 확장은 증분 2 범위**이므로 이번 검증 대상이 아니다(단 지연의 정당성은 별도 검토).

## Methodology

- 계약 스코핑 우선: 브리프 전문 + SoT v1.7.25 변경입항/§scratch 조항을 먼저 읽고 boundary matrix 구성 후 코드 대조(CLAUDE.md §5 "scope the contract read before opening it").
- `git diff --stat`·`git diff --check`·`git diff <file>` 로 9파일 전부 회수.
- 심볼 직접 확인: `WritingAcceptRequest.request_id`(main.py:1384-1385), `ContextPositionBody.version_id`(main.py:1281-1283), `_clear_scratch_for_saved_accept` 호출 지점(main.py:3706/3748/3764), accept.py의 scratch 비관여.
- 패턴 스윕(CLAUDE.md §4): `clear_draft`/`clear_accepted_item`/`delete_for_draft`/`delete_for_request` 전 호출처 grep → whole-draft 정리가 version-save 경로에 잔존하는지·이중 정리 여부 확인.
- 테스트 재실행(독립 green bar 재도출):
  - backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`
  - 집중: `python3 -m pytest tests/test_writing_scratch.py tests/test_writing_scratch_mongo.py -q -p no:cacheprovider`
  - frontend: `npx tsc --noEmit` + `npx vitest run` + `npm run gen:api`(이후 `git diff openapi.json src/api/schema.d.ts` 로 byte-identical 확인).

## Findings

### 1. 정본 계약 (SoT v1.7.25)

- **§265 accept 정리 조항(line 265)**: "정본 version이 저장된 accept는 그 accept의 `request_id`와 일치하는 scratch 항목만 정리한다(async-pad D2=A, v1.7.25)" — granularity를 **문구로 명시**(검증 H2 결함 해소: v1.7.20 승격 당시 whole-draft 의미가 rationale·구현에만 있고 문구에 없던 정밀도 결함). 200/502 양쪽 정리·비-PASS 비정리·대응 없으면 no-op·sibling 보존 전부 문구에 잠김. ✓
- **§267 schema(line 267)**: `version_id` nullable seam 추가(`intent`와 동형), "기존 레코드는 두 필드를 None으로 읽는다(마이그레이션 불요)". ✓
- **§262 목적 문구(line 262)**: **"복구 전용 low-stakes tier" 유지** — 용도 확장("복구 + 비동기 결과 보관")은 증분 2로 지연됨(변경입항·HANDOFF·work_log에 명시). §265 rationale이 "비동기 결과 패드가 재사용할 기반이다"를 인용하므로 §262와의 사소한 긴장 존재 → **Issues/H-1**.
- **버전로그(line 36) + 헤더(line 4)**: v1.7.24 → v1.7.25, 변경 내용·근거·검증 회귀 건수 기록 정확. ✓

### 2. 브리프 적합성

- **D2=A**(Owner decisions line 117): accept는 채택 항목만 삭제, `request_id` 대응, 대응 없으면 no-op. 구현 일치. 연결 수단 H1 확인 — `WritingAcceptRequest.request_id: str` 필수(main.py:1385), accept 서비스가 candidate 일치 검증(브리프 인용 `accept.py:227`). 신규 식별자 불요. ✓
- **D7**(Owner decisions line 122): scratch `version_id` 신설 + SoT schema 갱신. 구현 일치. ✓
- **"구현 시 필수 사항"**(브리프 line 124-129): (1) 용도 확장 — **지연(증분 2)**; (2) 정리 granularity 문구 못박기(H2) — **완료**; 기존 whole-draft 단정 회귀 갱신 — **완료**(`test_partial_analysis_failure_still_clears_*` 등 3건이 per-item+sibling 보존으로 재작성). 상한 상호작용·worker LLM은 증분 2/3. 지연은 투명하게 문서화됨(아래 Decisions 평가).

### 3. 구현 — `services/application/app/writing/scratch.py`

- `ScratchCandidate.version_id: str | None = None`(scratch.py:46-49) — `intent: str | None = None`과 **동형 additive seam**. ✓
- `WritingScratchRepository.delete_for_request` Protocol 추가(scratch.py:60-62) + `InMemoryWritingScratchRepository.delete_for_request`(scratch.py:92-102, 3키 필터). ✓
- `WritingScratchService.save(..., version_id=None)`(scratch.py:131-146) + `clear_accepted_item(...)`(scratch.py:161-168, `delete_for_request` 위임). ✓
- 모듈 docstring이 per-item 정리로 갱신되고 v1.7.20→v1.7.25 ratify 명시. ✓

### 4. 구현 — `services/application/app/writing/scratch_mongo.py`

- `MongoWritingScratchRepository.delete_for_request`(scratch_mongo.py:44-54, `delete_many` 3키 필터 → `deleted_count`). ✓
- `_doc`(scratch_mongo.py:74)·`_entry`(scratch_mongo.py:90)가 `version_id`를 write/read하되 `_entry`는 `doc.get("version_id")` — **legacy doc 안전**(필드 없으면 None). ✓
- 메모리 `mongo-adapter-needs-fake-collection-test` 선례 준수: 기존 fake-collection(`_Client.docs`) round-trip suite가 `delete_for_request` 3키 격리 + legacy version_id read를 모두 커버(이전 B-1 패턴 재발 없음). ✓

### 5. 구현 — `services/application/app/main.py`

- **generate 저장(main.py:3133-3146)**: `if body.current_position is not None:` 가드 안에서 `version_id=body.current_position.version_id` 추가(3143). `body.current_position` None 시 save 자체 스킵(브리프 "current_position 없으면 저장하지 않는다" 충족). ✓
- **accept 정리(`_clear_scratch_for_saved_accept`, main.py:3706-3726)**: `clear_draft` → `clear_accepted_item(project_id, cleanup_draft_id, body.request_id)`(3723-3724)로 교체. `body.request_id`는 `WritingAcceptRequest` 필수 필드. ✓
- **호출 지점**: 3748(502 partial, `WritingAcceptAnalysisError` — version 저장됨, return 직전)·3764(200, `if result.accepted:`) **두 saved 경로에서만**. non-PASS(`accepted=false`)는 3763 조건문으로 타지 않음. ✓ 계약(200/502 정리·비-PASS 비정리)과 정확 일치.
- **serialize(main.py:3787)**: `_writing_scratch_payload`에 `version_id` 추가. list 키셋 회귀가 잠금(test_writing_scratch.py:328). ✓
- **accept.py 비관여**: `grep scratch|clear services/application/app/writing/accept.py` → 출력 없음. scratch 정리는 오직 main.py 핸들러. ✓ 브리프 설계("패드는 accept를 타지 않는다"와 일치·관심사 분리).

### 6. 회귀 테스트 — 양방향 가드

boundary matrix(§265 모든 분기) ↔ 테스트 매핑, 양방향(under-strict + over-strict) 검증:

| §265 분기 | 테스트 | under-strict | over-strict |
|---|---|---|---|
| 200 accept → 채택 항목만 삭제 | `test_saved_accept_clears_only_the_accepted_item` | 정리 안 하면 wr1 잔존 → fail | whole-draft复歸면 sibling 사망 → fail |
| 502 partial → 채택 항목만 삭제 | `test_partial_analysis_failure_still_clears_the_accepted_item` | 502 return 아래로 cleanup 이동 시 fail | sibling 보존 단정 |
| 비-PASS → 정리 안 함 | `test_non_pass_accept_keeps_scratch`(len==2) | — | non-PASS 경로 잘못 정리 시 fail |
| 대응 없으면 no-op | `test_clear_accepted_item_no_match_is_a_no_op`(0 반환, 1 잔존) | — | no-match 과삭제 시 fail |
| sibling 보존(service) | `test_clear_accepted_item_removes_only_the_matching_request` | wr1 잔존 시 fail | wr2 삭제 시 fail |
| 3키 격리(mongo) | `test_delete_for_request_removes_only_the_matching_item` | — | 타 draft/타 request 과삭제 시 fail |
| version_id 저장 | `test_generate_with_position_persists_scratch`(`version_id=="v1"`) | save 인자 누락 시 None → fail | — |
| version_id round-trip(mongo) | `test_add_and_list_round_trip_newest_first`(`version_id="v9"`) | _doc↔_entry drift 시 fail | — |
| legacy version_id → None | `test_legacy_doc_without_version_id_reads_none` | — | 필수화 시 legacy load fail |
| list 키셋 | `test_*`(version_id 키 포함) | serialize 누락 시 fail | — |
| best-effort 격리 | `_ExplodingScratch.clear_accepted_item` raise + accept 성공 | — | — |

- 빈 셀 없음: §265가 요구하는 모든 분기(should fire 2 + should NOT fire 4)가 명명된 회귀에 매핑되고, 주 분기는 양방향 가드. ✓
- best-effort: `_ExplodingScratch`에 `clear_accepted_item` raise 추가(accept가 이제 이 메서드를 호출하므로 stub 갱신 필요 — 누락 없음). ✓

### 7. 프론트엔드 + gen:api

- `frontend/src/api/client.ts` `ScratchCandidate.version_id: string | null`(client.ts:354-356, "mirroring `_writing_scratch_payload`" 주석). backend serialize(항상 키 존재, 값은 null 가능)과 일치. ✓
- `npx tsc --noEmit` → exit 0(clean). ✓
- `npx vitest run` → **162 passed / 11 files**(무변, 로직 변화 없음). ✓
- `npm run gen:api` 후 `git diff openapi.json src/api/schema.d.ts` → **diff 없음(byte-identical)**. scratch endpoint가 `response_model` 없이 plain dict을 반환하므로 신규 version_id 키가 OpenAPI에 반영되지 않는다는 주장과 일치. ✓

### 8. 전체 suite + 위생

- backend `pytest --ignore=tests/test_memory_mongo.py` → **1257 passed / 73 skipped / 326 subtests**(작업자 주장과 정확 일치, 독립 재도출). ✓
- `git diff --check` → clean(공백 오류 없음). ✓
- 변경 9파일 전부 D2=A/D7 증분에 추적됨(orphans 없음). ✓
- **LLM 미사용 검증**: 이 증분은 기계적 계약 개정(스키마 필드·삭제 범위·직렬화 키)이며 gateway/LLM 호출 추가 없음 — "비동기 실행·worker LLM 루프는 증분 2" 주장과 일치. 코드상 신규 provider/gateway import·호출 부재 확인. ✓

## Issues / Risks

### Blocking (계약 의무)

**없음.** 동작 결함·추적 안 된 분기·누락된 over-strict 가드·내부 계약 **규칙** 모순 어느 것도 발견되지 않았다. §265 모든 분기가 명명된 양방향 회귀에 매핑됐고, accept.py는 scratch를 타지 않으며, `clear_draft`는 DELETE(whole-draft)에만·`clear_accepted_item`은 accept(per-item)에만 쓰인다.

### Hardening recommendations (비차단)

- **H-1(계약 문구 일관성, doc-only)**: §262(line 262)는 여전히 scratch를 "**복구 전용** low-stakes tier"로 서술하지만, §265(line 265)의 per-item 정리 rationale은 "**비동기 결과 패드가 재사용할 기반이다**"를 인용한다. 지연은 변경입항·HANDOFF·work_log에 투명하게 기록됐으나, §262 자체에는 패드 용도에 대한 언급이 없어 독자가 §262(복구 전용)와 §265(pad rationale) 사이에서 표면적 긴장을感知할 수 있다. 둘이 **규칙** 수준에서 모순되는 것은 아니라(§262는 용도 서술, §265는 동작+사전적 근거) blocking 아니다. 권고: §262에 한 줄 전방 포인터 추가(예 "비동기 결과 보관 용도는 증분 2에서 추가되며 §265의 per-item 정리가 그 기반") — 존재하지 않는 동작을 서술하지 않으면서 계약이 자체 모순으로 읽히지 않게 한다. 코드/테스트 변화 없음.
- **H-2(문구 정밀도, doc-only)**: §267 + 변경입항은 `version_id`가 `current_position.version_id`에서 오며 "**(없으면 None)**"이라 한다. 그러나 `ContextPositionBody.version_id`는 **필수 `str`**(main.py:1283)이므로, HTTP generate 경로에서 `current_position`이 존재하면 version_id는 항상 문자열이다. "(없으면 None)"은 실제로는 (a) D7 이전 legacy 레코드·(b) version_id 인자를 생략한 직접 서비스 호출자를 기술하며, HTTP 경로가 아니다. 권고: HTTP generate가 None version_id를 저장할 수 있다는 인상을 피하도록 "(legacy 레코드·직접 호출자는 None)"으로 한정. 경미.
- **(참고, 조치 불요)** HANDOFF/work_log가 "§261/§264/§267" clause 번호를 인용하는데 실제 SoT 줄 번호는 262/265/267 — clause vs 줄 번호 표기 차이. 인용 내용은 정확하므로 변경 불필요.

## Verdict

**합격 (PASS, 조건 없음).**

근거(가장 실질적 이유):
1. **동작이 정확하고 완전히 잠겼다** — D2=A per-item accept 정리·D7 additive `version_id` 모두 구현→SoT(§265/§267)→양방향 회귀(in-memory + mongo + HTTP)가 일치하며, §265의 모든 분기(should fire 2 + should NOT fire 4)에 빈 셀 없이 명명된 테스트가 매핑됐다.
2. **정본 계약 무변 경계 존중** — `source_snapshots`/`draft_versions`·명시 save·stale guard·accept 원자성 무변(브리프 핵심 설계). accept.py는 scratch를 타지 않고, `clear_draft`는 DELETE에만·`clear_accepted_item`은 accept에만 쓰인다(패턴 스윝 확인).
3. **green bar 독립 재도출** — backend 1257/73/326, frontend 162/11, tsc clean, `gen:api` byte-identical, `git diff --check` clean. 전부 작업자 주장과 정확 일치.
4. **지연은 투명하고 정당하다** — §261 용도 문구 확장은 worker가 실제로 결과를 scratch에 쓰기 전(증분 2)으로 미뤘고, 근거("SoT는 현재 사실을 반영")가 타당하며 3곳에 문서화됐다. 이는 문서 순서화 판단이지 누락된 lock이 아니다.

H-1/H-2는 doc-only hardening이며 합격을 가리지 않는다. 다만 H-1(§262 전방 포인터)은 이 증분이 건드린 §265 rationale과 같은 조항 묶음에 솄하므로, 증분 1 커밋에 함께 1줄 추가하면 깔끔하다(선택).

## Outstanding items

- **증분 1 미커밋**: 작업 tree에 uncommitted(커밋 미지시). green bar·`diff --check` clean이므로 커밋 가능 상태.
- **증분 2 추적 항목(이미 HANDOFF Next Tasks에 있음)**: (a) §261/§262 scratch 용도 문구를 "복구 + 비동기 결과 보관"으로 확장(worker가 async 결과를 scratch에 실제로 쓰는 시점); (b) Analysis식 생성 job collection + worker 생성 job claim 루프(worker 최초 LLM/gateway 호출 — 접근·타임아웃·실패 분류 신규); (c) generate 2048/4096 비동기 분기(1024 동기 유지). 색인 sync outbox는 건드리지 않음(H3).
- 권고: H-1(§262 전방 포인터)을 증분 1 커밋에 포함하면 §265와의 긴장이 같은 슬라이스에서 닫힌다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# 1. diff 범위 + 위생
git diff --stat
git diff --check
# 2. 계약-코드 대조 핵심 심볼
sed -n '3706,3726p;3744,3764p' services/application/app/main.py   # _clear_scratch_for_saved_accept + 호출 지점
sed -n '3133,3146p' services/application/app/main.py             # generate version_id 저장
sed -n '1281,1283p;1384,1385p' services/application/app/main.py  # ContextPositionBody.version_id / WritingAcceptRequest.request_id
grep -rn "clear_draft\|clear_accepted_item\|delete_for_request" services/application/app/main.py
# 3. 집중 회귀
python3 -m pytest tests/test_writing_scratch.py tests/test_writing_scratch_mongo.py -q -p no:cacheprovider
# 4. 전체 suite
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider   # 1257 passed/73 skipped/326 subtests
# 5. 프론트엔드 + gen:api
cd frontend && npx tsc --noEmit && npx vitest run && npm run gen:api && git diff --stat openapi.json src/api/schema.d.ts   # 162 passed, tsc clean, gen:api diff 없음
```
