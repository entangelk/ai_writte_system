# Phase 3A Deployed Rebuild Smoke 독립 검증

## Subject metadata

- 검증일: `2026-07-02`
- 요청자: 프로젝트 오너("클로드 작업 AI가 작업한 분 확인하고 검증하고 의심하고 또 의심해줄래? … Phase 3A rebuild의 deployed smoke를 추가했습니다")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상: Phase 3A 후속 slice — `scripts/phase3a_deployed_rebuild_smoke.py` + `tests/test_phase3a_deployed_rebuild_smoke_script.py`(6개 회귀) + 4개 doc 갱신(HANDOFF/CHANGELOG/work_log/plans)
- 정합 스펙 기준:
  - `docs/plans/03-indexing-kickoff-decisions.md` §구현 후속 — deployed rebuild smoke(신규 단락)
  - `docs/plans/03-indexing.md` 2026-07-02 slice 노트의 deployed smoke 문장
  - 교차 계약(직전 slice): `scripts/phase3a_rebuild_source_block_index.py`(CLI summary 8-field, SoT v1.6.22), HTTP endpoint `main.py:565` + `_rebuild_source_block_index_payload`(`main.py:296`, 9-field, `backend="in_memory_fake"`), `indexing/service.py::rebuild_source_block_index_summary`·`SourceBlockIndexRebuildSummary.to_dict`(`service.py:72-129`), `FAKE_VECTOR_BACKEND="in_memory_fake"`(`service.py:20`)
- 검증 대상 작업 출처: working tree, uncommitted. `git status`로 `scripts/phase3a_deployed_rebuild_smoke.py`, `tests/test_phase3a_deployed_rebuild_smoke_script.py` untracked, 5개 doc modified 확인.

## Scope

정합 스펙 스코프를 (1) kickoff 브리프 §구현 후속 — deployed rebuild smoke, (2) `03-indexing.md` slice 노트의 deployed smoke 문장로 좁혔다. smoke가 비교 대상으로 삼는 CLI/HTTP summary 계약은 직전 slice의 committed 상태를 기준으로 삼고, CLI summary(8-field) ↔ HTTP summary(9-field, `backend`)의 의도적 divergence와 `_comparable_summary`가 `backend`를 제외하는 정합성을 교차 점검했다.

검증 surface:

1. 정합 계약(kickoff §구현 후속 + slice 노트) 내부 정합성 + summary literal 일치
2. 구현 코드: `run_deployed_smoke`(snapshot 준비 + HTTP rebuild 호출), `run_live`(`--mongo-uri` 있으면 CLI rebuild 경로 비교), `terminal_status`(http/cli completeness + summaries_match), `_comparable_summary`(비교 field set)
3. 교차 정합: CLI summary(8-field, `backend` 없음) ↔ HTTP summary(9-field, `backend="in_memory_fake"`) divergence 문서화 여부, `_comparable_summary`의 `backend` 제외 정합성, fake-adapter 비지속성
4. 회귀 테스트: `tests/test_phase3a_deployed_rebuild_smoke_script.py` 6개 — HTTP-only 성공, optional CLI summary comparison match, mismatch `terminal_status` False / exit 1, main exit rule, file-path invocation import
5. 작업자 주장 카운트 재현 + 전체 suite + py_compile + `git diff --check` + 실제 compose live smoke

## Methodology

정합 스펙을 읽어 boundary matrix를 구성한 뒤 코드/테스트에 추적. 작업자 주장을 복사하지 않고 재실행·재도출. envelope 카운트는 실제 live compose stack 호출로 입증.

실행한 명령:

