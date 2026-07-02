# Phase 3B Index Sync/Outbox Decision Brief 독립 검증

## Subject metadata

- 검증일: `2026-07-02`
- 요청자: 프로젝트 오너("다음 작업 검증해줘. 계획서를 작성한거같은데 제대로 작성했는지 빠진건 없는지 더 고려해야될 건 없는지 … 48c55f0 — Phase 3B index sync/outbox 결정 브리프 추가")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상: Phase 3B planning slice(commit `48c55f0`) — 신규 결정 브리프 `docs/plans/03-index-sync-outbox-decisions.md` + 연계 변경(`03-indexing.md`, `README.md`, HANDOFF, CHANGELOG, work_log). 부수로 직전 commit `23e452e`(stale validation 검증 기록·문서 명확화)의 비-검증기록 부분 일관성도 확인.
- 정합 스펙 기준(브리프가 연결/참조하는 정본):
  - `docs/system-contract-sot.md` v1.6.24 Phase 3 bullets
  - `docs/plans/03-indexing.md`(MVP 범위·수용 기준·착수 전 결정사항)
  - `docs/plans/03-indexing-kickoff-decisions.md`(직전 Phase 3A 결정)
  - `docs/contracts.md` §7.2 IndexSyncRequest / §7.3 IndexSyncResult(envelope)
  - `docs/mongo_collections.md` §39 index_sync_logs / §64 Stale Index Detection
  - `docs/plans/README.md` 문서 지위와 우선순위
- 검증 대상 작업 출처: commit `48c55f0`(HEAD). worktree clean.

## Scope

본 slice는 code가 아니라 **planning artifact**(결정 브리프)다. 따라서 code slice의 boundary-matrix 검증 대신, 문서 검증 각도를 적용한다(CLAUDE.md §4 "Documentation-only changes"): (1) 브리프 내부 정합성, (2) 정본 계약(SoT/contracts/mongo_collections/indexing plan)과의 교차 정합성, (3) spec-precedence 위치의 명확성(§1), (4) 참조/링크 정확성, (5) 오너가 특히 요청한 **빠진 고려거리·누락** 탐지.

정합 스펙 스코프를 브리프가 명시적으로 연결하는 SoT/03-indexing/kickoff + 브리프가 prose로 참조하는 contracts §7.2~7.3, mongo_collections §39/§64로 좁혔다.

검증 surface:

1. 브리프 내부 정합성(경계·미확정 항목·추천안·slice 제안의 모순 여부)
2. 교차 정합: contracts §7.2/§7.3 envelope, mongo_collections §39 schema/index/status, §64 stale detection와의 정합·divergence
3. precedence 위치("Proposed for owner approval") 명확성 + README 우선순위 트리와 일치
4. 참조 정확성: §39 존재·status index 존재 주장, 링크 대상 존재, 역참조 연계
5. scope discipline: 미승인 proposal이므로 code wiring이 없어야 함
6. 작업자 주장(링크 확인·`git diff --check`·worktree clean) 재현
7. **planning gaps** — sync/outbox 첫 slice가 다뤄야 할 고려거리 누락 탐지

## Methodology

브리프를 정본 계약과 대조. 작업자 주장(링크·diff·clean)을 복사 없이 재실행. envelope literal은 §39/§7.2/§7.3 원문에서 재추출해 브리프 제안 모델과 비교.

실행한 명령/작업:

- `git status --short`, `git diff --check`, `git show --stat 48c55f0`/`23e452e`, `git show 48c55f0 -- <file>`로 indexing/README/HANDOFF/CHANGELOG diff 열독
- `Read`로 브리프 전량 + contracts.md §7.2~7.3(`:1050-1092`) + mongo_collections.md §39(`:2086-2136`)·§64(`:2771-2791`)·섹션 헤더 전목록 열독
- `grep`로 `index_sync_logs` 전 출현, status/index/sync_*_id/pending 추적; 링크 대상 `[ -f ]` 존재 확인; 역참조 `grep -rln`

## Findings

### 1. 브리프 내부 정합성

