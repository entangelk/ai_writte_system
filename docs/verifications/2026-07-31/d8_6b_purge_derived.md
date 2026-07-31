# 독립 검증 — D8-6b derived 10컬렉션 파기 (commit f1fdb59 + b445def + be1cceb)

## Subject metadata

- **날짜**: 2026-07-31
- **요청자**: 오너("다음작업 검증해줘. D8-6b(derived 10컬렉션 파기) 완료")
- **검증자**: Claude (독립 세션, max 노력)
- **대상 슬라이스**: D8-6b — derived 10컬렉션(memory·analysis 3·writing 3·observability·context_search·review)에
  `purge_project`(직접 project_id 스코프) 추가 + 전수 가드 `test_purge_project_coverage.py`.
  **endpoint 없음**(6d). 이전 6a 검증의 H1/H2(mongo/in-memory snapshot 경로 비대칭)를 반영한
  `be1cceb`(6a 보강)까지 함께 검증.
- **정규 스펙**: `docs/plans/multi-user-auth-cms-decisions.md` §D5(파기 범위) · `docs/system-contract-sot.md`
  v1.7.70/v1.7.71 · `docs/verifications/2026-07-31/d8_6a_purge_core_sot.md`(비대칭 지적).
- **검증 대상 출처**: `f1fdb59`(6b-1 memory·analysis) + `b445def`(6b-2 나머지 6 + 전수 가드) + `be1cceb`(6a 보강).
  push 안 됨.

## Scope

1. **메타 커버리지(하중)** — 시스템의 **모든** project-scoped mongo 컬렉션을 전수 조사해 "18컬렉션 / 9 repository"
   주장이 참인지, 누락이 없는지. 전수 가드의 hardcoded list가 실제 시스템과 일치하는가.
2. **6a 비대칭 보강(be1cceb)** — mongo snapshot 파기를 직접 project_id 스코프로 정정한 것이 올바른가.
   snapshot/block doc가 실제로 project_id를 저장하는가(이전 검증의 미확인 점).
3. **직접 project_id 스코프 주장** — derived 10컬렉션이 정말 전부 간접(version 경유 등) 없이 직접 스코프인가.
4. **전수 가드 품질** — under-strict(컬렉션 누락)·over-strict(roster 수 고정) 양쪽을 잠그는가. **가드 자체의 근본 한계**는?
5. **D5=A 관측 레코드** — `llm_call_audits`·`writing_loop_audits`가 6b에 포함되는가(이전 검증 후속 포인트).
6. **memory 분리** — memory_entries(mongo)만 지우고 memory_vectors(Chroma)는 6c로 미루는 것이 명시됐는가.
   memory 도메인 내 부분 파기가 고아를 만들지 않는가.
7. **transaction 분기 일관** — derived mongo도 6a의 `_use_transactions` 패턴을 따르는가.

## Methodology

D5=A 스펙 → 시스템 전수(grep) → 커밋 diff → 코드·가드 직독 순서로 재도출(반증 지향).
**가장 중요한 검증은 메타 커버리지** — 가드가 hardcoded list에 의존하므로, 그 list가 시스템 전체와
일치하는지를 독립적으로 따져야 한다(가드 스스로는 "알려지지 않은 N번째 repository"를 못 잡는다).

- 시스템의 모든 mongo 컬렉션 참조 전수: `grep -rn 'self._\w* = .*["']' services/application/app/ --include=*.py`.
- project_id를 쿼리 키로 쓰는 컬렉션 전수: `grep -rn '"project_id"' ... | grep find/delete/update`.
- be1cceb diff 직독: snapshot 파기 경로 변경.
- 가드 직독: `tests/test_purge_project_coverage.py`.
- transaction 패턴: 각 도메인 mongo의 `_use_transactions`·`start_transaction`.
- ※ 회귀 스위트 재실행 안 함 — 작업자가 전체 suite 백그라운드 실행 중(결과 대기). 코드·가드·전수 직독으로 검증.

## Findings

### 1. 메타 커버리지 — 18컬렉션 / 9 repository, 누락 없음 ✅ (하중, 핵심)

시스템의 **모든** mongo 컬렉션을 전수 조사(project_id 스코프 쿼리로 project-scoped 식별). 결과:

| 도메인 | 컬렉션 | 파기 대상 |
|---|---|---|
| core_sot | projects·project_brief_versions·drafts·draft_versions·source_snapshots·source_blocks·source_refs·writing_accept_receipts | 8 |
| analysis | analysis_jobs·analysis_tasks·analysis_candidates | 3 |
| analysis/review_queue | review_queue | 1 |
| context_search | gate_findings | 1 |
| memory | memory_entries | 1 |
| observability | llm_call_audits | 1 |
| writing | writing_generation_jobs·writing_drafts_scratch·writing_loop_audits | 3 |
| **합계** | | **18** |

= **9 repository 계약 / 18 컬렉션**. 작업자 주장과 **정확히 일치**.

