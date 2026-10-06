# Decision brief — 정본 기억 조회·수정·병합 표면

상태: `Approved; 수정·병합 슬라이스 구현 완료`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`../analysis_pipeline.md`](../analysis_pipeline.md), [`../architecture.md`](../architecture.md) §canonical append-only  
목적: 프로젝트 세부정보의 "승인된 작품 기억"이 제목만 보여 줘 *"무엇이 승인됐는지 볼 곳이 없어 수정도 못한다"* 는 지적, 그리고 *"같은 인물이 (나, 주인공) 처럼 갈라져 별도 생성됐다 — 통합할 수 있어야 하고 이어져 있어야 한다"* 는 지적이 들어온 시점에, 조회 확장·수동 수정·병합의 계약 모양을 추측 없이 좁힌다.

## Owner decisions — 2026-10-06

- 수정 경로는 추천안 **B. 수동 버전 편집 API**를 채택한다. append-only 원칙(이전 버전 `SUPERSEDED` 보존)을 그대로 지키면서 사람이 직접 정본을 고치는 요구를 만족하는 유일한 최소 모양이어서다. A(읽기 전용)는 요구를 못 채우고, C(폐기만)는 수정이 불가능하며, D(되돌리기까지)는 이력 표시가 깔린 뒤의 후속이 맞다.
- 병합(같은 날 두 번째 브리프)의 사슬 연결은 추천안 **A. 생존 사슬 승계 + `merged_into` 포인터**를 채택한다 — 병합 결과는 생존 쪽의 다음 버전(버전 리셋 없음), 흡수 항목은 `SUPERSEDED` 보존 + 앞링크로 결과를 가리킨다. *"이어져 있어야지"* 를 데이터로 보존하는 최소 모양.
- 조회 확장(목록·상세·이력 탭)은 fork 가 아니었다 — `GET /projects/{id}/memory` 가 이미 전 필드를 주고 있으므로 프런트 렌더만으로 계약 무변 실현이 가능했다. 설정 탭 배치는 "개요 화면은 이미 길다"는 선례(observability-dashboard-decisions)를 따랐다.

## 1. 수정 경로

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 읽기 전용 상세만 | 목록·상세·이력만 보강. 수정은 기존 검토 흐름(재분석 → 후보 수정) 유지 | 쓰기 계약 무변, 슬라이스 최소 | 오너 지적이 그대로 남는다 — 오타·오사실 고치려면 재분석을 기다려야 함 |
| B. 수동 버전 편집 API | `PUT /projects/{id}/memory/{memory_id}` — payload 는 후보 taxonomy 검증 재사용, 새 canonical 버전 발행 + 기존 버전 `SUPERSEDED` 보존, 재색인 outbox·활동 로그 동반 | append-only 원칙 유지 + 직접 수정 가능, `_versioned_upsert` 모양 재사용, 이력 자동 보존 | operation +1(SoT 갱신), 신규 리터럴 필요, 후보-키 멱등 기반이 안 통해 버전 가드로 재설계 필요 |
| C. 폐기(retire)만 신설 | 잘못 승인한 항목을 내리는 수단만 | 잘못된 정본 즉시 제거 | "수정"은 여전히 불가 — 요구와 어긋남 |
| D. B + 되돌리기 버튼 | B 에 이전 버전 payload 로 재발행하는 버튼까지 | 실수 복구가 화면에서 한 번 | 첫 슬라이스 범위 증가 — 이력 표시 뒤 후속으로 열어도 늦지 않음 |

채택: **B**. 로컬 1인 단계에서 "직접 수정" 요구와 정본 보존 정책을 함께 만족하는 최소 모양.

후속 고려: **D와 폐기**는 B 의 응답·화면이 버전 사슬을 그대로 노출하는 한 같은 자리에서 나중에 연다(되돌리기 = 옛 payload 로 B 를 부르는 것과 동일).

## 2. B 안의 계약 리터럴 (오너 승인 안)

1. `provenance` 신규 값 `human_edited` — 기존 `source_observed`/`ai_inferred` 둘 다 사람이 고친 값에는 거짓말이라 감사 축이 정직해야 한다.
2. `source_candidate_id` 는 합성 리터럴 `manual:{idempotency_key}` — 사람 편집에 후보는 없고, 저장소의 후보 유일 인덱스가 바로 그 키로 중복을 막으므로 **재시도는 replay** 가 된다(별도 idempotency 저장소 없이 brief PUT 과 같은 멱등 모양).
3. `analysis_job_id`·`source_ref_ids`·`confidence` 는 대상 버전의 값을 이어받는다 — 편집은 내용 교정이지 근거 재판정이 아니다.
4. `scope` 는 고친 payload 로 **재계산** — 이름이 바뀐 인물이 옛 정체성 키에 묶이면 compare·별칭 매처가 옛 이름을 계속 본다.
5. 동시성: `base_version`(정수) 불일치는 409, 보관 프로젝트도 409(brief PUT 선례; sibling 승격 경로에는 없는 가드라는 차이를 SoT 에 명시했다).
6. payload 스키마는 후보 taxonomy 검증을 그대로 통과해야 한다(키 추가·제거·빈 문자열 400).

