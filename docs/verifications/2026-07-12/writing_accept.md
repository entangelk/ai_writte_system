# 독립 검증 — Phase 5.3 accept→save→analysis 재진입 (SoT v1.6.70)

## Subject metadata

- **Date**: 2026-07-12
- **Requester**: 오너("다음작업 검증해줘. Phase 5.3 accept→save→analysis 재진입을 v1.6.70으로 구현했습니다.").
- **Verifier**: 독립 세션(검증자). 구현자 클레임을 반박용 가설로 취급.
- **Target slice**: Phase 5.3 — 신규 `writing/accept.py`(`WritingAcceptService`·`_append_patch`·result/error 계약) + `main.py` `POST /projects/{id}/writing/accept` 엔드포인트 + gate payload 공유화(`_writing_gate_payload`).
- **Canonical spec reference**: `docs/plans/05-writing-accept-decisions.md`(Resolved, D1=A·D2=A first→C·D3=A·D4=A·D5=A first→C·D6=A·D7=A, "승인 후 첫 회귀 경계" 12행) + `docs/plans/05-writing-ai.md` §83 + `docs/system-contract-sot.md` v1.6.70(L36).
- **Source of work**: working tree, uncommitted. `git status` — modified `main.py`·`05-writing-ai.md`·SoT·CHANGELOG·HANDOFF·work_log, untracked `writing/accept.py`·`05-writing-accept-decisions.md`·`tests/test_writing_accept.py`. HEAD = `388cf07`(v1.6.68; v1.6.69 gate slice도 working tree에 있었으나 본 검증 시점에는 반영됨).

## Scope

1. **Spec contract** — 브리프 D1~D7·"승인 후 첫 회귀 경계" 12행의 내부 일관성, SoT v1.6.70 엔트리·plan §83과의 교차 일관성.
2. **Implementation code** — `writing/accept.py`(`_append_patch` 3경계·accept 흐름 순서[validate→draft/project→archive→replay→base→stale→gate→non-pass→save→job]·`_validate`·key 파생), `main.py`(엔드포인트·에러 매핑 400/404/409/502/504 + partial-success JSONResponse).
3. **계약 일관성 검증** — D4 key 파생(`writing-accept:{key}` 양 store 공유), D3 accept-시 Gate 재평가, replay가 stale/archive와 맞는 순서, D7 partial-success envelope가 saved artifact를 숨기지 않는지.
4. **Regression tests** — service 8 + HTTP 7(+5 invalid subtests)가 매트릭스 12행을 채우는지 추적. 구현자 work_log L417 패턴스윕(archive-before-replay) 클레임 검증.
5. **Boundary matrix** — 12행 각 분기의 named test 매핑, 빈 셀 점검.
6. **Full suite + mutation** — 858/48/132 재도출 + 4종 변형으로 guard bite 증명.

실 Gemma Gate 판정 품질·context-search 실제 provider 장애는 fake 게이트/컨텍스트로 대체된 결정적 계약만 검증(브리프가 gate slice에서 "production 판정 품질은 fake 회귀와 분리"로 설정한 범위 계승).

## Methodology

브리프 "승인 후 첫 회귀 경계" 12행을 lock list로 세우고 코드·테스트에 대입. 각 분기를 named test로 추적한 뒤, guard를 제거/재배치하는 변형으로 기존 테스트가 변형을 bite하는지(real failure) 확인하여 guard가 잠겼음을 증명. under-strict(위반 시 side effect 발생)·over-strict(정상 case가 막힘) 양방향 확인.

