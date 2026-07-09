# (b-6) index-sync worker compose 서비스 + outbox per-target bookkeeping — 착수 결정 브리프

**상태**: `Resolved` (2026-07-09 오너 결정 — G0=A·G1=A·G2=A·G3=B·G4=B·G5=A·G6=A)
**관련**: SoT v1.6.53 G6=A(후속)·v1.6.52/54 per-target bookkeeping 정정(미룀). HANDOFF Next Tasks #1 (b-6).
**범위**: (1) `scripts/index_sync_worker.py` drain(archive + memory reindex + candidate 색인)을 docker-compose **서비스**로 올리고, (2) outbox를 **per-target(per-sink) bookkeeping**로 확장해 vector(Chroma)·lexical(ES) 각 sink의 성공/실패를 개별 추적.

## 오너 결정 (2026-07-09)

- **G0=A** · **G1=A**(ES per-call `request_timeout`이 hang을 bound → health port 불필요) · **G2=A**(오너 위임, 라벨 정정 포함 — single-replica + graceful SIGTERM + lease 600s, N-replica 확장성 보존) · **G3=B**(G4 coupling으로 A에서 상향) · **G4=B**(per-sink 재시도 예산) · **G5=A**(2 increment) · **G6=A**(버전 bump만, 새 literal 없음; "enum literal 일괄 consolidation(B)"은 future batch 부채로 추적).
- **#8**: lease 600s 유지(graceful 재시작은 현재 entry 처리 완료 후 종료라 stuck window 없음). 검증기록 `2026-07-08` 본문의 "targets.chroma.status가 combined 결과 반영" 오류를 이 slice에서 정정.
- **확장성 지시(오너)**: 향후 다른 LLM/다른 drain type 추가 가능성 — worker dispatch의 event-kind별 adapter 주입 구조를 유지해 새 event kind + adapter로 확장(compose 변경 불필요).
- **증분 분할**: 증분1(v1.6.56) = worker compose 서비스(G0/G1/G2, outbox 모델 변경 없음). 증분2(v1.6.57) = outbox per-sink bookkeeping(G3=B/G4=B: `IndexSyncTargetState` per-sink 예산 확장 + composite per-sink outcome + all-terminal 시 entry 정리 + dedup 의미 조정).

---

## 배경 / 성격

- v1.6.52(canonical ES lexical/hybrid)·v1.6.53(compose ES 서비스)·v1.6.54/55(candidate 색인·retrieval)까지 retrieval·색인 코드는 완성됐으나, **색인 적재 worker는 여전히 수동/out-of-band**다. compose 스택에 worker가 없어 배포에서 ES `memory_lexical`/`candidate_lexical` 인덱스가 채워지지 않는다(retriever는 인덱스 비어도 graceful이므로 기능 결함은 아님).
- 동시에 outbox의 per-target bookkeeping는 v1.6.52 정정·v1.6.54 재확인으로 **두 번 미뤄진** 상태. 사유: "enqueue는 배포 ES 구성을 몰라 무조건 ES target 시 비-ES 배포에서 영구 pending" → per-target 상태를 enqueue가 아닌 **worker가 drain 시점에 materialize**해야 한다.
- 이 slice는 **(b-5) G6=A가 "후속"으로 남긴 worker compose 서비스**를 구현하고(v1.6.53 브리프 :84-86,93가 정확히 "restart/loop 정책·health·중복 실행 설계가 붙어 별도 slice"로 지정), 동시에 **미뤄진 per-target bookkeeping를 해소**한다.

## 핵심 발견 — per-target 표면은 이미 존재하지만 inert

조사(1차 소스 직독)의 가장 중요한 발견: **per-target 상태 필드가 이미 존재·영속화되나 동작하지 않는다.**

