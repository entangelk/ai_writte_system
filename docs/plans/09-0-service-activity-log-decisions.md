# Phase 9 Slice 9.0 — 서비스 활동 로그 착수 결정 브리프 (A1~A8)

상태: `Awaiting owner decision`
작성: 2026-08-05
측정 기준: 베타 머신, HEAD `bc0d42a`, SoT v1.7.89, 회귀 기준선 backend 2173/4/1931 · frontend 265/18
부모 계획: [`09-service-activity-log.md`](09-service-activity-log.md)
발원: [`08-2c-project-name-history-decisions.md`](08-2c-project-name-history-decisions.md) §N2-a
착수 조건: **8.2c 구현 완료 뒤.** 같은 삭제 계약(D8-6)을 건드리므로 동시에 열지 않는다.

> **결정 전에는 아무것도 구현하지 않는다.** 이 브리프는 선택지와 대가만 늘어놓는다.
> 부모 계획 §4의 **불변식 5종(I1~I5)은 결정 대상이 아니다** — 그것을 뒤집으면 D8-6이 무너진다.

---

## Decision needed

오너 문언은 *"일반 서비스 로그에는 당연히 수정, 저장 뭐 이런 항목들이 저장되어야 할 테니까"*
하나다. 방향은 분명한데 **코드로는 여덟 갈래**이고, 그중 셋(A2·A4·A7)은 **나중에 되돌리기가
비싸다** — 기록 범위는 한 번 넓히면 쌓인 데이터가 남고, 실패 방향과 쓰기 지점은 40개
endpoint에 퍼진 뒤에는 일괄 변경이 곧 전면 수정이다.

**유도되지 않는 이유가 셋이다.**

1. **이미 기록하는 것과 겹친다.** `llm_call_audits`(관측)·`request_usage_ledger`(과금)·
   `admin_audit_events`(관리자)·`draft_versions`(본문 버전)가 각자 일부를 담고 있다.
   활동 로그가 그 위에 무엇을 더 담아야 하는지는 **제품 판단**이지 코드가 정해 주지 않는다.
2. **"저장"의 주체를 아는 자리와 "무엇을 저장했는지" 아는 자리가 다르다**(§0.3~0.4).
   endpoint는 둘 다 알지만 40곳이고, dependency는 주체만 알며, 서비스 계층은 주체를 모른다.
3. **실패 방향에 정반대 선례가 둘 있다**(§0.5). 어느 쪽을 따르는지가 "로그 저장소가 죽으면
   사용자가 원고를 저장할 수 있는가"를 결정한다.

---

## 0. 실측 (2026-08-05, HEAD `bc0d42a`)

### 0.1 지금 남는 것과 안 남는 것

