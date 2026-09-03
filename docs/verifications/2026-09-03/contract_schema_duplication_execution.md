# 계약 스키마 중복 전수조사 시행 — 독립 검증

## Subject metadata

- 검증일: 2026-09-03
- 요청자: 오너 — "작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래"
- 검증자: 이 세션(구현 세션과 다른 세션). 작업자가 남긴 보고(work_log·브리프 시행 결과·커밋 메시지)는 전부 **가설**로 취급해 원본에서 재유도했다.
- 대상: 커밋 5개 — `a63b521`(planner plan_id) · `226a821`(gate decision) · `6e9d497`(report 정책 bool) · `159157b`(extractor 앵커 v6) · `ed9e19e`(기록). HEAD `ed9e19e`, 트리 clean.
- 정규 계약: `docs/system-contract-sot.md` **v1.8.19**(변경이력 행 + Phase 2A 앵커 조항 + report 포인터 조항), 결정 브리프 `docs/plans/contract-schema-duplication-audit-decisions.md`(2026-09-02 확정, 시행 결과 절 포함).

## Scope

1. **계약 스코프 읽기** — 브리프의 확정 기준(A→B→C)·공통 KPI gate·Follow-up(over-strict 명시 요구)와 SoT v1.8.19 신규 조항. 경계 행렬: 후보 4축 각각의 should(모델 출력 계약 축소·서버 조립/유도)·should-NOT(legacy 키 통과·과잉 거부·logical_key 이동·공개 계약 변경).
2. **구현 코드 4커밋 전량 감사** — 프롬프트·파서·서버 상수·카탈로그 조립·시드·소비처.
3. **전수 회귀 재실행** — 작업자 보고 2701/1/3131·exit 0과의 대조.
4. **KPI gate 재실행** — OpenAPI 덤프가 슬라이스 전 트리(`8655653`)와 바이트 동일인지 **독립** 재덤프 대조(작업자 덤프 재사용 안 함).
5. **핀값 독립 재계산** — logical_key 이행 무손실 핀(사전 코드로 재계산), v5/v6 프롬프트 sha 핀.
6. **뮤테이션 14종** — 작업자 표 11종 전량 재실행 + 검증자 신설 3종.
7. **패턴 스윕** — 같은 root-cause(모델 에코·선택 아닌 복사)가 8개 call site의 나머지와 소비처·프론트에 잔존하는지.

## Methodology

환경(측정의 일부): WSL2 호스트, Python 3.12.3 / pytest 9.0.2, `.env` 없음(compose 기본값 사용), `docker compose -f docker-compose.test.yml up -d`로 test-mongo(127.0.0.1:27020, rs-test) 기동 후 `db.hello().isWritablePrimary` 확인. 이 머신 관례대로 skip 1(ES 패키지 탑재).

- 전수: `python3 -m pytest -q --tb=short -p no:cacheprovider`(로그 `/tmp/full_suite_verify.log`)
- OpenAPI: `python3 scripts/dump_openapi.py`를 **각 트리에서**(본 트리 + `git worktree add /tmp/pre_slice 8655653`의 사전 트리) 각각 실행 → `cmp`. md5 `10978d55571a90ccd52f65220fc354d3`·384,414B.
- logical_key 핀: 사전 트리(`8655653`) 코드로 v5 5필드 복사 출력을 파싱해 다이제스트 재계산 → 핀 셀 상수와 대조.
- sha 핀: `_IMMUTABLE_TEMPLATE_DIGESTS` 대상으로 모듈 상수 sha256 재계산 대조.
- 뮤테이션: 매번 `git status --short` empty 확인(사전 게이트) → 변이 → 집중 셀 실행 → **요약 라인 + FAILED/SUBFAILED 함께 판독** → `git checkout -- <path>` → clean 재확인. 적용한 diff 는 아래 표에 축약 없이 기재.
- 가드 단독: `pytest tests/test_typecheck.py`(mypy 8셀), `pytest tests/test_docs_indexes.py`(13셀).