- 구조는 kickoff-decisions와 동일 패턴(상태/정본 연결/확정 경계/미확정 항목/선택지 표/추천/slice 제안/보류). 자기모순 없음.
- 추천안 체인은 일관: §1 event source **B(archive events)** → §2 delivery **B(Mongo outbox)** → §3 저장 **A(index_sync_logs 단일)** → §4 첫 slice = "pending outbox entry 생성까지만, worker/adapter는 보류". 각 추천의 이유가 앞선 경계(Mongo 정본 단방향, archive write는 성공해야 함, fake adapter 단계)와 충돌 없다.
- "현재 확정된 경계"(line 9-13)가 직전 Phase 3A 결과(explicit rebuild 표면, validate guard)를 정확히 반영. 본 검증자가 직전 두 slice에서 확인한 사실과 일치.

### 2. 교차 정합 — envelope/§39 참조 정확성 (대부분 정확, 일부 divergence)

정확한 참조:
- `mongo_collections.md` §39 `index_sync_logs`는 **실제로 존재**(`:2086`), 전용 Purpose/Document Example/Indexes 섹션을 갖는다. 브리프 line 49 "기존 §39 이름과 index를 재사용" · line 53 "status index도 있다"는 **정확**. §39.3 인덱스(`:2131-2133`) 중 `{ status: 1, started_at: -1 }`가 status index다. (본 검증자는 최초 grep에서 §39를 놓쳤으나 원문 확인 결과 존재 확인.)
- `contracts.md` §7.2(IndexSyncRequest, `:1052`)·§7.3(IndexSyncResult, `:1070`) 존재. 브리프 line 12 "§7.2~7.3 … persistent sync envelope" 정확.

**divergence(아래 Issues에서 상세)**: status literal("succeeded" vs "success"), target shape(단수 `vector` vs 복수 `targets`{chroma,elasticsearch}), first-slice model의 project_id/user_id 누락.

### 3. precedence 위치 + README 우선순위

- 브리프 상태 = `Proposed for owner approval`(line 3). `03-indexing.md` 노트도 "이 브리프는 아직 SoT/public contract가 아니며, 승인 전에는 … 구현하지 않는다"로 명시. HANDOFF Next Task #2도 "owner가 승인/수정한다"로 표기.
- README "문서 지위와 우선순위"(`:32-44`) 트리에서 `docs/plans/` 미구현 계획은 우선순위 4. 브리프는 미승인 proposal이므로 4 이하에 해당하며, 어느 정본보다 우선하지 않음이 명확. CLAUDE.md §1(spec-precedence) 우려 충족 — 브리프가 canonical을 가장하지 않는다.
- README 번호 목록에 신규 #15로 추가, 기존 03-indexing 이하 재번호. precedence 섹션 자체는 변경 불필요(이미 docs/plans/ 포괄).

### 4. 참조/링크 정확성

- 브리프 전방 링크 3개(`../system-contract-sot.md`, `03-indexing.md`, `03-indexing-kickoff-decisions.md`) 전부 존재.
- 역참조: `03-indexing.md`(slice 노트 + 착수 전 결정사항 check item), `README.md`(목록), HANDOFF(Current Status + Next Task + 구조 트리), CHANGELOG, work_log에 모두 연결. 끊어진 링크 없음.
- prose 참조(contracts §7.2~7.3, mongo_collections §39) 실제 섹션 존재 확인(위 §2).

### 5. scope discipline — code wiring 없음

- `git show --stat 48c55f0`: 변경 파일 전부 `docs/` + HANDOFF + CHANGELOG. `services/`, `scripts/`, `tests/` 변경 **0건**. 미승인 proposal에 대한 code wiring 부재는 의도적이고 정확(브리프 §4·승인 전 보류와 일치). CLAUDE.md §3(surgical) 충족.
- 브리프 §4.3 "Worker/adapter execution은 구현하지 않는다"·§승인 전 보류(Chroma adapter, ES, polling worker, retry/backoff, query/Context Gate wiring, draft_saved)가 code 부재와 일치.

### 6. 작업자 주장 재현 + hygiene