- `git status`, `git diff --stat`, `git diff HANDOFF.md CHANGELOG.md docs/plans/03-indexing*.md docs/daily_logs/2026-07-02/work_log.md`(doc diff 전량)
- `Read`로 신규 script·신규 테스트 본체 전량 열독; serena symbolic로 `_rebuild_source_block_index_payload`·`SourceBlockIndexRebuildSummary.to_dict`·`rebuild_source_block_index_summary`·`FAKE_VECTOR_BACKEND` 본체 확보
- `python3 -m py_compile scripts/phase3a_deployed_rebuild_smoke.py tests/test_phase3a_deployed_rebuild_smoke_script.py`
- `python3 -m unittest tests.test_phase3a_deployed_rebuild_smoke_script -v`(6), `+ test_phase3a_rebuild_source_block_index_script + test_application_api + test_indexing_phase3a`(68), `python3 -m unittest discover tests`(381/37) 재실행
- `git diff --check`
- `docker compose ps`(stack health), 컨테이너 내 `grep -c "index/source-blocks/rebuild" services/application/app/main.py`(route baked 여부)
- live HTTP+CLI smoke: `python3 scripts/phase3a_deployed_rebuild_smoke.py --application-base-url http://127.0.0.1:8010 --mongo-uri "mongodb://127.0.0.1:27029/?replicaSet=rs0&directConnection=true"`
- live HTTP-only smoke(상동, `--mongo-uri` 없음)
- live 404 boundary: `curl -X POST …/snapshots/<존재하지 않는 id>/index/source-blocks/rebuild`

## Findings

### 1. 정합 계약 내부 정합성 + summary literal

- kickoff §구현 후속 — deployed rebuild smoke가 기술하는 surface(이미 떠 있는 HTTP endpoint로 snapshot 준비 → HTTP rebuild 실행, `--mongo-uri` 시 CLI 경로 비교, persistent backend 추가 않음)는 구현과 일치한다.
- slice 노트의 "두 public summary를 비교한다" / "핵심 count/pointer field가 일치하는지 비교한다"는 `_comparable_summary`(`scripts/phase3a_deployed_rebuild_smoke.py:176-188`)가 비교하는 8개 field(project_id, snapshot_id, target, records_attempted, records_written, records_indexed, records_query_visible, records_archived)와 정합. `backend`는 count/pointer field가 아니므로 제외 대상이며, 이는 CLI summary(8-field, `backend` 없음)와 HTTP summary(9-field, `backend`)를 비교 가능하게 만드는 유일한 정합 해석이다. 계약 내부 충돌 없음.

### 2. 구현 코드 — run_deployed_smoke / run_live / _comparable_summary

- `run_deployed_smoke`(`:56-101`): `POST /projects` → `POST /projects/{id}/drafts` → `POST /projects/{id}/drafts/{id}/versions`(`idempotency_key="phase3a-smoke-save-1"`)로 snapshot id를 확보한 뒤 `POST /projects/{id}/snapshots/{snapshot_id}/index/source-blocks/rebuild`를 호출한다. 각 응답은 `_json`(`:167-173`)이 `raise_for_status` + dict 검증으로 받는다. CLI 비교는 `cli_rebuild_fn` 주입 시에만 수행, `summaries_match`는 CLI가 없으면 `None`이다. 절차·literal 모두 계약과 일치.
- `run_live`(`:104-128`): `--mongo-uri`가 있으면 `_core_sot_from_mongo`(`:154-164`, `MongoCoreSotRepository.from_uri`)로 CoreSotService를 만들고 `scripts/phase3a_rebuild_source_block_index.rebuild_source_block_index`를 `cli_rebuild_fn`으로 감싼다. HTTP-only 모드와 CLI 비교 모드가 같은 `run_deployed_smoke` 경로를 탄다. `trust_env=False`로 proxy 환경 영향을 차단한다.
- `_comparable_summary`(`:176-188`): `backend`를 제외한 8-field dict로 정규화. CLI summary(`to_dict()` 호출, `backend=None`)와 HTTP summary(`to_dict(backend=FAKE_VECTOR_BACKEND)`) 모두 동일 8-field를 가지므로 정합 비교가 성립한다.

### 3. 교차 정합 — CLI/HTTP summary divergence + fake-adapter 비지속성

