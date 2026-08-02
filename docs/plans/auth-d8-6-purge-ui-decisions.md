# D8-6 영구 삭제 UI·감사 — 착수 결정 브리프

상태: `Verified PASS — D1~D5=A (v1.7.82, c2ca946, 2026-08-02)`
작성일: 2026-08-02  
부모 결정: [`multi-user-auth-cms-decisions.md`](multi-user-auth-cms-decisions.md) D5=A  
구현 기준: [`system-contract-sot.md`](../system-contract-sot.md) v1.7.69~v1.7.76, v1.7.81~v1.7.82

## Decision needed

관리자 화면에 불가역 project purge를 노출하기 전에 **2단계 삭제의 시행 위치, 확인 UX, 삭제 감사의
최소 보존 범위, 실패 후 재시도 의미**를 확정해야 한다. 기존 계약과 코드만으로는 선택할 수 없다:
정책은 archive→purge를 말하지만 endpoint는 활성 project도 지우며, 현재 endpoint는 사유/감사를
받지 않고, core SOT 선삭제 뒤 derived 실패 시 재시도도 불가능하다.

## 1. 실측 기준선 (착수 당시)

| 표면 | 현재 사실 | 이 슬라이스에 미치는 영향 |
|---|---|---|
| 정책 | D5=A는 사용자 archive → 관리자 영구 삭제의 **2단계** | UI만 archive로 제한할지 backend도 강제할지 미결정 |
| endpoint | `POST /admin/projects/{id}/purge`, body 없음, 204 | 확인 문구와 삭제 사유를 서버가 검증하지 못함 |
| 권한 | ADMIN tier, 74 operation 중 관리자 7개 | 소유권 승격 없이 파기 가능하도록 의도된 예외 |
| 파기 범위 | core SOT 8 + derived 10 + vector/index 5 backend | 성공하면 project 전체가 사라지고 복구 불가 |
| 재시도 | core SOT 선삭제. derived 실패 503 뒤 재호출은 404이고 derived에 도달하지 않음 | UI가 평범한 “다시 시도”를 주면 거짓 UX |
| 수습 | `scripts/purge_reconciler.py`, 기본 dry-run, `--apply`만 삭제 | 현행 순서를 유지할 현실적 운영 수습 경로는 존재 |
| 기존 감사 | `access_grants`·`access_grant_uses`는 project graph라 purge 대상 | 삭제 행위 감사로 재사용 불가 |
| reconciler | `project_id`가 있는 컬렉션을 DB에서 발견해 고아 행 삭제 | 삭제 감사를 보존하려면 단순 `project_id` 필드로 저장하면 안 됨 |
| 관리자 화면 | project 카드에 id·name·owner·archived와 승격 UI가 있음 | 같은 카드에 danger 영역을 둘 최소 surface는 준비됨 |

## D1 — 2단계 삭제를 어디서 강제할 것인가

### Decision needed

활성 project의 직접 purge를 허용할지, archive된 project만 purge할 수 있게 할지 정해야 한다. 지금은
문서 정책과 backend 동작이 갈라져 있어 UI만의 선택으로 끝나지 않는다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. backend와 UI 모두 archive 필수** | endpoint가 활성 project에 409, UI는 활성 카드에서 purge 입력을 숨기고 “먼저 보관” 안내 | D5의 2단계를 실제 보안 경계에서 강제 · API 직접 호출도 우회 불가 · 실수 방지 | 기존 endpoint 동작 변경 · 409/OpenAPI/회귀 추가 |
| B. UI만 archive 필수 | 화면은 archive project에만 purge를 보이되 endpoint는 활성 project도 허용 | 코드 변화가 작음 | curl/다른 클라이언트는 2단계를 우회 · 정책이 UI 관례에 불과 |
| C. 활성 project도 purge 허용 | 모든 카드에서 즉시 purge | 운영 속도 · backend 현행 유지 | 2단계 삭제라는 D5 결정과 충돌 · 실수 방지 장치 한 단계 소멸 |

**Recommendation + reason:** **A**. 영구 삭제의 실패 모드는 데이터 영구 소실이다. 이 프로젝트는
인가처럼 실패 비용이 큰 규칙을 UI가 아니라 backend dependency/도메인에서 강제해 왔다. 기존 D5도
“2단계”를 선택한 이유가 실수 방지였으므로 UI만 막는 B는 결정의 절반만 구현한다.