| 항목 | 작업자 주장 | 재확인 | 일치 |
|---|---|---|---|
| 링크 대상 존재 확인 | 했다 | 3 전방 링크 + 역참조 전부 존재 | ✅ |
| `git diff --check` | 통과 | worktree clean | ✅ |
| worktree clean | clean | `git status --short` 공백 | ✅ |

### 7. planning gaps — sync/outbox 첫 slice 누락 고려거리 (오너 요청 핵심)

아래는 브리프가 다루지 않았거나 under-specified한 항목. 브리프가 "제안" 단계이므로 이들은 결함이 아니라 **승인/첫 code slice 전에 해소할 고려거리**다.

## Issues / Risks

> 아래 1~5는 "빠진 건 / 더 고려할 건"에 대한 답이다. 브리프 자체의 정합성·참조·위치는 정확하므로 판정을 갈지 않지만, 첫 code slice 전에 브리프에 반영하거나 오너 결정으로 확정해야 한다.

1. **status literal 불일치 (가장 구체적)** — 브리프 §3·§4는 status `pending|running|succeeded|failed`를 제안. 그러나 정본 §39 문서 예시(`mongo_collections.md:2122`)와 §7.3 per-target은 `status: "success"`를 쓴다. **"succeeded" ≠ "success"**. 브리프의 enum을 그대로 채택하면 정본 envelope literal과 조용히 갈라진다. 해소: 기존 "success"를 재사용하거나, "succeeded"로 통일 시 §39/§7.3 갱신을 명시. (브리프 line 53 "§39 예시보다 넓어진다"고는 하나, literal rename까지는 언급 안 함.)
2. **target shape divergence** — 브리프 §4.1 first-slice model은 `target: vector`(단수·추상). 정본 §7.2는 `targets: ["chroma","elasticsearch"]`(복수 list), §39/§7.3은 `targets: {chroma:{…}, elasticsearch:{…}}`(복수 object, 구체 backend). Phase 3A가 이미 `target=vector`/`backend=in_memory_fake` 축소 계약을 세웠으나, persistent envelope(§7.2/§39)과의 정합은 아직 잠기지 않았다. 브리프가 첫 slice에 **어느 shape**을 저장할지(`target: vector` vs `targets: {…}`)와 `vector`↔`chroma`/`elasticsearch` 매핑 시점을 명시해야 한다.
3. **first-slice model에 project_id/user_id 누락** — 브리프 §4.1이 나열하는 field(event/source/target/status)에 `project_id`·`user_id`가 빠져 있다. §39 문서(`:2104-2105`)는 둘 다 갖고, §39 인덱스(`:2131-2132`)도 `project_id` 기반이다. `project_id`는 프로젝트 격리 수용 기준(03-indexing.md "한 프로젝트의 검색이 다른 프로젝트 record를 반환하지 않는다")에 필수이고 idempotency dedup 키에도 필요하다. model에 추가 또는 "§39 schema 준수"를 명시해야 한다.
4. **idempotency 키 미명시** — 브리프 §4.4 회귀 "repeated archive is idempotent w.r.t. outbox event"는 요구사항은 잡으나, **dedup 키**를 명시하지 않는다. 자연 후보는 §39 인덱스 `{project_id, source.mongo_collection, source.mongo_id}`(+ event type)다. 키가 schema를 결정하므로 브리프 단에서 명시 권장.
5. **§64 교차참조 누락 + version/content_hash 긴장** — (a) `mongo_collections.md` §64 Stale Index Detection(`:2771`)은 stale hit 발견 시 "create index_sync job"을 규정한다. 이는 브리프의 **지원된 option C(stale-hit→sync)** 그 자체다. 브리프는 C를 query/Context Gate wiring 부재로 후순위 하되 §64를 인용하지 않아, "§64가 이미 규정한 패턴"임이 안 보인다. §64 인용 권장. (b) §64는 staleness를 `mongo_version` 기준(`if index.mongo_version != mongo.version`)으로 잰다. 그러나 Phase 3A validator는 `content_hash` 기준이고, `03-indexing.md`도 content_hash 기준임을 명시했다. **정본 §64(version) ↔ Phase 3A 구현(content_hash)** 긴장이 존재하며, 본 브리프가 sync/stale 영역을 다루는 만큼 이 reconciliation을 플래그하면 유용하다(물론 별도 계약 갱정 사안).

