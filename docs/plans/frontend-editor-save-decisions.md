# 착수 결정 브리프 — Frontend 원고 editor·명시적 저장

상태: `Resolved — D1=A · D2=A · D3=A, owner confirmed 2026-07-16`

관련 정본: `docs/system-contract-sot.md` v1.6.98, `frontend-kickoff-decisions.md` D3=A, `frontend-project-navigation-decisions.md` follow-up, `product-shell.md`, HANDOFF Next Tasks

구현 진행: **A1 완료(v1.6.98)** — draft deep link·latest/empty load·평문 textarea·명시적 save intent·archive/409 read-only를 구현했다. **A2(version history selection·dirty 전환 확인·txt/Markdown export)는 다음 slice**다.

## Decision needed

`/projects/:projectId/drafts/:draftId` editor를 구현하기 전에 다음 세 경계를 확정해야 한다.

1. 한 번의 저장 의도와 `idempotency_key`의 수명을 어떻게 묶을지 — 같은 key에 다른 본문을 보내면 서버는 새 본문이 아니라 **최초 저장 version을 replay**하므로 클라이언트가 조용히 잘못 재사용하면 안 된다.
2. 사용자가 과거 version을 선택했을 때 그 선택을 URL에 둘지 화면 state에만 둘지 — 이 결정은 새로고침·deep link·뒤로가기 의미를 구속한다.
3. editor/save와 version/export를 한 번에 구현할지 작은 code slice로 나눌지 — 실패 시 핵심 집필 경로와 부가 read/export 경로를 분리할 수 있다.

백엔드 계약만으로는 브라우저 key 수명과 version navigation UX를 도출할 수 없다. 조용히 선택하면 재시도 때 편집 본문을 잃거나 바로 다음 slice에서 route를 다시 뜯을 수 있어 오너 결정이 필요하다.

## 확인된 현재 계약과 선례

- 저장은 `POST /projects/{project_id}/drafts/{draft_id}/versions`에 `{raw_text, idempotency_key}`를 보낸다.
- 같은 `(project_id, draft_id, idempotency_key)`는 같은 version을 반환한다. **재시도 body가 달라도 최초 snapshot 본문을 반환**한다(`tests/test_core_sot.py::test_idempotency_key_replay_returns_same_version_without_duplicate`). 따라서 key는 문자열이 아니라 **정확한 저장 payload에 결박된 intent token**으로 다뤄야 한다.
- 새 key는 다음 `version_number`를 mint한다. archive project/draft는 version 저장 409, version read/export는 허용한다.
- version list는 `version_number` 오름차순이며, detail은 snapshot `raw_text`를 돌려준다. list/detail에는 내부 `idempotency_key`가 노출되지 않는다.
- export는 선택 version의 본문을 JSON envelope의 `body`로 verbatim 반환한다. `txt|markdown`은 body가 같고 filename/content-type만 다르다.
- 척추 14 endpoint는 이미 `response_model`과 생성 TypeScript 타입이 있으므로 이번 slice는 백엔드 route/model 변경 없이 프론트 조립만으로 가능하다. `ARCH-1` trigger는 미발화가 기본이다.
- 확정된 기본값: 평문 `textarea`, 명시적 save only. autosave·rich editor·전역 cache/data router는 범위 밖이다.

## Owner decision and rationale (2026-07-16)

- **D1=A** — 저장 intent별 UUID를 exact `rawText`에 결박한다. 모호한 transport/5xx 실패 뒤 본문이 같을 때만 같은 key+body로 재시도하고, 본문이 바뀌면 새 intent/key를 만든다.
- **D2=A** — editor URL은 `/projects/:projectId/drafts/:draftId`로 고정하고 version 선택은 component state로 시작한다. 오너는 **B(query parameter)**의 과거 version 공유·새로고침 복원 가치도 인정해 A/B 사이에서 고민했지만, B는 현재 기본 루프에 필수인 route 계약이 아니라 **후속 additive 기능**이라고 판단해 우선 A를 확정했다. Dogfood에서 공유/복원 요구가 생기면 B를 첫 확장 후보로 다시 연다.
- **D3=A** — A1 editor/latest/save를 먼저 완결하고, A2 history/export로 Product shell A를 닫는다.

이 결정은 backend endpoint·Core SOT 멱등 계약을 바꾸지 않는다. 브라우저가 기존 계약을 안전하게 소비하는 방식과 구현 순서만 잠근다.