## Findings

### 1. 계약 스코프·경계 행렬 (SoT v1.8.19 ↔ 브리프)

- SoT v1.8.19 변경이력 행과 Phase 2A 앵커 조항(모델 wire 는 `source_ref_id` 하나·서버 조립·legacy 5필드 정확키 거부·logical_key 무변), report 포인터 조항(v3 명기)이 코드와 문구 수준에서 일치한다. `checked_constraints` 유지 근거(서버 재구성값이 상수라 모델 자기보고가 유일 정보원)는 브리프 판단과 정합.
- 현행 조항에 옛 계약(모델이 decision 을 냄·파서가 optional plan_id 를 읽음)을 서술하는 잔존 없음. `writing_gate_v1`·"불일치를 거부" 문구는 변경이력(보존 본연)에만 존재.
- 브리프 Follow-up 이 요구한 over-strict 축이 셀로 존재한다: **빈 findings pass**(`test_pass_requires_no_findings`)·**style-only pass**(`test_style_only_findings_still_pass`).

### 2. 구현 코드

- **plan_id**: 옛 프롬프트(8655653)에 plan_id 요구 문구 없음(파서에만 존재) — "프롬프트가 요구한 적 없다" 확인. 옛 파서가 모델 값을 그대로 `SearchPlan.plan_id` 로 넣고 이것이 API trace 에 실렸다(`routers/context_search.py:83`). 신규: 상수 통일·모델 값 무시.
- **gate decision**: 유도식 `max(recommended_decision, key=_PRIORITY, default=PASS)`(style 제외)은 옛 mismatch 검증식을 그대로 이동한 것 — "응답 decision 은 서버 계산값 그대로(공개 계약 무변)" 성립. 정확키 검사가 2키로 좁아져 legacy `decision` 키는 거부. 게이트 파서를 복제하는 소비처 없음(`gate_live_diag.py` 는 서비스 결과 소비).
- **report bool**: 소비처 전수 — `routers/writing.py`(응답 렌더)·`gate_prompt.py`(입력 렌더)·`http_models.py`(응답 모델)·`accept.py`(저장 페이로드) 전부 **조건분기 없음**(값 흐름만). `accept.py:148` 게이트·`_create_job` 분석 job 은 무조건 — "서버 정책값" 전제가 코드로 성립. 프론트는 이 bool 을 읽는 곳 없음(schema.d.ts 타입·테스트 fixture 뿐).
- **extractor v6**: 모델 wire 는 `{"source_ref_id"}` 하나, 파서가 카탈로그 행에서 5필드 조립(`extractor.py:313-336`), 모르는 id 는 parse error → repair 1회. 카탈로그 렌더(`prompt_builder.py`)와 repair 요청(`authoritative_source_ref_catalog` 재사용) 모두 슬림(5필드 에코 원천이 모델 뷰에서 소멸). v5 는 `*_V5` 상수로 동결 + 시드 유지, v6 신규 시드가 in-memory·Mongo 양 경로에 모두 추가(`main.py`). 프로덕션 배선은 `source_ref_catalog=core_sot` 전달 확인.
- **뮤테이션으로 드러난 구조**: 옛 코드의 repair 이후 카탈로그 재검증은 양 갈래가 모두 `return repaired`인 죽은 검사였고, shape-error repair 경로의 출력은 애초에 카탈로그 대조를 안 거쳤다(사전 잔존 구멍). 신규 코드는 repair 출력도 카탈로그 조립 검증을 통과해야 해 이 두 구멍이 같이 닫혔다 — ghost id 가 초안에 남아 저장 직전 러너 사전검증(`InvalidCandidateSource`)으로만 잡히던 이중 방어가 단층 방어로 정리됐다. 방향은 강화이고 SoT 조항("모르는 id 는 거부(repair 1회)")은 신규 코드를 정확히 서술한다.