비블로킹 관찰:
- §4.2 "same Mongo transaction/fallback unit"의 "fallback unit"이 모호하나 rollback 결정을 open으로 명시한 것은 적절. (compose는 replica set `rs0`라 transaction 가용.)
- 첫 slice가 pending entry만 만들고 drain worker가 없으므로 pending이 적체함을 한 줄로 명시하면 기대 설정에 도움.
- 신규 event literal(`project_archived`/`draft_archived`)은 §39/§7.2 event 어휘(현재 `analysis_completed`만)의 확장 — 브리프가 명시하면 명확.

## Verdict

**합격(planning artifact로서).**

하중 이유:
- 브리프는 내부 정합적이고 추천안 체인이 일관되며, 직전 Phase 3A 결과를 정확히 반영.
- 정본 참조가 정확: §39 `index_sync_logs` 존재 + status index 존재 주장 재확인, contracts §7.2/§7.3 존재. 링크 3개 + 역참조 전부 해결.
- precedence 위치가 명확: `Proposed for owner approval`, "아직 SoT/public contract가 아님" 명시, README 우선순위 트리(4계층)와 일치. canonical을 가장하지 않는다(CLAUDE.md §1 충족).
- scope discipline: 미승인 proposal에 code wiring 0건. 의도적·정확.
- 작업자 주장(링크 확인·`git diff --check`·worktree clean) 재현.

조건이 아닌 권고: Issues 1~5는 "제안" 단계 브리프의 결함이 아니라 **오너 승인/첫 code slice 전에 다루어야 할 고려거리**다. 오너가 물은 "빠진 건 / 더 고려할 건"에 대한 답이며, 특히 1(status literal), 2(target shape), 3(project_id 누락)은 첫 code slice schema에 직결하므로 승인 전 브리프에 반영을 권장한다.

## Outstanding items

- 브리프는 commit `48c55f0`로 반영, worktree clean. 게시는 오너 결정.
- 오너 결정 대기: Issues 1~5를 브리프에 보강할지 / 그대로 승인할지 / 수정할지.
- 승인 시 첫 code slice 범위는 브리프 §4(archive API 성공 후 pending sync log 생성 + idempotency 회귀)로 한정. 이 시점에 본 브리프의 schema 결정(1~4)이 확정돼 있어야 한다.
- §64 version ↔ Phase 3A content_hash 긴장은 별도 계약 갱정 사안(본 브리프 범위 밖이나 플래그됨).
- 부수: 직전 commit `23e452e`의 비-검증기록 부분(03-indexing.md "snapshot_missing short-circuit / content_hash drift" 명확화, SoT v1.6.24)은 본 검증자 직전 stale validation 검증과 일치함을 확인.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git status --short                                  # clean
git diff --check                                    # clean
git show --stat 48c55f0                             # docs/ + HANDOFF + CHANGELOG only (code 0건)
git show 48c55f0 -- docs/plans/03-indexing.md docs/plans/README.md HANDOFF.md CHANGELOG.md

# 참조 정본 존재 확인
grep -nE "^## 39\. index_sync_logs|^### 7\.[23] " docs/mongo_collections.md docs/contracts.md
sed -n '2086,2136p' docs/mongo_collections.md       # §39 schema + status index
sed -n '1050,1092p' docs/contracts.md               # §7.2/7.3 envelope
sed -n '2771,2791p' docs/mongo_collections.md       # §64 stale detection (version 기반)

# 링크/역참조
for f in docs/system-contract-sot.md docs/plans/03-indexing.md docs/plans/03-indexing-kickoff-decisions.md; do [ -f "$f" ] && echo "OK $f"; done
grep -rln "03-index-sync-outbox-decisions" docs/ HANDOFF.md CHANGELOG.md
```
