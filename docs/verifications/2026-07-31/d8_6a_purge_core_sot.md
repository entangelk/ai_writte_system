# 독립 검증 — D8-6a project 영구 파기 인터페이스(core_sot) (commit 45b6c16 + 3ac9748)

## Subject metadata

- **날짜**: 2026-07-31
- **요청자**: 오너("다음작업 검증해줘. D8-6a(영구 삭제 첫 서브슬라이스)를 완료했습니다.")
- **검증자**: Claude (독립 세션, max 노력)
- **대상 슬라이스**: D8-6(영구 삭제, D5=A)의 첫 서브슬라이스 — `CoreSotRepository.purge_project`
  (Protocol·in-memory·mongo) + `CoreSotService.purge_project` + outbox `PROJECT_PURGED` 이벤트/헬퍼.
  **endpoint 없음**(endpoint는 D8-6d).
- **정규 스펙**: `docs/plans/multi-user-auth-cms-decisions.md` §D5(파기 범위 = A)·§D6(관리자 범위) ·
  `docs/system-contract-sot.md` v1.7.69 · `CLAUDE.md` §3(패턴 스윹)·§4(양방향 회귀).
- **검증 대상 출처**: commit `45b6c16`(코드·테스트·문서) + `3ac9748`(기준선 갱신). push 안 됨.

## Scope

1. **파기 범위 vs D5=A 스펙** — 6a가 담당한 core_sot 범위가 정규 스펙의 전체 파기 범위와 어떻게
   관계맺는지. 6a~6d 분할이 D5=A 전체를 커버하는가.
2. **"부분 삭제 고아 위험 D5 회피" 설계** — endpoint가 없으면 production 호출이 없다 → 고아가
   생길 수 없다. purge_project가 정말 production(main.py·worker·scripts)에 연결되지 않았는가.
3. **snapshot 체인 파기의 완전성** — version→snapshot_id 순회가 snapshot·blocks를 빠짐없이 지우는가.
   mongo와 in-memory의 snapshot 파기 경로 차이가 결과에 영향을 주는가.
4. **transaction 무결성(mongo)** — `_use_transactions` 분기가 transaction/fallback 양쪽을 올바르게
   처리하는가. 테스트가 양쪽을 검증하는가.
5. **양방향 회귀** — under-strict(대상 잔류)·over-strict(인접 project 과삭제) 양쪽이 잠겼는가.
6. **enqueue 안 함 + PROJECT_PURGED** — service.purge_project는 정말 enqueue하지 않는가.
   enqueue_project_purged는 6a에서 어디에 쓰이는가(미사용/dead 코드인가).
7. **회귀 기준선** — 1779/1/1519 → 1786/4/1519. +7 passed, **skip 1→4(+3)** 의 정당성.
8. **NotFound / 부분 잔류** — 존재하지 않는 project, 재파기, 파기 후 잔류 금지.

## Methodology

D5=A 스펙(§파기 범위) → 커밋 diff → 코드 직독 → 테스트 직독 → 호출부 grep 순서로 재도출(반증 지향).

- `git show --stat 45b6c16 3ac9748`로 변경 파일 전수.
- D5=A 파기 범위: `multi-user-auth-cms-decisions.md:157-161` 직독.
- 코드 직독: `mongo_repository.py::_purge_project`·`service.py::purge_project`(in-memory + service).
- 호출부 전수: `grep -rn "purge_project\|enqueue_project_purged" services/ scripts/` — production
  경로(main.py·worker) 연결 여부.
- 테스트 직독: `test_core_sot.py::CoreSotPurgeTest`·`test_core_sot_mongo.py`·`test_indexing_phase3a.py`.
- transaction 양쪽 검증: `test_core_sot_mongo.py`의 `FallbackMongoTest`(non-tx)·`TransactionMongoTest`(tx)가
  `_MongoContractMixin`을 상속하는지 확인.
