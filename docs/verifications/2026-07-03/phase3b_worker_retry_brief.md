# Phase 3B index worker/retry 결정 브리프 독립 검증 (pre-implementation)

## Subject metadata

- 검증일: `2026-07-03`
- 요청자: 프로젝트 오너("다음 작업 검증해줘. 이번 작업은 기획 문서 작성 작업이거든? … 생각하지 못했던 부분, 추가하면 좋을 부분, 비차단 항목을 검토하고 의심해줘봐. 문서 먼저 만들어뒀습니다. 구현은 아직 안 들어갔습니다.")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상: pre-implementation 결정 브리프 `docs/plans/03-index-worker-retry-decisions.md`(신규) + 함께 갱신된 `03-indexing.md`, `plans/README.md`, `system-contract-sot.md`(v1.6.28), `HANDOFF.md`, `CHANGELOG.md`, `work_log.md`. **code 미착수.**
- 정합 스펙 기준(canonical contract scope):
  - 선행 계약 `docs/plans/03-index-sync-outbox-decisions.md` §3(저장 단위 split), §5(retry/backoff + error type), §7.4(dedup key)
  - `docs/mongo_collections.md` §39A.3~39A.4(`index_sync_outbox` idempotency + unique index), §39(`index_sync_logs`)
  - `docs/system-contract-sot.md` v1.6.26(archive outbox model literal)/v1.6.27(레지스트리 등록)
  - 구현 계약(이미 commit): `services/application/app/indexing/models.py::IndexSyncOutboxEntry` field set, `indexing/mongo_repository.py` unique index spec
- 검증 대상 작업 출처: working tree, uncommitted. `git status`로 `03-index-worker-retry-decisions.md` untracked + 6개 doc modified 확인. code 변경 없음.

## Scope

정합 스펙 스코프를 (1) 신규 브리프 본문 7개 절 + Owner decisions, (2) 브리프가 의존하는 선행 계약(§3 split / §5 error type / §39A unique index / model field set)으로 좁혔다. 본 검증은 "구현 worker가 이 브리프만 보고 추측 없이 구현할 수 있는가 + 선행 계약·이미 commit된 model/index와 모순이 없는가"를 판정한다. code가 없으므로 boundary matrix는 "결정 항목별 구현 가능성/일관성/빈칸"으로 대체하고, §7 수용 기준/§7 회귀 목록이 실제로 구현·검증 가능한지를 잣대로 삼았다.

검증 surface:

1. 브리프 본문 7개 절 + Owner decisions 내부 정합성 + 선행 계약과의 literal/의미 일치
2. 브리프 결정 vs 이미 commit된 `IndexSyncOutboxEntry` field set / `uniq_index_sync_outbox_event_source` unique index — status-aware dedup 호환성
3. §7 수용 기준 6항 + §7.7 회귀 8항의 구현 가능성(각 항이 빈칸 없이 구현 가능한지)
4. 갱신 문서 6개(03-indexing/README/SoT v1.6.28/HANDOFF/CHANGELOG/work_log)의 정확성·overclaim 여부·링크 정합성

## Methodology

브리프를 끝까지 읽고 각 결정을 선행 계약·commit된 model/index에 대입해 모순·빈칸을 추출. 구현 worker 관점에서 "이 항목을 코드로 옮길 때 무엇을 스스로 정해야 하는가"를 잣점으로 삼아 의심.

실행한 명령/조회:

- `git status`, `git diff --stat`(code 변경 없음 확인)
- `Read`로 `03-index-worker-retry-decisions.md` 전량 열독
- `git diff docs/system-contract-sot.md docs/plans/03-indexing.md docs/plans/README.md`(SoT v1.6.28 / indexing / README 갱신분)
- `git diff HANDOFF.md CHANGELOG.md docs/daily_logs/2026-07-03/work_log.md`(bookkeeping 갱신분 + overclaim 점검)
- 선행 계약 직독: `mongo_collections.md` §39A.3~39A.4(idempotency + unique index), `03-index-sync-outbox-decisions.md` §3/§5(split + error type), `models.py::IndexSyncOutboxEntry` field set
- `rg -n "_MONGO_URI =|def test_" tests/test_indexing_mongo.py` + discover(400/40) — work_log의 "live smoke follow-up" 서술이 commit된 code와 일치하는지 ground-truth 확인(일치 확인, `9ac59c3` hardening commit이 반영됨)

