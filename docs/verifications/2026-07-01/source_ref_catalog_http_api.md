# Phase 2A SourceRef Catalog HTTP API + Catalog Anchor Repair 독립 검증

## Subject metadata

- 검증일: `2026-07-01`
- 요청자: 프로젝트 오너("클로드 작업 AI가 작업한 부분 확인해서 검증하고 의심하고 또 의심해줄래?")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상: commit `ada3b39` "Add SourceRef catalog HTTP API" — Phase 2A source_ref catalog HTTP surface(SoT v1.6.18) + source_ref catalog anchor repair 보강(SoT v1.6.19)
- 정합 스펙 기준:
  - `docs/system-contract-sot.md` v1.6.18 / v1.6.19(변경 이력 표 + Phase 2A Application API 단락 + Phase 2A versioned provider extraction 단락)
  - `docs/plans/02-analysis-provider-wiring-decisions.md`(2026-07-01 follow-up 노트 + §5/§승인-뒤-구현-순서)
  - 교차 계약: `services/application/app/core_sot/service.py`(`create_source_ref`/`get_source_ref`/`list_source_refs`), `services/application/app/analysis/service.py::_validate_source_anchors`(기존 source validation 경계)
- 검증 대상 작업 출처: commit `ada3b39`(HEAD). working tree clean.

## Follow-up resolution

- 후속 보강일: `2026-07-01`
- 보강자: Codex
- 대상 이슈: I1 — adapter span/quote/content_hash mismatch → repair 분기가 회귀 테스트에 추적되지 않음.
- 보강 내용: `tests/test_analysis_extractor_schema.py`에 `test_versioned_prompt_adapter_repairs_catalog_anchor_drift_once`를 추가했다. 이 테스트는 catalog id는 유효하지만 anchor quote가 catalog와 다른 provider output을 준비하고, adapter가 repair를 정확히 1회 호출하며 repair prompt에 `"source_anchors must preserve catalog span, quote, and content_hash"`를 포함하는지 단언한다.
- 재실행: `python3 -m py_compile tests/test_analysis_extractor_schema.py` 통과, `python3 -m unittest tests.test_analysis_extractor_schema -v` 14개 통과, `python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_runner tests.test_application_api -v` 80개 통과, `python3 -m unittest discover tests -v` 356개 통과(37 skip), `git diff --check` 통과.
- 후속 판정: I1 폐쇄. 원 검증의 조건부 합격은 이 보강으로 합격 조건을 충족했다. 아래 원 검증 본문은 당시 판정과 근거 보존을 위해 그대로 둔다.

## Scope

정합 스펙 스코프를 SoT v1.6.18/v1.6.19 changelog 행 + 두 단락의 source_ref HTTP API bullet과 catalog anchor repair bullet로 좁혔다. 브리프가 chain하는 follow-up 노트만 포함하고, 이전 slice(v1.6.15~v1.6.17)의 이미 검증된 wiring/catalog-read/prompt 계약은 carried-forward로만 취급했다.

검증 surface:

1. 정합 계약(SoT v1.6.18/v1.6.19 + 브리프 follow-up)의 내부 정합성
2. 구현 코드: `services/application/app/main.py`(HTTP endpoints + `_source_ref_payload` + `CreateSourceRefRequest`), `services/application/app/analysis/extractor.py`(`extract` repair 흐름 + `_catalog_anchor_error`)
3. 회귀 테스트: `tests/test_application_api.py`(source_ref API 3건), `tests/test_analysis_extractor_schema.py`(`test_versioned_prompt_adapter_repairs_catalog_id_drift_once`)
4. 교차 경계: 하위 runner source validation(`analysis/service.py::_validate_source_anchors` → `InvalidCandidateSource` → `source_invalid`)과 adapter catalog check의 중복/보존 관계
5. 전체 회귀 재실행 + diff hygiene + live smoke 재현 가능성

## Methodology

정합 스펙을 먼저 end-to-end 읽어 boundary matrix를 구성한 뒤, 각 분기를 코드와 테스트에 추적했다. 작업자의 work log/HANDOFF 주장을 복사하지 않고 primary source에서 재도출했다.

실행한 명령:

- `git show --stat ada3b39`, `git show ada3b39 -- <file>`(변경 범위 + 각 파일 diff)
- `git show ada3b39 -- docs/system-contract-sot.md docs/plans/02-analysis-provider-wiring-decisions.md`(계약 diff)
- `python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_runner tests.test_application_api`(focused 3모듈 재실행)
- `python3 -m unittest discover tests`(전체 재실행)
- `git diff --check ada3b39~1 ada3b39`, `git status`(diff hygiene + clean tree)
- `python3 -m py_compile scripts/phase2a_provider_live_smoke.py services/application/app/main.py services/application/app/analysis/extractor.py`
- `grep -rn`로 CoreSotService 메서드 존재/예외 계층/정렬/에러 메시지 테스트 추적/`_validate_source_anchors` 필드 검증 범위 확인
- `Read`로 `extractor.py::extract`, `core_sot/service.py::{create,get,list}_source_ref`, `analysis/service.py::_validate_source_anchors`, 테스트 헬퍼(`_candidate`/`_anchor`)와 happy-path 테스트 본체 열독