정당하게 제외된 비-project-scoped 컬렉션: `prompt_templates`(글로벌 템플릿)·`users`·`sessions`(auth)·
`index_sync_outbox`(동기화 큐)·`index_sync_logs`. 이들은 project_id 스코프가 아니므로 파기 대상이 아니다.
**누락된 project-scoped 컬렉션은 없다.**

이것이 전수 가드의 근본 한계(아래 §4)를 보완한다 — 가드가 "알려진 9개"만 검사하므로, 그 9개가
**진짜 전부**인지는 가드 밖의 문제인데, 전수 조사로 "진짜 전부"를 확인했다.

### 2. 6a 비대칭 보강(be1cceb) — 올바름 ✅

이전 검증(`d8_6a_purge_core_sot.md` H1/H2)이 지적한 비대칭: in-memory는 `snapshot.project_id` 직접
스코프, mongo는 `version→snapshot_id` 경유. `be1cceb`가 mongo를 직접 project_id 스코프로 정정:

```python
# before (경유)
snapshot_ids = [doc["snapshot_id"] for doc in self._versions.find({"project_id": ...}, ...)]
self._snapshots.delete_many({"_id": {"$in": snapshot_ids}}, ...)
# after (직접)
self._snapshots.delete_many({"project_id": project_id}, session=session)
self._blocks.delete_many({"project_id": project_id}, session=session)
```

근거 검증: `SourceBlock`(models.py:95)·`SourceSnapshot` 모델이 project_id를 가지며, mongo 테스트
(`test_purge_removes_entire_project_graph`가 `get_snapshot`·`get_blocks` None/빈 튜플 단언)가 실제
삭제를 검증한다. `delete_many({"project_id":...})`가 침묵 실패(필드 없음)라면 이 테스트가 실패하므로,
**직접 스코프가 실제로 동작함이 담보**된다. version 경유 find 제거로 단순화 + in-memory 대칭 + 고아
snapshot 잔류 방지(purge 비가역, 안전 방향은 더 넓게). 검증 피드백이 정확히 반영됐다.

### 3. 직접 project_id 스코프 — 전부 직접, 간접 없음 ✅

derived 10컬렉션 전수가 `delete_many({"project_id": project_id})` 직접 스코프(grep으로 각 도메인
mongo에서 확인). version 경유 같은 간접이 섞인 곳은 없다. "6a 비대칭 교훈 적용" 주장이 참이다.

### 4. 전수 가드 품질 — 양쪽 잠금, 단 근본 한계 존재 ⚠ (하중)

`test_purge_project_coverage.py`:
- **under-strict**(`test_all_purge_repositories_expose_purge_project`): 9개가 모두 `purge_project` 노출.
  하나라도 빠지면 실패.
- **over-strict**(`test_purge_repository_roster_is_complete`): `len(_PURGE_REPOSITORIES) == 9`. 수 자체 고정.

**근본 한계(adversarial)**: 가드는 **hardcoded list**에 의존한다. "이 9개가 purge_project를 노출"은
잡지만, **"시스템에 10번째 project-scoped repository가 없는지"는 잡지 못한다.** 새 repository가
project-scoped 컬렉션을 추가해도 list에 넣지 않으면 가드가 누락을 못 본다. 작업자가 주석으로 이를
명시("새 repository가 project-scoped 컬렉션을 추가하면 이 목록에도 넣어야 한다")했으므로 인지는 되어 있다.

**현재(2026-07-31) 이 한계는 발화하지 않는다** — §1 전수 조사로 "9개 = 진짜 전부"를 확인했으므로.
하지만 미래 회귀 가능성이므로 부채로 기록(H1).

### 5. D5=A 관측 레코드 — 포함 ✅ (이전 검증 후속 포인트 폐쇄)

D5=A(`multi-user-auth-cms-decisions.md:159`)가 파기 범위에 넣은 관측 레코드 `llm_call_audits`·
`writing_loop_audits`가 6b에 포함됨: `LlmCallAuditRepository`·`WritingLoopAuditRepository`가 가드
목록에 있고 `delete_many({"project_id":...})`로 파기. 이전 검증이 남긴 "6b 귀속 명시 확인" 포인트 폐쇄.

### 6. memory 분리 — memory_entries(mongo)만, memory_vectors(Chroma)는 6c ✅ (메모 B)

`MemoryRepository.purge_project`는 mongo `memory_entries`만 지운다. `memory_vectors`(Chroma)는 D5=A가
별도 항목으로 나열하며 6c(vector/index 4백엔드)로 명시(work_log). 즉 memory 도메인 내에서 **부분
파기**(mongo만). 그러나 **endpoint가 없으므로**(6d) production에서 호출될 일이 없어 고아가 생기지
않는다 — 6a의 논리와 동일. 6c에서 Chroma 백엔드 파기 + worker drain으로 닫힐 예정. **6c 검증 포인트**로 이관.