- `IndexSyncOutboxEntry.targets: dict[str, IndexSyncTargetState]`(`models.py:90`)가 whole-event `status`(`:91`)와 **공존**. `IndexSyncTargetState`는 `{status, backend}`만(`models.py:71-74`, per-sink 재시도/last_error 필드 없음). Mongo에 round-trip 됨.
- 그러나 `_enqueue_event`는 **모든 이벤트에 단일 placeholder** `targets={CHROMA_TARGET("chroma"): IndexSyncTargetState(PENDING, IN_MEMORY_FAKE)}`를 하드코드(`service.py:363-368`). 실제 configured sink(vector-only vs vector+ES composite)는 worker 기동 시 `_build_memory_adapter`/`_build_candidate_adapter`에서 env로 결정.
- `record_outbox_success`는 **성공 시 entry를 삭제**(`mongo_repository.py:172`)하고 SUCCESS log만 쓴다 — `targets[].status`를 **절대 전이하지 않는다**. `record_outbox_failure`도 whole-event `$set`(`:197-209`) 또는 max 도달 시 DLQ 삭제(`:194-196`) — targets 미접촉.
- 즉 **(b-6) part 2는 "필드 추가"가 아니라 "이미 있는 inert 표면을 worker가 실제로 갱신하게 wire-up"**이다. schema 비용이 예상보다 작다.

## 조사에서 확인한 사실 (1차 소스 file:line)

- **worker는 철저히 one-shot**: `IndexSyncWorker.run_once`(`service.py:416-469`)는 bounded for-loop 후 summary 반환. `run_worker`(`index_sync_worker.py:223-259`)가 `run_once` 1회 호출, `main`이 exit 0/2. `parse_args`(`:210-220`)는 `--limit`(기본 10)·`--mongo-uri`·`--mongo-db`만 — **loop/sleep/restart/health 어디에도 없음**.
- **builder는 env-gated composite**: `_build_archive_adapter`(`:31-50`, Chroma only·lexical leg 없음), `_build_memory_adapter`(`:68-133`, `ELASTICSEARCH_URL` 시 composite), `_build_candidate_adapter`(`:136-207`, 동일). **worker만 configured sink를 안다** → per-target materialize 지점.
- **composite fan-out은 all-or-nothing**: `CompositeMemoryIndexSyncAdapter.index_memory`(`memory_index.py:210-212`)·`CompositeCandidateIndexSyncAdapter.index_candidate`(`candidate_index.py:198-200`)가 sink들을 try/except 없이 순차 호출, 첫 raise가 전파되어 entry 실패·requeue. 회귀 `test_candidate_index.py::test_sink_failure_propagates_not_swallowed`가 이를 lock.
- **중복실행 방지는 이미 claim 계층에 존재**: `claim_next_outbox_entry`(`mongo_repository.py:118-153`)가 atomic `find_one_and_update` PENDING→RUNNING + `claimed_at` lease + `INDEX_SYNC_CLAIM_TIMEOUT_SECONDS=600s` 경과 stale-lease reclaim. unique dedup index `[project_id, event, source.mongo_collection, source.mongo_id]`가 백업. 두 worker가 같은 entry를 lease 내 이중 claim 불가.
- **재시도 예산은 per-event**: `INDEX_SYNC_MAX_ATTEMPTS=3`·`CLAIM_TIMEOUT=600`·`BACKOFF=(60,300)`(`service.py:37-39`). per-sink 시도/last_error 필드 없음 → 한 sink가 계속 죽어도 건강한 sink가 같이 DLQ drop.
- **enum은 ES/lexical에 불완전하나 우회 가능**: `IndexSyncTarget`은 VECTOR만(`models.py:18-19`), `IndexSyncBackend`는 IN_MEMORY_FAKE/CHROMA만(`:22-24`). 단 targets dict key가 **자유 문자열**('chroma' today)이라 ES sink를 'lexical' key로 추가해 enum 변경 없이 가능. enum member 추가(IndexSyncTarget.LEXICAL 등)만이 새 SoT literal.
- **compose에 `restart:` 0건**(grep) — b-6이 스택 최초의 restart 관례 도입(net-new, mirror 아님). application은 `depends_on: service_healthy`×5 + healthcheck 템플릿 보유(`docker-compose.yml:27-72`).
- **worker에 HTTP server 없음**(one-shot CLI가 stdout에 JSON summary 1회 출력). 기존 /health는 모두 장시간 HTTP server 전용.
- **backfill은 vector-only**: `scripts/phase2b5_reindex_memory.py`가 outbox를 우회해 vector를 직접 upsert. **ES-lexical backfill 부재** → per-target bookkeeping가 ES-only 실패를 관측 가능하게 하되 자가치유 수단은 없음.
- **commit-후-enqueue skew**: `memory/service.py` promote/apply 경로가 `put_memory→update_memory→_enqueue_reindex`를 transaction wrap 없이. looping worker가 orphan 창을 줄이나 제거 못함(벡터 backfill만 수렴).