### 3. 전수 회귀 — 보고와 일치

**2701 passed / 1 skipped / 3131 subtests, exit 0, 1788.36s**(보고 2701/1/3131·exit 0·1786초). 셀 순증 +4 도 구조적으로 재현: 커밋별 테스트 함수 증감 +1/−1, +3/−3, +1/−0, +5/−2 → 순 +4. subtest +6 회계도 성립: plan_id 무시 셀 3 subtest + gate 거부 셀 순증 2(신규 5 − 옛 overstated 3, 옛 셀 subtest 3개는 사전 트리에서 확인) + 프롬프트 핀 테이블 v6 행 1.

### 4. KPI gate — 독립 재현

본 트리 덤프와 사전 트리(`8655653`) 덤프가 **바이트 동일**(각각 별도 실행, md5 동일). `schema.d.ts`·공개 계약 무변 성립. `llm_call_audits` 스키마·outcome 분류를 정의하는 observability 코드는 4커밋 어디에도 무접촉. mypy 가드 8셀·문서 인덱스 가드 13셀 단독 재실행 green.

### 5. 핀값 — 독립 재계산

- **logical_key 무손실 핀**: 사전 트리 코드로 같은 카탈로그·같은 후보(v5 5필드 복사 출력)를 파싱한 결과 `character_observation:00cd331087f57e4ce7865032428ac9fb03f3bb2252d7c0496e39a9353546ae55` — 핀 셀 상수와 **동일**. 핀값이 실제로 이행 전 코드 실측임이 입증됐고, v6 조립이 같은 identity 를 낸다(retry/replay 멱등 보존).
- **프롬프트 sha 핀**: v6 `7e2c5f93…`, v5 `bc2a0b12…` 재계산 일치.

### 6. 뮤테이션 14종 — 전부 기명 재실패

작업자 표 11종 재실행(셀 짝까지 일치; 파일 묶음 차이로 숫자가 ±1 흔들린 곳은 병기):

| 변이 | 적용 diff (요지) | 실측 재실패 |
|---|---|---|
| plan M1 | `plan_id=root.get("plan_id") or DEFAULT_PLAN_ID` | 3 failed — `test_valid_plan_parses_literals…` FAILED + `test_model_emitted_plan_id_is_ignored` SUBFAILED 2(plan-1·123; `""` 는 default 로 빠져 통과 — 설계된 사례) |
| plan M2 | `if "plan_id" in root: raise` | 12 failed(fixture 전면) |
| gate M1 | `decision = WritingGateDecision.PASS` | 17 failed(gate+quality 2파일; 작업자 16은 파일 묶음 차이) |
| gate M2 | `decision_driving = tuple(findings)`(style 포함) | 정확히 2셀 — `test_style_only_findings_still_pass`·`test_style_does_not_lift_a_non_style_decision` |
| gate M3 | 정확키 → 부분집합(`<=`) | 7 failed(거부 셀 SUBFAILED 5 포함) |
| report M1 | `requires_gate_check: bool = False` | `test_parse_typed_report_and_empty_arrays` 1 failed |
| report M2 | `_claim` `_exact` → 부분집합 | `test_legacy_bool_keys_are_rejected` 1 failed |
| report M3 | TEMPLATE 에 `"requires_gate_check": true,` 복원 | `test_invalid_first_output_repairs_once`(assertNotIn) 1 failed |
| extractor M1 | 조립값을 `start=99,end=100,quote="상수",hash="const"` 상수로 | 5 failed — 조립·identity 핀·legacy repair + runner 2(작업자 "3셀"의 상위집합) |
| extractor M2 | 앵커 `_require_fields` → `source_ref_id in item` | 2 failed(legacy repair + malformed payload SUBFAILED) |
| extractor M3 | v6 본문 `"from that item"→"from that id"` 같은 버전 편집 | sha 핀 셀 SUBFAILED(version=analysis_extract_v6) |

