# Verification — Phase 4 공유 in-process vector index slice (SoT v1.6.35)

## Subject metadata

- 검증일: 2026-07-05
- 요청자: owner ("클로드 검증 AI가 검증한 분에 대해서 확인하고 검증하고 의심하고 또 의심해줄래? ... 공유 in-process vector index ... 구현(SoT v1.6.35) ... 검증 ...")
- 검증자: 독립 검증 AI(Claude, 작업 AI와 다른 세션)
- 대상 slice/artifact: Phase 4 공유 in-process vector index — `services/application/app/indexing/service.py`(`rebuild_source_block_index_summary` optional `vector_index`/`embeddings` + snapshot-scope count 필터), `services/application/app/main.py`(`create_app` 단일 shared adapter 소유 + `_default_context_search_service`/`_rebuild_source_block_index_payload`에 shared 인스턴스 전달 + `vector_index` 주입 param), `tests/test_context_search_shared_index.py`(신규 3개), `docs/plans/04-shared-vector-index-decisions.md`(신규 브리프), `docs/system-contract-sot.md` v1.6.35. 브랜치 `phase4-slice-4-2-planner`, working tree(uncommitted) — 커밋/푸시 미수행.
- 정본 계약 참조:
  - `docs/plans/04-shared-vector-index-decisions.md`(상태 `Approved (2026-07-05)`) — "확정 계약" 6항(공유 인스턴스/비persistence/rebuild summary 불변/planner env 독립성/staleness 안전성/테스트 seam) + "수용 기준" 4항.
  - `docs/system-contract-sot.md` v1.6.35(changelog 36행) + §Phase 3A rebuild HTTP API(367행, snapshot scope 문구 추가) + §Phase 4(378행, v1.6.35 라인).
  - 선행 계약: SoT v1.6.22(CLI rebuild summary "누적 없음"), v1.6.23(HTTP rebuild summary), v1.6.24(`validate_source_block_record` stale guard 6 reason), v1.6.31/34(context search domain + HTTP API).
- 검증 대상 작업 출처: branch `phase4-slice-4-2-planner` working tree(uncommitted). `git diff --stat`: `service.py` 31행 / `main.py` 31행 / SoT 8행 / HANDOFF 6행 / CHANGELOG 2행 변경 + 신규 3개 파일(브리프, work_log, 회귀).

## Scope

1. 계약 스코핑 — 브리프 "확정 계약" 6항 + "수용 기준" 4항 → SoT v1.6.35 changelog + §Phase 3A/§Phase 4 해당 라인만 종단 독해. §8 real backend / prior-memory / tool-call planner는 스코프 밖.
2. 계약 자기 일관성 — 브리프 내부, 브리프↔SoT v1.6.35, 브리프↔선행 v1.6.22/23/24 "누적 없음"/stale guard 계약 간 모순 탐지.
3. 구현-계약 리터럴 일관성 — shared adapter 소유, `backend="in_memory_fake"`, optional `vector_index`/`embeddings`, snapshot-scope count 필터, env 무관 생성, planner 미구성 503이 코드에 paraphrase 없이 존재하는지.
4. boundary matrix 구축 — should-fire / should-NOT-fire / under-strict(양방향) 각 cell을 특정 회귀에 매핑; 빈 셸 탐지.
5. mutation testing(핵심) — (A) shared wiring 제거, (B) **snapshot-scope 필터 제거**(이 slice가 새로 넣은 코드; 작업자 mutation 증명에 포함되어 있지 않음), 각각 re-fail 실증.
6. suite 카운트 + envelope 주장 독립 재현 — 작업자 주장(473 OK/44 skip, pytest 429 passed/44 skip, py_compile, git diff --check).
7. 오류/위험 — 비durable memory 누적, archive mutation 미수신 의도성, pytest collection warning.

## Methodology

- 계약 스코프 먼저 좁힘: 브리프 6항 + 4 수용기준 + SoT v1.6.35 changelog/§Phase 3A rebuild/§Phase 4 + 선행 v1.6.22/23/24만 종단 독해.
- boundary matrix 구축 후 각 cell을 신규 3개 회귀 + 기존 rebuild/planner 회귀에 수동 매핑.
- **경험적 mutation testing**(핵심): `main.py`/`service.py`를 `/tmp`에 cp 백업 → Edit로 guard 무력화 → `python3 -m unittest tests.test_context_search_shared_index -v` 재실행 → re-fail 수/메시지 기록 → 백업에서 cp 복원 → diff stat가 원본과 동일한지 확인.
  - Mutation A: `_rebuild_source_block_index_payload`에서 `vector_index=`/`embeddings=` 주입 2행 제거(throwaway fallback 유도).
  - Mutation B: `rebuild_source_block_index_summary`의 `all_records`/`visible_records`에서 `if record.snapshot_id == snapshot_id` 필터 제거(project 전체 누적 유도).