## Findings

### Surface 1 — 정합 계약 내부 정합성

- SoT v1.6.18 changelog 행과 Phase 2A Application API 단락의 신규 bullet이 동일한 계약을 서술한다: create request는 `start_offset`/`end_offset`만 받고 Core SOT가 `quote`/`block_id`/`content_hash`를 계산, invalid span 400, missing/cross-project snapshot/ref 404, archived project 허용, non-idempotent 생성, catalog는 source order. 모순 없음.
- SoT v1.6.19 changelog 행과 versioned extraction 단락 개정이 일치한다: 첫 content가 JSON/schema는 통과했지만 `source_ref_id`/span/quote/content_hash가 catalog와 불일치하면 1회 repair 대상, repair 후에도 mismatch가 남으면 자동 보정 없이 기존 source validation이 `source_invalid` 보존.
- **교차-단락 점검**: v1.6.18이 "archived project에서도 생성·조회 허용"이라고 명시하고, v1.4 §113 구현 노트(2026-06-28 work log)도 archive를 soft-archive(`archived=True` 플래그, project/snapshot 보존)로 정의하므로 충돌 없음. `archive_project`(`service.py:423-427`)가 hard-delete가 아님을 코드로 확인.
- 브리프 §승인-뒤-구현-순서 1번이 "SourceRef catalog read + HTTP preparation surface 추가"로 개정됐고, 검증 기준에 "HTTP로 snapshot span에서 source_ref를 만들고 catalog/ref를 다시 읽는다"가 추가됐다. 계약 체인 일관됨.

### Surface 2 — HTTP API 구현 코드 vs 스펙 literal/경계

- POST handler(`main.py:504-520`)가 `core_sot.create_source_ref(project_id, snapshot_id, start_offset, end_offset)`에 위임하고 `NotFound→404`, `CoreSotError→400`으로 매핑. `InvalidSourceRef`와 `NotFound` 모두 `CoreSotError` 서브클래스(`service.py:36/40/48`)이고 handler가 `NotFound`를 먼저 잡으므로 404/400 분기 순서 정확.
- `CreateSourceRefRequest`(`main.py:199-201`)는 `start_offset`/`end_offset`만 선언 — 스펙 "start_offset, end_offset만 받으며" 일치. quote/block/content_hash는 Core SOT가 계산(`service.py:393-402`).
- `create_source_ref`(`service.py:371-405`)가 (a) snapshot 존재 + `project_id` 일치 → 아니면 `NotFound`, (b) span 정수/음수/`end<=start`/`end>len(raw_text)` → `InvalidSourceRef`, (c) span이 한 block 안에 들어가는지 → 아니면 `InvalidSourceRef`를 각각 검증. round-trip 회귀가 계산된 `quote`/`block_id`/`content_hash`를 직접 단언.
- GET list/get handler(`main.py:523-548`)가 같은 project 격리를 Core SOT에 위임. in-memory/Mongo 두 repo 모두 `(start_offset, end_offset, id)` ASC 정렬(`service.py:149-167`, `mongo_repository.py:202-213`) — "source order" 일치.

### Surface 3 — 회귀 테스트가 계약 분기를 잠그는지 (boundary matrix)

HTTP API 분기:

| 분기 | 코드 | 테스트 | 결과 |
|---|---|---|---|
| POST valid → 200 + 계산 필드 | `service.py:371-405` | `test_source_ref_create_list_get_round_trip` | ✓ pinned |
| POST invalid span(`end<=start`) → 400 | `service.py:382-389` | `test_source_ref_api_rejects_invalid_span_and_cross_project`(invalid) | ✓ pinned |
| POST cross-project snapshot → 404 | `service.py:380-381` | cross_create | ✓ pinned |
| GET list missing/cross snapshot → 404 | `service.py:416-418` | missing_list | ✓ pinned |
| GET single cross-project ref → 404 | `service.py:408-410` | cross_get | ✓ pinned |
| archived project 생성/조회 → 200 | (archive 검사 없음) | `test_source_ref_api_survives_project_archive` | ✓ pinned |
| POST beyond-text-length → 400 | `service.py:387` | (별도 테스트 없음, 400 경로 공유) | ◐ 미 pin |
| POST cross-block span → 400 | `service.py:405` | (별도 테스트 없음, 400 경로 공유) | ◐ 미 pin |
| POST missing snapshot → 404 | `service.py:380` | (POST에 대해 별도 없음; GET missing_list가 NotFound 경로 cover) | ◐ 미 pin |
| list 다중 ref source order | repo sort | (단일 ref round-trip만; 다중 정렬은 service-layer v1.6.16 테스트에 위임) | ◐ 위임 |

