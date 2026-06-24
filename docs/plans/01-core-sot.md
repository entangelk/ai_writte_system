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
- offset 기준은 원문/정규화문 중 하나로 명시하며 혼용하지 않는다.
- hash 알고리즘과 normalization 규칙은 재현 가능해야 한다.
- block이 바뀌어도 과거 version의 ref는 해석 가능해야 한다.
- 중복 save/retry가 같은 version을 두 번 만들지 않도록 idempotency 경계를 둔다.
- MongoDB 저장이 완료되기 전에는 후속 분석 성공을 응답하지 않는다.

## 수용 기준

- 동일 입력을 재처리하면 같은 snapshot hash와 block 경계를 얻는다.
- 임의의 `source_ref`로 정확한 snapshot, block, span, quote를 재구성한다.
- 다른 `project_id`로 동일 ID를 조회해도 데이터가 노출되지 않는다.
- 이전 draft version은 최신 저장 후에도 변하지 않는다.
- 중간 실패 후 재시도해 orphan/중복 문서가 생기지 않는다.

## 착수 전 결정사항

- [ ] 원문의 block 분할 기준과 scene marker 형식
- [ ] offset을 Unicode code point, UTF-16, byte 중 무엇으로 셀지
- [ ] 원문 정규화 여부와 `content_hash`/`normalized_text_hash`의 역할
- [ ] MongoDB transaction 범위와 비-transaction fallback
- [ ] draft autosave와 명시적 version save의 구분
- [ ] 프로젝트/draft 삭제를 archive, soft delete, hard delete 중 어떻게 제공할지
- [ ] 삭제·보관 시 과거 snapshot과 파생 기억 보존 정책

## 원문 및 상세 참고

- [`../abstract.md`](../abstract.md) §8.1~8.7, §13.2, §17 Phase 1
- [`../mongo_collections.md`](../mongo_collections.md) Part A~B, §45, §58, §62~63
- [`../contracts.md`](../contracts.md) §8
