# SourceRef persistence 독립 검증 (Slice 1 마무리 / R3 폐쇄)

## Subject Metadata

- **날짜**: 2026-06-28
- **요청자**: 사용자 ("다음작업 검증하고 의심하고 의심해줘")
- **검증자**: Claude (본 세션)
- **대상 커밋**: `94a3a7f` — persist source_refs to finish Slice 1 (§113 / R3 closure)
- **정본 spec 참조**: `docs/system-contract-sot.md` **v1.4** §100-101, §113 (Approved, 변경 없음)
- **선행 검증**: `docs/verifications/2026-06-28/mongo_adapter_recheck.md` R3 추적 포인트
- **작업 출처**: committed (`git log` 확정). working tree clean.
- **검증 입장**: R3가 실제로 닫혔는지(§113 보존 = archive 후 조회 가능), SourceRef schema 변경이 기존 계약(§100/§101)을 regression 시키지 않았는지, "spec-silent" 설계 판단이 진짜 silent인지를 증명(주장 수용 금지).

## Scope

1. **R3 폐쇄**: `source_refs` collection(in-memory + Mongo)이 §113 "보존"을 archive 회귀로 닫는지
2. **기존 계약 regression**: `SourceRef`에 `id`/`project_id` 추가 — positional 생성 regression / §100 offset / §101 within-block 보존
3. **Protocol/adapter**: `repository.py` ref 메서드, `mongo_repository.py` source_refs collection·index·mapper
4. **회귀 테스트**: persist round-trip / project_id 격리 / archive 보존 — in-memory + Mongo 양 경로
5. **spec-silent 판단**: "archive 후 신규 ref 생성 차단 미추가"의 정당성
6. **실구동**: Mongo replica set에서 전체 175개 + ref 21개 재현

## Methodology

### 1. Boundary matrix (§100/§101/§113 → 분기 → test)

§113 "source_refs는 보존한다"를 (a) 보존 회귀 / (b) project_id 격리 / (c) persist round-trip 분기로 분해하고 각각 regression test에 1:1 추적.

### 2. Regression sweep

`SourceRef(` 생성 전체 grep — positional 생성(필드 순서 변경 regression) 유무. 기존 offset/within-block 검증(service.py)과 §100/§101 literal 대조.

### 3. 독립 실행

```bash
python3 -m unittest discover -s tests                     # 175, 21 skip
# replica set
docker run -d --name coresot-mongo-test -p 27018:27017 mongo:7 --replSet rs0
# rs.initiate 후
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" \
  python3 -m unittest discover -s tests                   # 175, 0 skip
CORE_SOT_TEST_MONGO_URI=... python3 -m unittest tests.test_core_sot_mongo -v  # 21 ref+mixin
```

## Findings

### Surface 1 — 기존 계약 regression 없음 (SourceRef schema 변경)

`models.py:68-76`이 `SourceRef`에 `id`/`project_id`를 **앞에** 추가(기존 첫 필드 `snapshot_id` → 3번째). positional 생성이 있으면 regression.

**전체 sweep 결과** (`grep -rn "SourceRef(" services/ tests/`): 모든 실제 `SourceRef` 생성은 keyword args.
- `service.py:247-256` (create_source_ref): `id=`, `project_id=`, `snapshot_id=`, ... 전부 keyword
- `mongo_repository.py:366-375` (_to_source_ref): 동일 keyword
- `InvalidSourceRef`는 별개 예외 클래스(무관)

→ **positional regression 없음 확정.** ✓ 기존 `source_ref.content_hash`/`.quote`/`.block_id` 접근(기존 test)도 필드 보존으로 호환.

### Surface 2 — §100/§101 offset/within-block 계약 보존

`create_source_ref`(`service.py:225-259`)의 검증 로직이 기존과 동일:
- §100 offset: `_is_int` + `start_offset < 0` / `end_offset <= start_offset` / `end_offset > len(raw_text)` (`:236-243`)
- §101 within-block: `block.start_offset <= start_offset and end_offset <= block.end_offset` (`:245-246`)
- quote/content_hash/block_id 재구성 동일 (`:252-255`)