검증자 신설 3종(작업자 표에 없는 축):

| 변이 | 목적 | 실측 |
|---|---|---|
| NEW-1 gate: `decision = decision_driving[0].recommended_decision if … else PASS` | 유도 공식 자체(max) 를 약화 — always-PASS 와 다른 방향 | 2 failed — `test_decision_is_derived_from_the_strongest_finding`·`test_priority_chain_uses_strongest_finding_at_every_level` |
| NEW-2 extractor: 모르는 id 에 유령 `SourceRef` 합성(fails-open) | unknown-id 거부가 조립 상수와 무관하게 잠히는지 | 2 failed — `test_unknown_source_ref_id_is_rejected`·`test_versioned_prompt_adapter_repairs_catalog_id_drift_once` |
| NEW-3 gate: `root.pop("decision", None)` 후 정확키(거부→조용한 무시) | "legacy 키는 거부, 무시 아님" 경계 | 6 failed — 거부 셀 SUBFAILED 5 + `test_fence_does_not_weaken_decision_key_rejection` |

매 변이 후 `git checkout --` 원복·`git status --short` empty 확인. 최종 트리 clean(HEAD `ed9e19e`).

### 7. 패턴 스윕

- 4개 파서 모두 정확키 검사 유지(`_exact`/`_require_fields`/`set(root) !=` — 부분집합 아님). report/gate/extractor 의 모델 값 위치 인자 생성부·`["decision"]`/`get("decision")` 리더 잔존 없음.
- 나머지 4 call site(compare_judge·generation·retrieval_planner·revision)는 브리프 판정 그대로(에코 없음) — 이번 시행 범위 밖이며 브리프 표와 코드가 상충하지 않음.
- 프론트: 정책 bool 을 읽는 코드 없음. OpenAPI 바이트 무변이므로 `schema.d.ts` 도 무변.

## Issues / Risks

### Blocking (계약 의무 위반)

**없음.** 브리프가 요구한 경계(공개 계약 무변·KPI 의미 무변·over-strict 보존·logical_key 무변)에 빈 칸이 없다.

### Hardening recommendations (비차단)

1. **repair 수용 경계의 조임을 기록에 한 줄로 명시** — 옛 코드의 repair-후 카탈로그 재검증은 죽은 검사였고(양 갈래 `return repaired`), shape-error repair 출력은 카탈로그 대조를 안 거쳤다. 신규 코드는 repair 출력도 조립 검증을 통과해야 하므로 **수용이 엄격해졌다**(방향: 강화, ghost id 사전 차단). SoT 조항은 신규 코드를 정확히 서술하지만 시행 결과 표의 "모르는 id 는 기존대로 repair 1회"는 이 차이를 함축만 한다. 다음 SoT 개정 때 "repair 후에도 무효면 error"(옛: 무조건 수용)로 명문화하면 관측 대조(KPI 빈도 해석)에 유익.
2. **planner site 의 parse_error 단절도 KPI 노트에 병기** — 옛 파서는 `plan_id` 가 빈 문자열·비문자면 parse error 였고 지금은 어떤 값이든 무시한다. SoT v1.8.19 의 빈도 단절 문구는 gate·extractor 만 말한다. 관측된 적 있는 원인은 아니나(프롬프트가 요구한 적 없음) 시계열 대조표의 완전성을 위해 한 줄이면 충분.
3. **입력측 상수 bool 렌더 제거(D축 후보)** — `gate_prompt.py:60,66`(게이트 프롬프트가 모든 claim/hint 에 `requires_gate_check`/`should_analyze_after_save` 를 렌더)와 `accept.py:320`으로 저장되는 advisory report 가 이제 **상수 true** 만 실어 나른다. 출력 계약은 이번 조사 대상이 아니었으므로 무해하나, 에코 원천 관점에서 남은 토큰 노이즈다 — 호출 분산(D)축 비용 분석(`llm_call_audits` 토큰 분해) 재료로 함께 보라.
4. **report 정책 상수의 이중 잠금(선택)** — 기본값 반전(report M1)에 반응하는 셀이 `test_parse_typed_report_and_empty_arrays` 하나다. 목적에 충분하지만, accept 저장 페이로드나 게이트 API 응답이 `True` 상수를 실어 나르는 통합 셀 하나를 붙이면 공개 표면에서도 상수를 잡는다.