- snapshot 데이터 모델: `models.py::SourceSnapshot`·in-memory `snapshots` 타입·mongo 저장(`_id=snapshot_id`).
- ※ 본 검증은 **회귀 스위트를 재실행하지 않았다** — 작업자가 양방향 뮤테이션을 실측했고(3ac9748),
  코드·테스트를 직독으로 검증하는 것으로 충분하다고 판단. 스위트 재실행은 기준선(1786)의 재확인일 뿐.

## Findings

### 1. 파기 범위 vs D5=A — 분할이 전체를 커버 ✅ (하중)

정규 스펙(`multi-user-auth-cms-decisions.md:157-161`)이 정한 파기 범위:

> project 하나를 파기하면 `source_snapshots`·`draft_versions`·`source_refs`·`memory`·
> `memory_vectors`(Chroma)·ES 색인·`llm_call_audits`·`writing_loop_audits`·scratch가 모두 대상.
> **부분 삭제는 조용한 고아 데이터를 만든다.**

작업자의 4-서브슬라이스 분할과 스펙 항목의 대응:

| D5=A 스펙 항목 | 서브슬라이스 | 6a 코드에서 |
|---|---|---|
| source_snapshots·blocks | **6a** | `snapshots`·`blocks`(snapshot 체인) |
| draft_versions | **6a** | `versions` |
| source_refs | **6a** | `source_refs` |
| (+ project·draft·project_briefs·accept_receipts = core_sot 본체) | **6a** | 6 직접 컬렉션 |
| memory·llm_call_audits·writing_loop_audits·scratch | 6b | (미구현) |
| memory_vectors(Chroma)·ES 색인·worker drain | 6c | (미구현) |
| endpoint·권한·boundary matrix | 6d | (미구현) |

6a가 담당한 core_sot 범위(직접 project_id 스코프 6컬렉션: `versions`·`drafts`·`source_refs`·
`writing_accept_receipts`·`project_briefs`·`projects` + snapshot 체인 2: `snapshots`·`blocks`)는
D5=A 명시 항목 중 core_sot 부분을 정확히 커버한다. 누락 항목 없음(나머지는 6b·6c에 명시적 귀속).
**분할이 스펙을 빠짐없이 나눈 것이라는 점이 확인됐다.**

### 2. "부분 삭제 고아 위험 D5 회피" — 설계 참 ✅

D5=A가 "부분 삭제는 고아를 만든다"고 경고한 것에 대한 작업자의 해법: **endpoint는 6d에서만 추가 →
6a~6c 동안 purge는 production에서 호출될 일이 없다 → 부분 구현 상태의 고아가 생길 수 없다.**

이 주장을 grep으로 검증:

```
$ grep -rn "purge_project\|enqueue_project_purged" services/ scripts/
service.py:938:        self._repo.purge_project(project_id)        # 서비스 내부
mongo_repository.py:185/187/189: self._purge_project(...)          # 어댑터 내부
```

- `main.py`(엔드포인트)·worker entrypoint·`scripts/`에 **호출부 0건**.
- `enqueue_project_purged`도 services/ 내 **호출부 0건**(테스트만).

즉 6a 상태에서 `purge_project`·`enqueue_project_purged` 모두 production 경로에 연결되지 않았다.
**endpoint 없음 → production 호출 없음 → 고아 없음** 주장은 참이며, 이것이 D5 경고와 합리적으로
화해한다(production 노출은 6d에서 전체 파기 체인이 완성된 뒤에만). 이 슬라이스 단독으로는
"부분 삭제"가 세상에 노출되지 않는다.

### 3. snapshot 체인 파기 — 완전하나 mongo/in-memory 경로 비대칭 ⚠ (하중, 비차단)

