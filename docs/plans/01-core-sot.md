# Phase 1. Core SOT

상태: `Draft`  
선행 조건: [`00-foundations.md`](00-foundations.md)의 SOT·격리·candidate 원칙 합의  
후속 소비자: Analysis Pipeline, Indexing, Agentic Search, Writing AI

## 목표

사용자 원문을 손실 없이 버전 저장하고, 이후의 모든 AI 결과가 원문 위치를 재현 가능하게 가리킬 수 있는 정본 계층을 만든다.

## 범위

- 프로젝트의 생성·조회·목록·수정·보관/삭제를 위한 최소 metadata와 저장 계약
- 프로젝트별 draft의 생성·조회·목록·수정 계약
- immutable `draft_versions`
- 저장 시점의 `source_snapshots`
- chapter/scene/paragraph 단위 `source_blocks`
- span과 quote/hash를 포함한 `source_refs`
- 저장 API와 snapshot/block/ref 생성 흐름
- 모든 조회·저장의 `project_id` 격리

범위 밖:

- LLM 기반 구조화 기억 추출
- ChromaDB/Elasticsearch 색인
- 글 생성과 Review UI

## 최소 산출물

1. `projects`, `drafts`, `draft_versions`, `source_snapshots`, `source_blocks`, `source_refs` 계약
2. 프로젝트 및 draft 기본 CRUD service/API
3. draft save service/API
4. deterministic snapshot hash와 block split 규칙
5. `source_ref` 생성 및 무결성 검사
6. 저장 성공/부분 실패/재시도 정책
7. 후속 Phase가 재사용할 fixture

## 핵심 흐름

```text
save request
→ draft_version 생성
→ immutable source_snapshot 생성 및 hash 계산
→ block splitter 실행
→ source_blocks 저장
→ source_refs 생성 가능 상태 확인
→ analysis trigger 반환
```

## 반드시 잠글 계약

- snapshot은 생성 후 수정하지 않는다.
- offset 기준은 snapshot `raw_text`의 Unicode code point index이며, 정규화문/byte/UTF-16 offset과 혼용하지 않는다.
- `content_hash`는 `raw_text`의 UTF-8 bytes에 대한 SHA-256이다.
- `normalized_text_hash`는 v1 필수 계약이 아니다. 정규화 기반 dedupe/search가 필요해질 때 별도 계약으로 추가한다.
- block이 바뀌어도 과거 version의 ref는 해석 가능해야 한다.
- 중복 save/retry가 같은 version을 두 번 만들지 않도록 idempotency 경계를 둔다.
- MongoDB 저장이 완료되기 전에는 후속 분석 성공을 응답하지 않는다.

## 승인된 텍스트 정본 계약

- MongoDB의 raw snapshot이 원문 SOT다. 검색/인덱스/벡터DB는 MongoDB pointer, version, hash로 재조회 가능한 파생물이다.
- raw snapshot은 저장 후 변경하지 않는다. source offset과 quote 검증은 항상 raw snapshot 기준이다.
- update/upsert 확장성을 위해 draft/source snapshot/source block/source ref는 version을 보존하고, 후속 index는 해당 version을 metadata로 가진다.
- MVP `source_blocks`는 source reference를 안정적으로 만들기 위한 deterministic block이다.
- Markdown heading(`#`, `##` 등)은 heading block 또는 그 아래 paragraph의 context로 보존한다.
- 단독 줄 `---` 또는 `***`는 명시 scene marker로 처리한다.
- paragraph block은 빈 줄 경계로 나눈다.
- AI 추론 기반 장면 분할은 SOT block split에 사용하지 않는다.
- adaptive chunking, semantic chunking, 길이 기반 episode/section chunking은 Phase 3 이후 파생 index 전략 후보로 검토한다. 이들은 MongoDB raw snapshot/source_ref 정본을 대체하지 않는다.

## 승인된 저장·보존 계약

- Docker 기반 정상 runtime은 MongoDB transaction을 기본으로 사용한다.
- transaction 범위는 draft save의 load-bearing write set 전체다: `draft_versions`, `source_snapshots`, `source_blocks`, idempotency record 또는 save request record.
- non-transaction fallback은 transaction을 사용할 수 없는 local/test 환경의 제한적 경로다.
- fallback은 write order, idempotency lookup, orphan cleanup/retry guard를 가져야 하며, 후속 분석 성공을 MongoDB 저장 성공보다 먼저 응답하지 않는다.
- MVP는 명시적 version save만 지원한다.
- autosave는 초기 구현 범위가 아니며, 실제 필요성이 확인될 때 별도 사용자 결정으로만 추가한다.
- draft save request는 `idempotency_key`를 필수로 가진다.
- 같은 `project_id + draft_id + idempotency_key` 재시도는 새 version을 만들지 않고 같은 `draft_version`을 반환한다.
- project/draft 삭제는 MVP에서 archive로 처리한다.
- `draft_versions`, `source_snapshots`, `source_blocks`, `source_refs`는 archive 이후에도 보존한다.
- archive/delete 이후 파생 인덱스는 stale 처리, version filter, rebuild 대상으로 다룬다.
- 분석 후보의 부분 승인, 부분 저장, 나머지 retry는 Phase 2/6 review action idempotency 계약에서 다룬다. Slice 1 draft save idempotency와 섞지 않는다.

## 수용 기준

- 동일 입력을 재처리하면 같은 snapshot hash와 block 경계를 얻는다.
- 임의의 `source_ref`로 정확한 snapshot, block, span, quote를 재구성한다.
- 다른 `project_id`로 동일 ID를 조회해도 데이터가 노출되지 않는다.
- 이전 draft version은 최신 저장 후에도 변하지 않는다.
- 중간 실패 후 재시도해 orphan/중복 문서가 생기지 않는다.

## 착수 전 결정사항

- [x] 원문의 block 분할 기준과 scene marker 형식: Markdown heading, 단독 `---`/`***`, 빈 줄 paragraph 기반 deterministic MVP 규칙
- [x] offset을 Unicode code point, UTF-16, byte 중 무엇으로 셀지: raw snapshot Unicode code point
- [x] 원문 정규화 여부와 `content_hash`/`normalized_text_hash`의 역할: raw text 불변, `content_hash = sha256(raw UTF-8)`, normalized hash는 v1 필수 아님
- [x] MongoDB transaction 범위와 비-transaction fallback: transaction 기본, non-transaction fallback은 local/test 제한 경로
- [x] draft autosave와 명시적 version save의 구분: MVP는 명시적 version save only, autosave 후속 결정
- [x] 프로젝트/draft 삭제를 archive, soft delete, hard delete 중 어떻게 제공할지: MVP archive
- [x] 삭제·보관 시 과거 snapshot과 파생 기억 보존 정책: snapshot/version/source_ref 보존, 파생 index stale/filter/rebuild

## 원문 및 상세 참고

- [`../abstract.md`](../abstract.md) §8.1~8.7, §13.2, §17 Phase 1
- [`../mongo_collections.md`](../mongo_collections.md) Part A~B, §45, §58, §62~63
- [`../contracts.md`](../contracts.md) §8