- CLI summary는 `backend` 없음(`scripts/phase3a_rebuild_source_block_index.py:66-72`가 `summary.to_dict()` 호출), HTTP summary는 `backend="in_memory_fake"`(`main.py:304`가 `to_dict(backend=FAKE_VECTOR_BACKEND)`). 이 divergence는 직전 검증(`phase3a_rebuild_http_api.md`)에서 합격 판정된 의도적 차이이며, 본 smoke는 `_comparable_summary`로 이를 정합 처리한다.
- fake-adapter 비지속성: HTTP rebuild와 CLI rebuild는 각기 별도 `InMemoryVectorIndexAdapter` 인스턴스(`rebuild_source_block_index_summary` 내부에서 `service.py:101` 매 생성)를 쓰므로, 두 summary의 counts가 같은 것은 "같은 snapshot에서 같은 deterministic 절차로 동일 count가 재현됨"의 확인이지 공유 상태 공유가 아니다. 이는 kickoff 브리프가 smoke의 목적으로 서술한 "live Mongo runtime에서 재현 가능한지"와 일치.

### 4. 회귀 테스트 — boundary matrix 추적 결과 (⚠️ 일부 미잠금)

boundary matrix(terminal_status의 should-fire 분기):

| 분기 | 기대 | 추적 테스트(단독 실패 인자) | 상태 |
|---|---|---|---|
| HTTP-only, 전부 기록 → exit 0 | yes | `test_run_deployed_smoke_rebuilds_over_http`, `test_main_prints_summary_and_uses_terminal_exit_rule` | ✅ |
| HTTP-only partial(attempted≠written) → exit 1 | yes | 없음 | ⚠️ 미잠금 |
| summaries_match=False → terminal False / exit 1 | yes | `test_terminal_status_rejects_cli_http_summary_mismatch`(http_complete=T, cli_complete=T, match=F → F), `test_main_returns_one_when_cli_summary_does_not_match` | ✅ |
| CLI partial(attempted≠written, 단독) → exit 1 | yes | 없음(match=False와 동시 발생만) | ⚠️ 미잠금 |
| CLI 없을 때 summaries_match=None | yes | `test_run_deployed_smoke_rebuilds_over_http`(`assertIsNone`) | ✅ |
| file-path invocation import | yes | `test_script_file_path_invocation_can_import_repo_packages` | ✅ |

- 인용한 검증: `terminal_status`(`scripts/phase3a_deployed_rebuild_smoke.py:131-138`)의 CLI 경로는 `http_complete and cli_complete and summary["summaries_match"]`. `_summary()` fixture(`tests/...:181-192`)는 항상 `records_attempted=2, records_written=2`이므로 **어떤 테스트에서도 `http_complete=False`가 발생하지 않는다.** `http_complete` 검사를 제거/상수 True화해도 6개 테스트 전부 통과한다.
- `cli_complete=False`는 `test_main_returns_one_when_cli_summary_does_not_match`(`tests/...:139-157`, cli `records_written=1`)에서 나타나나, 같은 fixture가 `summaries_match=False`(`:148`)도 동시에 설정한다. `terminal_status`에서 `cli_complete` 검사를 제거해도 `summaries_match=False`가 exit 1을 유발해 테스트가 여전히 통과한다. 즉 `cli_complete` 분기는 단독 실패 인자로 잠기지 않았다.
- 단, **상류 CLI rebuild script의 자체 `terminal_status`는 partial-write를 양방향으로 잠갔다**: `tests/test_phase3a_rebuild_source_block_index_script.py:38-44` `test_terminal_status_requires_full_write_count`가 `assertTrue(2/2)` + `assertFalse(2/1)`. 본 smoke가 이 helper를 재사용하지 않고 `terminal_status`를 재구현한 것이 미잠금의 구조적 원인이다.
- 완화 맥락: 현 deterministic in-memory fake adapter는 partial write를 발생시키지 않으므로 런타임에 `http_complete`/`cli_complete`가 False가 될 경로가 현재는 없다(persistent backend 도입 전까지 사실상 사후 방어). 그러나 해당 검사는 smoke의 공개 envelope(0=pass, 1=mismatch 또는 incomplete) 계약 코드이므로 boundary-matrix 규칙상 untraced "should fire" 분기다.