- 테스트 실행: `python3 -m py_compile`, `python3 -m unittest discover tests`, `python3 -m pytest -q`, `git diff --check`.
- 문서 정합: `git diff docs/system-contract-sot.md`로 changelog/§Phase 라인이 브리프와 일치하는지 교차 검증.

사용한 정확한 명령은 §Reproduction에 열거.

## Findings

### 1. 계약 자기 일관성 — 부합 (내부 모순 없음)

- 브리프 "확정 계약" §1(공유 인스턴스) ↔ §3(rebuild summary snapshot scope) ↔ §2(비persistence, `backend` literal `in_memory_fake`)가 상호 모순 없이 연결됨. §3가 "공유 index가 누적하더라도 summary count는 snapshot_id로 scope"로 §1의 누적과 §2의 불변을 조화시킴.
- 브리프 §3 "v1.6.23 rebuild summary 계약과 Slice 4.3가 잠근 '누적 없음' 회귀는 불변" ↔ SoT v1.6.35 changelog "누적은 뒤에서만 일어난다" ↔ 선행 v1.6.22/v1.6.23 "누적 없음" 계약 — 일관.
- 브리프 §5 "공유 adapter는 fake archive mutation을 받지 않지만 query-time 재검증이 방어선" ↔ 선행 v1.6.24 `validate_source_block_record` 6 reason stale guard ↔ §수용기준 A3(rebuild 후 archive 시 제외) — 일관. archive mutation 미수신이 "누락"이 아니라 의도적 설계로 명시됨.
- 브리프 §4 "LLM_GATEWAY_BASE_URL 유무와 무관하게 항상 생성, planner 미구성 시 /context-search만 503" ↔ SoT v1.6.35 changelog 동일 문구 — 일관.
- SoT §Phase 3A rebuild HTTP 라인(367행)이 "v1.6.35부터 이 endpoint는 create_app이 소유한 공유 in-process vector index에 write하지만 ... summary count는 snapshot_id로 scope"로 갱신됨 — 브리프 §3와 일치. §Phase 4(378행)에 v1.6.35 라인 추가 — 일치.
- 내부 모순 탐지: 없음.

### 2. 구현-계약 리터럴 일관성 — 부합

- **공유 인스턴스**(브리프 §1): `create_app`이 `shared_vector_index = vector_index if vector_index is not None else InMemoryVectorIndexAdapter()` + `shared_embeddings = DeterministicFakeEmbeddingProvider()`를 소유(`main.py:323-324`). rebuild endpoint는 `vector_index=shared_vector_index, embeddings=shared_embeddings` 전달(`main.py:417-418`); default context search wiring도 동일 인스턴스 전달(`main.py:327-331`). `_default_context_search_service`는 같은 `vector_index`를 `vector_search`(query)와 `indexing_service`(stale guard) 양쪽에 연결(`main.py:245-256`) → rebuild write ↔ context search read 동일 store.
- **비persistence + backend literal**(브리프 §2): shared adapter는 `InMemoryVectorIndexAdapter()`(`main.py:323`); `backend`는 `summary.to_dict(backend=FAKE_VECTOR_BACKEND)`(`main.py:420`)이고 `FAKE_VECTOR_BACKEND = "in_memory_fake"`(`service.py:35`). paraphrase 없음.
- **rebuild summary snapshot scope**(브리프 §3, 이 slice의 핵심 코드 변경): `all_records`/`visible_records`가 `record.snapshot_id == snapshot_id`로 필터(`service.py:490-501`). throwaway 경로에서는 adapter가 해당 snapshot만 담으므로 값 동일, 공유 경로에서도 같은 값을 냄 — 브리프 §3 서술과 정확히 일치.
- **optional vector_index/embeddings**(브리프 §6 테스트 seam + CLI 비지속 유지): `rebuild_source_block_index_summary(*, ..., vector_index: InMemoryVectorIndexAdapter | None = None, embeddings: EmbeddingProvider | None = None)`(`service.py:462-469`). 미제공 시 `InMemoryVectorIndexAdapter()` throwaway + `DeterministicFakeEmbeddingProvider()`(`service.py:477-480`) — CLI script 비지속 유지 계약 일치.
- **planner env 독립성**(브리프 §4): `shared_vector_index`/`shared_embeddings`는 `create_app` 본문에서 env 조회 없이 항상 생성(`main.py:323-324`); `_default_context_search_service`는 `if not base_url: return None`(`main.py:223-225`); endpoint는 `context_search is None → 503`(`main.py:880-884`). rebuild는 env 무관 동작, /context-search만 env 의존 — 일치.
- **테스트 seam param**: `create_app(..., vector_index: InMemoryVectorIndexAdapter | None = None)`(`main.py:309`) — 브리프 §6 일치.

