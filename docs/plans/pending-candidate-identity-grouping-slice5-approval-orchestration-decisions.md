# Slice 5 착수 결정 브리프 — 그룹 승인 오케스트레이션

**상태**: 확정 — D1=A·D2=A·D3=A·D4=A 채택 (2026-09-04, 오너)
**정본**: `docs/system-contract-sot.md` v1.8.28 · 구현 페이즈
[`pending-candidate-identity-grouping-implementation-phases.md`](pending-candidate-identity-grouping-implementation-phases.md) §Slice 5
**계기**: 페이즈 공통 규칙 "원자성·부분 실패처럼 C 브리프가 열어 둔 계약 리터럴이 코드에서
유도되지 않으면 구현을 멈추고 해당 Slice 전용 짧은 결정 브리프를 작성한다". 그룹 승인은
이 페이즈에서 가장 위험한 슬라이스다(계획 문서 표현).

## Decision needed

`POST /projects/{pid}/analysis/review-inbox/groups/{group_id}/approve`(예상 operation
101→**102**)의 오케스트레이션 리터럴 4개가 기존 계약·선례에서 유도되지 않는다. 아래
Options table 4종이다.

## 계획·선례가 이미 묶은 것 (브리프 밖 — 이 슬라이스가 그대로 시행)

- **활동 로그**: Slice 4 브리프 A안이 "Slice 5 그룹 승인의 기록 모양에도 묶는다"고 못
  박았다 — `identity_group_approved`·target `candidate_identity_group`·그룹 행 1줄·
  `after`="applied=N, conflict=M, skipped=K"·**변경≥1일 때만**·멤버별 행 없음.
- **closed 그룹은 404, `contradicted`는 승인 허용**(거절 리터럴 ③과 같은 순서 — 사용자가
  모순을 그룹 승인으로 해소하는 것이 C안의 요지).
- **멤버 판정은 후보 상태 기계만**: `needs_review`만 대상, terminal 전 종류는 skip(거절
  리터럴 ①과 같은 면). eligible 0명이면 전원 skipped·변경 0·행 없음(거절 replay 관측과
  같은 모양).
- **canonical 중복 생성 금지**(계획 검증 항목): 남은 멤버는 **그룹 canonical을 강제
  대상**으로 판정한다 — 기존 compare의 scope matcher를 그대로 돌리면 event/open-question
  무매처 시 `create` 폴스루로 두 번째 canonical이 생긴다(C안이 막으려던 바로 그것).
  판정 자체는 기존 `CompareJudge` seam(같은 adapter·같은 검증)을 재사용한다.
- **진행 저장은 신규 상태 저장**: 계획이 "각 member step은 pending|applied|conflict|
  failed|skipped 상태와 결과 memory/version id를 저장한다"를 명시했다. member 행 확장은
  Slice 4 member 수명 리터럴(append-only 참조·`member_status` 신규 값 없음)과 충돌하므로,
  **그룹당 1문서의 approval 상태**(steps 내장)를 Slice 0 패턴(in-memory + Mongo 어댑터 +
  project purge 합류)으로 만든다. 파기 그래프 22→23컬렉션.
- **H1 이관 셀**(Slice 4 검증): mid-loop 스토리지 실패→전역 503, 재호출이 끝난 step을
  skip하며 이어가기 — 이 슬라이스에 포함.
- **LLM audit**: 기존 compare judge adapter 재사용(site `compare_judge`, 신규 site 아님)·
  `correlation_id`=group_id(잡이 없는 오케스트레이션의 유일한 자연 상관축)·판정 pair당
  1행·repair 둘째 행·terminal 거부 재분류 — Slice 2 셀 모양을 강제 대상 판정에 이식.
- **judge 미구성 + eligible≥2**: 시작 전 fail-fast 503(compare endpoint 선례) — seed 승격만
  해 두고 나머지를 묵히는 반쪽 상태를 만들지 않는다.
- **seed(첫 eligible) 선택**: `added_at` 최순, 동률은 후보 id 문자열 정렬(Slice 4 M8의
  교훈 — 어댑터와 무관한 결정성).

## Options table — D1. 요청 면: 멱등 key와 revision 409를 어떤 형태로?

Slice 0이 "revision은 승격 액션의 낙관적 동시성 축(Slice 5의 revision mismatch 409)"으로
지정했고, 계획 검증은 "같은 key replay, 그룹 revision mismatch 409"를 요구한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. body `{"expected_revision": N}` — revision이 key를 겸함 (권장)** | 최초 호출과 재개 호출 모두 요청 revision ≠ 그룹 현재 revision이면 409. 같은 revision 재전송은 approval 문서 revision과 붕괴해 replay/이어가기가 된다 | 요청 면 최소(필드 1개) · "명시적 key는 Slice 5"(v1.8.27 리터럴 ②)를 하나의 리터럴로 닫음 · replay 판정이 저장 문서와 live 그룹 양쪽 어느 쪽에도 시키지 않아도 된다 | "다른 사용자가 같은 revision으로 동시 승인"을 저장층에서 막지 않는다(아래 Deferred) |
| B. 불투명 idempotency key 문자열 + `expected_revision` 별도 | key로 approval 문서를 식별하고 revision은 별도 축으로 검사 | key 축과 동시성 축의 분리(재시도와 경쟁을 다른 값으로 표현 가능) | 필드 2개·규칙 2벌(이 프로젝트에 key 저장소·유일 제약 기반이 없어 분리의 이득이 실질 없다) |
| C. body 없음(상태 유도 — 거절 대칭) | 멱등을 후보 상태에서 유도 | 거절과 대칭 | revision mismatch 409를 표현할 수 없다 — 계획 검증 항목 위반 |