Catalog anchor repair 분기:

| 분기 | 코드 | 테스트 | 결과 |
|---|---|---|---|
| 첫 parse OK + id가 catalog에 없음 → 1회 repair | `extractor.py:182-184` | `test_versioned_prompt_adapter_repairs_catalog_id_drift_once`(`len(requests)==2`, repair prompt에 "source_ref_id must exactly match" 포함 단언) | ✓ pinned |
| 첫 parse OK + **id는 유효하나 span/quote/content_hash 불일치** → 1회 repair | `extractor.py:188-191` | **없음** | ✗ **UNTRACED** |
| 첫 parse OK + catalog 일치 → repair 없음(over-strict) | `extractor.py:138-140` | happy-path 테스트가 1-response provider 사용; 과잉 repair 시 `FakeProviderExhausted`로 에러(암시적 pin) | ◐ 암시적 pin |
| repair 1회만, 2회차 없음(no loop) | `extractor.py:141-148` | 위 id-drift 테스트가 `len(requests)==2`로 pin | ✓ pinned |
| repair 후에도 mismatch → draft 반환 → 하위 `source_invalid` 보존 | `extractor.py:148` | 단위 테스트는 아님; live smoke 첫 run에서 관측(HANDOFF:113). 하위 `_validate_source_anchors`가 별도 회귀로 4필드 검증 pin | ◐ live 관측 + 하위 pin |

### Surface 4 — adapter catalog check와 하위 source validation의 중복 검증

- adapter `_catalog_anchor_error`(`extractor.py:175-192`)는 `source_ref_id` 존재 + `start_offset`/`end_offset`/`quote`/`content_hash` 4필드 일치를 검사.
- 하위 `_validate_source_anchors`(`analysis/service.py:553-567`)도 **동일 4필드 + project_id**를 검사해 `InvalidCandidateSource` → runner `_failure_reason` 매핑(`runner.py:184-185`)으로 `source_invalid` 보존.
- 즉 catalog mismatch는 adapter(repair 시도)와 runner(terminal failure) **이중 경계**로 막혀 있다. 어댑터의 span/quote/hash 감지가 깨져도 부정확한 anchor가 candidate 저장소까지 도달하지 않는다. 이 점이 아래 Issues의 심각도를 완화한다.

## Issues / Risks

### I1 — adapter span/quote/content_hash mismatch → repair 분기가 회귀 테스트에 추적되지 않음 (conditional-pass 조건)

- 문제: `_catalog_anchor_error`의 두 번째 return(`"source_anchors must preserve catalog span, quote, and content_hash"`, `extractor.py:188-191`)은 `source_ref_id`가 catalog에 **있지만** span/quote/hash가 불일치할 때 발화한다. 이 분기를 exercise하는 테스트가 없다(`grep "must preserve catalog span" tests/` → NOT FOUND). id-drift(`source_ref_id`가 catalog에 없는 경우, 첫 번째 return)만 `test_versioned_prompt_adapter_repairs_catalog_id_drift_once`로 pin되어 있다.
- 원인: 신규 테스트가 `source-ref-1` → `source_ref-1` id 변형만 다루고, 동일 id에 span/quote/hash만 바뀐 케이스를 추가하지 않았다. 테스트 헬퍼 `_candidate`(`test_analysis_extractor_schema.py:29-36`)가 기본 anchor를 하드코딩하므로, 의도적으로 span/quote/hash만 어긋나게 만드는 케이스를 명시해야 한다.
- 영향/심각도(완화됨): SoT v1.6.19는 span/quote/content_hash mismatch를 "같은 1회 repair 대상"으로 명시한다. 이 감지가 회귀로 pin되지 않았으므로, 향후 누군가 `source_ref.quote != anchor.quote` 등의 조건을 제거/반전해도 **단위 테스트가 잡지 못한다**. 단, 하위 `_validate_source_anchors`가 동일 4필드를 독립 검증하므로 부정확한 anchor가 저장소까지 가지는 않는다(Surface 4). 손실되는 것은 spec이 요구하는 **repair 시도 1회**뿐이다.
- 해결 조건: id는 catalog에 있되 `start_offset`/`end_offset`/`quote`/`content_hash` 중 하나만 어긋나는 anchor를 준비해 (a) 정확히 1회 repair(`len(provider.requests)==2`), (b) repair prompt에 `"source_anchors must preserve catalog span, quote, and content_hash"` 포함을 단언하는 회귀를 추가할 것. CLAUDE.md 경계 매트릭스 규칙상 "should fire" 분기의 빈 cell은 green bar와 무관하게 차단 요소다.