**완전성**: mongo `_purge_project`는 `versions.find({project_id}, {snapshot_id})`로 snapshot_id 집합을
모아 `snapshots.delete_many({_id: {$in: ids}})` + `blocks.delete_many({snapshot_id: {$in: ids}})`.
정상 데이터(snapshot은 항상 version과 함께 `save_draft`에서 생성)에서 version이 가리키는 snapshot을
빠짐없이 지운다. blocks는 `SourceBlock`이 `snapshot_id` 필드를 가지므로(`models.py:96`) 같은 체인으로
지워진다.

**비대칭(adversarial 발견)**: 두 저장소가 snapshot을 찾는 경로가 **다르다**.

| | in-memory | mongo |
|---|---|---|
| snapshot 후보 수집 | `snapshot.project_id == project_id`(**직접** 스코프) | `versions → snapshot_id`(**경유**) |
| 의미 | project의 snapshot **전부** | version이 reachable한 snapshot만 |

`SourceSnapshot` 모델은 project_id를 가지므로(in-memory가 `snapshot.project_id`를 읽음,
`service.py:176`), in-memory는 직접 스코프가 가능하다. mongo snapshot doc은 `_id=snapshot_id`로
저장되고 project_id로 직접 스코프하지 않는다. **정상 invariant(모든 snapshot은 정확히 한 version을
통해 생성) 하에서는 두 경로가 같은 결과**를 낸다. 그러나 **version 없는 고아 snapshot이 존재하는
비정상 경로**에서는 in-memory는 지우고 mongo는 남긴다 → 결과가 갈라진다.

이것은 흥미롭게도 R-a 트랙에서 작업자가 "사본을 만들지 않고 같은 경로를 재사용한다"(측정 리그)고
강조한 원칙과 **대조적**이다 — 여기서는 두 저장소가 서로 다른 경로를 쓰며 결과 동일성이 invariant에
의존한다. 다만 purge는 **되돌릴 수 없는** 작업이므로 안전 방향은 "더 넓게 지우는 쪽"(in-memory)이고,
mongo 쪽이 잠재적 잔류 방향이다. 고아 snapshot이 발생할 수 있는 경로가 현재 코드에 없다면(**그렇다** —
snapshot은 `save_draft`에서만 생성되고 항상 version과 짝을 이룸) 실질적 위험은 낮다.

테스트(`test_purge_removes_entire_project_graph`)는 **정상 데이터만** 검증하므로, 이 비대칭은
회귀로 잡히지 않는다.

### 4. transaction 무결성 — 양쪽 검증 ✅

`mongo_repository.py:purge_project`: `if self._use_transactions:` 분기로 transaction(session.start_transaction)
또는 session=None fallback. SoT가 "non-transaction fallback은 single-writer local/test 전용"이라 정한
계약과 일치.

테스트 구조(`test_core_sot_mongo.py`): `_MongoContractMixin`(124줄)을
- `FallbackMongoTest`(694줄, non-transaction)와
- `TransactionMongoTest`(860줄, transaction)가 **모두 상속**.

`test_purge_removes_entire_project_graph`가 mixin에 있으므로 **두 클래스에서 각각 실행**된다.
작업자의 "mongo(양쪽 transaction 경로) 76 passed" 주장은 타당하다.

### 5. 양방향 회귀 — 양쪽 잠김 ✅

- **under-strict(대상 잔류)**: `test_purge_removes_entire_project_graph_and_leaves_others_intact`가
  `assertNotIn(project.id, repo.projects)` + draft·version·snapshot·blocks·source_refs 전부 단언.
  한 컬렉션이라도 남기면 실패. 작업자 실측 양방향 뮤테이션(snapshot 체인 제거 시 실패)이 이 방향.
- **over-strict(인접 과삭제)**: 같은 테스트가 인접 project `other`의 project·draft·version·snapshot을
  `assertIn`/`assertIsNotNone`로 보존 단언. **이것이 핵심** — purge에서 가장 치명적인 결함은
  대상이 아닌 project까지 지우는 것이며, 이 테스트가 그것을 잠근다.