## Options table — D2. applied 멤버의 후보 상태: confirmed 전이를 하는가?

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. confirmed 전이 + confirm의 부수효과 (권장)** | applied(update·add_evidence·no_change) 멤버는 `needs_review→confirmed` + de-index enqueue + 대기열 resolve. memory write만 갈린다(승격/버전/무변). conflict 멤버는 `needs_review` 잔류 + 대기열 적재 | 승인하면 검토함에서 사라진다(그룹 승인의 가시 목적) · 개별 승인(confirm)과 같은 부수효과 세트로 상태 기계가 한 몸 | job-level apply(전이 없음)와 모양이 갈린다 — 그 경로는 잡 단위 일괄이고 이것은 검토 판단이라는 위에 명시 |
| B. 상태 무변(job apply 대칭) | memory만 반영, 후보는 `needs_review` 유지 | job apply와 대칭 | 승인했는데 검토함에 계속 남는다 — "승인 결과까지 하나의 그룹으로 처리"(C안)와 모순 |

## Options table — D3. 그룹 행·relation 갱신 (Slice 3이 relation.group_id 정책을 Slice 5로 이관)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 그룹·멤버·relation 행 전부 불변 (권장)** | 거절과 대칭. 가시성은 roster 교집합(Slice 3)이 정리하고, relation.group_id는 영구 "표시 전용" — 승격·병합 이력은 memory의 supersede 체인과 approval 문서가 가진다 | 거절 리터럴 ④(member 수명)와 한 몸 · `closed`의 의미(병합 흡수 껍데기)를 확장하지 않음 · 읽기면 무변 | 승인 완료 그룹이 상태값으로 표시되지 않는다 — 완료 여부는 멤버 후보 상태에서 유도 |
| B. 승인 완료 시 그룹 closed + relation.group_id 재작성 | 완료를 그룹 행에 새기고 relation이 마지막 그룹을 가리키게 갱신 | 완료 상태가 저장값으로 보임 | `closed`(병합 흡수) 의미 중복 · conflict 멤버가 남은 그룹을 조기에 지운다 · Slice 3 읽기면·판정면의 "relation.group_id는 안 쓴다" 방어와 역행 |

## Options table — D4. 판정(judge) 실패의 격리 축

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 첫 실패에 그 step=`failed`·패스 종료 (권장)** | ProviderError·parse 거부가 나면 그 멤버 step을 `failed`로 저장하고 이번 패스를 끝낸다(나머지 `pending` 유지). 응답은 200에 step 상태 노출 — Slice 6 "부분 실패는 성공처럼 닫지 않는다"의 API면. 재호출이 failed/pending을 이어간다 | Slice 2 러너 "첫 실패로 단계 종료"와 같은 모양(죽은 게이트웨이에서 pair만큼 timeout을 태우지 않음) · 부분 결과가 사람에게 보인다 | 남은 멤버가 이번 패스에 안 돈다(재호출 필요 — UI가 안내) |
| B. 멤버별 격리로 계속 진행 | 실패한 멤버만 `failed`로 두고 다음 멤버로 | 한 번의 호출로 최대한 진행 | 게이트웨이 장애 시 멤버 수만큼 timeout 누적(Slice 2 M4′가 기각한 모양) |

## Recommendation + reason

**D1=A · D2=A · D3=A · D4=A.** 네 축 모두 "기존 선례의 같은 모양을 그룹 승인에 이식"하는
방향이다. 이 페이즈의 설계 자산(개별 승인 경로의 부수효과, compare judge seam, 버전
upsert 멱등, roster 교집합 가시성)을 재사용하고 새로운 의미(`closed` 확장, 불투명 key,
job-apply식 무전이)를 만들지 않는다. 로컬 1인 dogfood 단계에서 D1-A의 경쟁 창(동일
revision 동시 승인)은 관측되지 않았고, 관측 시 저장층 유일 제약으로 좁히는 문이 열려
있다(아래 Deferred).

## Follow-up considerations

- 응답 모양(제안): `{group_id, canonical_memory_id, steps: [{candidate_id, status,
  action, memory_id, version}], idempotent_replay}` — 목록류 정렬은 후보 id 정렬(거절과
  같은 결정성 리터럴). step `status`는 계획의 5값 그대로.
- approval 문서는 첫 호출에 생성, 재호출은 `applied` step 재실행 금지(계획 문장 그대로).
  memory측 candidate→memory 멱등 키가 이중 안전선이다.
- 409 응답은 그룹 현재 revision을 detail에 실어 클라이언트가 재동기화하게 한다.
- 등재 5곳: 오류선언 EXPECTED(+409)·tier 카운트(75/102)·활동 분류(logged 28→29)·프론트
  라벨 "정체성 그룹 승인"+비링크 사유·plans 인덱스 — 전수 전에 focused 4모듈로 선제 확인.
- Slice 4 H1 이관 셀(mid-loop 503·재호용 이어가기)을 이 슬라이스 셀 목록에 포함한다.

## Deferred / out of scope

- 동일 revision 동시 승인의 저장층 유일 제약(경쟁 관측 시).
- conflict 멤버의 후속 개별 처리 UX는 Slice 6(grouped UI) — 이 슬라이스는 API만.
- approval 문서의 보존 기한·정리(파기 그래프에는 project purge로 합류, 그 외 정리 없음).
