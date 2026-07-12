# 독립 검증 — Phase 5.4 structured candidate report (SoT v1.6.71)

## Subject metadata

- **Date**: 2026-07-12
- **Requester**: 오너("다음작업 검증해줘. D6는 A first → C 확장 확정으로 구현했습니다. …").
- **Verifier**: 독립 세션(검증자). 구현자 클레임을 반박용 가설로 취급.
- **Target slice**: Phase 5.4 — 신규 `writing/report.py`(extractor+parser)·`writing/models.py` 확장(CandidateClaim/NewMemoryHint/RiskNote + enum)·`writing/service.py`(enrich 합성)·`writing/gate_prompt.py`(report 소비)·`writing/accept.py`(advisory copy)·`analysis/{models,service,runner,prompt_builder,mongo_repository}.py`(advisory 보존·소비)·`main.py`(wiring+HTTP 직렬화).
- **Canonical spec reference**: `docs/plans/05-writing-self-report-decisions.md`(Resolved, D1=A·D2=A first→B·D3=A then B committed·D4=A·D5=B·D6=A first→C, "승인 후 첫 회귀 경계" 10행) + `docs/system-contract-sot.md` v1.6.71(L36).
- **Source of work**: working tree, uncommitted. `git status` — 10 modified + 3 untracked(report.py·브리프·테스트). HEAD 기준 v1.6.70까지 반영.

## Scope

1. **Spec contract** — 브리프 D1~D6·10행 매트릭스의 내부 일관성, SoT v1.6.71 엔트리와 교차 일관성.
2. **Implementation code** — `report.py`(strict parser·1회 repair·enrich), `models.py`(내부 필드명 `claim_type`/`hint_type`/`risk_type` vs public `type`), 3개 직렬화 경로(gate_prompt·accept `_candidate_report_payload`·main HTTP), analysis-side advisory 흐름(create_job→immutable_payload→Mongo→runner replace→prompt_builder).
3. **계약 일관성 검증** — D6=A "advisory only, direct candidate/memory mint 금지"(구조), "immutable advisory copy"(MappingProxyType), 구현자 payload-sweep name-leakage fix 클레임.
4. **Regression tests** — `test_writing_report.py`(7)+ `test_writing_accept.py` advisory copy 확장이 매트릭스를 채우는지 추적.
5. **Boundary matrix** — 10행 + D6 분기의 named test 매핑, 빈 셀 점검.
6. **Full suite + mutation** — 868/48/146 재도출 + 5종 변형으로 직렬화/소비 경로 guard 증명.

실 Gemma report 품질·extractor prompt 품질은 fake provider로 대체된 결정적 계약만 검증(브리프가 "production 판정 품질은 fake 회귀와 분리"로 설정한 범위 계승).

## Methodology

브리프 10행 + D6를 lock list로 세우고 직렬화 3경로·analysis 소비 경로를 named test로 추적. 각 경로의 guard를 변형(type→내부명, 소비 코드 제거)으로 망가뜨려 기존 테스트가 bite하는지 확인. 특히 구현자의 "내부 dataclass 이름(claim_type) 노출 방지 회귀" 클레임을 3개 직렬화 경로 각각에서 검증.