## 결정점 (G0~G6)

> 권고는 각 gate 첫 옵션에 "(추천)" 표시. increment 매핑: **증분1 = worker compose 서비스(G0/G1/G2)**, **증분2 = outbox per-target bookkeeping(G3/G4)**, **G5(분할)·G6(SoT literal)** 양 증분에 적용.

### G0 — worker compose 서비스 invocation 모델(loop 전략)
- **A(추천)**: 스크립트 내 `--loop`/`--interval` sleep 루프 + SIGTERM graceful shutdown(루프 내 in-flight entry 완료 후 exit). `restart: unless-stopped`는 crash 복구용.
- B: `run_once` one-shot 유지 + sleep 후 exit 0, `restart: always`로 재기동. worker class 변경 최소.
- C: 별도 daemon 모듈(`index_sync_daemon.py`)이 `run_once`를 감싸고 one-shot CLI는 그대로.
- **근거**: loop·graceful-shutdown seam(claim lease 600s 중 in-flight entry를 종료 전 완료)·last-drain health 신호를 한 곳에서 묶음. B는 어차피 sleep-before-exit이 필요하고 process-restart churn만, C는 `_build_*` 중복. A가 G6가 요구한 3전제(loop·health·중복방지)를 외부 스케줄러 없이 최소 변경으로 충족.
- **계약**: b-5 G6=A(worker out-of-band)를 **반전** — SoT changelog에 기록(버전 bump). loop/interval 자체는 운영 config라 새 SoT literal 아님.

### G1 — worker health/readiness 표면
- **A(추천)**: health port 없음(restart 정책 + 기존 exit-code map 0/2 + stdout JSON summary로 관측).
- B: 최소 HTTP `/health/live` 전용 포트(gateway 패턴 대칭).
- C: 파일 기반 last-drain-timestamp healthcheck(worker가 heartbeat 파일 쓰기, compose healthcheck가 file 신선도 검사).
- **근거**: worker에 HTTP server가 없어 B는 drain loop에 과대. 순 A는 "살아있으나 wedged"(느린 ES bulk에 갇힌) 상태를 못 잡지만, C는 stale heartbeat→unhealthy→restart 신호를 거의 무비용으로 제공(기존 JSON summary를 heartbeat source로 재사용). lease 600s가 어차피 heartbeat 최대 부재를 bound.
- **계약**: internal/운영 — SoT literal 아님. 단, A를 추천으로 올리되 **오너가 C(heartbeat)를 선호하면 증분1에 포함 가능**(둘 다 internal).