## D2 — 불가역 확인 UX

### Decision needed

관리자가 어떤 명시 행동을 해야 purge 요청을 보낼지 정해야 한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. project 이름 정확히 입력 + 경고문** | 보관된 카드의 danger 영역을 열고 표시된 이름을 그대로 입력해야 버튼 활성화 | 대상과 행위를 함께 인지 · 브라우저 기본 confirm보다 테스트 가능 · 이름이 사람이 읽기 쉬움 | 같은 이름 project가 있을 수 있으나 카드 안에서 대상 id/owner를 함께 표시해야 함 |
| B. project id 정확히 입력 | UUID/id를 그대로 입력 | 대상을 기계적으로 가장 정확히 확인 | 길고 복사 유도 · 사람의 주의 확인보다 copy/paste 의식이 됨 |
| C. 체크박스 또는 브라우저 confirm | “되돌릴 수 없음” 동의 1회 | 구현 최소 | 습관적으로 통과하기 쉬움 · 테스트/접근성/문구 통제가 약함 |
| D. 2인 승인 | 다른 관리자가 승인해야 실행 | 가장 강한 조직 통제 | 현재 로컬/소규모 단계와 계정 모델에 과함 · 운영이 한 명이면 삭제 불가 |

**Recommendation + reason:** **A**. 현재 단계에서 과한 조직 workflow 없이도 오조작을 막는 가장
작은 장치다. 카드에는 project 이름뿐 아니라 id·소유자·보관 상태와 “원고·기억·감사·색인 전체 삭제,
복구 불가”를 함께 보여 준다. 정확한 문자열 비교는 공백 trim이나 대소문자 완화 없이 UI가 표시한
이름과 일치시키는 것을 권장한다.

## D3 — 삭제 사유와 감사 저장

### Decision needed

삭제한 관리자와 이유를 영구 삭제 뒤에도 남길지, 남긴다면 project 전체 파기 정책의 어떤 예외로 둘지
정해야 한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 사유 필수 + 별도 최소 tombstone 감사** | endpoint body에 비어 있지 않은 `reason`; `admin_audit_events`에 actor/action/target id/reason/time/outcome. `target_project_id`를 써 reconciler의 project graph와 명시적으로 분리 | 누가·왜 삭제했는지 보존 · 향후 CMS/운영·분쟁 대응 · reconciler가 감사까지 지우지 않음 | D5 전체 파기에 **최소 감사 예외** 신설 · 사유에 개인정보를 쓰지 말라는 운영 안내 필요 |
| B. 사유 없이 자동 감사 | actor/action/target id/time/outcome만 보존 | 구조가 작고 민감한 자유문 없음 | “왜”가 없어 운영 가치가 낮음 · 접근 승격은 사유 필수인데 더 위험한 삭제가 사유 없음 |
| C. project와 함께 감사도 삭제 | 별도 감사 없음 | D5 all-delete를 문자 그대로 유지 · 신규 저장소/API 없음 | 누가 삭제했는지 증거가 0 · HANDOFF의 감사 잔여를 각하 |
| D. 외부 파일/로그에만 기록 | 애플리케이션 DB 밖 운영 로그 | project DB와 분리 | 조회·백업·접근통제 계약이 불명 · 머신 이동 시 소실 가능 |

**Recommendation + reason:** **A**. 접근보다 삭제가 더 강한 관리자 행위인데 감사 수준이 낮아지는
것은 맞지 않는다. 다만 삭제 요청 자체를 무효화하지 않도록 project 콘텐츠·이름·owner id는 보존하지
않고 **target id와 관리자 입력 사유만** 남기는 최소 tombstone을 권장한다. 필드 이름을
`target_project_id`로 두는 것은 우회가 아니라 의미 구분이다: 이 행은 project graph의 자식이 아니라
그 graph를 없앤 관리자 행위다. 이 예외는 SoT D5에 명시해야 한다.

### D3 하위 권장 계약

- 컬렉션: `admin_audit_events` (TTL 없음; 보존 기간 정책은 서비스 운영/법무 요구가 생길 때 별도 결정)
- 이벤트: `project_purge_requested`, `project_purge_succeeded`, `project_purge_failed`
- 공통 필드: `id`, `admin_user_id`, `action`, `target_type="project"`,
  `target_project_id`, `reason`, `at`