- **잔류/재파기**: `test_purge_leaves_no_residue_repurge_raises_not_found`가 파기 후 `get_project` None +
  재파기 NotFound. 부분 잔류(숨은 데이터)를 금지.

두 방향 모두 단언됐다(`CLAUDE.md` §4 "양방향 회귀" 충족).

### 6. enqueue 안 함 + PROJECT_PURGED — 코드·주석 일치 ✅ (메모 C)

- `service.py::purge_project`(935줄): `_require_project` → `_repo.purge_project`. **enqueue 호출 없음**.
  주석: "archive와 달리 enqueue하지 않는다 — enqueue는 endpoint(6d)에서 archive와 같은 시점에."
- `indexing/models.py`: `IndexSyncEvent.PROJECT_PURGED` 추가(주석: "drain은 6c에서 연결 — a 단계엔
  production 호출자가 없어 worker가 이 entry를 만나지 않는다").
- `indexing/service.py::enqueue_project_purged`: 헬퍼 정의. **services/ 내 호출부 0건**(테스트만).

즉 6a에서 `enqueue_project_purged`는 **정의만 있고 production 호출부가 없다**("정의됐으나 drain 대기"
상태). 이것은 의도적 슬라이스 분할이지만, 6a 단독으로 보면 미사용 메서드다. **6c에서 drain(handler)이
연결되고 6d에서 service/endpoint가 enqueue를 호출하는지**가 후속 슬라이스의 검증 포인트다.

### 7. 회귀 기준선 — +7 신규, skip +3 정당 ✅ (메모 D)

1786 passed / 4 skipped / 1519 subtests (직전 1779/1/1519).
- **+7 passed** = D8-6a 신규 회귀(in-memory 3·indexing 1·mongo 2×양쪽 클래스 = 작업자 보고와 정합).
- **skip 1→4(+3)**: 작업자 "알파 호스트 환경(live Chroma 등)". HANDOFF가 "skip 수는 머신·인프라
  기동 여부마다 다르다"고 정한 바와 일관. `-rs`로 정확한 skip 항목이 명시되지는 않았으나(메모 D),
  D8-6a 코드 변경과 무관한 인프라 skip으로 합리적.
- subtests 1519 무변(신규 테스트가 subtest를 안 쓰므로).

## Issues / Risks

### Blocking (계약 위반)

- **없음.** 파기 범위가 D5=A와 일치하고, "부분 삭제 고아 위험"이 endpoint 부재로 구조적으로 회피됐으며,
  양방향 회귀가 잠겼다. 코드·스펙·테스트 간 계약 위반이나 빈 경계 칸은 없다.

### Hardening recommendations (비차단)

- **H1(§3, 메모) — mongo/in-memory snapshot 파기 경로 비대칭 기록.** 두 저장소가 snapshot을 다른
  경로(직접 project_id vs version 경유)로 찾는 점, 그래서 고아 snapshot 비정상 경로에서 결과가
  갈라질 수 있음(안전 방향은 in-memory, mongo가 잠재 잔류)을 work_log에 한 줄로 명시하면, 다음
  검증자가 같은 의심을 반복하지 않는다. 현재 snapshot은 항상 version과 함께 생성되므로 실질 위험은
  낮지만, purge의 비가역성을 고려하면 기록 가치가 있다.
- **H2(§3, 권장) — mongo snapshot doc의 project_id 저장 여부 확인.** mongo가 version 경유한 이유가
  (a) snapshot doc에 project_id 필드가 없어서인지, (b) version-reachable만 지우려는 의도적 선택인지가
  코드/주석에 명시되지 않았다. (a)라면 경유가 필연이고, (b)라면 in-memory를 경유로 맞추는 쪽이
  일관적이다. 6b/6c에서 derived·vector까지 지울 때 이 경로 결정이 재사용되므로 지금 정해두면 좋다.
- **H3(§6, 부채) — enqueue_project_purged 호출부 연결 추적.** 6a에서 production 호출부가 없는
  미사용 메서드. **6c(drain)·6d(endpoint에서 enqueue)에서 실제로 연결되는지**를 후속 슬라이스
  검증의 명시적 포인트로 둘 것.
- **H4(§7, 메모) — skip +3의 -rs 명시.** 알파 호스트 환경 skip이라는 설명은 합리적이나, 어떤
  3개 테스트가 skip됐는지 `-rs` 출력을 기준선 갱신에 한 줄 남기면 머신 차이와 회귀가 확실히 구분된다.

## Verdict

**합격(conditional 아님).**

하중 이유:
1. 파기 범위가 D5=A 스펙(§157-161)과 일치 — 6a는 core_sot(6 직접 + 2 snapshot 체인), 나머지는
   6b·6c·6d에 명시적 귀속, 누락 없음.
2. "부분 삭제 고아 위험 D5 회피" 설계가 참 — purge_project·enqueue_project_purged 모두 production
   호출부 0건(grep 확인), endpoint가 6d에만 추가되므로 6a 상태의 부분 파기가 세상에 노출되지 않는다.
3. 양방향 회귀 잠김 — under-strict(대상 잔류)·over-strict(인접 과삭제)·잔류/재파기.
4. transaction/non-transaction 양쪽 검증(`FallbackMongoTest`·`TransactionMongoTest`가 mixin 상속).
5. 회귀 0건, +7 신규.

차단 사안이 없으므로 조건 없이 합격. H1·H2(snapshot 경로 비대칭)는 **6b·6c에서 derived·vector까지
파기 범위를 넓힐 때 재검토할 지점**으로, 지금은 core_sot 정상 데이터에서 결과가 같으므로 6a 합격을
막지 않는다.

## Outstanding items

- **후속 검증 포인트(6b/6c/6d)**: (a) H3 enqueue 호출부 연결, (b) H1/H2 snapshot 경로 비대칭이
  derived·vector 파기에서 재사용될 때의 일관성, (c) D5=A 관측 레코드(`llm_call_audits`·
  `writing_loop_audits`)의 6b 귀속 명시, (d) 6d endpoint 권한·boundary matrix 확장(auth 69→70 operation).
- **머신 상태**: 본 검증은 다른 머신에서 repo만 봤다. 작업자 보고("host argon2 OK, test-mongo ON")를
  재실행으로 확인하지 않았다(코드·테스트 직독으로 충분하다고 판단).
- **push 안 됨**: 45b6c16·3ac9748은 main 로컬 커밋.

## Reproduction

```bash
# 1. 커밋 범위 (코드+테스트+문서, endpoint 없음)
git show --stat 45b6c16 3ac9748

# 2. production 호출부 0건 확인 (고아 위험 회피의 근거)
grep -rn "purge_project\|enqueue_project_purged" services/ scripts/
#  → service.py / mongo_repository.py 내부만, main.py·worker·scripts 없음

# 3. D5=A 파기 범위 vs 분할 (스펙 직독)
sed -n '146,162p' docs/plans/multi-user-auth-cms-decisions.md

# 4. snapshot 파기 경로 비대칭 (H1/H2)
sed -n '171,205p' services/application/app/core_sot/service.py          # in-memory: 직접 project_id
sed -n '189,205p' services/application/app/core_sot/mongo_repository.py  # mongo: version 경유

# 5. 양쪽 transaction 검증 클래스
grep -n "class FallbackMongoTest\|class TransactionMongoTest\|class _MongoContractMixin" \
  tests/test_core_sot_mongo.py

# 6. 회귀(선택 — 코드·테스트 직독으로 검증됐으므로 생략 가능)
#    docker compose -f docker-compose.test.yml up -d
#    until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done
#    python3 -m pytest tests/test_core_sot.py tests/test_core_sot_mongo.py tests/test_indexing_phase3a.py -q
```