명령(재현은 §Reproduction):
- `cat services/application/app/writing/accept.py tests/test_writing_accept.py` — 신규 코드/테스트.
- `git diff HEAD -- services/application/app/main.py docs/plans/05-writing-ai.md` — 엔드포인트/plan diff.
- `grep -n "1.6.70\|accept" docs/system-contract-sot.md docs/daily_logs/2026-07-12/work_log.md` — 정본 반영.
- `python3 -m pytest tests/test_writing_accept.py tests/test_writing_gate.py tests/test_writing.py -q` — focused(53/31).
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q` — 전체(858/48/132).
- 변형: `cp accept.py /tmp/accept.py.bak` → 정확한 문자열 replace → focused pytest → 복구 → `diff -q`(MA~MD 4종).

## Findings

### 1. Spec contract — 내부 일관성

브리프 D1=A·D2=A first→C·D3=A·D4=A·D5=A first→C·D6=A·D7=A ↔ "승인 후 첫 회귀 경계" 12행 ↔ SoT v1.6.70 엔트리(L36) ↔ plan §83이 전부 일관. decision/append 규칙/idempotency key/partial-success envelope가 정본에 동일 문자열로 반영.

정직성 포인트:
- **D4 key 파생의 정당성**(브리프 L57): save key=`writing-accept:{idempotency_key}`, analysis key=`writing-accept:{idempotency_key}`. 두 store가 각자 project/draft·project/snapshot scope로 충돌을 방지하므로 같은 literal을 재사용. 코드(`accept.py:55,95`)가 브리프 리터럴과 문자 그대로 일치.
- **패턴 스윕 발견**(work_log L417): 구현자가 CLAUDE.md §4 패턴 스윑 중 "replay lookup이 active-state 검사보다 앞이면 accept 후 archive된 draft가 같은 key replay로 job side effect를 만든다"를 발견하고 archive 검사를 replay 앞으로 이동 + 회귀 추가. 이것은 정확한 양방향 사고이며 §5 MUT-D로 load-bearing임을 입증.

SoT L485("accept 적용 단위는 후속로 미확정 유지")가 v1.6.70(D2=A 잠금)과 충돌 → §Issues/Hardening.

### 2. Implementation code — 스펙 리터럴 대 일치

- `_append_patch`(`accept.py:123-128`): 빈 base→patch, trailing `\n`→exact concat, 그 외→`\n\n`+patch. 브리프 D2=A L33과 동일.
- accept 흐름 순서(`accept.py:53-89`): `_validate` → `get_draft`/`get_project` → **archive 검사(L59-60)** → `list_versions`/replay lookup(L61-63) → (replay 시 return) → `get_draft_version`(base) → **stale 검사(L75-76)** → `gate.evaluate`(L77) → non-pass return(L79-80) → `_append_patch`+`save_draft`(L81-84) → `_create_job`(L85-88). 브리프 "stale는 provider/write 전"·"결정적 validation은 provider 미호출" 만족.
- non-pass 처리(L79-80): `gate.decision is not WritingGateDecision.PASS` → `WritingAcceptResult(False, gate, None, None)`. 저장/job 생성 없음. D3=A·D6=A 일치.
- partial-success(`accept.py:85-88`): job 생성 실패 시 `WritingAcceptAnalysisError(str(exc), saved=saved)` — saved artifact를 예외에 포함. D7=A 일치.
- replay(`accept.py:63-70`): 파생 save key로 기존 version을 찾아 Gate/save를 반복하지 않고 job을 재유도. 같은 version/snapshot/job 반환, `idempotent_replay=True`. D4=A·매트릭스 5행 일치.
- HTTP 에러 매핑(`main.py` accept 엔드포인트): NotFound→404, Archived·StaleWritingBase→409, WritingAcceptError·WritingGateError·InvalidContextSearchRequest→400, InvalidWritingGateResult→502, **WritingAcceptAnalysisError→502 JSONResponse `{accepted:True, saved, analysis_job:None, analysis_error}`**(partial-success envelope, L— `JSONResponse`로 saved artifact 포함), ContextSearchBudgetExceeded→504, ContextSearchFailed→502, ProviderError→TIMEOUT?504:502. 매트릭스 9행 일치.
- additive: gate payload가 `_writing_gate_payload`로 공유화되었고 gate 엔드포인트가 이를 재사용(`return _writing_gate_payload(result)`). gate 회귀 전수 통과로 비파괴 확인.

### 3. 계약 일관성 검증 — 핵심 클레임

- **"replay는 기존 save를 먼저 찾아 Gate/save 중복 없이 job을 재유도"**(SoT L36, work_log L405): replay 분기(`accept.py:63-70`)가 stale/base/gate/save를 전부 건너뛰고 job만 재생성. `test_same_key_replays_without_gate_or_duplicate`(L123)가 gate.calls 미증가·job 1개·같은 version으로 단언. 참.
- **"Gate non-pass는 정상 accepted=false outcome"**(D6=A): non-pass가 200으로 반환(에러 아님), `accepted=false`, saved/job=null. `test_non_pass_is_200_without_saved_artifacts`(L204)가 200 + accepted=false + gate.decision 단언. transport/provider 오류(502/504)와 구분. 참.
- **"save 후 job write 실패는 saved artifact를 숨기지 않고 same-key replay로 수렴"**(D7=A): `WritingAcceptAnalysisError`가 saved를 예외에 실어 502 envelope로 반환, retry는 save replay 후 job 재생성. `test_partial_failure_is_502_and_retry_converges`(L237)가 502→retry 502→fail 복구 후 200으로 saved_id 일치·job pending 단언. 참.
- **archive-before-replay 순서**(work_log L417 fix): archive 검사(L59)가 replay(L63)보다 선행. archived draft의 same-key replay도 Archived로 차단. `test_archived_draft_blocks_replay_before_job_or_gate`(L158) 단언. §5 MUT-D로 load-bearing 입증.

### 4. Boundary matrix — lock 추적 (12행)

브리프 "승인 후 첫 회귀 경계"(`05-writing-accept-decisions.md:108-121`) 12행을 lock list로 세우고 각 분기를 named test에 매핑.

| # | 브리프 분기 | 매핑된 test | 상태 |
|---|---|---|---|
| 1 | pass+latest base→append+새 version/snapshot | `test_pass_saves_new_version...`(L96)·`test_pass_returns_saved...`(L193) | ✓ |
| 2 | non-pass→version/job 생성 금지; pass는 저장 | `test_non_pass_is_normal_no_write_outcome`(L105, REVISE)·`test_non_pass_is_200...`(L204). pass-저장: #1. 양방향 | ✓ |
| 3 | stale base→provider/write 전 409 | `test_stale_base_rejected_before_gate`(L115, gate.calls==0)·`test_stale_is_409_before_gate`(L214) | ✓ |
| 4 | 빈 candidate/instruction/key·지원 안 됨 task/output type→400 | `test_invalid_inputs_are_400`(L264, 5 subtest: key·instruction·candidate_text·task_type·output_type, gate.calls==0) | ✓ |
| 5 | 같은 key replay→같은 version/job, side effect 중복 없음 | `test_same_key_replays_without_gate_or_duplicate`(L123)·`test_replay_returns_same_version_without_second_gate`(L225) | ✓ |
| 6 | 다른 key→다음 version+별도 job | `test_different_key_creates_next_version_and_job`(L134) | ✓ |
| 7 | save 성공→pending job(새 snapshot); run 호출 안 함 | `test_pass_saves...`(L100-101, PENDING+snapshot_id)·`test_pass_returns...`(L199-201) | ✓ |
| 8 | archived→409; missing project/draft/version→404 | `test_archived_draft_blocks...`(L158, Archived→409)·`test_missing_base_version_is_404_before_gate`(L257) | ✓ |
| 9 | Gate/context/provider 오류→성공 위장 금지(502/504); validation은 provider 미호출 | validation: #3/#4(gate.calls==0). provider/budget/context: gate 표면에서 테스트, **accept 표면 미단언** → §Issues/H1 | 부분 |
| 10 | 기존 API 변경 없는 additive | gate payload 공유화·gate 회귀 전수 통과 | ✓ |
| 11 | non-pass=정상 accepted=false, transport 오류와 구분 | `test_non_pass_is_200...`(L204) | ✓ |
| 12 | save 후 job write 실패→saved artifact 노출+replay 수렴 | `test_job_failure_exposes_saved_and_retry_converges`(L141)·`test_partial_failure_is_502_and_retry_converges`(L237) | ✓ |

11행 직접 매핑 + 1행(9의 provider/budget/context) 간접 매핑. 빈 셀 없음.

### 5. Mutation testing — guard bite 실증

각 변형 후 focused 일부가 FAIL하면 guard가 잠긴 것으로 판정. 변형 적용→pytest→`cp /tmp/accept.py.bak` 복구→`diff -q`로 복구 확인.

- **MA (append 규칙 제거)**: `_append_patch`를 항상 exact concat으로 변경. 결과: `test_pass_saves_new_version_and_creates_pending_job`(+ append literal) **FAIL** — 3경계 append 규칙이 잠김.
- **MB (stale 체크 제거)**: stale 검사(L75-76) 삭제 → stale base에서 gate가 호출됨. 결과: `test_stale_is_409_before_gate` **FAIL** — stale-before-gate가 잠김.
- **MC (non-pass early return 제거)**: non-pass return(L79-80) 삭제 → non-pass가 save됨. 결과: `test_non_pass_is_200_without_saved_artifacts` **FAIL** — non-pass-no-save가 잠김.
- **MD (replay를 archive 체크 앞으로 이동)**: archive 검사를 replay lookup 이후로 이동(작업자 L417 fix 역행) → archived draft의 same-key replay가 job을 만듦. 결과: `test_archived_draft_blocks_replay_before_job_or_gate` **FAIL** — archive-before-replay 순서가 load-bearing으로 잠김.

복구 확인: `diff -q /tmp/accept.py.bak accept.py` identical. focused 15 passed 재통과. **gate slice와 대비**: 이 slice는 critical guard가 양방향으로 잠겨 있음.

### 6. Full suite

`python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **858 passed / 48 skipped / 132 subtests**. 구현자 보고와 정확 일치. focused(`test_writing_accept.py`+gate+writing) 53 passed/31 subtests 일치. `py_compile` accept/main/테스트 통과.