- 실패 필드: 내부 예외 본문 대신 안정적인 `outcome`/`error_kind`만 저장
- 조회: `GET /admin/audit-events?action=project_purge`, 최신순, ADMIN tier
- UI: 관리자 화면의 “최근 영구 삭제 기록”에 actor username, target id, reason, outcome, time 표시
- 감사 write가 요청 전에 실패하면 purge를 시작하지 않는 **fail-closed**를 권장한다.
- purge 자체가 시작된 뒤 outcome 감사 write가 실패했을 때의 응답 의미는 D5에서 함께 확정한다.

## D4 — endpoint 재시도 의미

### Decision needed

core SOT 삭제 뒤 derived 실패 시 503→재호출 404인 현행을 이번 UI 슬라이스에서 바꿀지 정해야 한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 현행 순서 유지 + reconciler 수습** | endpoint는 그대로, 503 UI는 “상태 불확정·재시도 금지·운영 수습 필요”를 표시하고 purge 버튼을 다시 주지 않음 | 이번 범위 최소 · 이미 검증된 reconciler 활용 · 살아 있는 project에서 기억만 먼저 지우는 위험 없음 | endpoint 자체는 여전히 재시도 불가 · 수동 운영 필요 |
| B. derived 선삭제 후 core SOT | 실패한 요청을 다시 호출해 derived를 반복 정리 가능 | 재시도가 derived에 도달 | 실패를 방치하면 **살아 있지만 기억/감사 일부가 없는 project**가 남아 사용자 작업 훼손 가능 |
| C. core SOT purge를 무조건 멱등화 | project가 없어도 derived cleanup을 계속하고 204 | 재호출로 수습 가능 · 구현이 B보다 직선적 | never-existed와 already-purged가 모두 204 · 기존 404 계약 소멸 · target 검증 약화 |
| D. purge operation journal/saga | 먼저 durable operation을 만들고 단계별 진행·재개, 같은 operation id로 retry | 상태와 재시도 의미가 가장 정확 · 향후 분산 저장소에 적합 | 이번 UI 잔여를 크게 넘는 새 orchestration · 상태 machine/복구 worker 필요 |

**Recommendation + reason:** **A를 이번 슬라이스에 적용하고 D를 서비스 운영 규모가 실제로 요구할
때 후속으로 연다.** B는 재시도성을 위해 더 위험한 중간 상태를 만들고, C는 존재하지 않는 id의 404
계약을 없앤다. 현재는 발생 조건이 드물고 검증된 reconciler가 있으므로 UI가 거짓 재시도를 막고 운영
경로를 안내하는 것이 가장 작은 안전한 변경이다. 단, “멱등 재시도”라는 과거 문구는 A 확정 즉시
SoT/docstring에서 현행 한계로 정정돼야 한다.

## D5 — 감사 기록의 성공·실패 원자성

### Decision needed

D3=A일 때 Mongo 장애가 감사와 purge 사이에 발생하면 어떤 결과를 정본으로 볼지 정해야 한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 요청 행 선기록 + 결과 행 best-effort** | requested 기록 실패는 fail-closed. 이후 succeeded/failed 기록은 시도하되 실패가 purge 결과를 뒤집지 않음 | 최소한 누가 어떤 삭제를 시작했는지 남음 · 감사 장애 때문에 이미 끝난 삭제를 503으로 거짓 보고하지 않음 | 결과 행이 없으면 pending인지 감사 write 실패인지 구분 어려움 |
| B. 요청·purge·결과를 한 Mongo transaction | DB 부분은 강한 원자성 | Mongo 안에서는 결과 일치 | vector/index는 worker라 transaction 밖 · 18컬렉션/서비스 경계를 한 session으로 다시 설계해야 함 |
| C. 결과 감사까지 fail-closed | succeeded 기록 실패도 503 | 모든 성공 응답에 완료 감사 존재 | 데이터는 이미 삭제됐는데 503을 내며 재시도 불가 문제를 악화 |
| D. journal(D4-D)로 통합 | 상태 전이 자체가 감사 | 가장 정확 | D4-D의 큰 범위를 그대로 부담 |