### 5. 작업자 주장 카운트 재현 + 전체 suite + 정적 검증

| 항목 | 작업자 주장 | 재실행 결과 | 일치 |
|---|---|---|---|
| focused 신규 테스트 | 6 통과 | `Ran 6 tests` OK | ✅ |
| 관련 묶음 | 68 통과 | `tests.test_phase3a_deployed_rebuild_smoke_script + test_phase3a_rebuild_source_block_index_script + test_application_api + test_indexing_phase3a` → `Ran 68 tests` OK | ✅ |
| 전체 discover | 381 / 37 skip | `Ran 381 tests` OK (skipped=37) | ✅ |
| py_compile(신규 2파일) | 통과 | OK | ✅ |
| `git diff --check` | 통과 | clean | ✅ |

### 6. 실제 compose live smoke 재현

- `docker compose ps`: `application`(8010→8000, healthy), `gateway`(8011→8001, healthy), `mongo`(27029→27017, healthy). 작업자 주장 포트와 일치.
- 컨테이너 내 route baked 확인: `grep -c "index/source-blocks/rebuild" services/application/app/main.py` → `1`. 실행 중이던 image가 rebuild endpoint 포함 현재 코드로 rebuild됨을 확인(신규 script 자체는 host-side이므로 컨테이너에 없는 것이 정상; Dockerfile은 `services/`만 COPY).
- HTTP+CLI smoke: `summaries_match=true`; http_summary `backend="in_memory_fake"`, `records_attempted=2`/`records_written=2`/`records_indexed=2`/`records_query_visible=2`/`records_archived=0`; cli_summary 동일 8 counts(`backend` 없음); exit 0.
- HTTP-only smoke(`--mongo-uri` 없음): `summaries_match=None`, `cli_summary=None`, exit 0.
- 404 boundary: 존재하지 않는 snapshot으로 rebuild → HTTP 404.

## Issues / Risks

1. **(경계 미잠금, 조건부) smoke 자체 `terminal_status`의 partial-write 분기 2개 미잠금** — `http_complete=False`(단독)와 `cli_complete=False`(단독)가 should-fire 분기임에도 어떤 테스트의 단독 실패 인자로 잠기지 않았다. 상류 CLI script의 `terminal_status`는 양방향으로 잠갔으나 본 smoke가 이를 재사용하지 않고 재구현했다. 현 fake adapter로는 partial write가 발생하지 않아 실발현 가능성은 낮으나, 계약 코드로서 untraced 분기다. 해소 조건: (a) `http_summary.records_attempted != records_written`을 단독 실패 인자로 하는 회귀 추가 + `cli_complete`만 False인 회귀 추가, 또는 (b) smoke의 `terminal_status`를 상류 공통 helper로 통합해 partial-write 계약을 상속.
2. **(비블로킹, 구조 관찰)** `terminal_status` 재구현이 곧 이슈 1의 원인. 직전 검증 권고 O1(summary 빌드 공통화)은 이행됐으나 terminal-status 공통화는 누락됐다. persistent backend 도입 시 3곳(script/HTTP/smoke)의 completeness 판정이 따로 놀 위험이 있다.
3. **(비블로킹, 계약 under-specification)** `_comparable_summary`의 비교 field set이 code-defined다. 단 kickoff 문구("핵심 count/pointer field")와 정합하므로 진성 gap은 아니다.
4. **(비블로킹, 재현 메모)** 작업자는 `--mongo-uri 'mongodb://localhost:27029/?directConnection=true'`(replicaSet 생략), 검증자는 `?replicaSet=rs0&directConnection=true` 사용. 둘 다 동작. host client가 `mongo:27017`을 해석 못하므로 directConnection이 필요하다는 점은 양쪽 모두 동일.

## Verdict

**조건부 합격.**