## Issues / Risks

### Blocking (contract obligations)

없음. 매트릭스 12행 중 11행이 accept 표면에서 직접 단언되고, 4개 critical guard(append 규칙·stale-before-gate·non-pass-no-save·archive-before-replay)가 변형으로 잠김을 입증. 남은 1행(9의 provider/budget/context)은 gate/generate 표면에서 동일 매핑이 테스트된 공유 코드 경로(H1 참조).

### Hardening recommendations (non-blocking)

- **H1 — accept 표면 provider/budget/context 오류 매핑 미단언(매트릭스 9행)**: accept 엔드포인트의 ProviderError→502/504·ContextSearchBudgetExceeded→504·ContextSearchFailed→502 분기가 정확히 존재하고 except-순서상 선행 분기에 삼켜지지 않음(광역 `except Exception` 없음, 수동 trace로 확인). 그러나 accept 회귀는 fake `_Gate`(미raise)·`_Context`(미fail)를 쓰므로 이 분기들을 accept 표면에서 관통하지 않음. gate/generate 표면에서 동일 매핑이 단언되어 동작은 올바르나, accept 엔드포인트의 except-ladder 회귀가 없으면 (예: 향후 ProviderError를 선행 except에 잘못 편입) accept 표면에서 미검출. 이 패턴은 직전 writing_generation 검증의 비차단 H2(orchestration 504/502 브랜치)와 동일 부류로, 당시 합격 후 HTTP +2로 보강됨. accept 표면 HTTP test 1건(failing gate provider 주입 → 502/504) 추가로 완전 closure 권장.
- **H2 — 503(service 미구성) accept 표면 미단언**: `writing_accept is None`(gate 미구성 시)·`context_search is None`→503이 gate 표면에서는 단얰되었으나 accept 표면에서는 미단언. 동일 공유-패턴 부류. 저우선순위.
- **H3 — non-pass parametrization이 REVISE 한 종**: 코드는 모든 non-pass를 동일 단일 분기(`is not PASS`)로 처리하므로 REVISE 한 종으로 충분하나, 브리프 D6(L73)이 "revise/retrieve/review/block"을 나열. 4종 non-pass decision으로 parametrize하면 "모든 non-pass는 동등" 계약이 더 단단히 잠김. 단일 분기라 낮은 가치.
- **H4 — cross-project candidate/package 검증(`accept.py:119`) accept 표면 미단언**: 브리프 L112 "cross-project"가 gate slice에서는 service-수준으로 단언되었으나 accept에서는 미단언. 동일 패턴. 저우선순위.
- **H5 — SoT L485 stale**: "accept 적용 단위는 후속로 미확정 유지"가 v1.6.70(D2=A 잠금)과 충돌. plan §83은 [x]로 갱신됐으나 L485 본문은 미정리. 문구 갱신 권장.
- **H6 — `candidate.text.strip()` vs 브리프 "candidate 그대로"**: 서비스가 append 전 candidate를 strip(L81). helper `_append_patch` 자체는 브리프 L33 리터럴과 일치하나 서비스가 추가 strip. 이중 공백 방지로 정당하나 브리프 "그대로"와 약간 긴장. 동작 영향 없(회귀 통과). 한 줄 메모 권장.