persist 추가(`:257 record_source_ref`)만 신규. **surgical change.** ✓

### Surface 3 — R3 폐쇄 (§113 보존)

§113 "*source_refs는 보존한다*"를 archive 후 조회 가능으로 실현:
- `source_refs` collection: in-memory(`service.py:67` dict) + Mongo(`mongo_repository.py:63`)
- `record_source_ref` persist(`:115-116`, `:166-167`) + `get_source_ref` 재조회(`:118-119`, `:169-171`)
- **archive 보존 회귀**:
  - in-memory `test_archive_preserves_source_ref`(test_core_sot.py:333) — archive 후 `repo.source_refs` 존재 + `get_source_ref` 작동
  - Mongo `test_archive_preserves_persisted_source_ref`(Mixin, 양 경로) — archive 후 `repo.get_source_ref` 작동, §113 인용

**boundary matrix 빈 칸 없음**: 보존 should-fire(archive 후 조회) + should-NOT-fire(archive가 ref 미삭제)가 동일 test에 under-strict로 lock. ✓ **R3 추적 포인트 폐쇄.**

### Surface 4 — project_id 격리

`get_source_ref`(`service.py:261-265`): repo에서 id 조회 → `project_id != project_id` 시 `NotFound`. over-strict guard 존재.
- test: in-memory `test_source_ref_get_enforces_project_isolation`(test_core_sot.py:205) + Mongo Mixin(양 경로). cross-project → `NotFound` 명시. 정상 조회는 persist test에서 implicit. **양방향 lock.** ✓

### Surface 5 — Mongo adapter 정합

- collection `source_refs`(`:63`), index `(project_id, snapshot_id)` `source_refs_by_snapshot`(`:94-97`) — project 격리 + snapshot별 조회 모두 커버. get_source_ref는 `_id` PK 조회라 index 불필요하지만, Phase 2 candidate 연결/snapshot별 조회 대비로 합리적.
- `_source_ref_doc`/`_to_source_ref`(`:352-375`): project_id 포함 전 필드 왕복 매핑 → get_source_ref 격리 검사에 필요한 project_id 보존. ✓

### Surface 6 — 실구동 재현 (사용자 주장 검증)

| 단계 | 결과 |
|---|---|
| 단위 스위트(Mongo 미연결) | 175 tests, **OK (skipped=21)** |
| 단일 노드 replica set 전체 discover | **175 tests, OK (0 skipped)** |
| ref-specific Mongo(fallback+transaction) | **21 tests, OK** — archive 보존/격리/재구성 양 경로 전부 pass |

사용자 주장(175개 / 21 skip / 연결 시 전부 통과) 정확. ✓

### Surface 7 — spec-silent 판단 정당성

설계: "archive된 project/draft에 대한 신규 ref 생성 차단은 §113이 침묵하므로 추가하지 않음"(`work_log:112`).

- §113 literal: "*source_snapshots, draft_versions, source_blocks, **source_refs는 보존한다***" — 보존만 명시. "archive 후 생성 차단"은 **진짜로 침묵**.
- create_source_ref는 snapshot 존재만 요구(`service.py:233`); snapshot은 archive 후 보존되므로 archive된 snapshot에 신규 ref 생성이 현재 허용됨.
- 작업자가 이것을 spec-faithful로 두고 work_log에 근거 명시 → **CLAUDE.md "spec-silent-but-code-enforced" 회피**에 부합. 임의 구현 아님. ✓

### Surface 8 — SoT 변경 없음 주장

v1.4 §113을 구현으로 충족. SourceRef schema(id/project_id)는 spec이 명시하지 않은 구현 디테일이므로 SoT 변경 불필요. 주장 타당. ✓ 문서(CHANGELOG:5/25, work_log:107-118) 정합.

## Issues / Risks