### G2 — 중복실행 / single-writer leader guard [오너 위임 → A 결정; 라벨 정정 포함]
- **A(결정)**: single-replica 배포 관례 + graceful SIGTERM(현재 entry 처리 완료 후 루프 종료) + lease 600s 유지. atomic claim이 이미 이중 실행을 막으므로 외부 election 불필요. **N-replica 확장은 코드 변경 없이 가능**(atomic claim이 안전성 보장) — 오너 확장성 요구 대응.
- B: N-replica 기본 허용(lease-only, graceful 종료 없이) — single-user 규모에 claim 경합만 추가.
- C: 외부 leader election — 불필요한 기구.
- **근거**: 5개 표면 전원 — `claim_next_outbox_entry`(`mongo_repository.py:118-153`)가 atomic `find_one_and_update` PENDING→RUNNING + `claimed_at` lease(600s) + stale-reclaim이라 **replica 수와 무관하게 이중 claim 불가**(오너가 확인 요청한 "이중 실행 방지 확실" = 확실). graceful 재시작은 "현재 entry를 끝까지 처리하고 종료"라 stuck window 없음; ungraceful crash만 lease(600s)에 bound. single-replica 관례로 exactly-one-writer 의도 명시 + N-replica 확장성 보존. (작성 중 A/B 라벨이 본문과 채팅 표에 서로 달라 혼란을 드렸음 — 이 정정본이 canonical.)
- **계약**: internal — 배포 cardinality·graceful 종료는 운영. lease 상수 `INDEX_SYNC_CLAIM_TIMEOUT_SECONDS=600`은 graceful 종료 도입으로 재검증 필요성이 낮아져 현행 유지(#8).

### G3 — outbox per-target bookkeeping SCOPE [오너 결정: G4 coupling으로 A→B 상향]
- **A(추천)**: minimal-but-real per-sink status — worker가 claim 시 **실제 sink target을 materialize**(configured sink를 앎), per-sink SUCCESS/FAILED를 기존 `targets` dict에 기록, **모든 target SUCCESS일 때만 entry 삭제**, composite adapter가 replay 시 **이미 성공한 sink를 skip**. 재시도 예산은 증분2에서 per-event 유지(MAX_ATTEMPTS=3).
- B: full per-sink status + per-sink 재시도 예산(`IndexSyncTargetState`에 per-sink attempt_count/last_error 추가, 실패 sink만 재시도).
- C: 다시 미루기(증분1만 ship).
- **근거**: schema가 이미 존재(round-trip 됨) → 비용은 "wire-up". C는 두 번 미뤄진 결정을 세 번 미룸(오너가 b-6에 명시 scope). B는 가장 깊은 변경(TargetState 확장 + per-sink 예산 + partial-success 회복)을 한 증분에 묶어 b-2 점진 선례(G5)와 충돌. **A**가 관측 가치(ES-only 실패 가시·성공 sink 재색인 회피)를 가장 작은 계약 인접 변경으로 delivering. 성공-경로 동작 변경(삭제 시점)만 수반, per-sink 예산은 후속. idempotent sink가 whole-event replay를 correct하게 만들어 미룸이 안전.
- **계약(혼합)**: 내부 `IndexSyncStatus` 값 + 자유 문자열 target key('vector'/'lexical') 재사용 → **새 SoT literal 없음**. 단 성공-경로 변경(`record_outbox_success`가 첫 성공에 삭제하지 않고 all-targets-SUCCESS까지 entry 보존, `mongo_repository.py:172`)은 dedup 의미를 이동시키고 `IndexSyncRepository` Protocol(`service.py:66-103`) 표면에 per-target 갱신을 추가 → SoT changelog에 행동 변경으로 기록. v1.6.52/54 deferral 사유(enqueue sink-agnosticism·영구-pending 회피)는 **enqueue가 아닌 worker에서 target materialize로 보존**.

### G4 — 실패 의미론 — per-sink 재시도 vs whole-event requeue [오너 결정: B]
- **A(추천)**: whole-event requeue + composite가 성공 sink skip(G3-A와 짝). per-event 예산이 terminal DLQ-drop 지배.
- B: per-sink 재시도 예산(실패 sink만 재시도, 성공 sink는 SUCCESS 유지).
- C: per-sink DLQ-drop(한 sink max 도달 시 해당 sink만 FAILED, entry 유지).
- **근거**: G3-A와 짝. 기존 재시도 상수·DLQ-at-max 경로(`mongo_repository.py:194-196`) 보존, composite에 "성공 sink skip"만 추가(`memory_index.py:210-212`, `candidate_index.py:198-200`). B/C는 `IndexSyncTargetState` 확장 + per-event max_attempts drop 상호작용 재설계 필요(더 깊은 증분). 기존 all-or-nothing 회귀(`test_candidate_index.py:552-561`)는 A 아래 over-strict guard(성공 sink 재색인 안 됨) 획득.
- **계약**: internal. **수용 한계**: A 아래 persistently-down ES sink가 whole-event를 pin·DLQ drop → 건강한 Chroma가 벌 받음, backfill vector-only라 DLQ drop된 ES 실패에 **수렴 수단 없음**. 증분2의 accepted limitation(work-log 명시), C가 미래 fix.

### G5 — commit / increment 분할
- **A(추천)**: 2 increment — **증분1 = worker compose 서비스(G0/G1/G2, outbox 모델 변경 없음)** / **증분2 = outbox per-sink bookkeeping(G3=B/G4=B: per-sink 재시도 예산·composite per-sink outcome·all-terminal 정리·dedup 조정)**. b-2 G0=A 2-increment 선례 대칭(SoT v1.6.54/55).
- B: 단일 commit(두 deliverable을 한 SoT 버전으로).
- C: 3+ 증분(graceful-shutdown·health·bookkeeping·per-sink 재시도 분리).
- **근거**: 증분1은 순수 운영(loop/health/중복방지)·outbox 데이터 모델 미접촉 → 독립 ship 가능·저위험, 즉시 가치(always-on drain). 증분2는 계약 인접(성공-경로·dedup 이동·Protocol 확장)·최대 위험을 격리. 증분1 loop/lease를 증분2 성공-경로 rewrite 전에 검증 가능. C는 과분할, B는 이질적 위험 묶음.
- **계약**: 증분마다 SoT 버전 bump + changelog. 증분1 = G6 A→B 반전 기록, 증분2 = v1.6.52/54 deferral 해소 + 성공-경로/dedup 의미 이동 기록. SoT entry 2건.

### G6 — SoT 버전 bump + 새 public literal 도입 여부
- **A(추천)**: 버전 bump, **새 public literal 없음** — 내부 `IndexSyncStatus` 값 + 자유 문자열 target key('vector'/'lexical') 재사용. changelog에 G6 반전 + deferral 해소 기록.
- B: 버전 bump + 새 public literal(`IndexSyncTarget.LEXICAL` / `IndexSyncBackend.elasticsearch` enum member) — ES sink를 SoT에 명시 계약 표면으로.
- C: SoT 변경 없음(순수 internal).
- **근거**: indexing/outbox 계층은 SoT에 literal이 surface되지 않는 한 internal. `IndexSyncStatus`/targets bookkeeping는 public literal이 아니고 `IndexSyncEvent`(4종)만 public. 자유 문자열 key가 이미 동작('chroma' placeholder가 방증) → ES sink를 'lexical' key로 enum member 없이 가능. B는 전체 verification 경계-매트릭스 처리를 trigger하고 오너가 요청 안 한 계약 표면. C는 오답(G6 반전 + 성공-경로 의미 변경은 계약급이라 반드시 기록).
- **계약**: A = 증분당 1 SoT changelog entry(G5). 새 enum member·새 `IndexSyncEvent` 없음.

## 한계 / 수용 사항 (오너 인지 필요)

1. **ES-lexical backfill 부재**(vector-only backfill만): 증분2가 ES-only 실패를 관측 가능하게 하나 자가치유 없음. G4-A 아래 DLQ drop된 ES 실패는 수렴 수단 없음 → accepted limitation(work-log 명시), ES backfill은 별도 후보.
2. **lease 600s가 one-shot 기준 산정**: daemon ungraceful crash 시 in-flight entry 최대 10분 stuck. G2=A(finish-in-flight via `stop_check`)가 graceful 재시작 창을 닫는다 — 현재 entry를 끝까지 처리한 뒤 다음 claim 경계에서 종료하므로 entry가 `RUNNING`으로 남지 않는다(**PENDING 강제 복귀 아님**). ungraceful crash 창은 lease(600s stale-reclaim)가 커버. lease-release(강제 PENDING 복귀)는 채택하지 않았다(정정: 본 문서의 예전 "lease-release" 언급은 canonical G2=A가 아님).
3. **commit-후-enqueue skew**(transaction 없음): looping worker가 orphan 창을 줄이나 제거 못함. 벡터 backfill만 수렴. b-6이 이 창을 넓히지 않도록 주의(CLAUDE.md §3).
4. **사전 존재 문서 결함(정정 권고)**: 검증기록 `docs/verifications/2026-07-08/canonical_memory_lexical_hybrid_rrf.md` 본문(### 1)이 "envelope `targets.chroma.status`가 combined 결과 반영"이라 했으나, 1차 소스(`mongo_repository.py:155-210`)는 targets.status가 **결코 전이되지 않음**(성공=삭제, 실패=whole-event $set)을 보임. 이 기록을 정본으로 믿으면 per-target이 이미 동작한다고 오인. b-6과 별개지만 의존 전 정정 권고.

## 검증 계획

- **증분1 회귀**: loop 동작(`--loop`/`--interval` + SIGTERM graceful drain 완료 — `stop_check`가 현재 entry 처리 후 다음 claim 경계에서 종료), exit-code map 보존, compose `restart:` 선언 + `depends_on`(healthcheck는 G1=A로 worker엔 없음), **SIGTERM→graceful wiring**(signal handler→`_GracefulShutdown` flag→`run_loop` 종료). mutation 양방향.
- **증분2 회귀**: worker가 claim 시 target materialize(vector/lexical), per-sink SUCCESS/FAILED 기록, **all-targets-SUCCESS까지 entry 보존**(성공=삭제 의미 변경 under-strict guard), composite가 성공 sink skip on replay(over-strict guard), 기존 `test_sink_failure_propagates_not_swallowed` 재방문·양방향 lock, dedup 의미 이동 회귀. mutation 양방향.
- **전체 스위트**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py`(현재 689 passed/45 skipped 기준 증분별 +N).
- **실 bring-up(sandbox docker 가용 시)**: worker compose 서비스가 기동 후 loop drain하고, ES 구성 시 `_build_*` composite가 실 `memory_lexical`/`candidate_lexical`을 채우는 end-to-end. 불가 시 out-of-band 위임.
- **SoT 정합**: G6 반전·deferral 해소·성공-경로 의미 변경을 changelog에 정확히 기록.

## 제외 (후속)

- per-sink 재시도 예산 + partial-success 회복(G3-B/G4-B/G4-C) — 증분2 이후 별도.
- ES-lexical backfill 스크립트(`phase2b5_reindex_memory.py` 대칭) — 한계 #1의 fix.
- (b-4) hybrid 튜닝·(c)~(e)·Phase 6 후보 전이 — HANDOFF Next Tasks #1 잔존.
- commit-후-enqueue skew의 transaction/enqueue-retry 처리 — 한계 #3, 별도.

## 오너에게 묻는 질문

1. **G0**: worker를 in-script `--loop`+SIGTERM(A), one-shot+restart:always(B), 별도 daemon 모듈(C)?
2. **G1**: health는 port 없음·restart+exit-code(A), HTTP /health/live(B), 파일 heartbeat healthcheck(C)?
3. **G2**: 중복실행 방지는 lease+single-replica+graceful SIGTERM(finish-in-flight)(A), N replica lease-only(B), 외부 election(C)?
4. **G3**: per-target bookkeeping는 minimal-but-real(A), full per-sink 예산(B), 다시 미루기(C)?
5. **G4**: 실패는 whole-event requeue+성공 sink skip(A), per-sink 예산(B), per-sink DLQ(C)?
6. **G5**: 2 increment 분할(A), 단일 commit(B), 3+ 분할(C)?
7. **G6**: SoT 버전 bump만·새 literal 없음(A), bump+새 literal(B), SoT 변경 없음(C)?
8. 한계 #2(lease值 재검증)·#4(검증기록 정정)를 이 slice에 포함할지, 별도 후속으로 둘지?