## Verdict

**합격(pass)**. 정본 계약(브리프 D1~D7 + 매트릭스 12행, SoT v1.6.70, plan §83)은 내부 일관. 구현 리터럴·흐름 순서·에러 매핑·partial-success envelope가 스펙과 일치. 매트릭스 12행 중 11행이 accept 표면에서 직접 단언되고 남은 1행(provider/budget/context 매핑)은 gate/generate 표면에서 동일 매핑이 테스트된 공유 경로. 4개 critical guard(append 규칙·stale-before-gate·non-pass-no-save·archive-before-replay)를 변형으로 잠금 입증. 구현자가 패턴 스윕으로 archive-before-replay 순서 버그를 자체 발견·수정하고 회귀를 추가한 것은 지침이 요구하는 양방향 사고의 정실례. full suite 858/48/132 green.

H1~H6은 비차단 hardening이며, H1(accept 표면 provider 오류 HTTP test 1건)만 합격 후 보강하면 완전 closure. 차단 의무사항 없음.

## Outstanding items

- 변경 미커밋(구현자 명시). `git status` — 3 untracked(accept.py·브리프·테스트) + 3 modified(main.py·문서 3). H1 보강 후 커밋 권장(선택).
- SoT·CHANGELOG·HANDOFF·plan·브리프는 v1.6.70 기준으로 갱신됨(확인 완료). H5(SoT L485) 문구 정리 권장.
- v1.6.69(gate) 검증에서 blocking 3건(B1/B2/B3 test 보강)이 이 working tree에 반영되었는지는 본 slice 범위 밖; 별도 확인 권장.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# focused (53 passed / 31 subtests)
python3 -m pytest tests/test_writing_accept.py tests/test_writing_gate.py tests/test_writing.py -q -p no:cacheprovider