## Findings

### 1. 결정 자체는 선행 계약과 일치하고 사유가 명확하다 (sound)

- **§2 one-shot command first(B) / daemon later(C)**: 로컬 1인 runtime에 맞고, 장기 service 재사용 경로를 닫지 않는다. Application archive endpoint 안에서 inline 실행하지 않는다는 §7.6 명시는 선행 "delivery = Mongo outbox/polling, archive write와 derived sync 실패 분리" 원칙과 정합. ✅
- **§3 claim timeout 10분(C)**: "Docker/Compose restart는 process만 되살릴 뿐 MongoDB의 `running` 상태를 자동 복구하지 않는다"는 사유가 정확하고, process lifecycle과 DB lifecycle의 분리를 짚은 점이 좋다. ✅ (단, 구현에 필요한 field가 빠졌다 → Issues #2)
- **§4 backoff 1분→5분→failed + max_attempts=3**: 선행 §5의 `max_attempts=3`을 유지. schedule 매핑이 명확하다(attempt 1 실패→+1분, attempt 2 실패→+5분, attempt 3 실패→terminal failed = backoff interval 2개). ✅
- **§5 backend_error/not_found 모두 3회**: 선행 §5와 일치. ✅ (단, not_found의 worker-time 의미가 모호하다 → Issues #3)
- **§6 status-aware dedup(active-only)**: 검증자가 직전 검증에서 제기한 risk #3의 해소 방향과 일치. ✅ (단, unique index와 충돌 → Issues #1)
- **§7.7 회귀 양방향 가드**: claim timeout에 대해 "stale running(>10min)→reclaimable"(under-strict)과 "non-stale running→not reclaimable"(over-strict)을 모두 나열. idempotency도 "terminal→reenqueue new"와 "active→reenqueue same"으로 양방향. 좋은 구조. ✅ (단, "terminal→reenqueue new"는 Issues #1이 해소되어야 구현 가능)

### 2. 구현을 막는 빈칸 — status-aware dedup vs 기존 unique index (Issues #1, load-bearing)

- 브리프 §6/§7.5/Owner decisions: "`success|failed` terminal entry만 있으면 같은 dedup key라도 새 active request 생성을 허용한다."
- 이미 commit된 unique index(`mongo_collections.md` §39A.4 / `mongo_repository.py:48-57`):
  ```javascript
  { project_id: 1, event: 1, "source.mongo_collection": 1, "source.mongo_id": 1 }
  { unique: true, name: "uniq_index_sync_outbox_event_source" }
  ```
  이 index는 **status를 포함하지 않는다.** 따라서 outbox에 terminal entry(status=success/failed)가 남아 있으면, 같은 dedup key의 새 entry insert가 unique 제약으로 **거부된다.** 즉 브리프의 핵심 결정이 현재 index로는 **불가능**하다.
- 브리프 §6 option B 단점이 "unique index 또는 lookup strategy를 조정해야 한다"고 **인지는 하지만**, **어떻게** 조정할지는 명시하지 않는다. 구현 worker가 다음 중 하나를 임의로 선택해야 한다:
  - **(A) partial unique index**: `partialFilterExpression: { status: { $in: ["pending","running"] } }`를 붙여 active entry에만 uniqueness를 적용. terminal entry는 outbox에 잔류하되 새 active와 공존. dedup query는 "active status filter + key 조회".
  - **(B) terminal 이동**: terminal 도달 시 outbox entry를 삭제(또는 `index_sync_logs`로 이동). outbox는 active만 보유 → 기존 unique index 그대로 유효. 선행 §3("outbox는 active lifecycle, logs는 terminal history")와 가장 문자 그대로 부합.
- 더 중요한 모순: **브리프의 자체 회귀 §7.7 "terminal entry 뒤 재enqueue → new active request"가 Issues #1 해소 없이는 통과할 수 없다.** 즉 브리프의 수용 기준이 브리프가 미결정한 사항에 의존한다.
- 선행 §3 원문("outbox는 pending/running/failure-retry lifecycle을 소유, logs는 completed or terminal attempt history를 소유")이 (B)를 뉘앙스하지만, §7.5의 "같은 dedup key의 terminal success|failed만 있으면"이라는 표현은 terminal이 outbox에 있는 것처럼 읽혀 (A)를 시사한다. **브리프가 (A)/(B) 중 어느 쪽인지, 그에 따른 unique index 변경/미변경과 dedup query 대상을 명시해야 한다.**

### 3. 구현을 막는 빈칸 — claim timeout에 필요한 lease field가 model에 없다 (Issues #2, load-bearing)

- 브리프 §7.1: "stale claim 대상: `running` with claim timestamp older than 10 minutes". §7.7: "stale running older than 10 minutes → reclaimable".
- 이미 commit된 `IndexSyncOutboxEntry` field set: `sync_request_id, project_id, user_id, event, source, targets, status, attempt_count, max_attempts, next_attempt_at, last_error`. **claim timestamp/lease/owner field가 없다.**
- 따라서 "claim timestamp older than 10min" 판정을 위해 **신규 field(예: `claimed_at` 또는 `claim_expires_at`) 추가**가 필요한데, 브리프는 이 schema 확장을 명시하지 않는다. 구현 worker가 field명·type·Mongo 영속(`_outbox_doc`/`_to_outbox_entry` 확장)·stale-claim query용 index(`(status, claimed_at)` 등)를 스스로 정해야 한다. §39A.4 index 목록에도 stale-claim용 index가 없다.

### 4. 비차단이지만 명시하면 좋은 항목 (구현 worker의 추측을 줄임)

- **#3 `not_found`의 worker-time 의미 모호.** §5는 not_found를 "후속 LLM orchestration/query selector의 reselection loop 오류 타입"으로 해석한다(query-time 관점). 그런데 worker가 archive event를 처리할 때 adapter가 not_found를 반환하는 경우(예: 파생 index에 해당 project/draft record가 이미 없음)는 **개념적으로 idempotent success**(목표 상태 = "파생 index가 해당 항목을 노출하지 않음"이 이미 달성됨)에 가깝다. worker-time not_found를 3회 retry하는 것이 의미가 있는지(not_found가 transient할 수 있는 경우에만), 아니면 idempotent success로 처리할지가 브리프에 구분되지 않는다. worker-time vs query-time not_found를 분리해 명시하면 좋다.
- **#4 fake adapter의 archive-mutation 연산 미정.** 현 `VectorIndexAdapter` Protocol은 `upsert_records`만 있다. archive event 처리에 필요한 delete/tombstone/mark_archived 연산이 정의되지 않았다. §7.6 "fake adapter path로 lifecycle 검증"이 fake가 archive 시 무엇을 하는지(no-op/recorded call)까지는 안 쓴다. 선행 §4가 "worker slice에서 tombstone/status update 우선 검토"로 미뤄둔 항목과 연결되므로, fake가 simulate할 연산의 형태를 한 줄 명시하면 좋다.
- **#5 stale running reclaim 시 attempt_count 처리 미정.** worker가 claim(running) 후 crash 났을 때, 10분 뒤 다른 worker가 reclaim할 때 **attempt_count를 올리는지, last_error를 어떻게 남기는지**가 불명. crash가 attempt를 소비하지 않으면 고착/무한 재claim 위험이 있고, 소비하면 crash가 budget을 깎는다. max_attempts budget 무결성에 직결되므로 명시 권장.
- **#6 `index_sync_logs` schema 미세.** §7.4 "각 attempt 결과를 sync_request_id로 append"인데, 현 `IndexSyncLog` model에 timestamp가 없다(attempt 시각). `sync_log_id` 생성 규칙도 미정. §39 log 예시의 started_at/finished_at과도 정렬 필요.
- **#7 timestamp 저장 type.** 현 model은 `next_attempt_at: str | None`(ISO string). worker의 범위 query(`next_attempt_at <= now`)·index 활용은 BSON Date가 자연스럽다. 신규 `claimed_at`과 함께 string vs BSON Date를 통일 명시.
- **#8 동시 claim 원자성.** one-shot command 동시 실행/cron overlap 시 같은 entry 중복 claim을 막기 위해 claim이 atomic(findAndModify 한 트랜잭션)이어야 한다. 로컬 1인 runtime에선 저위험이나, 구현 원칙으로 한 줄 명시 권장.
- **#9 `--limit` claim 순서.** §7.6이 `--limit`만 언급. claim 순서(`next_attempt_at` asc? `sync_request_id`?)가 미정. test 결정성/공정성에 영향.

### 5. 갱신 문서 6개 — 정확성/overclaim/링크

- SoT v1.6.28 항목은 "브리프를 승인했다"로 code 미착수를 정확히 반영(overclaim 없음). 결정 literal(10분/1분→5분/3회/active-only dedup)도 브리프와 일치. ✅
- 단, SoT가 status-aware dedup의 WHAT은 lock했으나 HOW(partial index vs terminal 이동)는 브리프도 미결정이므로 SoT에 "구현 시 index/terminal-location 확정 필요"가 빠진다. SoT 독자가 open question을 모르게 된다. minor(Issues #1 해소 시 SoT에도 반영 권장).
- `03-indexing.md` checklist 해당 항목 `[x]`로 closure + 브리프 링크 추가, 원문 참고에 브리프 추가 — 정합. ✅
- `plans/README.md`에 항목 16으로 브리프 추가, 이후 번호 shift 정확. ✅
- HANDOFF/CHANGELOG/work_log 모두 "승인/작성" 표현, 결정 literal 일치, overclaim 없음. work_log의 "live smoke follow-up: 3 live / 400(40) / 기본 URI 제거"는 `9ac59c3` hardening commit과 ground-truth 일치 확인. ✅
- 브리프 링크 대상(`../system-contract-sot.md`, `03-indexing.md`, `03-index-sync-outbox-decisions.md`) 존재 확인. ✅

## Issues / Risks

> 본 slice는 pre-implementation 브리프이므로 "code 결함"은 없다. 아래는 브리프가 구현 worker에게 떠넘기는 빈칸/모순이다. #1/#2는 구현 착수 전 브리프 보강을 권장(load-bearing).

1. **[구현-차단, 브리프 보강 권장] status-aware dedup vs unique index 미해결.** 기존 unique index에 status가 없어 terminal 후 신규 active request 생성이 거부된다. 브리프 §6/§7.5는 이를 전제하지만 HOW(partial unique index vs terminal→logs 이동/outbox 유지)를 명시하지 않는다. 브리프 자체 회귀 §7.7 "terminal→reenqueue new"도 이 결정에 의존. 선행 §3와 §7.5 표현이 (B)/(A)로 엇읽힌다. → 권고: 브리프에 (A) partial index 또는 (B) terminal 이동 중 하나를 명시적으로 채택하고, 그에 따른 §39A.4 index 변경 여부와 dedup query 대상(active filter)을 한 문단 추가.
2. **[구현-차단, 브리프 보강 권장] claim lease field 부재.** §7.1/§7.7의 "claim timestamp > 10min" 판정에 신규 field가 필요하나 model/§39A에 없고 브리프도 schema 확장을 안 쓴다. → 권고: field명/type/`_outbox_doc` 영속/stale-claim용 index를 브리프 §7.1에 명시.
3. **[비차단, 명시 권장] not_found worker-time 의미.** worker-time(adapter가 archive 대상 record 부재 반환)은 idempotent success에 가까운데 3회 retry로 규정. transient 가능 케이스와 구분 명시.
4. **[비차단, 명시 권장] fake adapter archive-mutation 연산.** 현 Protocol엔 delete/tombstone op가 없음. fake가 simulate할 형태 한 줄 명시.
5. **[비차단, 명시 권장] stale running reclaim의 attempt_count/last_error 처리.** max_attempts budget 무결성에 직결.
6. **[비차단] `index_sync_logs` timestamp/sync_log_id schema, timestamp 저장 type(string vs BSON Date), 동시 claim 원자성, `--limit` claim 순서.** 구현 시 정해야 할 low-level 항목들.

## Verdict

**조건부 합격(Conditional pass)** — 브리프의 결정 방향과 사유는 선행 계약과 일치하고 사운하며, §7 수용 기준/§7.7 회귀 구조(양방향 가드 포함)도 양호하다. 갱신 문서 6개는 overclaim 없이 정확하다.

단, **구현 착수 전에 브리프가 닫아야 할 2개 load-bearing 빈칸**이 있다:
- Issues #1: status-aware dedup의 HOW(unique index 충돌 해소 — partial index vs terminal 이동). 브리프 자체 회귀 §7.7이 이에 의존.
- Issues #2: claim lease field(model/§39A에 부재).

이 두 항목은 "구현 worker가 브리프만 보고 추측 없이 코드를 쓸 수 있는가"에 직결되고, #1은 선행 계약(§3 split)과도 표현이 엇갈린다. 따라서 **이 둘을 브리프에 보강하기 전까지는 worker 구현 slice를 시작하지 않는 것을 권장**한다. Issues #3~#6은 비차단 권고(구현 중 결정해도 되지만, 미리 적으면 추측이 줄든다).

정리: 결정 라인(what)은 승인 가능, 구현 mechanics(how) 2점은 브리프 보강 후 구현 slice 진입.

## Outstanding items

- 본 브리프 + 6개 doc 갱신은 working tree에 uncommitted. commit/publish는 owner 결정.
- 구현 slice 진입 전 권장: 브리프 §6/§7에 Issues #1(unique index/terminal-location)·#2(claim lease field) 보강. #1 해소 시 SoT v1.6.28에도 "index/terminal-location 확정" 반영.
- 오너가 다음 slice에서 함께 다룰 후속(브리프 §명시적 후속 + HANDOFF Next Task 3): `index_sync_logs` attempt append/read surface, actual ChromaDB/Elasticsearch mutation(tombstone/status update), stale-hit sync job, `analysis_completed` wiring.

## Reproduction

```bash
# 브리프 + 갱신 문서 상태
git status                                 # 03-index-worker-retry-decisions.md untracked + 6 doc modified, code 변경 없음
git diff --stat

# 정합 계약 직독(브리프가 의존하는 선행 lock)
sed -n '/39A.4 Indexes/,/^---/p' docs/mongo_collections.md        # unique index에 status 없음 확인 (Issues #1)
sed -n '/class IndexSyncOutboxEntry/,/^$/p' services/application/app/indexing/models.py  # claimed_at 부재 확인 (Issues #2)
sed -n '/## 3. 저장 단위/,/채택: \*\*B\*\*/p' docs/plans/03-index-sync-outbox-decisions.md | tail -8  # split contract 원문

# 갱신 문서 overclaim/링크 점검
git diff docs/system-contract-sot.md docs/plans/03-indexing.md docs/plans/README.md
git diff HANDOFF.md CHANGELOG.md docs/daily_logs/2026-07-03/work_log.md

# (참고) work_log "live smoke follow-up" ground-truth — 9ac59c3 hardening과 일치
rg -n "_MONGO_URI =|def test_" tests/test_indexing_mongo.py
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27099/?directConnection=true' python3 -m unittest discover tests   # 400 / skipped=40
```