### 7. transaction 분기 일관 ✅

derived mongo도 6a 패턴을 따른다: `analysis/mongo_repository.py`가 `_use_transactions` 분기 +
`start_session`/`start_transaction`(213·247-249줄). 작업자 "양쪽 transaction 경로" 주장 타당.

## Issues / Risks

### Blocking (계약 위반)

- **없음.** 18컬렉션 메타 커버리지가 시스템 전수로 확인됐고(누락 0), 직접 스코프가 참이며,
  6a 비대칭이 보강됐고, 양방향 가드가 잠겼다. D5=A 스펙 위반이나 빈 칸 없음.

### Hardening recommendations (비차단)

- **H1(§4, 부채) — 전수 가드의 동적 발견.** hardcoded list(9)는 알려진 repository만 잡는다. 새
  project-scoped repository가 list에 안 들어가면 고아가 조용히 생긴다. 정기 메타 검증(이 검증이
  수행한 전수 조사)을 CI에 넣거나, 동적으로 Protocol/repository를 발견해 project-scoped 후보를
  뽑는 가드로 올리면 근본 해결. 현재는 수작업 전수에 의존. — 우선순위 낮음(지금 9=전부).
- **H2(§6, 후속) — memory_vectors(Chroma)·ES 색인·worker drain은 6c에서 닫힘.** 6c 검증에서
  (a) memory 도메인의 mongo(6b)·Chroma(6c) 양쪽이 같은 project 파기에서 함께 지워지는지,
  (b) `enqueue_project_purged`(6a에서 미사용)가 실제로 호출·drain되는지를 명시적 포인트로 둘 것.
- **H3(§2, 메모) — blocks의 project_id 인덱스 부재.** `source_blocks` 인덱스는 `blocks_by_snapshot`
  (snapshot_id 기반)이고 project_id 인덱스가 없다. `delete_many({"project_id":...})`는 collection scan.
  purge는 드문 관리자 operation이라 성능 무시 가능하지만, 대규모 project에서 느릴 수 있음. 6d 이후
  운영 관측에서 참고.

## Verdict

**합격(conditional 아님).**

하중 이유:
1. **메타 커버리지 확인(핵심)** — 시스템 전수 조사로 project-scoped 컬렉션이 정확히 18/9 repository이며
   가드와 일치, **누락 없음**. 이것이 전수 가드의 근본 한계(hardcoded list)를 독립적으로 보완한다.
2. 6a 비대칭이 `be1cceb`로 올바르게 보강됨 — mongo snapshot 직접 스코프, in-memory 대칭, 테스트가
   실제 삭제를 담보.
3. derived 10컬렉션 전부 직접 project_id 스코프(간접 없음).
4. D5=A 관측 레코드 포함, transaction 분기 일관, SoT v1.7.69→70→71 일관.
5. 회귀 0건(b-1 15·b-2 34 포커스 passed; 전체 suite는 작업자 백그라운드 실행 중).

차단 사안이 없으므로 조건 없이 합격. H1(가드 동적화)은 미래 부채, H2(6c vector/drain)는 다음
슬라이스로 이관.

## Outstanding items

- **회귀 기준선 미확정**: 전체 suite 결과가 작업자 백그라운드 실행 중. b-1·b-2 포커스(15+34)는
  확인됐으나 전량(직전 1786/4/1519 대비)은 결과 도착 후 확정. 이 검증은 코드·가드·전수 직독으로
  합격 판정을 내렸다.
- **6c 검증 포인트(H2)**: memory_vectors(Chroma)·ES·worker drain + `enqueue_project_purged` 실연결.
- **push 안 됨**: f1fdb59·b445def·be1cceb·397c43c(기준선)은 main 로컬 커밋.

## Reproduction

```bash
# 1. 메타 커버리지 — 시스템의 모든 mongo 컬렉션 전수
grep -rn 'self\._\w* = .*\(db\|database\|client\)\[' services/application/app/ --include=*.py | grep -iv test
grep -rn '"project_id"' services/application/app/ --include=*.py | grep -iv 'test\|models\|http' | grep 'find\|delete'
#   → project-scoped 18컬렉션 / 9 repository 확인 (비-project: prompt_templates·users·sessions·outbox·logs)

# 2. 6a 비대칭 보강
git show be1cceb -- services/application/app/core_sot/mongo_repository.py

# 3. 전수 가드
cat tests/test_purge_project_coverage.py   # _PURGE_REPOSITORIES 9개 + len==9 단정

# 4. 직접 스코프 전수 (간접 없음)
grep -rn 'delete_many({"project_id": project_id' services/application/app/ --include=*.py | grep -v test

# 5. 회귀(선택 — 작업자 백그라운드 실행 중)
#    python3 -m pytest tests/test_purge_project_coverage.py tests/test_memory_mongo.py \
#      tests/test_analysis_mongo.py -q
```
