# 착수 결정 브리프 — event/open_question 정본 중복 누적을 어디서 막는가

상태: `Proposed — 오너 결정 대기`
작성: 2026-09-09
선행: [`02b-6-semantic-identity-resolution-decisions.md`](02b-6-semantic-identity-resolution-decisions.md)(D4=A, off 기본) · [`pending-candidate-identity-grouping-decisions.md`](pending-candidate-identity-grouping-decisions.md)(C 채택, Slice 0~6 구현 완료) · [`final-save-analysis-decisions.md`](final-save-analysis-decisions.md)(D4=A, 최종 저장이 분석을 동기 실행)

## 결정 필요

**event·open_question 후보의 중복 제거 장치가 canonical 축·candidate 축 양쪽 다 꺼져 있다. 어느 축에서 막을 것인가.**

같은 사건이 재분석마다 새 canonical memory가 된다. 세 축(2B.6 semantic matcher · C 노선 후보 그룹 · always-create 유지)이 이미 내려진 서로 다른 결정과 얽혀 있어, 구현자가 하나를 골라 진행하면 **오너가 고르지 않은 방향으로 정본 정책을 커밋하게 된다.**

## 현재 확정된 경계 (결정이 아니라 사실)

1. **canonical 축 semantic matcher는 꺼져 있다.** 2B.6 D4=A가 *"추측 threshold로 canon 병합 금지, 기본 off"* 로 확정했다. `ANALYSIS_SEMANTIC_MATCH_THRESHOLD` 가 없으면 `_build_semantic_matcher` 가 `None` 을 반환하고([`main.py:1093-1101`](../../services/application/app/main.py#L1093-L1101)), `_find_matches` 는 scope 없는 후보에 `()` 를 반환한다([`compare.py:288-296`](../../services/application/app/analysis/compare.py#L288-L296)) → **항상 `create`**.
   - **실측(2026-09-09, 알파)**: application 컨테이너 env에 이 값이 **없다**. `CHROMA_HOST`·`EMBEDDING_SERVICE_URL`·`ELASTICSEARCH_URL` 은 셋 다 있다 — 즉 인프라가 없어서가 아니라 **결정에 따라 꺼져 있다**.
2. **candidate 축 shortlist도 event/open_question에는 없다.** Slice 1이 *"event/open-question은 주입된 retriever가 고르고, retriever가 없으면 shortlist가 비는 no-op"* 로 계약했는데([`identity_judging.py:16-19`](../../services/application/app/analysis/identity_judging.py#L16-L19), [`:251-275`](../../services/application/app/analysis/identity_judging.py#L251-L275)), 조립부 [`main.py:896-918`](../../services/application/app/main.py#L896-L918)이 `shortlist_retriever` 를 **넘기지 않는다**. character는 정규화 이름으로 shortlist되지만 event/open_question은 no-op다.
   - 즉 **C 노선(미승인 후보 정체성 그룹, 2026-09-02 확정, Slice 0~6 구현·검증 완료)이 event/open_question에 대해서는 빈 채로 서 있다.**
3. **중복을 만드는 것은 재분석이고, 재분석은 의도된 동작이다.** 최종 저장이 분석을 동기 실행하고(final-save D4=A), 그 뒤 본문을 고치면 `최종 저장 후 수정됨 · 수동 분석 필요` 가 되어 **같은 Scene을 다시 분석**한다(D3=B). snapshot은 저장마다 새로 생기므로 job idempotency 키 `(project_id, snapshot_id, idempotency_key)`([`analysis/service.py:281-306`](../../services/application/app/analysis/service.py#L281-L306))는 이 반복을 막지 않는다 — 막아서도 안 된다.
4. **character는 이 문제에서 안전하다.** 정규화 이름이 결정적 scope key라 재분석해도 같은 정본에 걸리고, 중복 정본이 생기면 `>1` → 결정적 `conflict` 로 review에 올라간다. **문제는 결정적 키가 없는 두 타입에만 있다.**
5. **정본 payload는 누적되지 않는다.** `update` 는 payload 교체, `add_evidence` 는 이전 payload 보존이고([`memory/service.py:363-372`](../../services/application/app/memory/service.py#L363-L372)) 판정 프롬프트는 후보 1 + 정본 1 쌍이다([`compare_judge.py:139-152`](../../services/application/app/analysis/compare_judge.py#L139-L152)). **따라서 이 결정은 "프롬프트가 커진다" 문제가 아니다** — 정본 *개수* 가 늘어 검색 상한(8) 안에 최근 사실이 못 들어오는 **검색 품질** 문제다.
6. **아직 관측된 피해는 0이다.** 실측(2026-09-09): `ai_writing_system.memories` **0건**, analysis 후보/job 컬렉션도 생성 전. `source_blocks` 640 · `drafts` 12 는 있으나 **분석 파이프라인이 실데이터로 한 번도 안 돌았다.** 이 브리프는 관측이 아니라 **구조 예측**이며, 그 점이 ⓐ를 정당한 선택지로 남긴다.
7. **판정 예산은 공유 자원이다.** run당 새 판정 20쌍 상한(S-1 D3, [`identity_judging.py:41-47`](../../services/application/app/analysis/identity_judging.py#L41-L47))은 **run 단위**다. event/open_question을 shortlist에 넣으면 character와 같은 20을 나눠 쓴다.

## 선택지

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **ⓐ 그대로 · 트리거만 정한다** | always-create를 유지하고 *"무엇을 보면 여는가"* 만 지금 적는다 | 데이터 0건에서 threshold를 추측하지 않는다(2B.6 D4=A · auto-promotion D2=B와 정합) · 구현 0 | 도그푸드가 시작되면 **가장 먼저 아픈 자리**가 된다 · 이미 canonical이 된 중복은 사후 정리가 비싸다(승인·파기 감사 경로를 지나야 한다) |
| **ⓑ canonical 축을 켠다** (2B.6 D4=B) | `ANALYSIS_SEMANTIC_MATCH_THRESHOLD` 에 초기값을 박아 semantic 매칭을 켠다 | 배선이 이미 있다 — env 하나로 즉시 효력 | **추측 threshold가 canon을 자동 병합한다.** 낮으면 서로 다른 사건이 하나로 뭉개지고(정본 손상, 되돌리기 어렵다) 높으면 아무것도 안 막는다. **2B.6이 명시적으로 거부한 방향이다** |
| **ⓒ candidate 축을 배선한다** | `CandidateShortlistRetriever` 구현체를 만들어 `main.py` 조립에 주입한다. event/open_question 후보가 그룹 리뷰에 묶여 **사람이 한 번에 본다** | **이미 채택된 C 노선의 빈 칸을 채우는 것**이지 새 노선이 아니다 · threshold가 틀려도 대가가 **리뷰 노이즈**지 정본 손상이 아니다(자동 병합이 없다) · 정본은 승인을 지나야 생기므로 중복이 **사람 앞에서** 걸린다 | 구현이 ⓑ보다 크다(retriever + 배선 + 회귀) · threshold/top-K는 여전히 골라야 한다(다만 되돌릴 수 있는 값이다) · run당 20 예산을 character와 나눠 쓴다 |
| **ⓓ 결정적 키를 부여한다** | event에 `(snapshot_id, 정규화 텍스트 해시)` 류의 결정적 scope key를 준다 | LLM도 threshold도 전혀 필요 없다 | **동작하지 않는다.** 재분석은 같은 문장을 다시 뽑지 않는다 — LLM이 매번 다르게 요약한다. 바이트 동일 재추출만 잡는데 그건 거의 안 일어난다. 정직하게 적으면 이 행은 탈락이다 |
| **ⓔ ⓒ 먼저 · ⓑ 후속** | candidate 축을 먼저 배선하고, 리뷰에서 사람이 승인/거절한 그룹을 **threshold 캘리브레이션 fixture**로 삼아 나중에 canonical 축을 켠다 | 2B.6 D7이 유예한 *"실 embedding + 실 데이터 fixture"* 를 **공짜로 만든다** — 승인/거절된 그룹이 곧 정답 라벨이다 · 각 단계가 되돌릴 수 있다 | 가장 길다(두 슬라이스) · ⓒ의 비용을 그대로 진다 |

## 추천 — ⓔ (ⓒ부터, ⓑ는 데이터가 생긴 뒤)

이유 셋:

1. **이미 고른 노선의 빈 칸이다.** 2026-09-02에 오너가 C(미승인 후보 정체성 그룹)를 골랐고 Slice 0~6이 구현·검증까지 끝났다. 그 노선이 event/open_question에 대해 no-op라는 것은 **새 결정이 아니라 미완**이다. 새 메커니즘을 더하기 전에 있는 것을 마저 잇는 편이 싸다.
2. **틀렸을 때의 대가가 다르다.** ⓑ의 threshold 오류는 **정본을 조용히 병합한다** — 2B.6이 거부한 바로 그것이다. ⓒ의 threshold 오류는 리뷰 화면에 엉뚱한 그룹이 뜨는 것이고 사람이 거절하면 끝난다. 데이터 0건에서 값을 골라야 한다면 **되돌릴 수 있는 쪽**에서 고른다.
3. **ⓒ가 ⓑ의 전제를 만들어준다.** 2B.6 D7이 실 fixture를 sandbox 밖 후속으로 미뤘는데, 승인·거절된 그룹이 바로 그 라벨 데이터다. ⓑ를 켤 시점의 threshold를 **추측이 아니라 측정**으로 정할 수 있다.

**ⓐ도 정당하다.** 실데이터가 0건이고 도그푸드가 아직 시작 전이라면 *"지금은 안 만든다"* 가 값싼 답이다. **다만 그 경우 트리거를 반드시 함께 적는다** — 트리거 없는 유예는 망각이고, K-3 ⓐ도 트리거 문장이 있어서 살아남았다. 제안 트리거: **한 프로젝트의 canonical event가 50건을 넘는 순간, 또는 리뷰에서 같은 사건의 중복을 사람이 처음 알아본 순간.**

## 후속 고려 (어느 쪽을 고르든 열어 둘 것)

- **threshold 정본은 하나여야 한다.** ⓒ의 shortlist 임계값과 2B.6의 `ANALYSIS_SEMANTIC_MATCH_THRESHOLD` 가 별개 env로 갈라지면 값이 둘이 되고 어느 쪽이 진짜인지 아무도 모른다. 같은 축인지 다른 축인지를 **배선 전에** 정한다.
- **run당 20 판정 상한**(S-1 D3)을 event가 나눠 쓴다. character 판정이 밀리지 않는지 확인하거나 타입별로 예산을 나눌지 결정한다.
- 어느 선택지도 **이미 canonical이 된 중복은 지우지 못한다.**

## 유예 · 범위 밖

- **character 별칭/동명이인**(2B.7) — 다른 축이고 이 브리프가 건드리지 않는다.
- **이미 생긴 중복 정본의 사후 병합** — merge/split review 경로이며 지금 결정 대상이 아니다.
- **K-3 창 가드** — 2026-09-08에 ⓐ로 확정됐다([`k3-context-window-guard-decisions.md`](k3-context-window-guard-decisions.md)). 축이 다르고 이 브리프와 무관하다.
- **무순위 폴백 절단 신호**(`MongoDirectCanonicalMemoryRetriever` 가 관련도 없이 앞 8개를 자르는 것) — 결정이 필요 없는 별건으로 분리해 진행한다.