## D1. `idempotency_key` 생성·재시도 수명

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 저장 intent별 UUID + exact payload 결박 (추천)** | Save 클릭 시 `crypto.randomUUID()`로 `{key, rawText}` intent를 만든다. transport/5xx처럼 commit 여부가 모호한 실패 뒤 **본문이 그대로면 같은 key+body**로 재시도한다. 본문이 바뀌면 새 intent/key다. 2xx 또는 현재 API의 확정적 400/404/409/422 뒤 intent를 종료한다. | 서버 멱등 계약을 정확히 사용한다. 같은 key에 바뀐 본문을 보내 최초 version이 조용히 replay되는 오류를 막는다. 별도 저장소 없이 작다. | 새로고침하면 in-memory intent가 사라져 모호한 요청을 이어받지 못한다. 네트워크 실패 후 본문을 바꾸면 이전 요청의 결과와 새 저장이 둘 다 version이 될 수 있다. |
| B. Save 시도마다 새 UUID | 클릭할 때마다 이전 실패 여부와 무관하게 새 key를 만든다. | 구현이 가장 단순하다. 본문과 key mismatch가 없다. | 응답 유실 후 재시도가 중복 version을 mint해 서버 멱등 계약의 핵심 효과를 버린다. |
| C. sessionStorage 저장 journal | `{draftId,key,rawText}`를 sessionStorage에 저장해 새로고침 뒤에도 같은 intent를 복구한다. | 모호한 실패와 새로고침을 함께 견딘다. | stale journal·다중 탭·완료 판정·본문 노출 수명을 새로 소유한다. 로컬 1인 MVP의 첫 editor치고 상태 계약이 커진다. |
| D. 본문 hash 기반 결정적 key | draft id와 raw text hash로 key를 만든다. 동일 본문은 언제나 같은 version으로 dedup한다. | 새로고침 뒤 별도 journal 없이 같은 본문 재시도가 dedup된다. | 나중에 동일 본문을 의도적으로 새 version으로 저장할 수 없다. 현재 계약의 “저장 요청 멱등”을 “내용 dedup”으로 바꾼다. |

### Recommendation + reason

**D1=A를 추천한다.** 현재 단계에서 필요한 것은 전역 offline journal이 아니라 사용자가 Save를 눌러 만든 한 HTTP 요청의 안전한 재시도다. A는 key를 exact `rawText`와 함께 보존해 서버의 “같은 key면 최초 version replay” 의미를 훼손하지 않으며, sessionStorage·다중 탭 정책을 열지 않는다.

구현 lock:

- 같은 in-flight intent의 중복 submit은 1 POST만 허용한다.
- network error 또는 5xx 후 textarea가 intent의 `rawText`와 같으면 같은 key와 같은 body를 재사용한다.
- 실패 후 textarea가 달라졌으면 이전 key를 절대 재사용하지 않고 새 key를 만든다.
- 2xx(`idempotent_replay` true 포함) 뒤 intent를 폐기하고 응답 version을 현재 기준선으로 삼는다.
- 현재 Application이 내는 400/404/409/422는 저장을 거부한 확정 응답으로 보고 intent를 폐기한다. 409 archive는 read-only로 전환한다. 그 밖의 status/transport/response-parse fault는 commit 여부를 단정하지 않고 intent를 유지한다.
- first slice는 새로고침을 가로지르는 request journal을 보장하지 않는다. 실제 중복 version이 dogfood에서 관측되면 D1=C를 별도 검토한다.

## D2. Version 선택과 URL

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. draft route 고정 + component state 선택 (추천)** | editor 주소는 `/projects/:projectId/drafts/:draftId` 하나다. 최초 진입은 최신 version을 열고, version 목록 클릭은 같은 화면의 selected version state만 바꾼다. 새로고침하면 다시 최신이다. | route spine이 작고 unsaved editor와 version 선택 책임이 한 화면에 머문다. version이 0개인 새 draft도 같은 URL을 쓴다. | 과거 version deep link·새로고침 복원이 없다. 브라우저 뒤로가기로 version 선택을 이동하지 못한다. |
| B. query parameter | `/drafts/:draftId?version=:versionId`; query가 없으면 최신이다. | 과거 version 공유·새로고침 복원과 version 0개 route를 함께 지원한다. | query/history 동기화와 invalid/cross-draft query 404 UX가 첫 editor에 추가된다. |
| C. nested version route | 최신 editor는 `/drafts/:draftId`, 과거 선택은 `/drafts/:draftId/versions/:versionId`다. | 주소 의미가 가장 명시적이고 기존 API path와 닮았다. | 같은 editor의 latest/selected route가 둘이 되고, 과거 version을 편집해 새 latest로 저장할 때 route 전환 규칙이 필요하다. |
| D. 모든 editor route에 version id 필수 | `/drafts/:draftId/versions/:versionId`만 editor로 사용한다. | 현재 본문 기준이 항상 URL에 드러난다. | 아직 version이 없는 새 draft에 주소가 없고, 빈 editor를 위해 별도 route가 다시 필요하다. |

### Recommendation + reason

**D2=A를 추천한다.** 이번 목표는 “프로젝트 생성 → 원고 입력 → 저장” 루프를 먼저 닫는 것이고, 과거 version 공유 URL은 아직 확인된 요구가 아니다. draft가 editor identity이고 version은 그 안의 read selection으로 두면 새 draft와 최신 본문 진입이 한 route에서 동작한다. B/C는 dogfood에서 과거 version 링크·브라우저 history 요구가 실제로 나타날 때 additive로 열 수 있다.

구현 lock:

- 최초 진입: version 0개면 빈 editor, 1개 이상이면 가장 큰 `version_number`의 detail을 읽는다.
- 과거 version 선택은 해당 snapshot 본문을 textarea에 표시한다.
- 과거 version을 수정해 Save하면 append-only 새 latest version을 mint하고 그 version을 선택 상태로 바꾼다. 기존 version은 수정하지 않는다.
- version 변경 전에 dirty text가 있으면 조용히 덮어쓰지 않는다. A2에서 최소 확인 UI를 추가하며, autosave로 우회하지 않는다.
- 새로고침은 최신 version으로 복귀한다. 이 동작은 D2=A의 의도된 한계다.

## D3. Code slice 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. A1 editor/save → A2 history/export (추천)** | A1은 draft 링크·직접 진입·latest/empty load·textarea·명시적 save·read-only까지. A2는 version 목록 선택·dirty 전환 확인·txt/Markdown download를 붙인다. | 핵심 “입력→저장”을 먼저 관통하고 idempotency 회귀에 집중한다. history/export 결함이 save slice를 가리지 않는다. | A1 종료 시 Product shell A는 아직 완료가 아니며 문서 상태를 한 번 더 갱신한다. |
| B. editor/save/history/export 한 slice | Product shell 잔여를 한 번에 닫는다. | 한 번의 릴리스·검증으로 A를 완료한다. | idempotency·selection·Blob download·dirty UX를 동시에 디버깅해 slice가 커진다. |
| C. read editor → save → history/export 세 slice | 조회와 write도 분리한다. | 각 변경이 가장 작다. | 사용자가 실제로 글을 저장하는 가치가 한 slice 더 늦고 문서/검증 overhead가 기능보다 커진다. |

### Recommendation + reason

**D3=A를 추천한다.** A1만으로 첫 실제 집필 write loop가 닫히고, A2는 이미 저장된 version을 대상으로 독립적으로 검증할 수 있다. C처럼 save 자체를 늦추지는 않으면서 B의 동시 상태 수를 줄인다.

## 추천 조합

**D1=A · D2=A · D3=A**

- 저장 intent별 UUID를 exact 본문에 묶고 모호한 재시도에서만 재사용한다.
- editor URL은 draft identity까지만 두고 version 선택은 component state로 시작한다.
- A1 editor/save를 먼저 완결한 뒤 A2 history/export로 Product shell A를 닫는다.

## 선택 후 A1 code slice

1. `DraftList` 원고 행을 `/projects/:projectId/drafts/:draftId` 링크로 변경한다.
2. 새 `DraftEditor`가 project·draft·version list를 읽는다.
   - version 없음: 빈 textarea.
   - version 있음: 최신 meta의 detail을 읽어 exact `snapshot.raw_text` 표시.
   - archived project/draft: textarea read-only, Save 숨김/비활성.
3. API client가 생성 타입으로 `getDraft`·`listDraftVersions`·`getDraftVersion`·`saveDraft`를 추가한다.
4. 명시적 Save만 새 version을 mint한다.
   - 저장 전후 baseline을 추적하고 unchanged 상태에서는 accidental version mint를 막는다.
   - 기존 본문을 모두 지운 dirty 상태의 `raw_text=""` 저장은 허용한다(백엔드 계약과 일치).
   - brand-new empty draft는 unchanged이므로 의미 없는 첫 empty version을 mint하지 않는다.
5. 회귀:
   - exact project/draft path와 direct URL 격리
   - 0-version empty / latest version load / archived read-only
   - Save request exact URL·body·새 version 반영
   - in-flight 중복 방지
   - ambiguous failure same text → same key, changed text → new key
   - 같은 key replay가 새 version을 만들지 않는 UI 처리
   - list/detail/save 404·409·5xx 오류와 입력 보존
   - unchanged save suppression과 nonempty→empty save over-strict guard

## A2 후속 범위

- version 목록과 selected version detail
- dirty 상태에서 version 전환 확인
- 선택 version txt/Markdown export 응답을 `Blob`으로 내려받기
- filename/content-type/body가 서버 envelope과 일치하는 회귀
- Product shell A 종료 smoke와 `ARCH-1` trigger 점검

## Follow-up considerations

- dogfood에서 network ambiguity로 중복 version이 실제 발생하면 sessionStorage journal(D1=C)을 검토한다.
- 과거 version 공유·새로고침 복원 요구가 생기면 query parameter(D2=B)를 우선 검토한다. nested route는 editor와 read-only version view가 실제로 분리될 때 후보로 남긴다.
- dirty navigation 보호는 A1에서 현재 앱의 brand/back link와 `beforeunload` 범위로 최소 구현하고, 전역 route blocker는 navigation 표면이 늘 때 검토한다.
- A1/A2 모두 backend route/request/response model을 수정하지 않는 한 `ARCH-1`은 미발화다. A 완료 체크포인트에서 다시 확인한다.

## Deferred / out of scope

- autosave, debounce save, offline queue, sessionStorage/localStorage draft persistence
- rich text/Markdown preview, collaborative editing, diff/merge/branch model
- route loader/action, TanStack Query, 전역 store
- version rename/delete, rollback mutation(과거 version을 읽어 새 version으로 저장하는 것만 가능)
- DOCX/PDF/EPUB export
- Analysis 자동 실행 상태 UI, Writing/Review UI