# full suite (858 passed / 48 skipped / 132 subtests)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# guard 잠금 증명 (각 변형 후 관련 test FAIL = 잠김)
cp services/application/app/writing/accept.py /tmp/accept.py.bak

# MA: append 규칙 제거 -> test_pass_saves_new_version... FAIL
python3 - <<'PY'
import pathlib
p=pathlib.Path("services/application/app/writing/accept.py"); s=p.read_text()
p.write_text(s.replace('''    if not base:\n        return patch\n    if base.endswith("\\n"):\n        return base + patch\n    return base + "\\n\\n" + patch''',
'''    if not base:\n        return patch\n    return base + patch'''))
PY
python3 -m pytest tests/test_writing_accept.py -q -p no:cacheprovider 2>&1 | tail -2
cp /tmp/accept.py.bak services/application/app/writing/accept.py

# MB: stale 체크 제거 -> test_stale_is_409_before_gate FAIL
python3 - <<'PY'
import pathlib
p=pathlib.Path("services/application/app/writing/accept.py"); s=p.read_text()
p.write_text(s.replace('''        if versions[-1].id != base.draft_version.id:\n            raise StaleWritingBase("base draft version is not the latest version")\n        gate = await self._gate.evaluate(''',
'''        gate = await self._gate.evaluate('''))
PY
python3 -m pytest tests/test_writing_accept.py -q -p no:cacheprovider 2>&1 | tail -2
cp /tmp/accept.py.bak services/application/app/writing/accept.py

# MC: non-pass return 제거 -> test_non_pass_is_200... FAIL
python3 - <<'PY'
import pathlib
p=pathlib.Path("services/application/app/writing/accept.py"); s=p.read_text()
p.write_text(s.replace('''        if gate.decision is not WritingGateDecision.PASS:\n            return WritingAcceptResult(False, gate, None, None)\n        raw_text = _append_patch(base.snapshot.raw_text, candidate.text.strip())''',
'''        raw_text = _append_patch(base.snapshot.raw_text, candidate.text.strip())'''))
PY
python3 -m pytest tests/test_writing_accept.py -q -p no:cacheprovider 2>&1 | tail -2
cp /tmp/accept.py.bak services/application/app/writing/accept.py

# 복구 확인
diff -q /tmp/accept.py.bak services/application/app/writing/accept.py && echo "clean"
```