명령(재현은 §Reproduction):
- `cat services/application/app/writing/report.py tests/test_writing_report.py` — 신규 extractor/테스트.
- `git diff HEAD -- services/application/app/{writing,analysis}/*.py main.py` — 관통 diff.
- `grep -rln writing_candidate_report tests/` — advisory 필드 테스트 커버리지.
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q` — 전체(868/48/146).
- 변형: `cp` 백업 → 정확한 문자열 replace → focused pytest → 복구 → `diff -q`(MUT-1/2/3 + B2a/B2b).

## Findings

### 1. Spec contract — 내부 일관성

브리프 D1=A·D2=A first→B·D3=A then B·D4=A·D5=B·D6=A first→C ↔ 10행 매트릭스 ↔ SoT v1.6.71이 일관. enum literal(claim type 8종·hint type 7종·risk type 7종·severity 4종)이 브리프 L38과 `models.py:53-88`에 동일하게 반영.

정직성 포인트:
- **D6=A 안전성**(브리프 L78): report는 `ai_inferred` advisory이며 runner가 accepted snapshot을 다시 읽고 기존 source_ref/schema validation을 통과한 candidate만 기록. report 자체로 candidate/memory를 직접 만들지 않음. 코드 구조 확인 — runner는 `replace(snapshot, writing_candidate_report=...)` 후 `extractor.extract(snapshot)`(runner.py), extractor가 snapshot을 독립 재추출하므로 report→candidate 직접 mint 코드 경로 없음. 단 advisory 성격은 extract **prompt** 설계에 의존(모델 품질, fake 범위 밖).
- **구현자 payload sweep**(work_log L477/L483): "dataclass 내부명(claim_type/hint_type/risk_type)이 advisory wire에 샐 가능성을 발견해 public `type`으로 명시 직렬화". 이 발견은 정확 — 내부 필드명과 public wire명이 의도적으로 분리됨(`models.py:94,100,108` vs 직렬화 `type`). **회귀는 accept 경로에만 추가**(`test_accepted_report_is_copied...`의 `assertNotIn("claim_type", ...)`). 이 회귀는 강함(MUT-1로 bite 입증). 그러나 동일 leakage 위험이 3경로 중 2경로에서 미잠금(→ §Issues).

### 2. Implementation code — 스펙 리터럴 대 일치

- `parse_report`(`report.py:66-76`): root exact-set{self_reported_constraints, candidate_claims, new_memory_hints, risk_notes}·각 item `_exact`(set equality)·enum 생성자로 unknown 즉시 reject. 브리프 D2=A L38 strict.
- confidence guard(`report.py:93`): `isinstance(c, bool)` 먼저 → bool reject(bool이 int subclass라 우회 방지)·`not isinstance(c,(int,float))`·`not math.isfinite(c)`(NaN/inf)·`not 0<=c<=1`(range). 브리프 항목 3 충족.
- enrich+repair(`report.py:38-56`): provider 1회 → parse 실패 시 1회 repair prompt(`{"invalid": content, "error": ...}`) → 재실패 `InvalidCandidateReport`. 브리프 D4=A·항목 4 충족.
- advisory copy(`accept.py:91-96,132-147`): `_create_job`이 `_candidate_report_payload(candidate)`를 `analysis.create_job(writing_candidate_report=...)`로 전달. `create_job`(`analysis/service.py`)이 `immutable_payload`(=MappingProxyType, `analysis/models.py:140-141`)로 불변화. 브리프 D6=A "immutable advisory copy" 충족(구조).
- 3개 직렬화 경로 모두 명시적으로 `type` 사용: gate_prompt.py·accept.py `_candidate_report_payload`·main.py `_writing_candidate_payload`. (어느 것이 잠겼는지는 §5)
- analysis 흐름: create_job→immutable_payload 저장→mongo `_job_doc`/`_to_job` round-trip→runner가 job.writing_candidate_report를 snapshot에 `replace`→prompt_builder가 extract payload에 포함. (어느 것이 잠겼는지는 §5)
- additive: gate.py(판정/strict schema) 변경 없음 → 항목 8 "기존 strict Gate schema 유지" 구조 만족.

### 3. 계약 일관성 검증 — 핵심 클레임

- **"Gate가 report를 typed JSON으로 소비"**(사용자 클레임): gate_prompt.py가 enriched candidate의 4필드를 typed `type`으로 직렬화해 prompt에 포함. `test_gate_receives_structured_report_not_repr`(test_writing_report.py:78)가 risk_notes[0]["type"]=="pov" 단언. 참(risk 필드 한정).
- **"accept 시 서버 report를 pending AnalysisJob에 immutable advisory copy로 저장"**: accept가 `_reporter.enrich`(accept.py:57-58)로 candidate를 풍부하게 한 뒤 `_create_job`으로 advisory copy를 job에 저장. `test_accepted_report_is_copied_to_pending_analysis_job`(test_writing_accept.py:212)가 job.writing_candidate_report 단언. 참.
- **"Analysis runner가 report를 보조 prompt로 사용"**(사용자 클레임): 코드는 runner.py에서 snapshot에 report 부착 후 extract, prompt_builder.py에서 extract payload에 포함. **그러나 이 경로를 관통하는 테스트 없음**(→ §5 MUT-B2a/B2b).
- **"report에서 AnalysisCandidate나 memory를 직접 생성하지 않음"**(사용자 클레임): 구조적 확인 — report→candidate/memory 직접 mint 코드 경로 없음. extractor가 snapshot 독립 추출. advisory 성격은 prompt에 의존. 부작용 코드 없음은 확인.

### 4. Boundary matrix — lock 추적 (10행 + D6)

| # | 브리프 분기 | 매핑된 test | 상태 |
|---|---|---|---|
| 1 | prose 불변 + extractor request가 candidate+package 포함 | prose: gate.py/generate 평문 유지(구조). extractor request 내용: 미검증 | 부분(H) |
| 2 | 네 field가 enriched candidate + **HTTP response** | enriched candidate: `test_parse...`(L36)·`test_gate_receives...`(L78). **HTTP response: 미검증** | 부분(B1) |
| 3 | strict parser(enum/required/exact/confidence/NaN/bool) | `test_confidence_rejects_bool_nan_and_range`(L43)·`test_schema_and_unknown_enum...`(L49) | ✓ |
| 4 | malformed→repair 1회→성공; repair invalid→502 | `test_invalid_first_output_repairs_once`(L55)·`test_invalid_repair_fails`(L67) | ✓ |
| 5 | provider fault/timeout → 502/504 (위장 금지) | report extractor provider 오류 HTTP 매핑: 미검증(shared pattern) | 부분(H) |
| 6 | identity mismatch → provider 호출 전 400 | accept validate(`accept.py:119`) covers. enrich 자체 cross-project(`report.py:40`): 미검증 | 부분(H) |
| 7 | 빈 배열 유효 | `test_parse_typed_report_and_empty_arrays`(L39) | ✓ |
| 8 | Gate prompt report 수신 + strict schema 유지 | gate.py 미변경(구조). gate prompt 수신: `test_gate_receives...`(L93) | ✓ |
| 9 | agent-loop self_report 종료채널과 비충돌 | 구조(필드명 분리). 직접 test 없음 | 구조 ✓ |
| 10 | accept가 enriched/legacy 양쪽 text 기준 재평가 + canon write 없음 | `test_accepted_report...`(L212, enriched). legacy: 기존 accept 회귀(reporter=None) | ✓ |
| D6 | runner가 report를 보조 prompt로 소비 + direct mint 금지 | **runner 소비: 미검증. mint 금지: 구조.** advisory copy 저장: `test_accepted_report...`(L212) | 부분(B2) |

7행 직접 매핑 + 3행 부분(B1·B2 + H). 빈 셀: 항목 2의 HTTP response(B1), D6의 analysis 소비(B2).

### 5. Mutation testing — 직렬화/소비 경로 guard 증명

각 변형 후 focused가 FAIL하면 잠김, 통과하면 unlocked. `cp` 백업→replace→pytest→복구→`diff -q`.

- **MUT-1 (accept `_candidate_report_payload` claims `type`→`claim_type`)**: `test_accepted_report_is_copied_to_pending_analysis_job` **FAIL**. accept advisory 경로 잠김(`assertNotIn claim_type` + `type` 단언). ✓
- **MUT-2 (main `_writing_candidate_payload` HTTP claims `type`→`claim_type`)**: **63 passed, FAIL 없음**. HTTP 응답 report 필드 이름 노출 unlocked. ✗
- **MUT-3 (gate_prompt claims `type`→`claim_type`)**: **63 passed, FAIL 없음**. gate prompt의 claims/hints 이름 unlocked(회귀는 risk_notes[0]["type"]만 검사). ✗
- **MUT-B2a (runner의 report→snapshot 부착 제거)**: **63 passed, FAIL 없음**. analysis runner advisory 소비 unlocked. ✗
- **MUT-B2b (prompt_builder의 report 포함 제거)**: **63 passed, FAIL 없음**. extract prompt advisory 포함 unlocked. ✗

복구 확인: 3파일 `diff -q` identical, focused 63 passed 재통과.

### 6. Full suite

`python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **868 passed / 48 skipped / 146 subtests**. 구현자 보고(868/48/146)와 정확 일치. `py_compile` report/models/accept/main 통과. focused(report+accept+writing+gate) 63 passed/45 subtests(구현자 "86/8/45"의 45 subtest 일치; 8 skipped는 mongo-env 계통).