### 3. boundary matrix — 모든 cell lock, 빈 cell 없음

| cell | 계약 조항 | 방향 | lock 회귀 | 비고 |
|---|---|---|---|---|
| shared write→read hit | §1, 수용기준 A1 | should-fire | `test_rebuild_endpoint_populates_index_queried_by_context_search`(before empty → after non-empty, `sot_reloaded=True`) | ✓ |
| summary snapshot scope | §3, A2 | should-NOT-fire(누적 없음) | `test_rebuild_summary_stays_snapshot_scoped_when_index_accumulates`(`first==first_again`, `< total`) | ✓ |
| summary snapshot scope under-strict | §3 | under-strict | **Mutation B 직접 증명**(6≠15 re-fail) | ✓ verifier 보강 |
| archive 후 hit 제외 | §5, A3 | should-fire | `test_archived_draft_hit_excluded_by_stale_guard`(archive 후 `micro_evidence == []`) | ✓ |
| shared wiring under-strict | §1 | under-strict | Mutation A 직접 증명(2 re-fail) — 작업자 주장 재현 | ✓ |
| backend literal | §2 | literal | `test_application_api` `backend: in_memory_fake`(828행 회귀) | ✓ 기존 |
| env 무관 rebuild | §4 | should-fire | `test_application_api` rebuild 회귀 3종이 `create_app()`(env 없음)로 app 생성 | ✓ 간접 |
| planner 미구성 503 | §4 | should-fire | `test_context_search_api`(v1.6.34) | ✓ 기존 |
| 새 인스턴스 빈 index(비durable) | A4 | should-fire | `test_..._populates_index...` before 검증 + `_shared_app()` 매번 새 adapter/app | ✓ 간접 |
| throwaway fallback(CLI 비지속) | §3, §6 | should-fire | `test_phase3a_rebuild_source_block_index_script`(`vector_index` 미전달 경로) | ✓ 기존 |
| 정상 케이스 over-strict | — | over-strict | shared wiring 정상일 때 after non-empty 통과 | ✓ |

boundary matrix에 빈 cell 없음. 단, 아래 §4에서 작업자 mutation 증명 범위의 불완전성을 별도로 다룸.

### 4. mutation testing — 양 mutation 모두 re-fail 실증 (B는 verifier가 보강)

| mutation | 무력화 대상 | 결과 | 의미 |
|---|---|---|---|
| **A** shared wiring 제거 | `_rebuild_source_block_index_payload`에서 `vector_index=`/`embeddings=` 주입 제거 → throwaway adapter | **2 re-fail**(test 1·3, `AssertionError: [] is not true`) | under-strict guard ✓ — 작업자 주장(`micro_evidence == []` 2개 재실패) 정확히 재현 |
| **B** snapshot-scope 필터 제거 | `all_records`/`visible_records`에서 `snapshot_id` 필터 제거 → project 전체 누적 | **1 re-fail**(test 2, `AssertionError: 6 != 15`) | under-strict guard ✓ — first_again이 A+B 누적(15) 반환해 `first==first_again`(6) 위반 |

