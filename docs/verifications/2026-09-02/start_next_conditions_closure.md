# 2026-09-02 독립 재검증 — start-next 검증 조건 4건 폐쇄 (24cb00a)

## Subject metadata

- 검증일: 2026-09-02 (2차)
- 요청자: 오너 ("보강한거 재검증해줘")
- 검증자: Claude Code (1차 기록 [`start_next_intent_preservation.md`](start_next_intent_preservation.md)와 동일 검증자, 구현자와는 별도 세션)
- 대상: `24cb00a` "Close start-next verifier conditions" (main, 작업 트리 clean)
- 정본 참조: `docs/system-contract-sot.md` v1.8.16 (무변 — 본 커밋은 계약이 아니라 검증 조건 폐쇄)
- 환경: 동일 호스트(python3.12·pydantic 2.12.5·fastapi 0.127.0)

## Scope

1차 조건부 판정의 조건 4건이 실제로 닫혔는지 — 각 조건을 폐쇄 **증거**(가드가 물어야 함)까지 확인한다. 상품 코드는 무변임을 전제로(아래 확인) 도메인 동작 재검은 생략하고, 잠금·생성물·문서 축만 본다.

## Methodology

아래 Reproduction. 핵심은 폐쇄의 증명 방향: 1차에서 무잠금을 입증한 변이 FA·FB를 **동일 diff로 재적용**해 이번엔 기명 셀이 재실패하는지 본다(변이 사전 `git status --short` 0줄 게이트 → 적용 → 재실패 → `git checkout --` → clean 확인, 루트 CWD에서).

## Findings

- **커밋 범위 확인**: `24cb00a`는 `README.md`·`schema.d.ts`·`tests/test_writing.py`·`tests/test_writing_generation_job_mongo.py`·work_log·HANDOFF만 고친다 — **상품 코드 0줄**. 따라서 1차의 전수 재구성(진행점 2590+꼬리 220 green, 유일 실패 docs 가드)은 그대로 이전되며, 본 재검은 델타 축만 보면 된다.
- **조건 ①(README 정본 표기)**: `README.md:106`이 **v1.8.16**, 잔존 v1.8.15 표기 0건. `tests/test_docs_indexes.py` → **13 passed, 282 subtests**(1차 red였던 `test_the_readme_names_the_current_contract_version` 포함 전부 green).
- **조건 ②(schema.d.ts 생성물)**: 검증자가 `npm run gen:api`를 재실행해 **트리 무차이** — 커밋된 schema.d.ts가 정본 OpenAPI와 일치한다(1차의 3곳 불일치: `NextUnitPayload` 미등재·응답 `next_unit` 선택/컴포넌트 오기·요청 `intent` `@default` 누락 — 전부 해소 확인).
- **조건 ③(400 경계 4분기)**: 신규 셀 `WritingGenerateApiTest::test_start_next_intent_binding_rejects_invalid_pairs_before_provider`(`tests/test_writing.py`)이 4 서브테스트로 **상태코드 400 + `detail` 리터럴 핀 + `provider.last_request is None`(provider 호출 전 실패)** 을 잠근다 — 1차 하드닝 권고(detail 핀)까지 채택된 강한 형태.
  - **FA' 변이(4분기 검증 블록 통째로 삭제) 재적용** → **4 SUBFAILED**(append_with_next_unit·start_without_next_unit·start_with_blank_title·start_with_blank_goal 각각), 요약 "4 failed, 67 passed". 1차 FA(무잠금, 96 green)와 정확히 반대 — 폐쇄 입증.
- **조건 ④(job몽고 신규 필드)**: round-trip fixture가 `intent="start_next_unit"`·`next_unit={"title": "다음 장면", "goal": "긴장 유지"}` 실값을 넣는다.
  - **FB' 변이(`_doc`에서 intent/next_unit 두 줄 삭제) 재적용** → `test_round_trip_preserves_all_fields_including_failure_enum` **1 failed**. 1차 FB(무잠금, 31 green)와 반대 — 폐쇄 입증.
- **수치 재현**: writing 묶음 unittest → **192 OK**(1차 191 + 신규 1셀) · job몽고 → **14 passed** · 프론트 writing 2파일 → **72 passed** · `tsc --noEmit` rc=0 · `npm run build` **711 modules** 성공. work_log에 조건별 폐쇄 근거와 명령이 전부 기록됐고 HANDOFF 착수점·분량 기록(752줄) 갱신 관례 준수.

## Issues / Risks

### Blocking (계약 의무)

- 없음.

### Hardening recommendations (비차단)

- 없음 — 1차 하드닝(detail 리터럴 핀)이 이번에 채택됐다.

## Verdict

**합격** — 1차 조건 4건이 전부 실측으로 닫혔다: ①·②는 가드 green·gen:api 무차이로, ③·④는 1차 무잠금 입증 변이(FA·FB)를 동일 diff로 재적용해 기명 셀이 재실패함으로써 폐쇄를 증명했다(FA' 4 SUBFAILED·FB' 1 failed). 상품 코드 무변(전수 결과 이전)·수치 전부 재현·문서 기록 관례 준수.

## Outstanding items

- 다음 작업은 identity group **구현** 슬라이스(HANDOFF 착수점) — 브리프 C의 스키마·shortlist+judge·그룹 액션 멱등성·grouped Inbox UI 분할 계획이 필요하다.
- N3(finalize key replay 활동 행 중복, UI 도달 불가)·`_scene_payload` 장면당 버전 스캔 유예는 그대로.

## Reproduction

```bash
git status --short        # clean
python3 -m pytest tests/test_docs_indexes.py -q          # 13 passed, 282 subtests
cd frontend && npm run gen:api && git status --short     # 무차이
python3 -m unittest tests.test_writing_scratch tests.test_writing_generation_job tests.test_writing_generation_worker tests.test_writing tests.test_writing_revise   # 192 OK
python3 -m pytest tests/test_writing_generation_job_mongo.py -q   # 14 passed
# FA': routers/writing.py의 4분기 검증 블록 삭제 → tests/test_writing.py -q → 4 SUBFAILED
# FB': generation_job_mongo._doc에서 intent/next_unit 삭제 → job몽고 suite → round-trip 1 failed
# (변이 후 git checkout -- 복원은 루트 CWD에서, clean 확인)
```