## 3. 조회 표면 (fork 아님 — 확정 범위)

- 설정에 "작품 기억" 탭: canonical 목록(타입·버전·출처 라벨 + 관찰 본문), 항목 상세(payload 전 필드·근거 수), 버전 이력(`supersedes` 사슬 전체, append-only 보존 표시).
- 개요의 요약 그리드는 그대로 두고 "전체 보기 →" 링크로 탭을 가리킨다.
- 근거 인용문 본문 표시는 유예 — memory 행엔 `source_ref_ids` 만 있고 인용문은 snapshot 축에 있어 교차 조회 계약이 별도로 필요하다. 우선 개수만.

## 4. 병합 — 사슬 연결 (같은 날 두 번째 브리프, 오너 결정 A안)

같은 인물이 분석 표기("나"/"주인공")에 따라 갈라져 canonical 둘로 살아 있는 사례가
도그푸드에서 관측됐다. 기존 병합 기계(`reconciliation.py`)는 **후보→정본** 흡수만
있어 정본↔정본에는 경로가 없었다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 생존 사슬 승계 + `merged_into` 포인터 | 병합 결과는 생존 쪽의 다음 버전(`supersedes`=생존 현재). 흡수 항목은 `SUPERSEDED` 보존 + 신규 필드 `merged_into`가 결과를 가리킴 | 두 사슬 모두 데이터로 연결 — 흡수된 이력에서 결과로 점프 가능, 버전 리셋 없음 | `memory_entries` 필드 1개 추가(옛 행 결측=None) |
| B. 승계만, 포인터 없음 | 흡수 항목은 그냥 `SUPERSEDED`; 무엇과 합쳐졌는지는 활동 로그에만 | 스키마 무변 | 흡수 사슬이 조용한 막다름 — "이어져 있어야지"를 로그 검색으로만 만족 |
| C. 새 사슬 + `merged_from` 목록 | 결과를 v1 새 항목으로, 부모 둘을 목록으로 | 부모 대칭 | 버전 리셋(생존 v3이면 병합이 v1) — 사슬 연속성과 어긋남, 필드도 필요 |

채택: **A**.

**병합 계약 리터럴(A안 확정 안):**

1. `POST /projects/{id}/memory/merge` — `{survivor_memory_id, absorbed_memory_id, base_survivor_version, base_absorbed_version, idempotency_key, payload}`. 낡은 base 는 **양쪽 각각** 검사(오류 메시지가 축을 밝힌다).
2. payload 는 **편집 기반** — 화면이 양쪽 관찰을 이어 미리 채우고 사람이 하나의 문장으로 다듬어 보낸다(서비스는 이어붙이지 않는다). 근거는 양쪽 **유니온**(인물의 별도 상태·근거가 모두 이어진다), 신뢰도·분석 잡은 생존 쪽 이어받기(직접 수정과 같은 규칙).
3. `provenance=human_edited`·`source_candidate_id="manual:{idempotency_key}"`(직접 수정과 같은 합성 멱등 키)·`scope` payload 재계산.
4. 거절면: 자기 병합·타입 불일치·**인물 외 taxonomy**·비-canonical 대상·보관 프로젝트 409, payload 스키마 위반 400. 인물 한정은 `reconciliation` 의 character-only 제한과 같은 이유다(사건·떡밥의 통합 의미는 미정의).
5. 활동 로그 `canonical_memory_merged` 1행(`after="version=N, absorbed=1"`, replay 무행 — 그룹 승인 선례의 요약 모양).

## 승인 전 보류

- 되돌리기 버튼(이전 버전 payload 재발행)
- 폐기(retire) — canonical 을 내리는 상태 전이
- 수동 신규 기억 생성(사람이 처음부터 직접 추가)
- 근거 인용문 본문 조회(memory ↔ source_ref 교차 계약)
- 사건·떡밥 병합(같은 기계의 확장)·3+ 일괄 병합·분리(split)
- **병합 재발 방지** — 분석이 같은 표기("나")를 다시 승격하면 중복이 재생된다. 별칭 매처가 정본을 읽는 축(character-alias)에서 병합 뒤 지속을 검토한다.