## Issues / Risks

### Blocking (contract obligations)

B1·B2 모두 **코드 동작은 올바르고 test만 부재**(MUT로 unlocked 입증, 코드는 직렬화/소비를 올바르게 수행). fix는 test 추가만으로 완결.

- **B1 — HTTP generate 응답의 enriched report field 직렬화 전수 미검증(매트릭스 항목 2)**: `_writing_candidate_payload`(`main.py`)가 4개 report 필드를 `type`으로 올바르게 직렬화하나, (a) test_writing.py의 generate HTTP 테스트가 reporter를 배선하지 않아 응답의 report 필드가 항상 빈 채로 직렬화됨(test_writing.py:186 `self_reported_constraints == ()`), (b) `type`/`claim_type` 이름 가드 없음(MUT-2 입증). 브리프 항목 2 "HTTP response에 나타남" + D2=A public schema가 contract-required인데 enriched HTTP 응답의 존재·이름이 잠기지 않음. fix: generate HTTP 테스트에 reporter 주입 + 응답 4필드 존재·`type` key 단언.
- **B2 — analysis-side advisory 소비(runner 부착·prompt 포함·Mongo round-trip·새 필드) 전수 미검증(매트릭스 D6)**: `writing_candidate_report`가 tests 전체에서 accept copy 1곳(test_writing_accept.py:218)에만 등장. runner.py의 `replace(snapshot, writing_candidate_report=...)`(MUT-B2a unlocked)·prompt_builder.py의 extract payload 포함(MUT-B2b unlocked)·mongo_repository의 round-trip·AnalysisJob/SnapshotText 신규 필드가 어떤 test도 관통하지 않음. 브리프 D6=A "runner가 report를 보조 prompt로 소비"가 이 slice의 계약인데 소비 경로가 named test로 잠기지 않음. fix: report가 부착된 job으로 runner를 돌려 extract prompt에 report가 포함됨을 단언하는 test(인메모리 extractor로 prompt 관찰) + Mongo round-trip test.

