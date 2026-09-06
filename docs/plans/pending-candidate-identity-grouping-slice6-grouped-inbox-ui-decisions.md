# Slice 6 착수 결정 브리프 — grouped Inbox UI 가 읽을 것이 없다

**상태**: Draft — 오너 결정 대기 (2026-09-06)
**정본**: `docs/system-contract-sot.md` v1.8.29 · 구현 페이즈
[`pending-candidate-identity-grouping-implementation-phases.md`](pending-candidate-identity-grouping-implementation-phases.md) §Slice 6
**계기**: 페이즈 공통 규칙 — *"Slice 진행 중 … C 브리프가 열어 둔 계약 리터럴이 코드에서
유도되지 않으면 구현을 멈추고 해당 Slice 전용 짧은 결정 브리프를 작성한다"*

## Decision needed

Slice 6 은 페이즈 문서가 **UI 전용**으로 그은 슬라이스다(*"계약을 바꾸는 Slice 는 0·3·4·5"*).
그런데 그 UI 가 그리려는 두 가지가 **읽기면에 존재하지 않는다**. 둘 다 고치려면 Slice 3 이
만든 읽기면(`identity_group` payload)을 넓혀야 하고, 그것은 UI 전용이라는 이 슬라이스의
전제를 깨는 계약 개정(SoT 개정 + `_review_inbox_payload` 변경)이다.

| # | 그리려는 것 | 읽기면에 있는가 | 결과 |
|---|---|---|---|
| **D1** | 그룹 **승인** 버튼 | ✗ — `POST …/groups/{gid}/approve` 는 body `{"expected_revision": N}` 가 **필수**(D1=A, SoT v1.8.29 ①)인데 `GET …/review-inbox` 의 `identity_group` 은 `group_id·group_size·group_status·group_member_ids·identity_rationale_summary` 만 싣는다. **`revision` 을 아무 읽기 경로도 주지 않는다** | 승인 버튼을 **만들 수 없다**. 409 detail 에 현재 revision 이 있지만 그것은 사람용 문자열이고 **H3 가 `detail` 분기를 금지**한다 |
| **D2** | `uncertain` 관계의 *"같은 대상일 수 있음"* 표시 | ✗ — `uncertain` 은 relation 행에만 남고 group member 로 연결되지 않는다(`identity_judging.py`: *"`same` 만 group member 로 연결"*). 읽기면에 relation 을 노출하는 경로가 **없다** | 표시를 **만들 수 없다** |