하중 이유(합격 측):
- 정합 계약(kickoff §구현 후속 + slice 노트) ↔ 구현 literal 전부 일치. route path·9-field HTTP summary·8-field CLI summary·`backend` divergence 처리 모두 정합.
- 작업자 주장 카운트(focused 6 / 묶음 68 / discover 381+37 / py_compile / `git diff --check`)를 전부 재현.
- 실제 compose live smoke(HTTP+CLI)가 `summaries_match=true`, counts 2/2/2/2, exit 0으로 재현; HTTP-only 모드와 404 boundary도 live 확인.
- 4개 doc(HANDOFF/CHANGELOG/work_log/plans)이 상호 일관되고 코드·재검증과 일치하며, 첫 smoke 404 → `docker compose up -d --build application` 후 통과라는 경위까지 정직하게 기록.

조건(불합격 인자는 아님, boundary-matrix 규칙상 조건부):
- smoke 자체 `terminal_status`의 partial-write 분기 2개(`http_complete` 단독, `cli_complete` 단독)가 untraced "should fire" 분기다. 이 잠금이 추가되거나 상류 공통 `terminal_status`로 통합되기 전까지는 full 합격으로 올리지 않는다. 현 fake adapter로는 partial write가 발생하지 않아 즉시 영향은 없으므로, 오너 판단으로 후속 보강으로 연기 가능하다(이 경우 조건은 "추가 보강 예정"으로 남김).

> **Update (2026-07-02, 후속 slice `ed35ca8`/`3bce5d8` 검증 시 폐쇄 확인)** — 위 조건부 사유가 **폐쇄**됐다. commit `ed35ca8`에서 단독 회귀 2건이 추가됐고, `terminal_status` 본체는 불변이다:
> - `test_terminal_status_rejects_http_partial_without_cli`: `http_complete=False` 단독(cli 없음) → False. Gap 1 폐쇄.
> - `test_terminal_status_rejects_cli_partial_even_when_summaries_match`: `cli_complete=False` 단독(`summaries_match=True`) → False. Gap 2 폐쇄.
>
> deployed smoke 모듈 6→8, 전체 discover 381→388. 본 판정은 **full 합격으로 승격**된다. 폐쇄 재확인 상세는 `docs/verifications/2026-07-02/phase3a_stale_validation.md` §7.

## Outstanding items

- 작업 tree는 uncommitted(`scripts/phase3a_deployed_rebuild_smoke.py`, `tests/test_phase3a_deployed_rebuild_smoke_script.py` untracked + 5 doc modified). 커밋·게시는 오너 승인 전이다.
- compose stack은 healthy하게 살아 있음(application 8010 / gateway 8011 / mongo 27029). 오너가 내리지 말 것을 요청한 상태.
- 이슈 1의 partial-write 잠금 보강 여부는 오너 결정 대기. 보강 시 본 검증 기록 Verdict를 full 합격으로 갱신한다.
- 후속: persistent Chroma-like adapter, archive 후 파생 index stale/automatic sync는 여전히 계약 미확정 후보(HANDOFF Next Tasks).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 정적 / 회귀
python3 -m py_compile scripts/phase3a_deployed_rebuild_smoke.py tests/test_phase3a_deployed_rebuild_smoke_script.py
python3 -m unittest tests.test_phase3a_deployed_rebuild_smoke_script -v                                   # 6
python3 -m unittest tests.test_phase3a_deployed_rebuild_smoke_script tests.test_phase3a_rebuild_source_block_index_script tests.test_application_api tests.test_indexing_phase3a -v   # 68
python3 -m unittest discover tests                                                                        # 381 / 37 skip
git diff --check

# live compose (stack 이미 healthy 전제)
docker compose ps
python3 scripts/phase3a_deployed_rebuild_smoke.py \
  --application-base-url http://127.0.0.1:8010 \
  --mongo-uri "mongodb://127.0.0.1:27029/?replicaSet=rs0&directConnection=true"      # summaries_match=true, exit 0
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  "http://127.0.0.1:8010/projects/000000000000000000000000/snapshots/000000000000000000000001/index/source-blocks/rebuild"   # 404
```