| 사용자 행위 | 지금 남는가 | 어디에 |
|---|---|---|
| 원고 본문 저장 | **부분** — 버전은 남지만 **시각·주체가 없다** | `draft_versions`(`version_number` 순번만, [`models.py:78`](../../services/application/app/core_sot/models.py#L78)) |
| 프로젝트·원고 개명 | **아니오** | 덮어쓰기([`service.py:450`](../../services/application/app/core_sot/service.py#L450)·[`:458`](../../services/application/app/core_sot/service.py#L458)) |
| 프로젝트·원고 archive | **아니오** | `archived` 플래그만 |
| 후보 승격·거절·편집 | **아니오** | 결과 상태만 남는다 |
| AI 생성·분석 요청 | **예** | `llm_call_audits`(호출 단위) · `request_usage_ledger`(과금 단위, 회원 축) |
| 관리자 행위(파기·승격 발급) | **예** | `admin_audit_events` · `access_grant_uses` |
| 로그인·로그아웃 | **아니오** | 세션 문서만(만료로 사라진다) |

### 0.2 mutating operation 40개의 성격별 분포 — A2의 실질

`@app.{post,patch,put,delete}` **40개**(GET 36 별도). A2 선택지가 이 표의 어디에 선을 긋느냐다.

| 묶음 | 수 | 예 |
|---|---|---|
| **정본 변경**(project·draft·version·brief·source-ref) | **10** | `POST /projects` · `PATCH /projects/{id}` · `POST …/drafts/{id}/versions` · `PUT …/brief` · `PUT …/draft-order` |
| **검토 결정**(기억을 바꾸는 사용자 판단) | **9** | `…/candidates/{id}/promote`·`/reject`·`/edit`·`/confirm` · `…/jobs/{id}/apply`·`/auto-promote` · `…/review-queue/{id}/reconcile` · `…/gate-findings/{id}/resolve`·`/dismiss` |
| **AI·작업 요청**(유료 9 포함) | **14** | `…/writing/generate`·`gate`·`revise`·`accept` · `…/analysis/jobs/{id}/run`·`compare` · `…/context-search` · `…/writing/scratch` |
| 파생 색인 재구축 | 1 | `…/index/source-blocks/rebuild` |
| 인증 | 2 | `/auth/login` · `/auth/logout` |
| 관리자 | 4 | `/admin/users`·`…/deactivate` · `…/purge` · `…/access-grants` |

### 0.3 쓰기 지점 후보 세 자리는 이미 코드에 있다 (그리고 넷째는 이미 기각된 적이 있다)

| 자리 | 무엇을 아는가 | 실재 |
|---|---|---|
| **endpoint 본문** | 주체·대상·**결과**·의미(무엇으로 개명했는지) 전부 | 40곳 |
| **dependency**(`require_project_owner`) | 주체·project·method·path. **결과는 모른다**(route 실행 *전*에 돈다) | 이미 이 자리에서 `access_grant_uses`를 쓴다([`main.py:1633`](../../services/application/app/main.py#L1633) — *"this dependency is the single choke point … cannot be bypassed by adding an endpoint"*) |
| **서비스 계층**(`core_sot` 등) | 대상·의미. **주체를 모른다** — `rename_project(project_id, name)`에 user가 없다 | 서명 변경 필요 |
| ~~미들웨어~~ | HTTP 표면만 | **D7=A가 이미 기각**했다([`main.py:1544-1546`](../../services/application/app/main.py#L1544)): *"path patterns become the policy and new routes open silently"*. 8.3 Q7=A가 같은 근거를 재확인했다 |

### 0.4 주체(`user_id`)가 endpoint 본문까지 오는 곳은 지금 9곳뿐이다

대부분의 project 경로는 `dependencies=_REQUIRE_PROJECT_OWNER`(리스트 형태)로 선언돼 **인증은
지나지만 user 객체를 바인딩하지 않는다**. `current=Depends(...)`로 실제 사용자를 받는 자리는
**9곳**(관리자·인증 경로 위주)이다. 즉 **A7=A(endpoint)를 고르면 34개 project 경로에
`current=Depends(require_authenticated_user)` 인자가 추가**된다 — 논리 변경은 아니지만 diff는 넓다.

### 0.5 실패 방향의 정반대 선례 둘 — A4가 고르는 것

| 선례 | 방향 | 코드가 말하는 이유 |
|---|---|---|
| `llm_call_audits` | **격리(fail-open)** | [`llm_call_scope.py:247`](../../services/application/app/observability/llm_call_scope.py#L247) `# deliberate isolation boundary` — 감사 저장소 예외가 정상 200을 503으로 뒤집는 것을 막는다 |
| `access_grant_uses` | **fail-closed** | [`access_grants.py:136`](../../services/application/app/auth/access_grants.py#L136) — *"the opposite of the LLM-call audit, which is isolated precisely because it is not load-bearing for a security boundary"* |

### 0.6 저장소·파기 배선 템플릿은 이미 있다

- 저장소 한 쌍의 표준형: [`auth/admin_audit.py`](../../services/application/app/auth/admin_audit.py)
  (frozen dataclass + Protocol + in-memory + `*_mongo.py`, `clock`/`id_factory` 주입).
- 파기 배선: purge endpoint가 도메인마다 `X.purge_project(project_id=…)`를 **10줄**로 부른다
  ([`main.py:3561-3573`](../../services/application/app/main.py#L3561)). 새 컬렉션은 **한 줄 추가**이고,
  빠뜨려도 reconciler가 `project_id` 보유 컬렉션을 발견해 수습한다(= I1의 안전망).
- **fake-collection 왕복 테스트가 신규 `*_mongo.py`의 표준 요구**다(선례: `gate_findings`·`loop_audit`).

---

## A1 — 어디에 저장하는가

### Decision needed

`mongo_collections.md` **§43 `system_events`**가 이 용도를 위해 **자리만 잡아 두고 코드는 0줄**이다
(`draft_saved` 예시까지 적혀 있다). 그 자리를 되살릴지, 이름을 새로 지을지.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 새 컬렉션 `activity_events`**(추천) | 사용자 행위 전용. §43은 "이 절로 대체됨" 포인터를 달고 폐기 | **이름이 내용을 말한다** — 이 저장소가 `target_project_id`로 값을 치르고 배운 것 · 훗날 진짜 시스템 이벤트(배포·워커 장애)가 생겨도 섞이지 않는다 | 문서 한 절을 개정해야 한다(§43 → 폐기 포인터 + 새 절) |
| B. §43 `system_events` 이름 그대로 | 문서에 이미 있는 이름·인덱스를 쓴다 | 새 절이 필요 없다 · "미구현 스펙"이 하나 줄어든다 | **이름이 거짓말을 한다** — 담기는 것은 사용자 행위인데 "system"이다 · §43의 필드 스펙(`payload` 자유형)은 어차피 A3에서 다시 정한다 |
| C. 도메인별 분리(`draft_activity`·`project_activity`…) | 축마다 컬렉션 | 각 축의 쿼리가 단순 | **타임라인을 만들려면 N개를 합쳐야 한다** — 이 페이즈의 목적이 정확히 그 타임라인이다 · purge 배선도 N줄 |
| D. 기존 감사 컬렉션 확장 | `admin_audit_events`에 사용자 행위를 더한다 | 컬렉션 0개 추가 | **SoT v1.7.78이 명시적으로 금지**한 오염이다(관리자 감사 ≠ 소유자 활동) · purge 생존 여부가 정반대라 한 컬렉션에 둘 수 없다 |

**Recommendation + reason: A.** D는 계약 위반이고 C는 목적과 반대다. A와 B의 차이는 이름 하나인데,
이 저장소는 **이름이 뜻과 어긋나면 사고가 난다**는 것을 8.2에서 이미 겪었다(`project_id` vs
`target_project_id` — 이름 하나가 과금 기록을 지울 뻔했다). §43은 걷어내는 편이 스펙 유령을 줄인다.

---

## A2 — 무엇을 기록하는가 (범위)

### Decision needed

§0.2의 40개 중 어디까지인가. **이 결정이 이 페이즈의 크기를 정한다** — 쓰기 지점 수, 부피,
그리고 "이미 다른 데 있는 것을 또 쓰는가"가 전부 여기서 갈린다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 정본 변경만 (**10**) | 생성·개명·저장·archive·brief·순서 | 가장 작다 · 오너 문언("수정, 저장")에 정확히 대응 | 후보 승격처럼 **기억을 바꾼 사용자 결정**이 안 남는다 — "어제 뭘 했더라"의 절반이 빈다 |
| **B. 정본 + 검토 결정 (**19**)**(추천) | 위 + 승격·거절·편집·확정·apply·reconcile·finding 처리 | **"상태를 바꾼 사용자 행위" 전부**가 한 타임라인에 모인다 · AI 호출은 이미 두 축이 기록하므로 중복이 없다 | 쓰기 지점 19곳 |
| C. 전 mutating (**34**, AI 요청 포함) | 위 + 생성·분석·검색 요청 | 프로젝트에서 일어난 일이 빠짐없이 한 곳에 | **원장·관측과 정면 중복**(A8) · 유료 경로는 이미 두 곳에 남고 세 번째 정본이 생긴다 |
| D. C + 조회(GET 36) | 열람까지 | 접근 추적까지 된다 | 부피가 한 자릿수 배로 뛰고, **접근 이력은 승격 감사(`access_grant_uses`)의 축**이라 성격이 섞인다 |

**Recommendation + reason: B.** 기준은 **"사용자가 무엇을 바꿨는가"**다. 승격·거절은 원고를 바꾸지
않지만 **기억을 바꾸고**, 그것이 이 제품에서 되돌리기 가장 어려운 종류다(memory는 append-only라
잘못 승격해도 과거가 남는다). 반대로 AI 요청은 **바꾼 것이 아니라 요청한 것**이고 이미
`llm_call_audits`·`request_usage_ledger` 둘이 담는다 — 세 번째 사본은 A8이 말하는 두 정본 문제다.

---

## A3 — 문서 형태 (무엇을 담는가)

### Decision needed

행 하나의 모양. **변경 전후 값을 담을지**가 실질이며, 그것이 "삭제 전까지 사용자 텍스트가
어디까지 복제되는가"를 정한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 고정 코어만 | `_id`·`project_id`·`actor_user_id`·`action`·`target_type`·`target_id`·`at` | 부피 최소 · 키 집합을 회귀가 고정하기 쉽다(8.2 선례) | *"이름을 바꿨다"*만 알고 **무엇으로 바꿨는지 모른다** — 개명 이력이 여전히 없다 |
| **B. 고정 코어 + 짧은 값 변화**(추천) | 위 + `before`/`after`(**짧은 식별 문자열만** — 이름·제목·상태) | 개명·상태 변화를 사람이 읽을 수 있다 · 담기는 것이 **본문이 아니라 라벨**이라 부피가 예측 가능 | "짧은 값"의 경계를 계약으로 못박아야 한다(안 그러면 다음 사람이 본문을 넣는다) |
| C. `event_type` + 자유 `payload` dict | §43 스펙의 형태 | 지금 가장 유연 | **키 집합 고정 가드를 못 쓴다**(8.2가 파기 reconciler 때문에 도입한 그 가드) · 소비 시점에 비용을 낸다 |
| D. B + 본문 diff | 원고 변경분까지 | 완전한 이력 | **본문은 이미 `draft_versions`+`source_snapshots`에 있다** — 두 정본 · 부피 폭증 |

**Recommendation + reason: B, 그리고 "짧은 값"을 계약으로 못박는다.** D가 없어도 되는 이유는
본문 이력이 이미 정본에 있기 때문이고, A로는 개명이 안 남아 이 페이즈의 목적 절반이 빈다.
C를 피하는 이유는 실측에 있다 — 8.2가 **문서 키 집합 자체를 고정하는 셀**을 넣은 것은 파기
reconciler가 `find_one` **표본 한 건**으로 컬렉션을 판정하기 때문이고, 자유형 payload는 그 가드를
무력화한다.

---

## A4 — 기록 실패는 요청을 실패시키는가

### Decision needed

§0.5의 정반대 선례 둘 중 어느 쪽인가. **"로그 저장소가 죽으면 사용자가 원고를 저장할 수 있는가"**
한 문장으로 요약된다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 격리(fail-open)**(추천) | 기록 실패를 삼키고 요청은 성공. `llm_call_audits` 선례 | **사용자의 저장이 로그 때문에 실패하지 않는다** · 이 저장소의 규칙("하중을 받는 것만 fail-closed")과 일치 | **구멍이 조용히 생긴다** — 로그가 비어도 아무도 모른다 |
| B. fail-closed | 기록 실패 = 요청 실패(503). `access_grant_uses` 선례 | 로그에 구멍이 없다 | **원고 저장이 감사 저장소 가용성에 묶인다.** 활동 로그는 보안 경계를 지지 않으므로 이 대가를 정당화할 하중이 없다 |
| C. 혼합 | 정본 변경은 fail-closed, 나머지는 격리 | 중요한 것만 보장 | **두 규칙이 한 컬렉션에** — 다음 사람이 어느 쪽인지 매번 판단해야 하고, 그 판단이 갈리는 것이 사고의 형태다 |

**Recommendation + reason: A.** 판정 기준은 코드가 이미 문장으로 갖고 있다 — *"not load-bearing for
a security boundary"*. 승격 접근 이력은 **그 기록이 없으면 관리자 열람을 아무도 설명할 수 없어서**
fail-closed였다. 활동 로그가 없다고 잘못 열리는 문은 없다. **다만 A를 고르면 "구멍을 어떻게 아는가"가
남는다** — 진단 카운터는 이번 범위 밖으로 두고 후속 고려에 적었다.

---

## A5 — 이번 슬라이스가 조회 통로를 여는가

### Decision needed

8.1·8.2·8.2b·8.2c는 전부 "저장만 하고 소비는 다음 슬라이스"였다. 여기서도 그럴지.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 저장 + 계약만 | 조회는 다음 슬라이스 | 검증 표면이 좁다 · 저장소 관례 그대로 | **부모 계획 §2의 목표 상태에 도달하지 못한다** — 그 목표는 전부 "제품이 답할 수 있는가"다 |
| **B. 소유자 조회 하나**(추천) | `GET /projects/{id}/activity`(project tier, 최신순, operation **77**) | 목표 상태에 이번 슬라이스에서 닿는다 · 응답 형태가 **다른 슬라이스에 종속되지 않는다**(8.2c와 다른 점 — 그쪽은 원장 조인 형태를 8.5가 정해야 했다) · 선례가 있다(`GET …/access-log`, D8-5f) | operation +1 → 인증 tier 전수 가드·에러 선언 등재 |
| C. 관리자 전역 조회까지 | + `/admin/activity` | 운영 관점이 함께 열린다 | 전역 조회는 **승격 계약 우회 위험**을 다시 연다(관리자가 내용을 보는 경로) — D8-5b가 메타데이터만 준 이유 |

**Recommendation + reason: B.** A가 관례이긴 하나 그 관례의 근거는 *"소비자가 정해지기 전에 응답
형태를 못박지 말라"*였다(8.2c N4). 여기서는 **소비자가 이미 정해져 있다** — 프로젝트 소유자다.
C는 관리자에게 프로젝트 내용을 여는 문이라 별도 결정(승격 계약)이 선행해야 한다.

---

## A6 — 보존 기간

### Decision needed

TTL을 두는가. 이 컬렉션은 프로젝트와 함께 사라지므로(I1) **프로젝트 수명 안에서만** 문제다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. TTL 없음**(추천) | 프로젝트 파기까지 산다 | 이 저장소의 **모든** 감사 컬렉션이 그렇다(`admin_audit_events`·`access_grant_uses`·`request_usage_ledger`) · 스케줄러 없는 스택에 새 인프라를 안 들인다 | 장수 프로젝트에서 무한히 는다 |
| B. TTL N일 | Mongo TTL 인덱스 | 부피 상한 | **"어제 뭘 했더라"는 짧게 필요하지만 "이 설정 언제 바꿨더라"는 길게 필요하다** — N을 지금 고를 근거가 없다 |
| C. project당 최근 N건 상한 | 밀어내기(scratch per-draft 20 선례) | 부피가 프로젝트 수에 선형 · 인프라 0 | 밀어낸 것은 복구 불가 · 상한값이 또 하나의 잠정 상수 |

**Recommendation + reason: A.** 부피가 실제로 문제가 되면 **그때 C**가 다음 수단이다(선례가 있다).
지금 B·C를 고르는 것은 측정 없이 상수를 하나 더 만드는 일이고, 8.1 P7의 "잠정 기본값"이 이미
재평가 트리거를 달고 있다.

---

## A7 — 어디서 쓰는가, 그리고 누락을 무엇이 막는가

### Decision needed

§0.3의 네 자리 중 어디서 기록하는가. **가드가 함께 결정된다** — 이 저장소의 표준은 "규칙이
아니라 강제"다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. endpoint 본문 + 전수 가드**(추천) | 대상 endpoint마다 한 줄. `ACTIVITY_LOGGED_ACTIONS` 표를 정본으로 두고 `main.py`를 파싱해 **미등재 mutating route를 실패**시킨다(`billable_actions` 선례) | **결과를 안 뒤에 쓴다** — 실패한 요청이 "했다"로 남지 않는다 · 의미를 안다(무엇으로 개명했는지 = A3=B의 재료) · 새 route가 조용히 빠지지 않는다 | 19곳(A2=B 기준)에 한 줄씩 · project 경로 34곳에 `current=Depends(...)` 인자 추가(§0.4) |
| B. dependency 한 곳(choke point) | `require_project_owner` 안에서 기록. `access_grant_uses`와 같은 자리 | **쓰기 지점 하나**, 우회 불가 | **결과를 모른다**(route 실행 전에 돈다) — 404·409·502로 끝난 요청도 "저장함"으로 남는다 · 의미를 모른다(`PATCH /projects/{id}`까지만 안다) · A4=A(격리)와 상성이 나쁘다(이 자리는 fail-closed 구역이다) |
| C. 미들웨어 | 응답 뒤에 method·path·status·user 기록 | endpoint 0줄 수정 · 상태코드를 안다 | **D7=A가 기각한 형태**(경로 패턴이 정책이 되고 새 route가 조용히 열린다) · HTTP 표면만 알아 A3=B의 before/after를 못 만든다 |
| D. 서비스 계층 | `core_sot.rename_project(...)` 안에서 | 도메인 의미를 가장 정확히 안다 | **주체를 모른다** — 서명 전부에 `actor` 추가(D7=A가 "every signature changes"로 기각한 그 형태) · HTTP 밖 호출(워커·스크립트)까지 기록돼 성격이 흐려진다 |

**Recommendation + reason: A.** B·C는 **"요청이 왔다"는 기록이지 "무엇이 바뀌었다"는 기록이 아니다.**
이 페이즈의 목적은 후자다. 비용(한 줄 × 19 + 인자 추가)은 크지 않고, 이 저장소는 같은 값을 이미
두 번 치렀다(인증 D7=A, quota 8.3 Q7=A) — 그 대가로 얻은 것이 **전수 가드가 성립하는 구조**다.

> **★ 라우터 정리와의 순서**: 가드가 `main.py`를 파일로 읽는 형태라면, [`main.py` 라우터 정리](../../HANDOFF.md)
> 뒤에는 그 가드도 함께 옮겨야 한다. 이미 같은 부채가 둘 있다(`test_billable_actions.py`·
> `test_auth_api.py`). **라우터 정리를 먼저 하면 이 세 번째를 안 만든다.**

---

## A8 — 원장·관측과 중복해서 기록하는가

### Decision needed

A2=B를 고르면 AI 요청은 활동 로그 밖이다. 그렇다면 **사용자 타임라인에 "생성했다"가 빠지는데**,
그것을 어떻게 볼 것인가.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 중복 기록하지 않는다 — 소비 시점에 합친다**(추천) | 활동 로그는 A2 범위만. 화면이 필요하면 `llm_call_audits`·원장과 `project_id`+`at`으로 조인 | **두 정본을 만들지 않는다** · 각 컬렉션의 뜻이 하나로 유지된다 | 타임라인 화면이 두세 소스를 합쳐야 한다(조인 규칙은 소비 슬라이스가 정한다) |
| B. 전부 활동 로그에도 남긴다 | AI 요청도 한 행 | 조회가 가장 단순(한 컬렉션) | **같은 사건이 세 곳에 산다** — 하나가 빠지거나 어긋나면 어느 것이 참인지 규칙이 필요해진다 |
| C. 요약만 남긴다 | action + 결과만, 상세는 원장·관측 | 타임라인이 자족적 | 여전히 부분 사본 — "요약이 원본과 어긋나면?"이 남는다 |

**Recommendation + reason: A.** 이 저장소가 반복해 피해 온 것이 정확히 **두 정본**이다(KPI `_fold`
공유 · quota `snapshot()` · 8.2c N3=A의 근거). 조인 축도 이미 있다 — `llm_call_audits`는
`project_id`, 원장은 `target_project_id`이고 둘 다 시각을 든다.

---

## 후속 고려 (이 결정이 열어 두어야 하는 문)

- **A4=A의 대가(조용한 구멍)를 나중에 어떻게 보는가.** 기록 실패 카운터를 진단 지표로 노출하는
  것이 자연스러운 다음 수단이다. 이번 범위 밖이며, 같은 형태의 잔존 한계가 관측 트랙에도 있다
  (HANDOFF 추적 부채 "scope-None 경로").
- **A3=B의 "짧은 값" 경계는 계약이다.** 다음 사람이 본문을 넣지 못하게 회귀가 상한을 잠근다
  (예: 문자열 길이 상한 + 어떤 필드가 허용되는지 화이트리스트).
- **A2를 나중에 C로 넓히는 것은 가능하다**(행 추가). 반대로 D(조회 기록)는 성격이 다른 축이라
  넓히기 전에 별도 결정이다.
- **8.5 관리자 CMS가 오면 A5=C(전역 조회)가 다시 올라온다** — 그때는 승격 계약과 함께 본다.
- **`draft_versions`에 시각·주체가 없는 문제는 이 페이즈가 우회한다.** 활동 로그가 "누가 언제
  저장했는가"를 담으므로 실용적으로는 닫히지만, **정본 자체는 여전히 시각을 모른다.** 정본에
  타임스탬프를 더하는 것은 core SOT 스키마 변경이라 별도 판단이다.

## 이번 슬라이스에서 결정하지 않는 것 (범위 밖)

- 되돌리기(undo)·시점 복원 — 로그는 사실 기록이지 복원 도구가 아니다
- `admin_audit_events`·`access_grant_uses`의 개정 — 별개 트랙(I3)
- 프론트 화면 — A5=B를 고르면 API까지이고 화면은 다음
- 워커·스크립트가 만든 변경의 기록 — 주체가 사람이 아니다(§0.3 D안의 부작용)

## 결정 뒤 구현 순서 (예정)

1. **회귀 먼저**(양방향): 기록 형태·키 집합 고정 · **실패한 요청은 기록하지 않는다**(A7=A의
   핵심, over-strict) · **기록 실패가 요청을 죽이지 않는다**(A4=A) · purge가 활동 로그를 지운다
   (실 Mongo) · **미등재 mutating route가 가드에서 실패한다**(A7 전수 가드)
2. **저장소** — `activity_events` in-memory + Mongo 한 쌍(`admin_audit` 형태), fake-collection 왕복
3. **HTTP** — 대상 endpoint에 한 줄 + `current` 인자 · purge 배선 한 줄
4. **조회**(A5=B면) — operation 77, tier 가드·에러 선언 등재
5. **정본** — `mongo_collections.md` 새 절(+§43 처리) · SoT 변경이력
6. **뮤테이션** — 기록 제거 · 실패 경로에도 기록(over-strict) · fail-closed로 바꾸기 · 가드 등재
   누락 · purge 배선 제거. **뮤테이션 전 `git status --short` 공백**([`verification.md`](../guides/verification.md) §Mutation testing)
7. **독립 검증** — 다른 작업자