## Verdict

**합격**

- 전수 2701/1/3131·exit 0 독립 재현, OpenAPI 덤프 사전 트리와 바이트 동일 독립 재현, mypy 8·문서 인덱스 13 가드 green.
- 뮤테이션 14/14(작업자 11 + 신설 3) 기명 재실패 — under-strict·over-strict 양방향 모두 물림.
- 핵심 주장 3건을 문서가 아닌 원물로 입증: logical_key 핀값은 사전 트리 코드 재계산과 동일, v5/v6 sha 핀 재계산 일치, "프롬프트가 plan_id 를 요구한 적 없다"는 사전 트리 템플릿 grep 으로 확인.
- 경계 행렬(브리프+SoT v1.8.19)에 빈 칸 없음. 차단 0건.

## Outstanding items

- **배포 대기(오너)**: 앱 계열 이미지 재빌드 필요(프롬프트 v2/v3/v6·파서 변경). 운영 Mongo `prompt_templates` 에는 v6 행 insert(v5 행과 무충돌 — 핀 테스트가 시드 절차를 잠금).
- 호출 분산(D)축·진단 캡처 표본(브리프 Audit material C)은 별도 슬라이스 대기, identity group Slice 1 대기(HANDOFF 참조).
- 이 검증 기록 자체의 인덱스 등재·판정 분포 갱신은 본 커밋에 포함.

## Reproduction

```bash
# 환경: .env 없음, compose 기본값
docker compose -f docker-compose.test.yml up -d
docker exec ai_writte_system-test-mongo-1 mongosh --quiet --port 27020 \
  --eval 'quit(db.hello().isWritablePrimary ? 0 : 1)'
python3 -m pytest -q --tb=short -p no:cacheprovider   # 2701/1/3131, exit 0

# KPI gate (사전 트리 대조)
git worktree add /tmp/pre_slice 8655653
python3 scripts/dump_openapi.py > /tmp/head.json
python3 /tmp/pre_slice/scripts/dump_openapi.py > /tmp/pre.json
cmp /tmp/head.json /tmp/pre.json                        # byte-identical
git worktree remove /tmp/pre_slice

# logical_key 핀 (사전 코드 재계산 → 핀 셀 상수와 대조)
cd /tmp/pre_slice && python3 - <<'EOF'
import json, sys; sys.path.insert(0, "/tmp/pre_slice")
from services.application.app.analysis.extractor import parse_analysis_extraction
content = json.dumps({"candidates": [{
  "candidate_type": "character_observation", "provenance": "source_observed",
  "confidence": 0.8,
  "source_anchors": [
    {"source_ref_id": "source-ref-1", "start_offset": 0, "end_offset": 2, "quote": "민아", "content_hash": "hash-1"},
    {"source_ref_id": "source-ref-2", "start_offset": 3, "end_offset": 5, "quote": "편지", "content_hash": "hash-1"}],
  "payload": {"name": "민아", "observation": "민아가 편지를 발견했다."}}]}, ensure_ascii=False)
print(parse_analysis_extraction(content)[0].logical_key)  # …00cd331087f5…
EOF

# 뮤테이션 예시(NEW-3): git status --short empty 확인 → gate.py 에 root.pop("decision", None) 삽입
# → pytest tests/test_writing_gate.py -q (6 failed) → git checkout -- services/application/app/writing/gate.py
```