- Mutation A는 작업자 work_log/HANDOFF에 명시된 증명과 동일(`micro_evidence == []` 2개 재실패). 재현 확인.
- **Mutation B는 작업자가 명시적으로 증명하지 않은 영역**이다. work_log "Mutation 실증" 항목은 "rebuild payload에서 공유 vector_index/embeddings 주입 제거 시 2개 재실패"만 기록하고, 이 slice가 새로 넣은 핵심 코드인 snapshot-scope 필터(`service.py:490-501`)의 무력화 mutation은 빠져 있다. 다만 회귀 `test_rebuild_summary_stays_snapshot_scoped_when_index_accumulates` 자체는 존재하고, verifier가 Mutation B로 re-fail을 직접 실증했으므로 boundary는 lock되어 있다. 즉 **빈 셸이 아니라, 작업자 mutation 증명의 범위가 불완전했을 뿐**이다. 차단 사유는 아니나 향후 slice 교훈으로 기록 가치(§Issues/Risks #2).
- 복원 검증: 두 mutation 모두 `/tmp` 백업에서 cp 복원 후 `git diff --stat`가 원본(service.py 31 / main.py 31)과 동일한 것을 확인했고, 3개 회귀가 다시 통과함.

### 5. suite 카운트 + envelope 주장 독립 재현 — 부합

- `python3 -m py_compile services/application/app/main.py services/application/app/indexing/service.py tests/test_context_search_shared_index.py` → OK.
- `python3 -m unittest tests.test_context_search_shared_index -v` → Ran 3, OK.
- `python3 -m unittest discover tests` → **Ran 473, OK (skipped=44)** — 작업자 주장(473 OK/44 skip) 재현.
- `python3 -m pytest -q` → **429 passed, 44 skipped** — 작업자 주장(429 passed/44 skip) 재현.
- `git diff --check` → 통과(working tree 변경에 whitespace 오류 없음).
- 관련 묶음 `tests.test_context_search_shared_index tests.test_application_api tests.test_phase3a_rebuild_source_block_index_script` → 56개 통과(rebuild 전·후 경로 + throwaway CLI 경로 + env 없는 create_app 경로 포함).

## Issues / Risks

1. **(비차단, 품질) pytest collection warning** — `tests/test_context_search_shared_index.py`의 HTTP helper class `TestClient`(`test_context_search_shared_index.py:46`)가 pytest `Test*` naming convention에 걸려 수집을 시도했다가 `__init__` 생성자 때문에 `PytestCollectionWarning: cannot collect test class 'TestClient'` 2건(클래스 + 모듈) 발생. 기능 영향은 없음(수집 실패로 무시되고, 실제 3개 `SharedVectorIndexTest` 회귀는 정상 수행됨 — pytest 429 passed에 포함). 기존 파일(`test_context_search_api.py` 등)의 동명 helper 관행을 따른 것으로 보이나, 향후 helper 이름을 `HttpTestClient` 등으로 바꾸면 warning이 사라짐. 계약 위반 아님.

2. **(비차단, 검증 방법론 관찰) 작업자 mutation 증명 범위 불완전** — 작업자는 shared wiring에 대한 mutation만 증명했고, 이 slice가 새로 넣은 snapshot-scope 필터(`service.py:490-501`)에 대한 mutation은 누락했다. 결과적으로 boundary 자체는 회귀로 lock되어 있고(verifier가 Mutation B로 re-fail 실증), "빈 셸"은 아니다. 그러나 "새로 추가된 guard마다 mutation을 돌린다"는 원칙이 지켜지지 않았다. 차단 사유는 아니나, 이 slice의 핵심 계약 변경(snapshot scope)이 re-fail로 직접 증명되지 않은 채 작업자 자체 검증이 종료되었기 때문에 verifier가 보강 확인했다. 향후 slice에서 mutation 범위를 "이 slice가 새로 넣은 모든 guard"로 확대할 것을 권고.

3. **(비차단, 설계 의도 확인) shared index의 archive record 누적** — `InMemoryVectorIndexAdapter`는 `mark_archived`를 갖지 않고(archive mutation은 별도 `RecordingArchiveIndexMutationAdapter`/outbox 경로), archive endpoint는 vector index를 직접 수정하지 않는다(`main.py:478-490`는 `sync_outbox.enqueue_*`만). 따라서 archive 후에도 shared index에 record가 남지만, query-time `validate_source_block_record`(`service.py:563-599`)가 SOT 재조회로 `draft_archived`/`project_archived`를 잡아 결과에서 제외한다. 브리프 §5가 이것을 명시적 설계로 서술하므로 결함이 아니다. 다만 프로세스 수명 동안 stale record가 in-memory dict에 누적되는 점은 비durable(재시작 소실) 성질로 흡수되므로 운영상 메모리 누수 위험은 낮다.

4. **(out of scope, not a defect) deployed smoke 미실행** — `scripts/phase4_context_search_deployed_smoke.py`가 rebuild를 호출하지 않아, 배포 환경에서 공유 index vector hit을 관통 검증하려면 rebuild→context-search 2-step 확장 또는 수동 실행이 필요하다. HANDOFF Next Tasks 1에 이미 후속으로 기록되어 있고, 본 검증은 코드/회귀 단위 검증이 목적이므로 본 slice의 합격 여부와 무관하다.

## Verdict

**합격.**

load-bearing 이유:
- 계약 자기 일관성(브리프 6항 + 수용기준 4항 ↔ SoT v1.6.35 ↔ 선행 v1.6.22/23/24)에 내부 모순 없음.
- 구현-계약 리터럴 일관성: shared adapter 소유, `backend="in_memory_fake"`, optional `vector_index`/`embeddings`, snapshot-scope count 필터, env 무관 생성, 503 매핑이 모두 코드에 paraphrase 없이 존재.
- boundary matrix의 모든 cell이 특정 회귀에 매핑되고 빈 cell 없음.
- mutation testing 양방향 실증: Mutation A(shared wiring, 작업자 주장 재현) 2 re-fail + Mutation B(snapshot-scope 필터, verifier 보강) 1 re-fail. 이 slice의 두 핵심 코드 경로(shared wiring + snapshot scope)가 모두 under-strict로 lock됨.
- suite 카운트(473 OK/44 skip, pytest 429 passed/44 skip), py_compile, git diff --check 모두 독립 재현.

조건 사유: 없음. 비차단 관찰(pytest collection warning, 작업자 mutation 범위 불완전→verifier 보강 완료, archive record 누적 설계 의도)은 합격을 뒤집지 않는다.

## Outstanding items

- **커밋/푸시 미수행**: 작업 전체가 working tree(uncommitted). owner 요청 시 진행. 본 검증은 working tree 상태 기준.
- **deployed smoke 확장**: `scripts/phase4_context_search_deployed_smoke.py`에 rebuild 단계를 추가해 배포 환경에서 공유 index vector hit을 관통 검증하는 것은 HANDOFF Next Tasks 1의 후보로 남아 있음(sandbox 밖 승인 네트워크 필요). 본 검증과 무관.
- **선행 검증의 빈 셸 폐쇄 상속 없음**: 본 slice는 직전 검증(`docs/verifications/2026-07-04/context_search_slice_4_3.md`)의 차단 조건을 상속받지 않는 독립 slice(4.3의 빈 셸 2종은 이미 커밋 `f8699a7`로 폐쇄됨).

## Reproduction

```bash
# 1. 컴파일 + 신규 회귀
python3 -m py_compile services/application/app/main.py services/application/app/indexing/service.py tests/test_context_search_shared_index.py
python3 -m unittest tests.test_context_search_shared_index -v   # Ran 3, OK

# 2. 전체 suite (473 OK / 44 skip, pytest 429 / 44 skip)
python3 -m unittest discover tests                                # Ran 473, OK (skipped=44)
python3 -m pytest -q                                              # 429 passed, 44 skipped

# 3. 관련 묶음 (rebuild 전·후 + throwaway CLI + env 없는 create_app 경로)
python3 -m unittest tests.test_context_search_shared_index tests.test_application_api tests.test_phase3a_rebuild_source_block_index_script -v   # 56 passed

# 4. whitespace 검사
git diff --check

# 5. Mutation A — shared wiring 제거 → 2 re-fail
cp services/application/app/main.py /tmp/main.py.bak
# Edit: _rebuild_source_block_index_payload에서 vector_index=shared_vector_index, embeddings=shared_embeddings 2행 제거
python3 -m unittest tests.test_context_search_shared_index -v   # 2 failures (test 1·3, micro_evidence == [])
cp /tmp/main.py.bak services/application/app/main.py             # 복원

# 6. Mutation B — snapshot-scope 필터 제거 → 1 re-fail (verifier 보강)
cp services/application/app/indexing/service.py /tmp/service.py.bak
# Edit: rebuild_source_block_index_summary의 all_records/visible_records에서 "if record.snapshot_id == snapshot_id" 필터 제거
python3 -m unittest tests.test_context_search_shared_index -v   # 1 failure (test 2, 6 != 15)
cp /tmp/service.py.bak services/application/app/indexing/service.py   # 복원

# 7. 복원 확인
git diff --stat services/application/app/indexing/service.py services/application/app/main.py   # service.py 31 / main.py 31 (원본 동일)
python3 -m unittest tests.test_context_search_shared_index                                      # Ran 3, OK
```