### Hardening recommendations (non-blocking)

- **H1 — extractor request 내용 미검증(항목 1)**: report extractor request가 candidate_text+context_package를 포함하는지 어느 test도 `provider.last_request`로 단언하지 않음. enrich 회귀가 호출만 확인. request payload 조성 test 추가 권장.
- **H2 — report extractor provider 오류 HTTP 매핑 미검증(항목 5)**: report extractor의 ProviderError→502/504·InvalidCandidateReport→502(main.py 신규 분기)가 accept/gate 표면처럼 HTTP로 관통 안 됨. 동일 shared-pattern 부류. failing report provider HTTP test 권장.
- **H3 — gate prompt의 claims/hints 이름 노출 미잠금(MUT-3)**: 회귀가 risk_notes[0]["type"]만 검사. claims/hints 직렬화도 `type`을 쓰나 잠기지 않음. risk와 함께 claims/hints의 `type` key도 단언하거나 parametrize 권장(내부 prompt라 public 계약은 아니나 일관성).
- **H4 — enrich 자체 cross-project check(`report.py:40`) 미검증(항목 6)**: accept validate가 선행하지만 generate 경로의 enrich 자체 가드는 test 없음. defense-in-depth 가드 단언 권장.
- **H5 — immutability 미검증**: `immutable_payload`=MappingProxyType로 구조적으로 불변이나, write 후 mutation 시도→거부를 단언하는 test 없음. low priority.
- **H6 — enrich가 stale/archive 검사 전 실행**: accept.py가 validate 직후 enrich(provider 호출)한 뒤 archive/stale 검사. stale/archived accept가 report extractor 호출을 1회 낭비. endpoint의 context_search 호출이 이미 stale 전에 일어나는 기존 패턴과 일관되므로 정확성 버그는 아니나, enrich를 stale/archive 이후로 미루면 provider 호출 절약(저우선순위).

## Verdict

