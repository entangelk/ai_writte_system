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

### Issues found — "수정 기록 로그"는 이 저장소에 없다 (실측 2026-08-05, HEAD `c956fa3`)

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

### Next steps

1. **8.2c 구현** — 브리프 §"결정 뒤 구현 순서" 그대로: 회귀 먼저(6종) → 저장소(in-memory +
   Mongo, `_id`=project id) → purge endpoint 쓰기 한 줄 → 프론트 문구 → 정본 3곳 → 뮤테이션 5종
   → 독립 검증. **새 operation 없음(76 유지).**
2. 그 뒤 `main.py` 라우터 정리 + 관리자 주소 분리(오너 2026-08-04 후속 확정).
3. Phase 9는 8.2c 구현이 닫힌 뒤 착수 결정 브리프부터. 라우터 정리 뒤가 유리하다(쓰기 지점이
   mutating endpoint 전체에 퍼진다).