### I2 — 동일 HTTP 상태코드를 공유하는 sub-branch들이 별도로 pin되지 않음 (경계 risk, 비차단)

- `beyond-text-length`(`end>len(raw_text)`), `cross-block span`(어느 block에도 안 들어감) → 400, `POST missing snapshot` → 404 sub-branch가 tested 분기와 상태코드를 공유하므로 별도 회귀가 없다. 모두 동일 `InvalidSourceRef`/`NotFound` 경로라 행동 차이는 없지만, 분기 매트릭스 관점에서는 빈 cell이다. I1보다 우선순위 낮음.

### I3 — live smoke 독립 재현 불가 (sandbox 제약)

- `scripts/phase2a_provider_live_smoke.py`는 `LLAMA_BASE_URL` 기본값 `http://192.168.1.29:9080`의 실제 llama.cpp endpoint로 외부 TCP를 열어야 한다. 본 검증 환경은 Python/httpx 외부 TCP가 차단되어 live smoke를 독립 재실행할 수 없었다(work log도 sandbox 내부 실행이 `[Errno 1] Operation not permitted`로 막혔음을 기록).
- 완화: smoke가 사용하는 HTTP source_ref 준비 경로(POST/GET)는 `test_source_ref_create_list_get_round_trip`가 동일 endpoint로 단위 cover한다. smoke의 end-to-end 가치(실제 모델)는 작업자의 documented run(HANDOFF:111/113, `run_http_status=200`, `succeeded`, candidates 3)을 신뢰한다.

## Verdict

**조건부 합격 (Conditional Pass)**

- 적격 사유(합격 방향):
  - HTTP API 3 endpoint와 boundary(valid 200 / invalid span 400 / cross-project·missing 404 / archived 허용)가 코드와 회귀로 일관되게 pin되어 있다.
  - Catalog anchor repair의 id-drift 분기와 "repair 1회만" no-loop 분기가 pin되어 있다.
  - catalog mismatch의 안전성이 adapter + 하위 `_validate_source_anchors` 이중 경계로 보장된다(Surface 4).
  - 계약(SoT v1.6.18/v1.6.19)의 내부 정합성 통과, 산출물(work log/HANDOFF/CHANGELOG/브리프)과 코드가 일치.
  - focused 79개 / 전체 355개(37 skip) / `git diff --check` / py_compile / clean tree 모두 독립 재현 확인.
- 차단 조건(I1): adapter의 **span/quote/content_hash mismatch → 1회 repair 분기**가 회귀 테스트에 추적되지 않는다. SoT v1.6.19가 이 mismatch를 명시적 repair 대상으로 규정하므로, boundary matrix의 빈 cell이다. I1의 회귀(유효 id + 단일 필드 불일치 케이스)를 추가하기 전까지는 합격으로 닫을 수 없다. 심각도는 하위 이중 경계로 완화되었으므로 "불합격"이 아닌 "조건부 합격".
- 비차단 risk: I2(동일 상태코드 sub-branch), I3(live smoke 독립 재현 불가)는 기록만 남기고 합격을 막지 않는다.

## Outstanding items

- I1 회귀 추가 전까지 본 slice는 조건부 합격 상태로 유지된다. 추가 후 본 검증 기록의 Verdict/Outstanding을 합격으로 갱신할 것.
- live smoke는 network sandbox 밖(승인된 외부 네트워크)에서만 재현 가능하므로, CI/자동화가 아닌 수동 실행 경로로 남아 있다.
- commit `ada3b39`는 local HEAD에만 있고 `git push` 대기 상태다(게시 승인은 오너 결정).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# focused 3모듈 (작업자 주장 79개)
python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_runner tests.test_application_api

# 전체 (작업자 주장 355 passed / 37 skipped)
python3 -m unittest discover tests

# diff hygiene + clean tree
git diff --check ada3b39~1 ada3b39
git status   # nothing to commit, working tree clean

# 컴파일
python3 -m py_compile scripts/phase2a_provider_live_smoke.py \
  services/application/app/main.py services/application/app/analysis/extractor.py

# I1 재현(grep): 두 번째 에러 메시지를 단언하는 테스트가 없음을 확인
grep -rn "must preserve catalog span" tests/   # → NOT FOUND

# live smoke (network sandbox 밖에서만; sandbox 내부는 provider_error로 낙하)
# python3 scripts/phase2a_provider_live_smoke.py
```