**조건부 합격(conditional pass)**. 정본 계약(브리프 D1~D6 + 매트릭스 10행, SoT v1.6.71)은 내부 일관. producer 측(extractor·strict parser·enrich·1회 repair·gate prompt 수신·accept advisory copy + name-leakage guard)은 정확하고 accept 경로 이름 노출 가드는 강하게 잠김(MUT-1). 구현자가 payload sweep으로 실제 이름 노출 위험을 발견하고 accept 경로 회귀를 추가한 것은 정확한 발견. full suite 868/48/146 green.

그러나 매트릭스의 contract-required consumer 표면 2곳이 named test로 잠기지 않음 — (B1) HTTP generate 응답의 enriched report 필드(존재·이름), (B2) analysis-side advisory 소비(runner 부착·prompt 포함·Mongo round-trip). 둘 다 MUT로 "코드는 올바르나 test 부재"를 입증했으므로 fix는 **test 추가만**으로 완결(production 코드 무변경). 구현자의 이름 노출 fix를 같은 직렬화 경로 2곳(HTTP·gate-prompt)과 analysis 소비 경로로 확장하면 잠금 완결. B1·B2 test 추가 시 합격.

## Outstanding items

- 변경 미커밋(구현자 명시). 10 modified + 3 untracked. B1·B2 test 보강 후 커밋 권장.
- SoT·CHANGELOG·HANDOFF·브리프는 v1.6.71 기준 갱신됨(확인 완료).
- 직전 v1.6.69(gate) 검증 blocking 3건·v1.6.70(accept) H1이 working tree에 반영되었는지는 본 slice 범위 밖; B1(HTTP report) 보강 시 같이 확인 권장.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# full suite (868 passed / 48 skipped / 146 subtests)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# B1 입증: HTTP claims 이름 노출 unlocked (변형 후 FAIL 없음 = 잠금 부재)
cp services/application/app/main.py /tmp/main.py.bak
python3 - <<'PY'
import pathlib
p=pathlib.Path("services/application/app/main.py"); s=p.read_text()
p.write_text(s.replace(
  '                {"text": x.text, "type": x.claim_type.value,\n                 "requires_gate_check": x.requires_gate_check}',
  '                {"text": x.text, "claim_type": x.claim_type.value,\n                 "requires_gate_check": x.requires_gate_check}'))
PY
python3 -m pytest tests/test_writing_report.py tests/test_writing_accept.py tests/test_writing.py tests/test_writing_gate.py -q -p no:cacheprovider 2>&1 | tail -2   # 63 passed = B1
cp /tmp/main.py.bak services/application/app/main.py

# B2 입증: analysis advisory 소비 unlocked
cp services/application/app/analysis/runner.py /tmp/runner.py.bak
python3 - <<'PY'
import pathlib
p=pathlib.Path("services/application/app/analysis/runner.py"); s=p.read_text()
p.write_text(s.replace(
  '''            if job.writing_candidate_report is not None:
                snapshot = replace(
                    snapshot,
                    writing_candidate_report=job.writing_candidate_report)
            drafts = await self._extractor.extract(snapshot)''',
  '''            drafts = await self._extractor.extract(snapshot)'''))
PY
python3 -m pytest tests/test_writing_report.py tests/test_writing_accept.py tests/test_writing.py tests/test_writing_gate.py -q -p no:cacheprovider 2>&1 | tail -2   # 63 passed = B2
cp /tmp/runner.py.bak services/application/app/analysis/runner.py

# (참조) accept 경로는 잠김 증명: accept claims type->claim_type 시 FAIL
cp services/application/app/writing/accept.py /tmp/accept.py.bak
python3 - <<'PY'
import pathlib
p=pathlib.Path("services/application/app/writing/accept.py"); s=p.read_text()
p.write_text(s.replace('        "candidate_claims": [{"text": x.text, "type": x.claim_type.value,',
                       '        "candidate_claims": [{"text": x.text, "claim_type": x.claim_type.value,'))
PY
python3 -m pytest tests/test_writing_accept.py -q -p no:cacheprovider 2>&1 | tail -2   # 1 failed = accept 잠김
cp /tmp/accept.py.bak services/application/app/writing/accept.py
```