**Recommendation + reason:** **A**. 삭제 전 감사가 없으면 행위 자체가 무기록이므로 시작을 막되,
삭제 후 감사 실패는 이미 일어난 파기를 되돌릴 수 없다. 응답은 purge 결과를 기준으로 하고, 결과 행
누락은 `requested`만 남은 운영 이상으로 조회한다. 이 tradeoff는 UI에서 “완료 기록 확인”을 새 요청의
성공 조건으로 삼지 않는 대신 관리자 감사 화면에서 pending을 눈에 띄게 해야 한다.

## Recommendation summary

> **오너 확정(2026-08-02): D1~D5 전부 A.** D4-D operation journal/saga는
> 방향도 승인하되 이번 슬라이스에는 넣지 않고, 원격 저장소·다중 worker에서 수동 reconciler가
> 실제 운영 부담이 되는 시점의 후속 확장으로 추적한다.

| 결정 | 추천 |
|---|---|
| D1 | **A** — archive를 backend와 UI 모두에서 강제 |
| D2 | **A** — project 이름 정확히 입력 + 전체 파기/복구 불가 경고 |
| D3 | **A** — 사유 필수 + project graph 밖 최소 tombstone 감사 + 관리자 최근 기록 |
| D4 | **A** — 현행 순서와 reconciler 유지, 503에서 재시도 UI 금지 |
| D5 | **A** — requested 선기록 fail-closed, 결과 기록 best-effort |

## Follow-up considerations

- Phase 8 관리자 CMS는 `admin_audit_events`의 일반화된 event envelope을 재사용할 수 있다. 다만 지금
  usage quota 감사까지 미리 구현하지 않는다.
- 실제 법적 삭제/보존 요구가 생기면 최소 tombstone의 보존 기간과 사유 자유문의 개인정보 정책을
  별도 결정한다.
- purge saga(D4-D)는 원격 저장소·다중 worker 운영에서 수동 reconciler가 실제 부담이 될 때 연다.
- 관리자 최근 기록의 pagination/기간 filter는 데이터가 커질 때 추가한다. 첫 slice는 bounded recent
  list로 충분하다.

## Deferred / out of scope

- 휴지통 복원, purge undo, project 백업/restore
- 2인 승인, 조직 역할, 법무 hold
- 자동 reconciler daemon과 알림 채널
- 사용자 자신의 hard delete
- Phase 8 사용량/결제 감사 이벤트
- 일반 관리자 감사 대시보드(이번에는 purge 최근 기록만)

## 결정 뒤 구현 슬라이스

1. **계약·회귀** — 선택 결과를 이 문서와 SoT에 반영. archive 경계·request body·audit 모델·에러
   계약을 양방향 테스트로 먼저 잠근다.
2. **backend** — audit repository/service, purge orchestration, admin recent-audit API, Mongo 인덱스와
   `docs/mongo_collections.md`.
3. **frontend** — generated schema client, archived card danger 영역, 이름 확인·사유, 성공 시 card 제거,
   503 상태 불확정(재시도 없음), 최근 삭제 감사 목록.
4. **검증** — backend/frontend 집중→전체→build, archive/active·이름 under/over-strict·감사 fail-closed·
   신규 ADMIN operation 전수 가드 mutation.
5. **기록·독립 검증** — SoT/CHANGELOG/work log/HANDOFF 정리, 커밋 뒤 별도 검증자에게 인계.

## 구현 결과

- backend는 archive되지 않은 project의 purge를 409로 거부하고, 비어 있지 않은 `reason`을 받는다.
- `admin_audit_events`는 project graph 밖의 최소 tombstone이다. `target_project_id`를 쓰고 TTL을 두지
  않으며, requested 기록은 fail-closed, succeeded/failed 결과 기록은 best-effort다.
- `GET /admin/audit-events?action=project_purge`는 ADMIN tier의 최근 50건 조회다.
- 관리자 화면은 archive된 카드에만 danger 영역을 열고, 정확한 project 이름과 사유가 모두 맞아야
  요청한다. 503은 상태 불확정·운영 수습 필요를 알리며 같은 화면에서 재시도 버튼을 제공하지 않는다.
- **D4-D 추적 약속**: 이번에는 A를 유지한다. 원격 저장소·다중 worker가 도입되거나 수동 reconciler가
  실제 운영 부담이 되는 시점에는 durable operation journal/saga로 확장한다. 단순 재시도 버튼이나
  404 의미 변경으로 대체하지 않는다.