D1 은 이 슬라이스의 **완료 기준**(#6 "그룹 승인/거절 실패·부분 실패를 사람이 이해할 수
있다")에 직결하므로 어떤 형태로든 답이 있어야 한다. D2 는 §Slice 6 **범위** 문장에는 있으나
같은 절의 **검증 목록**에도 **완료 기준 #6** 에도 없다 — 그 비대칭이 D2 를 선택지로 만든다.

## 실측한 사실 (추측 아님)

- `CandidateIdentityGroup.revision` 은 저장 엔티티에 있다(`analysis/identity_groups.py:64`).
  `review_inbox._identity_summaries` 는 이미 그 `group` 객체를 손에 쥐고 요약을 만든다 —
  **읽기면에 싣지 않기로 한 것이지 못 싣는 것이 아니다.**
- `group/{gid}` 단건 GET 은 없다. 그룹을 읽는 경로는 `review-inbox` 목록/단건 두 개뿐이다
  (`grep "groups/" routers/*.py` = reject·approve 두 라우트).
- `revision` 은 판정 패스가 멤버를 붙일 때 오른다. 즉 목록을 읽은 뒤 승인을 누르기까지
  값이 낡을 수 있고, **그때 409 로 재동기화하는 것이 D1=A 의 설계**다(Slice 5 브리프).
- Review Inbox 응답은 `dict[str, object]` 선언이라 **OpenAPI/`schema.d.ts` 는 무변**이다
  (Slice 3 이 확정한 지문). 프론트 타입은 `api/client.ts` 의 손선언이다.

---

## D1. 승인 버튼이 `expected_revision` 을 어디서 얻는가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 읽기면에 `group_revision` 을 더한다 (권장)** | `identity_group` payload 에 키 하나 추가. `_identity_summaries` 가 이미 든 `group.revision` 을 그대로 싣는다 | D1=A(낙관적 동시성 축)를 **그대로 보존**한 채 클라이언트가 값을 얻는 유일한 정직한 경로 · 순수 additive(기존 소비자 무영향) · `schema.d.ts` 무변 · 구현 ~4줄 + 셀 · 409 재동기화 경로가 설계대로 산다 | Slice 6 이 계약을 건드린다(SoT 개정·페이즈 문서의 "UI 전용" 문장 정정) · 그룹당 값이 멤버 수만큼 반복된다(`group_id` 등과 같은 모양이라 새 성질은 아님) |
| B. `expected_revision` 을 optional 로 바꾼다 | 없으면 서버가 현재 revision 을 채택 | 읽기면 무변 · 프론트 최소 | **D1=A 를 무력화한다** — 값을 안 보내는 클라이언트에게 낙관적 동시성이 사라지고, 판정이 멤버를 붙인 뒤에도 "내가 본 그룹"이 아닌 것을 승인한다. 오너가 A 로 확정한 축을 구현자가 되돌리는 모양 |
| C. 그룹 단건 GET 신설(`GET …/groups/{gid}`) | 승인 직전에 revision 을 읽는다 | 그룹 상세(멤버 payload·relation)를 나중에 확장할 자리가 생긴다 | operation 102→103 · 목록에서 이미 그룹을 다 아는데 클릭마다 왕복 1회 추가 · **경합을 못 줄인다**(읽고 나서 누르는 사이에 또 오를 수 있다 — A 와 같은 409 재동기화가 여전히 필요) |
| D. 프론트가 409 `detail` 을 파싱해 재시도 | 아무 값이나 보내고 409 의 숫자를 읽어 재전송 | 서버 무변 | **H3 정면 위반**(`detail` 분기 금지) · 첫 호출이 항상 버려지는 왕복 · 유료 경로에 의미 없는 호출을 던진다 |

**추천: A.** 로컬 1인 도그푸드 단계에서 필요한 것은 "승인 버튼이 눌린다" 하나이고, A 는
오너가 이미 확정한 D1=A 를 **바꾸지 않고** 그 축이 요구하는 값을 클라이언트에게 주는
유일한 선택지다. B 는 오너 결정을 구현자가 되돌리는 방향이고, C 는 A 가 주는 것을 왕복
하나 더 써서 준다. **계약 개정 자체는 피할 수 없다** — 피하는 유일한 길이 B(축 무력화)뿐인데
그것이 가장 비싼 값이다.

## D2. `uncertain` 표시를 이 슬라이스에서 여는가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **B. 표시도 액션과 함께 유예한다 (권장)** | §Slice 6 범위 문장에서 `uncertain` 표시를 빼고, 페이즈 Deferred 의 *"수동 합치기/분리 확정 액션"* 항목에 **표시**를 합쳐 같은 트리거를 단다 | 완료 기준 #6·검증 목록 어느 쪽도 요구하지 않는다 · Slice 6 이 UI 전용으로 남는다(D1 의 키 하나만 예외) · `uncertain` 은 **그룹 밖 pair** 라 읽기면 확장이 그룹 요약이 아니라 **item 최상위 새 축**이다 — 가시성·정렬·결정성 규칙을 Slice 3 만큼 새로 정해야 하는 분량 | 도그푸드에서 uncertain 이 얼마나 나오는지 **관측 자체가 안 된다** — 유예의 트리거가 *"uncertain 표시가 검토를 막을 때"* 인데 표시가 없으면 그 트리거가 영영 안 온다(→ 트리거 재작성 필요) |
| A. 지금 연다 | item 에 `uncertain_peer_ids`(가시 후보로 교집합) 를 additive 로 싣고 UI 가 배지로 표시 | 도그푸드 관측이 열린다 · Slice 3 의 roster 규칙을 재사용 | 그룹 요약이 아닌 **새 읽기 축**(ungrouped 후보에도 붙는다) · 결정성·tie-break·양끝 가시성 규칙을 새로 정하고 셀로 잠가야 한다 — Slice 3 규모의 백엔드 작업이 UI 슬라이스 안에 들어온다 |
| C. 그룹 안 uncertain 만 표시 | roster 양끝이 모두 같은 그룹인 uncertain 만 | 범위 최소 | **거의 공집합이다** — 같은 그룹이라는 것은 `same` 경로로 이어졌다는 뜻이고, 그 pair 에 uncertain 이 또 있는 경우만 보인다. 만들어도 화면에 뜰 일이 드물어 관측 가치가 없다 |

**추천: B**, 단 **트리거를 고쳐 단다**. 지금의 트리거(*"uncertain 표시가 실제 검토를 막을 때"*)는
표시가 있다는 전제를 깔고 있어 B 를 고르면 자기모순이 된다. 대체 트리거로 **"`contradicted`
그룹이 처음 관측될 때 또는 오너가 검토함에서 '이 둘이 같은 것 같은데 안 묶였다'를 만날 때"**
를 제안한다 — 관측 가능한 사건이고, 그때가 표시와 액션을 **한 슬라이스로** 여는 자리다.

## Follow-up considerations

- D1=A 를 고르면 SoT 개정 1행(v1.8.29 → 신규)과 페이즈 §Slice 6 의 "계약을 바꾸는 Slice 는
  0·3·4·5" 문장 정정이 함께 간다. `identity_rationale_summary` 처럼 **표시 전용이 아니라
  요청 입력**이 되는 첫 그룹 필드라 그 성격을 계약 문장에 적는다.
- 승인 후 UI 재조회는 목록 전체 재읽기다(현행 `runAction` 패턴). `steps[]` 의 부분 실패는
  **재조회로 사라지지 않게** 컴포넌트 상태에 남긴다 — "부분 실패를 성공처럼 닫지 않는다"가
  화면에서 성립하는 자리가 여기다.
- 활동 타임라인의 `candidate_identity_group` 은 **비링크 유지**를 제안한다(Slice 4 Deferred
  *"LINKABLE 확장은 Slice 6 UI 때 본다"* 에 대한 답). Slice 6 은 그룹 전용 URL 을 만들지
  않고 검토함 목록 안에서 접었다 편다 — 사유 문자열 *"검토함 목록 안에만 있다"* 가 그대로
  참이다. 오너가 반대하면 이 줄이 D3 가 된다.
- 그룹 승인은 **유료 경로**다(8.0 B4/B6). 버튼에 402/429 처리와 확인 헤더 축이 개별
  후보 승인과 다르다 — UI 문구를 기존 유료 화면(`WritingPanel` 의 quota 표시)과 맞춘다.

## Deferred / out of scope

- `uncertain` 수동 합치기/분리 **액션**(페이즈 Deferred 그대로 — D2 가 B 면 표시도 여기 합류).
- shortlist 상한·페이징(트리거: 검토함 그룹 수가 세 자리).
- 그룹 상세 화면(멤버별 source/job 대조 전용 페이지) — Slice 6 은 목록 안 확장으로 푼다.
- `contradicted` 그룹의 사람 해소 경로.