### 비차단 observation (합격에 영향 없음, Phase 2 추적)

1. **"존재하지 않는 id → NotFound" 명시적 test 부재**: `get_source_ref`의 첫 분기(repo `None` → NotFound)는 cross-project isolation test가 ref-존재+다른-project 경로로 부분 커버하나, "id 자체가 없는" 경로는 별도 test 없음. repo None → NotFound 매핑이 자명하므로 비차단이나, completeness 차원 권고.
2. **archive 후 신규 ref 생성 허용(spec-silent)**: code가 허용, spec 침묵 → 작업자가 의도적 spec-faithful. 이것은 boundary matrix의 한 칸(post-archive ref 생성 정책)이 미정의로 남아있음. Phase 2 candidate 연결 시 정책 결정 필요 — 추적 포인트(HANDOFF Next Tasks 반영 권장).
3. **create_source_ref idempotency 없음**: 같은 span 재호출 시 매번 새 id의 ref 생성(§111은 draft save idempotency만 규정). spec-silent. Phase 2 candidate 연결 시 중복 ref 정책 결정 — 추적 포인트.

### Blocking

**없음.** R3 폐쇄(§113 보존, 양 경로 회귀), 기존 계약 regression 없음, project_id 격리 양방향 lock, Mongo 실구동 175/21 재현, spec-silent 판단 근거 기반.

## Verdict

**합격 (Pass)**

**근거:**

1. **R3 폐쇄**: §113 "source_refs 보존"이 archive 후 조회 가능으로 실현되고, in-memory + Mongo 양 경로 under-strict 회귀로 lock. 선행 재검증 R3 추적 포인트 폐쇄.
2. **기존 계약 regression 없음**: SourceRef schema 변경(id/project_id 추가)이 keyword-only 생성으로 positional regression 회피(전체 sweep 증명). §100 offset / §101 within-block / quote·content_hash·block_id 재구성이 기존과 동일 보존. 단위 스위트 175개(이전 168 → +7)가 기존 테스트 regression 없이 통과.
3. **project_id 격리**: `get_source_ref` over-strict guard(cross-project → NotFound), 양방향 lock.
4. **Mongo adapter 정합**: source_refs collection + `(project_id, snapshot_id)` index + project_id 포함 mapper. 단일 노드 replica set에서 전체 175개(0 skip) + ref 21개 양 경로 재현.
5. **spec-silent 판단 정당**: archive 후 신규 ref 생성 차단은 §113이 진짜로 침묵 → work_log 근거 기반 spec-faithful 처리. 임의 강제 아님.
6. **SoT 변경 없음**: v1.4 §113 구현 충족, schema 변경은 구현 디테일.

## Outstanding Items

1. **커밋 상태**: 94a3a7f committed, working tree clean. 게시는 소유자 결정 대기.
2. **비차단 추적**: 위 observation 2~3(archive 후 ref 생성 정책 / create_source_ref idempotency)은 Phase 2 candidate 연결 slice에서 결정 권장. HANDOFF Next Tasks 반영 제안.
3. **후속 slice(작업자 명시)**: plan 01 최소 산출물 #7(fixture), project/draft list/get API, gateway compose 편입.

## Reproduction

```bash
# 단위 스위트 (Mongo 미연결)
python3 -m unittest discover -s tests   # 175, skipped=21

# Mongo replica set 전체 + ref 집중
docker run -d --name coresot-mongo-test -p 27018:27017 mongo:7 --replSet rs0
# wait myState==1
docker exec coresot-mongo-test mongosh --quiet --eval 'rs.initiate()'
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" \
  python3 -m unittest discover -s tests                                  # 175, 0 skip
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" \
  python3 -m unittest tests.test_core_sot_mongo -v 2>&1 | grep source_ref # ref 양 경로
docker rm -f coresot-mongo-test

# regression sweep (positional SourceRef 생성 없음 확인)
grep -rn "SourceRef(" services/ tests/ | grep -v "id="
```
