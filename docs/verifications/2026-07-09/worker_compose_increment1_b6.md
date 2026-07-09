# 검증 기록 — (b-6) 증분1 worker compose 서비스 (주장 v1.6.56)

## Subject metadata
- **날짜**: 2026-07-09
- **요청자**: 오너 ("작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증 에이전트(Claude) — 작업 AI의 산물과 무관하게 1차 소스에서 재유도
- **대상 slice/artifact**: (b-6) 증분1 = index-sync worker를 docker-compose **서비스**로 상시 가동(`--loop` drain + SIGTERM graceful shutdown). 결정 브리프 `docs/plans/04-worker-compose-outbox-bookkeeping-decisions.md`(Resolved 2026-07-09).
- **정본 계약 참조**: `docs/plans/04-worker-compose-outbox-bookkeeping-decisions.md`(오너 결정 G0=A · G1=A · G2=A · G5=증분1 · G6=A · #8). 증분1 범위 = worker compose 서비스(G0/G1/G2) **한정**, outbox 데이터 모델 변경 없음, SoT 버전 bump만(새 literal 없음).
- **작업 소스**: working tree, **미커밋**(`git status`: 7개 modified + 1개 untracked plan). commit hash 없음.

## Scope
1. `services/application/app/indexing/service.py` — `IndexSyncWorker.run_once` 신규 `stop_check` 파라미터
2. `scripts/index_sync_worker.py` — `parse_args`/`_build_index_sync_worker`/`run_worker`/`_GracefulShutdown`/`_install_signal_handlers`/`run_loop`/`main`
3. `docker-compose.yml` `worker` 서비스 + `services/application/Dockerfile`(`COPY scripts/`) + `.dockerignore`
4. 신규 회귀 6건 — `tests/test_indexing_phase3a.py` 1 + `tests/test_index_sync_worker_script.py` 5
5. G5(outbox 모델 미변경) 무결성 + #4 사실기반(targets[].status 전이 여부)
6. 문서 표면(SoT 버전 bump / CHANGELOG / HANDOFF / work_log / #8 정정)
7. 실 동작 end-to-end smoke(독립 재실행)

## Methodology
- `git diff --name-only` / `git diff --check`(변경 범위 + whitespace)
- `git diff services/application/app/indexing/service.py`(surgical 변경 확인)
- `python3 -m pytest -q --ignore=tests/test_memory_mongo.py`(전체 스위트)
- `python3 -m pytest -q <신규 6 노드>`(타겟 회귀)
- `docker compose config --services` / `docker compose config`(worker 서비스 파싱 + 렌더링)
- **독립 실 Mongo smoke**(주체: 검증자, worker가 쓴 인스턴스와 **상이**한 `mongodb://127.0.0.1:27018` standalone, throwaway db `b6_verify_smoke`): `IndexSyncOutboxService(MongoIndexSyncRepository.from_uri(...)).enqueue_project_archived(...)`로 entry 적재 → one-shot drain + `--loop`+SIGTERM subprocess 관찰
- 1차 소스 직독: `service.py` run_once 전문, `index_sync_worker.py` run_loop/main 전문, `mongo_repository.py:117-210`, `models.py`, 결정 브리프 전문, 검증기록 `2026-07-08/canonical_memory_lexical_hybrid_rrf.md`
- **다중 에이전트 독립 검증**: 6개 표면별 독립 감사자 + 발견별 adversarial 반박 에이전트(완료 21/23 전부 `CONFIRMED`, 기각 0)

## Findings

### 1. `run_once` stop_check(service.py) — **PASS**
- `stop_check: Callable[[], bool] | None`가 for-loop **각 claim 직전**(`service.py:431`)에서 검사 → 이미 claim된 in-flight entry는 그 iteration 내에서 끝까지 처리(성공→삭제 / 실패→requeue)되고, **다음 claim 경계**에서 정지. canonical G2=A("현재 entry 처리 완료 후 루프 종료")에 정합.
- `stop_check=None`(기본값, `:421`)이면 guard가 short-circuit → one-shot 경로 후진호환 불변. G5(증분1) 계약("outbox 모델 변경 없음") 충족.

### 2. `index_sync_worker.py` loop/signal/exit — **PASS(로직) + 1 blocking test-gap**
- `run_loop`(`:308-372`): worker(sink adapter 포함)를 **1회** 빌드(`:321`) 후 `run_once` 반복. busy(claimed>0)면 즉시 재drain(대기 없음), idle(claimed==0)일 때만 `sleep_fn(interval)`(`:361-362`). `stop_check=stop.is_requested`를 `run_once`에 주입(`:341`).
- `_install_signal_handlers`(`:302-305`): SIGTERM+SIGINT 양쪽을 `signal.signal`로 등록(main-thread 전용 — `main`에서 `:388-389` 호출).
- exit-code map 양 모드 보존: loop→`run_loop` return 0(`:372`); loop 모드에서 `_build_index_sync_worker`의 `ValueError`가 `run_loop`→`main`의 `except ValueError`로 전파→exit 2(`:392-394`); one-shot→0 / ValueError→2.
- **이슈 2-1 [blocking test-gap, CONFIRMED]**: 실제 signal→request wiring(`_install_signal_handlers`가 SIGTERM/SIGINT→`stop.request`)이 **단위테스트에 한 번도 걸리지 않음**. 모든 loop 테스트가 `install_signal_handlers_fn=lambda stop: None`로 stub(`test_index_sync_worker_script.py`). CLAUDE.md("untraced branch는 green bar와 무관하게 blocking") 관점에서 미회귀 분기. 단, 본 검증자의 subprocess smoke(§4)가 통합 수준에서 SIGTERM→`loop_stopped` graceful exit를 실증하므로 **기능 결함이 아닌 회귀-락 부재**.
- **이슈 2-2 [minor]**: "loop 시작 전 이미 stop 요청"退化 경로, `INDEX_SYNC_INTERVAL` env-override 분기 미회귀(flag override·env-부재 default만 테스트).

### 3. compose/Dockerfile/.dockerignore — **PASS(wiring) + 1 major boundary**
- `docker compose config` 파싱 정상. worker 서비스: `restart: unless-stopped`(G0 crash 복구), healthcheck **없음**(G1=A no health port), `command: python scripts/index_sync_worker.py --loop`, `depends_on` mongo/embedding/chroma/elasticsearch 모두 `service_healthy`(4×), env 배선(CORE_SOT_MONGO_URI/EMBEDDING_SERVICE_URL/CHROMA_HOST/ELASTICSEARCH_URL/INDEX_SYNC_INTERVAL).
- Dockerfile: `COPY scripts/ ./scripts/`가 `COPY services/` **후**에 위치(의존성 캐시 레이어 보존). `.dockerignore`: `scripts/` 제외 해제 + 주석으로 사유 명시.
- **이슈 3-1 [major boundary, CONFIRMED]**: `stop_grace_period: 60s`(`docker-compose.yml:227`) vs 합산 sink timeout. composite **MEMORY_UPSERTED** 1건이 embedding→Chroma→ES로 **순차 fan-out**(각 sink call마다 `request_timeout` bound). 각 timeout의 합 worst-case가 60s를 초과하면 compose가 SIGTERM 후 60s에 **SIGKILL** → entry가 **RUNNING으로 600s lease 만료까지 stuck**(그 후 `claim_next_outbox_entry` stale-reclaim이 회수). lease가 bound하므로 **데이터 손실은 아니나 실 운영 경계 위험**. G1=A 근거("each sink call bounded by request_timeout")가 stop_grace_period와의 관계를 명시하지 않음.
- **이슈 3-2 [observation]**: `stop_grace_period: 60s`는 브리프에 없는 **spec-silent literal**. 또한 `INDEX_SYNC_INTERVAL`(default 30)이 `stop_grace_period`에 대해 bound 없음 — CPython 3.12에서 non-raising SIGTERM handler(`_GracefulShutdown.request` 패턴)는 `time.sleep`을 **중단시키지 않음**(반박 에이전트가 실측). 따라서 idle sleep 중 SIGTERM은 sleep 복귀 후에야 처리 → interval > grace면 SIGKILL 가능. 단 idle sleep엔 in-flight entry가 없어 **무해**(재시작만).

### 4. 회귀 6건 — **PASS(계약 pin) + 위 §2-1 blocking test-gap**
- `test_run_once_stop_check_finishes_in_flight_entry_then_stops`(`test_indexing_phase3a.py`): 3 시나리오(baseline full drain / stop_after_first→claimed=1·succeeded=1·잔여 2 / never_stop→claimed=3)로 **양방향**(under-strict: 무시 시 3건 claim / over-strict: 과잉 정지 시 <3) pin. ✅
- `WorkerLoopTest`(3): busy pass 대기 없음·idle pass sleep(interval)·`--loop` dispatch→`run_loop`+`_GracefulShutdown` — 양방향 pin. ✅
- `ParseArgsLoopTest`(2): default(one-shot, interval=30)·`--loop --interval 7` override. ✅
- **독립 실 Mongo smoke(검증자)**: one-shot — enqueue 1→`outbox 0`·`success` log·rc=0 ✅; **`--loop`+SIGTERM** — event seq `[loop_started, pass, pass, loop_stopped]`(passes=2)·rc=0·outbox 0 ✅. 작업 AI 헤드라인 클레임을 다른 Mongo 인스턴스에서 그대로 재현.

### 5. G5 outbox 무결성 + #4 사실기반 — **PASS**
- `git diff --name-only` = 정확히 7개 파일. `models.py`·`mongo_repository.py` **미접촉**. `run_once` 전문(`service.py:415-474`) 변경은 stop_check guard(+`Callable` import) **한 곳**.
- **#4 사실기반 CONFIRMED**: `claim_next_outbox_entry`(`mongo_repository.py:125-152`)는 entry-**level** status만 `PENDING→RUNNING`(`:143`). `record_outbox_success`(`:155-173`)는 `delete_one`(`:172`)+SUCCESS log. `record_outbox_failure`(`:175-210`)는 DLQ 삭제(`:195`) 또는 whole-event `$set`(`:197-209`, status/attempt_count/next_attempt_at/claimed_at/last_error). **어느 경로도 `targets[].status`를 전이하지 않음**(enqueue 시 1회 기재 후 갱신 없음). → 2026-07-08 기록의 "envelope `targets.chroma.status`가 combined 결과 반영"(`canonical_memory_lexical_hybrid_rrf.md:36`)은 **사실 관계 오류**(#8 정정 대상 맞음). 증분2가 이 inert 표면을 wire-up할 예정.

### 6. 문서 표면 — **결함 집중 영역(verdict 좌우)**
- **이슈 6-1 [blocking — 브리프 자체 결함, 구현 결함 아님, CONFIRMED×5]**: **G2 lease-release 자기모순**. canonical G2=A 결정 본문(`:63-67`, `:66`가 "이 정정본이 canonical"이라 자기선언)+#8(`:10`)은 "현재 entry 처리 완료 후 종료, lease 600s **유지**, PENDING 복귀 **아님**". 그러나 검증계획(`:106`: "lease-release(G2-A) — graceful shutdown이 in-flight entry를 즉시 PENDING 복귀")+한계#2(`:100`: "G2-A(release)")+질문#3(`:123`)은 "lease-release → PENDING 복귀"를 명시. **구현은 canonical(finish-in-flight)을 정확히 따름** → 구현은 정상이나 **브리프가 자기모순**. 정정 필요(lease-release 언급 제거/수정, 또는 오너가 실제 lease-release를 원하면 미구현 동작 변경).
- **이슈 6-2 [major]**: **SoT v1.6.56 bump 무·CHANGELOG 무**. `system-contract-sot.md:4` 여전 "v1.6.55", 버전로그 표 top도 v1.6.55. working tree에 "1.6.56"은 브리프에만 존재. G5/G6("증분마다 버전 bump + changelog") 미충족. b-2 선례(`work_log.md:124` "SoT·CHANGELOG·work_log·HANDOFF는 증분2에 일괄")로 증분2/커밋 시점 지연 가능하나, "완료" 주장과 충돌.
- **이슈 6-3 [major]**: **HANDOFF 능동 모순** — 여전 "worker(`index_sync_worker.py`)는 compose 서비스가 **아님**"(`HANDOFF.md:18`) + "v1.6.55"(`:8`). 신규 코드와 정면 충돌.
- **이슈 6-4 [minor]**: **work_log b-6 기술 무** — `docs/daily_logs/2026-07-09/work_log.md`는 b-5/b-2만. CLAUDE.md §5("작업 완료 후 work_log, 예외 없음") 위반.
- **이슈 6-5 [minor]**: **#8 정정 미적용** — `2026-07-08/canonical_memory_lexical_hybrid_rrf.md:36`의 false claim 그대로. (#8 정정은 의미상 증분2 outbox bookkeeping와 짝이나, 오너가 "이 slice에서 정정" 명시.)
- **이슈 6-6 [observation]**: 브리프 검증계획(`:106`)이 "depends_on/**healthcheck**"를 언급하나 G1=A는 health port/healthcheck **부재**를 선택 — 브리프 내 워딩 불일치(구현은 G1=A 정합).

## Issues / Risks
1. **[blocking, 브리프 결함] G2 lease-release 자기모순**(6-1) — 구현은 무관하나 계약 문서 자체가 정정 대상. 6 감사자 전원 + 반박 5건이 독립 CONFIRMED.
2. **[major] stop_grace_period 60s 경계**(3-1) — composite entry의 합산 sink timeout이 60s 초과 시 SIGKILL→entry 600s RUNNING stuck(stale-reclaim이 회수). lease가 bound라 비치명적이나 운영 경계.
3. **[blocking test-gap] signal wiring 미회귀**(2-1) — 실 SIGTERM→graceful 경로의 단위 락 부재(통합 smoke는 실증).
4. **[major] 문서 표면 누락/모순**(6-2~6-5) — SoT bump·CHANGELOG·HANDOFF(능동 모순)·work_log·#8.
5. **경계 위험(비차단)**: `INDEX_SYNC_INTERVAL > stop_grace_period` 시 idle sleep 중 SIGKILL 가능(무해, in-flight entry 없음).

## Verdict — **조건부 합격 (conditional pass)**

**합격 사유(load-bearing)**:
- 구현은 canonical G2=A(finish-in-flight)에 **정확히 정합** — 6 감사자 / 반박 21건 / 독립 실 Mongo smoke(one-shot + loop+SIGTERM) 전원 일치하게 **구현 결함 0건**.
- 회귀 6건은 계약을 양방향으로 pin; 전체 suite **695 passed / 45 skipped**(baseline 689 + 6 정확).
- G5 충족(outbox 모델 미접촉, run_once surgical); #4 사실기반 독립 확인.

**합격 전제 조건(닫혀야 "합격")**:
1. **(6-1)** 브리프 G2 lease-release 자기모순 정정 — 검증계획 `:106`·한계#2 `:100`·질문#3 `:123`의 lease-release/PENDING-복귀 언급을 canonical G2=A에 맞게 제거/수정. (오너가 실제 lease-release를 원하면 그것은 미구현 동작 변경이므로 별도 slice.)
2. **(6-2/6-3/6-4)** 문서 표면 처리 결정 — (a) b-2 선례대로 SoT bump·CHANGELOG·HANDOFF를 증분2로 지연 **하더라도**, (i) work_log는 **지금** b-6 증분1 기술(CLAUDE.md §5 예외 없음), (ii) HANDOFF의 "worker는 compose 서비스 아님" 능동 모순은 **지금** 정정; 또는 (b) v1.6.56 bump + CHANGELOG를 지금 적용.
3. **(6-5)** #8 정정은 **증분2 착수 전**(해당 기록에 의존하기 전)까지는 반드시 적용.

**권장(비차단)**:
- (3-1) per-entry 최대 sink-timeout 예산 vs `stop_grace_period: 60s` 관계를 문서화하거나 grace 상향; `INDEX_SYNC_INTERVAL ≤ stop_grace_period` 권장.
- (2-1) SIGTERM→graceful-exit 통합 회귀 추가(또는 본 smoke를 공식 lock으로 승격); 退化·env-override 단위 케이스 보강.

## Outstanding items
- working tree **미커밋**(7 modified + 1 untracked plan). 커밋/공개는 오너 승인 대기.
- 증분2(v1.6.57, G3=B/G4=B per-sink bookkeeping)이 차순이며 #8 정정 이해에 의존.
- 다중 에이전트 워크플로우는 verdict 확정(6 감사자 + 반박 21/23 만장일치 CONFIRMED, 기각 0) 후 정지. 잔여 반박 2건 + 완전성 비평은 마무리 중이었으나 결과를 뒤집을 소지 없음.

## Reproduction
```bash
cd /mnt/d/devel/에베베/ai_writte_system
git diff --stat                          # 7 files, +349/-6
git diff --check                         # CLEAN
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # 695 passed, 45 skipped
python3 -m pytest -q \
  "tests/test_indexing_phase3a.py::IndexSyncWorkerTest::test_run_once_stop_check_finishes_in_flight_entry_then_stops" \
  "tests/test_index_sync_worker_script.py::WorkerLoopTest::test_run_loop_drains_until_stop_then_exits" \
  "tests/test_index_sync_worker_script.py::WorkerLoopTest::test_run_loop_idles_when_no_entries_claimable" \
  "tests/test_index_sync_worker_script.py::WorkerLoopTest::test_main_loop_mode_dispatches_run_loop" \
  "tests/test_index_sync_worker_script.py::ParseArgsLoopTest::test_defaults_are_one_shot_with_30s_interval" \
  "tests/test_index_sync_worker_script.py::ParseArgsLoopTest::test_loop_flag_and_interval_override"   # 6 passed
docker compose config --services | grep worker            # worker (parses)
# 독립 실 Mongo smoke(검증자): mongodb://127.0.0.1:27018 db b6_verify_smoke
#   enqueue_project_archived → one-shot: outbox 0/success/rc 0
#   --loop + SIGTERM: [loop_started,pass,pass,loop_stopped] rc 0 outbox 0
```
