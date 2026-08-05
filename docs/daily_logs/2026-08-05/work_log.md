# 2026-08-05 작업 로그

## Task — Slice 8.2c 브리프 확정(N1~N6) + Phase 9(서비스 활동 로그) 신설

### Goals

- HANDOFF "Owner Decisions Needed" 첫 항목인 **8.2c 브리프 N1~N6을 오너 결정으로 닫는다**.
- 오너가 N2·N3에 붙여 온 조건부 질문("수정 기록 로그는 남기는가? 남긴다면 A가 아니라 B·C까지
  가야 하지 않나?")을 **실측으로 답하고**, 그 답이 결정을 바꾸는지 판정한다.
- 문서 작업만 한다. 구현은 다음 단계(오너 지시).

### User Decisions and Rationale

- **N1~N6 전부 A로 확정**(2026-08-05). 브리프
  [`08-2c-project-name-history-decisions.md`](../../plans/08-2c-project-name-history-decisions.md)
  §"오너 결정"에 표로 기록했고, 각 항목 제목에도 확정을 달았다.
- **N2·N3은 조건부 승인이었다.** 오너 문언: *"A이긴 한데, 수정 기록에 대한 로그는 남기는지
  확인해 달라. 로그를 남기면 A가 아니라 B 혹은 C까지 가야 하지 않나? 일반 서비스 로그에는 당연히
  수정·저장 같은 항목들이 저장되어야 할 테니까."* / N3에는 *"파기가 아니라 첫 생성·수정 시
  스냅샷이 찍힐 텐데… 다크데이터로 남게 되려나?"*
  → 실측·분석(아래 Issues found) 뒤 **A 유지로 확정**. 근거는 브리프 §N2-a에 남겼다.
- **활동 로그 자체는 만든다 — 단 별도 페이즈로.** 오너 지시로
  [`09-service-activity-log.md`](../../plans/09-service-activity-log.md)를 신설했다.
  8.2c는 그것을 기다리지 않는다(두 축이 직교하므로 — §N2-a).
- **N5는 A(남는 것을 명시)로 확정하되 오너 단서를 함께 기록했다**: *"일반화(B)를 해도 상관없다고
  보는 게, 이건 정책에 대한 부분이라 서비스 이용약관에 명시할 수 있으니까."* → 화면 문구는 A로
  가고, **약관 명시를 후속 고려에 등재**했다(약관 문서 자체가 아직 이 저장소에 없다).

### Issues found — "수정 기록 로그"는 이 저장소에 없다 (실측 2026-08-05, HEAD `1f8b99c`)

오너 질문을 코드로 확인한 결과, 사용자 활동 로그는 **한 줄도 없다**.

| 확인 대상 | 결과 | 근거 |
|---|---|---|
| 범용 이벤트 로그 `system_events`(§43이 `draft_saved` 예시까지 적어 둔 것) | **문서에만 있고 코드 0줄**. `services/`·`scripts/`·`tests/` 전수 grep 0건, §55에서 "Optional for MVP" | [`mongo_collections.md` §43](../../mongo_collections.md) |
| 프로젝트 개명 | 기록 없음 — `replace(project, name=…)` → `put_project` 덮어쓰기 | [`core_sot/service.py:450`](../../../services/application/app/core_sot/service.py#L450) · [`main.py:3419`](../../../services/application/app/main.py#L3419) |
| draft 제목 변경 | 동일 | [`core_sot/service.py:458`](../../../services/application/app/core_sot/service.py#L458) |
| 본문 저장 이력 | `draft_versions`+`source_snapshots`는 append-only인데 **`created_at`도 `user_id`도 없다**(`version_number` 순번뿐) | [`core_sot/models.py:78`](../../../services/application/app/core_sot/models.py#L78) |
| 기존 감사 3종 | `admin_audit_events`·`access_grant_uses`·`llm_call_audits`/`request_usage_ledger`. 어느 것도 소유자의 일상 편집을 안 담고, SoT v1.7.78이 그 분리를 명시적으로 못박았다 | SoT §D8-5f |

**즉 다중 사용자 서비스인데 "내가 어제 뭘 고쳤더라"에 답할 수단이 없다.** 본문은 버전으로
복원되지만 그 버전이 *언제* 생겼는지조차 저장돼 있지 않다. 이것이 Phase 9 신설의 근거다.

### Decisions — 로그가 생겨도 N2는 넓히지 않는다 (판정 근거)

가르는 축은 하나, **purge 생존 여부**다.

1. **축 1(활동 로그)** = 프로젝트 자식. `project_id`를 쓰므로 purge와 함께 지워지고, endpoint가
   빠뜨려도 reconciler가 `project_id` 보유 컬렉션을 DB에서 발견해 쓸어 간다
   ([`purge_reconciler.py:49`](../../../scripts/purge_reconciler.py#L49)). **삭제 계약 무변**.
2. **축 2(8.2c)** = purge를 살아남는 기록. 현재 생존자는 `admin_audit_events`·`request_usage_ledger`
   둘뿐이고 **둘 다 이름을 안 든다**. 여기 들어가는 것은 전부 D8-6의 예외라 최소면적이 원칙.
3. 따라서 **활동 로그는 이름 이력의 소스가 될 수 없다**(purge 때 같이 사라지므로). N3=A는 활동
   로그 유무와 **무관하게** 필요하다 — 오너 우려의 전제("생성·수정 때 이미 스냅샷이 찍힌다")가
   성립하지 않는 지점이 여기다.
4. 반대로 활동 로그를 purge 생존으로 만들면 개명 이력·draft 제목·저장 이벤트 전체가 삭제
   예외로 승격돼 **D8-6을 사실상 폐기한다.** 로그의 존재는 N2를 넓히는 근거가 아니라 **두 축을
   분리해야 하는 근거**다.
5. **다크데이터 우려는 방향이 반대다.** N3=A는 파기된 프로젝트만 행을 갖는다(소비자 = 8.5 원장
   조회·8.6 청구서). N3=B는 살아 있는 프로젝트 전부 + 개명 횟수만큼 쌓이는데 소비자는 똑같이
   8.5 하나뿐 — 그쪽이 다크데이터이고, 덤으로 `projects`와 이름 정본이 둘이 된다.

### Completed work — 문서만 (코드 0줄)

- [`plans/08-2c-project-name-history-decisions.md`](../../plans/08-2c-project-name-history-decisions.md)
  — 상태 `Awaiting owner decision` → **`Resolved`**. §"오너 결정(2026-08-05)" 표 + **§N2-a**(위
  실측·분석) 신설, N1~N6 제목에 확정 표기, 후속 고려에 **약관 명시**와 **Phase 9 분리** 2건 추가.
- [`plans/09-service-activity-log.md`](../../plans/09-service-activity-log.md) **신설** — Phase 9
  계획. 실측 공백 표 · 목표 상태 · 범위 · **불변식 5종**(I1 프로젝트 자식이다 · I2 삭제 계약의
  예외가 아니다 · I3 기존 감사에 얹지 않는다 · I4 `project_id` 격리 · I5 tier 전수 가드) ·
  착수 브리프에서 정할 **A1~A8** · 선행/순서 · 완료 기준.
  **A4(기록 실패 방향)에 이 저장소의 정반대 선례 둘을 명시**했다 — `llm_call_audits`는 격리,
  `access_grant_uses`는 fail-closed. 어느 쪽인지는 제품 정책이라 브리프 사안이다.
- [`plans/README.md`](../../plans/README.md) — **Phase 9 절 신설** · 8.2c 행 상태 갱신 ·
  Phase↔MVP 표에 Phase 9 행 · 문서 수 주장 98→99.
- [`README.md`](../../../README.md) — 같은 가드가 보는 계획 문서 수 98→99(브리프 수 81은 무변 —
  새 문서가 `*-decisions.md`가 아니다).

### Verification

- `python3 -m pytest tests/test_docs_indexes.py -q` → **12 passed / 10 subtests**. 새 문서 등재와
  링크, 그리고 두 문서의 계획 문서 수 주장이 디스크와 일치함을 확인했다.
- 코드 변경이 없으므로 backend/frontend 회귀는 돌리지 않았다(기준선 무변: backend 2173/4/1931 ·
  frontend 265/18).
- 뮤테이션 없음 — 이 작업은 문서 전용이다.

### 아직 안 한 것 (의도)

- **`mongo_collections.md` §43B 예외 포인터 · 새 절 · SoT v1.7.90**은 **구현과 함께** 간다.
  지금 쓰면 정본이 코드가 아직 하지 않는 동작을 서술하게 된다(브리프 §"결정 뒤 구현 순서" 5번).
- 같은 이유로 `08-2-usage-ledger-decisions.md`의 **L6 상태 갱신**과 `CHANGELOG.md`도 구현 시점.

### 독립 검증 반영 (같은 날, `c884151` 대상)

판정 **합격 — 구현 착수 가능**. Blocking 0. 검증자가 D8-6 계약·`service.py:450`/`:458`·
`models.py:78`·`system_events` 0건·reconciler 발견 메커니즘·A4의 정반대 선례 둘·operation 76·
문서 수 98→99·`test_docs_indexes` 12/10을 전부 재확인했고, **하중을 받는 주장은 코드 독스트링
자체가 이미 서술하고 있었다**(`ledger.py:9-12`가 "이름이 `project_id`가 아닌 것이 핵심",
`access_grants.py:136-143`이 "opposite of the LLM-call audit … not load-bearing for a security
boundary" — A4가 인용한 대비가 한 글자 일치).

비차단 지적 2건을 닫았고, **파고들어 보니 둘의 뿌리가 검증자 추정과 달랐다.**

| 지적 | 검증자 추정 | 실제 원인 | 조치 |
|---|---|---|---|
| `main.py` "6,074줄"이 71줄 낡음 | c956fa3 이후 `4cfd950`이 71줄을 더했다 | **맞다.** 다만 `4cfd950`은 `9911b3d`보다 **앞**이라 6,145는 어제(8.2c 브리프 작성) 시점에도 이미 참이었다 — HANDOFF의 2026-08-04 실측 자체가 그때 낡은 값을 적었고 내가 그것을 Phase 9로 복사했다 | Phase 9 §6 + **HANDOFF 추적 부채 두 곳**(6,074→**6,145**, 낡은 이유 명시). 데코레이터 77개는 재측정 결과 무변 |
| `main.py:3419` 인용이 라벨과 불일치 | 인용은 현행에 맞고 라벨(c956fa3)과 안 맞는다 | **라벨이 틀렸다.** 실측 시점 HEAD는 `c956fa3`가 아니라 **`1f8b99c`**였고(`c956fa3`는 13커밋 전), 인용은 처음부터 그 트리 기준으로 정확했다 | 세 문서의 실측 HEAD 라벨을 `1f8b99c`로 정정 |

**★ 라벨이 틀린 뿌리 — 세션 시작 시 주어진 git 스냅샷의 HEAD가 낡아 있었다.** 그것을 그대로
"측정 기준"으로 옮겨 적었고, 실제로 읽은 파일은 작업 트리(`1f8b99c`)였다. 검증자는 그 라벨을
참으로 놓고 드리프트를 계산했기 때문에 **없는 드리프트를 하나 찾아냈다**(3419가 옛 트리에서는
`issue_access_grant`였다는 지적 — 사실이지만 이 문서와 무관하다). **실측 라벨은 스냅샷이 아니라
`git log -1`로 직접 확인해 적는다** — 틀린 라벨은 검증자를 잘못된 기준선으로 보낸다.

### Next steps

1. **8.2c 구현** — 브리프 §"결정 뒤 구현 순서" 그대로: 회귀 먼저(6종) → 저장소(in-memory +
   Mongo, `_id`=project id) → purge endpoint 쓰기 한 줄 → 프론트 문구 → 정본 3곳 → 뮤테이션 5종
   → 독립 검증. **새 operation 없음(76 유지).**
2. 그 뒤 `main.py` 라우터 정리 + 관리자 주소 분리(오너 2026-08-04 후속 확정).
3. Phase 9는 8.2c 구현이 닫힌 뒤 착수 결정 브리프부터. 라우터 정리 뒤가 유리하다(쓰기 지점이
   mutating endpoint 전체에 퍼진다).

---

## Task 2 — 검증 기록 커밋 + Phase 9 착수 결정 브리프 작성 (A1~A8)

### User Decisions and Rationale

- **검증 기록을 남기라는 것이 오너 요청이었다**(내가 "검증자가 쓰는 기록"이라 판단해 보류한 것을
  정정). 검증자가 [`verifications/2026-08-05/slice_8_2c_brief_and_phase9.md`](../../verifications/2026-08-05/slice_8_2c_brief_and_phase9.md)와
  숫자 주장 4곳을 **작업 트리에 남기고 커밋하지 않아** 내가 커밋했다(`bc0d42a`).
  **기록 본문은 손대지 않았다** — hardening 2건의 폐쇄와 정정은 이 로그와 `cced53f`에 있고,
  검증 기록에 구현자가 끼어드는 절이 이 저장소에 없다(전례 0건, 확인함).
- **Phase 9 문서를 "결정할 수 있는 브리프"로 만들라**는 요청. 종전 `09-service-activity-log.md`는
  질문만 나열한 계획이라 오너가 고를 수 없었다 → **선택지 표 + 장단점 + 구현자 추천** 형식의
  착수 브리프를 별도 문서로 분리했다(이 저장소의 계획/브리프 분리 관례 그대로 —
  Phase 8도 `08-member-request-quota.md` + `08-0-…-decisions.md`였다).

### Completed work

- **`bc0d42a`** — 검증 기록 + `verifications/README.md`(42일치·218건, 판정 분포 08-05 기준)·
  최상위 `README.md`·`docs/README.md` 숫자 갱신. 실측 재확인: 파일 218개·날짜 42개.
- **[`plans/09-0-service-activity-log-decisions.md`](../../plans/09-0-service-activity-log-decisions.md) 신설**
  — A1~A8 각각이 `선택지 | 설명 | 장점 | 단점` 표 + 추천 + 근거를 갖는다. **§0 실측이 브리프의
  하중을 받는다**:

  | 실측 | 값 | 어느 결정을 움직이는가 |
  |---|---|---|
  | mutating operation 성격별 분포 | 정본 10 · 검토 결정 9 · AI 요청 14 · 색인 1 · 인증 2 · 관리자 4 = **40** | A2(범위)가 이 표의 어디에 선을 긋는지가 곧 페이즈 크기 |
  | 쓰기 지점 후보 | endpoint(결과·의미 다 안다) · dependency(결과 모름) · 서비스 계층(주체 모름) · 미들웨어(**D7=A가 이미 기각**, `main.py:1544`) | A7 |
  | `current=Depends(...)`로 user를 받는 endpoint | **9곳뿐** — A7=A면 project 경로 34곳에 인자 추가 | A7의 실제 비용 |
  | 실패 방향 선례 | `llm_call_scope.py:247` 격리 / `access_grants.py:136` fail-closed(*"not load-bearing for a security boundary"*) | A4 |
  | 배선 템플릿 | `auth/admin_audit.py` 한 쌍 · purge 도메인 호출 **10줄**(`main.py:3561-3573`) | 구현 순서 |

- [`plans/09-service-activity-log.md`](../../plans/09-service-activity-log.md) §5를 질문 나열에서
  **브리프 포인터 + 추천 요약표**로 교체(계획은 범위·불변식, 브리프는 선택지 — 역할 분리).
- 인덱스: `plans/README.md` Phase 9 행 추가 + 100개/82개, 최상위 `README.md` 같은 두 숫자.
- HANDOFF: "Owner Decisions Needed"에 **Phase 9 A1~A8** 항목 신설(추천 8건 요약 + "되돌리기 비싼
  것은 A2·A4·A7") · Phase 9 결정완료 항목과 Next Tasks 3번을 브리프 작성 완료 상태로 고쳐 씀.

### Decisions (구현자 판단, 오너 확정 전)

- **A2를 B(19개)로 추천한 기준은 "사용자가 무엇을 *바꿨는가*"다.** 승격·거절은 원고가 아니라
  **기억을 바꾸고**, memory가 append-only라 되돌리기가 가장 어렵다. 반대로 AI 요청은 바꾼 것이
  아니라 요청한 것이며 이미 `llm_call_audits`·`request_usage_ledger` 둘이 담는다.
- **A4를 격리로 추천한 근거는 코드가 이미 문장으로 갖고 있다** — `access_grant_uses`가
  fail-closed인 이유가 *"보안 경계에 하중을 받기 때문"*이고, 활동 로그가 없다고 잘못 열리는 문은
  없다. 대신 "구멍을 어떻게 아는가"를 후속 고려로 남겼다.
- **A7=A(endpoint)를 추천하면서 그 대가를 숨기지 않았다** — 34곳 인자 추가. B(dependency)가 한
  줄로 끝나지만 **route 실행 전에 돌아 결과를 모른다**(404·409로 끝난 요청이 "저장함"으로 남는다).

### Verification

- `python3 -m pytest tests/test_docs_indexes.py -q` → **12 passed / 10 subtests**(신규 브리프 등재·
  링크·계획 문서 수 100/82 실측 일치).
- 브리프의 코드 인용 5건은 작성 후 직접 재확인했고 두 건(`main.py` 미들웨어 기각 주석·purge 배선)은
  실측값으로 정정했다 — **어제 라벨 사고의 재발 방지 절차를 그대로 적용**했다.
