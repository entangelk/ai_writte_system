# 2026-08-27 작업 로그 (알파)

> **[세션 1] 오너 도그푸드 UI 지적 7건 — 관리 콘솔 재편 · 개인 허브 스타일 · 프로젝트 설정 탭 ·
> 원고 단위 · 저장 기록 접기 (백엔드 1필드 · 프론트 6슬라이스 · 신규 15셀 · mutation 12종).**
> 오너가 구버전 빌드(슬라이드 탭 이전)로 도그푸드하며 모은 지적 7건으로 착수했다. 착수 전 질의
> 4건에 오너가 전부 권장안을 채택했고(아래 "오너 결정"), 그중 둘은 **작업을 하지 않기로** 한
> 결정이다(원고 길이 제한 보류 · 검토함은 설정 탭에 넣지 않음).

## 목표

오너 도그푸드 지적 7건을 UI 슬라이스로 처리한다. 백엔드 계약 변경은 지적 ①이 요구하는
`AdminUserPayload.status` 한 필드로 제한한다.

## 오너 결정 (2026-08-27)

| # | 결정 | 이유 · 트레이드오프 |
|---|---|---|
| D1 | **프로젝트 설정 탭 = 작품 정보·개요 + 원고 내보내기 + 활동 타임라인. 검토함은 제외** | 검토함은 집필 중 수시로 드나드는 **작업 흐름**이라 설정이 아니다. 편집기 드로어에도 같은 이름의 탭이 이미 있어 일관된다. 대가: 작업 공간 상단에 링크가 둘(검토함·설정) 남는다 — 셋이 나란하던 종전보다는 줄었다 |
| D2 | **원고 본문 길이 제한은 이번에 넣지 않는다** | 오늘은 UI 변경일이고, 길이 제한은 서버 계약 변경(422 응답·회귀·저장 실패 경로)이라 별도 슬라이스가 맞다. **현재 상태: 제한이 아예 없다**(아래 "발견한 문제" ①) |
| D3 | **저장 기록은 최신 5개 + 나머지 접기** | 드롭다운 하나로 압축하는 안보다 자주 쓰는 최신 버전 접근성이 유지된다. 대가: 옛 version 은 클릭 한 번이 더 든다 |
| D4 | **관리 메인의 "전체 프로젝트"는 사용자 상세로 이관, 소유자 없는 것만 남긴다** | 소유자 없는 프로젝트는 사용자별 페이지로 **갈 수 없다**. 보통 0건이라 화면을 늘리지 않고, 생기면 그 자체로 이상 신호다 |

### 세션 후반 — 보고 뒤 오너 후속 지시 3건

| # | 결정 | 원문 · 맥락 |
|---|---|---|
| D5 | **원고 본문 길이 제한 = 4000자. 단, "일단 테스트"가 선행** | *"본문 길이제한 나중에 4000자 정도로 제한해야한다고 해줘 (일단 테스트, 8000컨텍스트 안에 들어갈지 확인해봐야함)"* — D2(보류)를 **방향까지 정한 유예**로 갱신한 것이다. 4000자 ≈ **2,353 tok**(1.7자/tok). **★ 착수자가 알아야 할 것: 본문은 생성 프롬프트에 통째로 실리지 않는다**(브리프 §6 — `raw_text` 는 accept 저장 경로에만 등장하고 창에 들어가는 것은 `context_search` 조각) — 그래서 오너의 "8000 컨텍스트" 질문은 **본문이 아니라 검색 조각 예산**의 질문이고, 재는 자리는 `GET /writing/budget` 의 `context_budget_tokens` 다 |
| D6 | **`unit_kind` 존치 여부는 열어 둔다 — 오늘은 그대로** | *"그러면 장이나 장면을 나누는 이유가 뭐지? … 필요없는거 아냐? 흠…. 일단 알겠어. 메모해둬서 내가 까먹지 않게해주고"*. 오너가 **계층이라고 이해하고 있었다**는 사실이 이 세션에서 처음 드러났다(SoT v1.7.9 D2=A 가 계층안을 각하하고 평면을 택했으나 그 결정이 오너에게 전달된 적이 없다). 판단은 유지·제거·계층화 셋이 모두 열려 있다 |
| D7 | **`test_the_whole_writing_track_is_declared` 실패는 유예** | *"테스트는… 뭐지? 저거는 나중에 손봐야겠네. 메모만 해주고"*. 그때까지 **백엔드 전수는 이 1건이 빨간 채로 돈다** — 다음 작업자가 새 실패와 헷갈리지 않도록 HANDOFF 마감 메모에 명시했다 |

### `unit_kind` 전수 확인 (D6 의 근거)

오너 질문(*"나누는 이유가 뭐지?"*)에 답하려고 저장소 전체를 훑었다. **결론: 어떤 동작도 분기시키지 않는다.**

| 쓰일 법한 자리 | 실제 |
|---|---|
| 생성 프롬프트 | **미사용** — `raw_text` 자체가 프롬프트에 안 실린다 |
| export heading 레벨 | **매핑 없음** — SoT v1.7.17 이 명시(*"unit_kind별 heading 레벨 매핑 없음"*) |
| 계층(부모-자식) | **없음** — `core_sot/models.py` 에 parent 필드 없음, `position` 은 프로젝트 전체가 하나로 이어짐 |
| 분석·검색·기억 | **미사용** |
| 실제로 쓰이는 곳 | ① 원고 목록 라벨(`정본 순서 1 · 장`) ② export manifest 의 기록 필드 — **그 manifest 는 오늘 UI 에서 뺐다**(계약에는 남음) |

저장·왕복·유효값 검증(`isinstance(unit_kind, UnitKind)`)은 있으나 **그 값에 따라 갈리는 코드 경로가 0개**다.

## 완료한 작업

### Slice 1 — 관리 콘솔 재편 (지적 ①②③) · 커밋 `5bd12c2`

- **백엔드**: [`api/models.py`](../../services/application/app/api/models.py) `AdminUserPayload`에
  `status: str` 추가 + [`routers/admin.py`](../../services/application/app/routers/admin.py)
  `_admin_user_payload`에 배선. `gen:api` 재생성(`schema.d.ts` +2줄, `paths` 무변).
- **원인**: 가입 요청 행은 `is_active=True`로 저장되고(승인 축과 활성 축은 별개 —
  [`auth/models.py`](../../services/application/app/auth/models.py) 주석) payload 에 `status`가
  없어 관리 목록이 **로그인조차 못 하는 계정을 "활성"으로** 표시했다.
- **프론트**: `userStatus.ts` 신설(비활성 > 승인 대기 > 거절됨 > 활성 순 — 비활성화는 단방향
  D6 이라 승인 축보다 앞선다) · 사용자 검색 · 행마다 프로젝트 수·상세 링크.
- **`/admin/users/:userId` 신설**: 그 사용자의 프로젝트만(+프로젝트 검색). 승격·접근 이력·
  영구 삭제 카드는 `AdminProjectCard.tsx`로 추출해 관리 메인의 소유자 없는 프로젝트와 공유.
  **사용자별 프로젝트 조회 operation 은 새로 파지 않았다** — 기존 목록 둘을 읽어 화면에서 좁힌다.
- **작업장 출구**(지적 ③): 링크는 2026-08-24 커밋 `36d5778`에 **이미 있었다**(오너는 구버전
  빌드를 봤다). `.section-link` 라 눈에 안 띄던 것을 accent 버튼으로 승격.

### Slice 2 — 내 작업 `/me` (지적 ④) · 커밋 `b13ba37`

- 이 화면은 만들어진 뒤로 **제 CSS 가 한 줄도 없었다**(`.hub-section`·`.quota-summary`·
  `.hub-projects` 전부 미선언). 프로젝트 목록을 `.resource-list`/`.resource-row`로 —
  프로젝트 목록 화면과 같은 행 처리.
- 프로젝트·최근 활동을 `<details>`로, 활동은 **날짜 그룹마다** 접히고 가장 최근 하나만 열린다.
  **상한 100건은 그대로** — 접는 것은 화면이지 데이터가 아니다.

### Slice 3 — 프로젝트 설정 탭 (지적 ⑤) · 커밋 `cbe4ed1`

- `/projects/:id/settings` 신설(`?tab=brief|export|activity`). `ProjectOverview`·
  `ActivityTimelinePage`에서 back-link·머리글을 떼어 셸로 올렸다(두 컴포넌트는 이제 탭 내용이다).
- 원고 내보내기를 `DraftList` → `ProjectExportPanel.tsx`로 이관.
- **추적 정보(manifest) 옵션 제거**. 다만 **zip 경로는 여전히 manifest 를 읽는다** — 무엇이
  포함되고 어느 version 인지가 거기에만 있다. 사용자에게 파일을 주지 않는 것과 서버에 묻지
  않는 것은 다른 일이며, 그 구분을 셀 하나가 양방향으로 잠근다.
- 옛 `/overview`·`/activity` 주소는 해당 탭으로 리다이렉트(링크·북마크 보존).

### Slice 4 — 원고 단위 (지적 ⑥) · 커밋 `84126e6`

- **select 높이**: 원인은 padding 이 아니라 **글꼴**이었다. 브라우저가 select 에 제 UI 글꼴을
  주므로 같은 padding 에도 line-box 높이가 달라진다 — `font: inherit`로 맞추고 UA 화살표를 끈 뒤
  caret 을 `currentColor` gradient 로 직접 그렸다(이미지가 아니라 gradient 인 것은 테마 때문).
- **기본값 기타 → 장**. 서버 기본값(`UnitKind.OTHER`)은 그대로 뒀다 — 그쪽은 "값이 오지 않았을
  때"의 답이고 화면은 "사람이 고르는 첫 값"이다.
- **설명문**: 아래 "발견한 문제" ②로 인해 오너의 이해가 아니라 **실제 동작**을 적었다.

### Slice 5 — 저장 기록 접기 (지적 ⑦) · 커밋 `7f25804`

- 최신 5개만 펼치고 나머지는 `<details>`. 보고 있는 version 이 접힘 안에 있으면 열어 둔다.

## 발견한 문제

### ① 원고 본문에 길이 제한이 없다 (오너 질의에 대한 답)

- **문제**: 오너가 *"길이 제한 우리가 하지 않았나?"* 라고 물었으나, `raw_text`에는
  [`api/models.py:494`](../../services/application/app/api/models.py#L494)·`:679` 어디에도
  `max_length`가 없다. 프론트 `formatCharCount`도 표시만 한다.
- **제한이 있는 것은 다른 것들이다**: 문체 예시 `PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS=1000` ·
  활동 로그 라벨 200자 · 생성 출력 길이 프리셋(`WRITING_OUTPUT_LENGTH_*`) · 서버 K-3 창 가드.
  **본문 저장 자체는 무제한**이다.
- **처리**: 오너 결정 D2 로 보류. 넣는다면 서버 `max_length` + 422 + 프론트 사전 차단 + 회귀가
  한 슬라이스로 가야 한다.

### ② `unit_kind`는 계층이 아니다 — 오너 이해와 실제가 다르다

- **오너 이해**: *"장은 그 안에 다량의 장면 원고를 쓸 수 있고, 장면은 그냥 그거 하나가 장면"*.
- **실제**: SoT **D2=A 평면 ordered unit**이다. 셋은 같은 목록의 이름표이고 `position`은
  전체가 하나로 이어진다. **부모-자식 관계가 없고**(`core_sot/models.py`에 parent 없음),
  프롬프트에도 export heading 에도 쓰이지 않는다(v1.7.17: *"unit_kind별 heading 레벨 매핑 없음"*).
- **처리**: 설명문을 **실제 동작대로** 썼다(*"셋 다 한 목록에 나란히 놓이고… 계층은 없습니다"*).
  오너 이해대로 적었으면 화면이 거짓을 말했을 것이다. **계층 구조를 실제로 원하시는지는 오너
  확인이 필요하다** — 원한다면 그것은 UI 문구가 아니라 데이터 모델 변경이다.

### ③ 기존 실패 1건 (내 작업과 무관, 미수정)

- `tests/test_application_api.py::WritingErrorContractDeclarationTest::test_the_whole_writing_track_is_declared`
- **원인**: 2026-08-26 세션 3이 추가한 `DELETE /projects/{id}/writing/scratch/{scratch_id}`가
  그 셀의 `EXPECTED` 잠금 목록에 등재되지 않았다. 가드는 정상 작동한 것이고(새 writing 경로는
  에러 선언을 등재해야 한다) 등재가 빠진 것이다.
- **확인**: 내 첫 변경 **이전** working tree(`git stash`)에서도 같은 실패 — 내가 만든 것이 아니다.
- **처리**: 스코프 밖이라 손대지 않았다. 다음 작업자의 첫 항목 후보.

## Mutation (양방향 회귀 검증)

**절차 준수**: 각 mutation 전에 `git status --short` 빈 것을 확인했고, 대상 변경은 이미 커밋된
상태에서만 mutate → `git checkout --` 복원 → 트리 clean 재확인했다.

| # | mutation | 파일 | 재실패한 셀 |
|---|---|---|---|
| M1 | `status === "pending"` 분기 삭제 (under) | `admin/userStatus.ts` | AdminConsole › tells a pending signup apart from an active account |
| M2 | 대기 행을 "비활성"으로 과대교정 (over) | `admin/userStatus.ts` | 〃 |
| M3 | `RECENT_VERSION_COUNT` 5 → 999 (under) | `drafts/DraftEditor.tsx` | 저장 기록 접기 › keeps the newest five in hand and folds the rest away |
| M4 | `olderVersions`를 빈 배열로 = 목록 자르기 (over) | `drafts/DraftEditor.tsx` | 〃 |
| M5 | 활동 그룹 `open={index === 0}` → `open` (under) | `me/PersonalHubPage.tsx` | 접기 · 목록 스타일 › folds each activity day and opens only the most recent |
| M6 | `owner_id === userId` 필터 제거 (under) | `admin/AdminUserDetail.tsx` | AdminUserDetail › shows only this user's projects and filters them by name |
| M7 | 검토함 탭을 설정에 추가 (over) | `projects/ProjectSettingsPage.tsx` | ProjectSettingsPage › gathers the three occasional screens under one tab bar |
| M8 | manifest 체크박스 부활 (under) | `projects/ProjectExportPanel.tsx` | ProjectExportPanel › no longer offers the manifest, but still reads one to build the zip |
| M9 | zip 경로의 `manifest: true` → `false` (over) | `projects/ProjectExportPanel.tsx` | ProjectExportPanel › bundles each unit as its own file inside a zip |
| M10 | 기본 단위 `chapter` → `other` (under) | `drafts/DraftList.tsx` | DraftList › defaults the unit to 장 and explains that the three are labels, not a hierarchy |
| M11 | `<option value="other">` 삭제 = 선택지 축소 (over) | `drafts/DraftList.tsx` | 〃 |
| M12 | payload 의 `"status": user.status` 삭제 (under) | `routers/admin.py` | SignupApprovalApiTest::test_admin_user_list_separates_pending_from_active |

**★ M8 은 첫 시도가 무효였다** — 체크박스를 `drafts.some(archived)` 조건 블록 **안**에 넣어
보관 원고 없는 픽스처에서 렌더되지 않았고, 셀이 통과했다. 조건 밖으로 옮겨 재실행해 재실패를
확인했다. *mutation 이 통과하면 가드가 약한 것일 수도, mutation 이 안 먹은 것일 수도 있다 —
먼저 후자를 의심한다.*

## 기준선

- 백엔드 **2276 passed · 119 skipped · 2334 subtests**(`test_application_api.py` 제외 실행) +
  `test_application_api.py` **123 passed · 492 subtests · 1 failed**(위 ③, 기존 실패).
- 프론트 **370 passed / 34 files**(종전 366 + 신규 15 − 이관·재구성 분). `tsc --noEmit` clean.
- `npm run build` 성공 — 신규 lazy 청크 `AdminUserDetail`(3.15 kB) · `userStatus`(3.92 kB),
  진입 번들 433.50 kB.

## 부수 발견 — buttonAppearance 가드가 실제로 물었다

`.section-link.primary-link`에 accent 면을 로컬로 선언했더니
[`buttonAppearance.test.ts`](../../frontend/src/buttonAppearance.test.ts)가 *"겉모습을 정하는
자리가 둘"* 로 잡았다. 통합 규칙 **세 벌 모두**(base·hover·disabled)에 선택자를 등재해 해소했다.
`:disabled`는 `<a>`에 결코 매치되지 않지만, **세 규칙의 자리 집합이 갈리지 않게** 하려고 함께
넣고 사유를 주석에 남겼다. 그 가드가 없었다면 여섯 번째 사본이 조용히 생겼을 것이다.

## 다음 단계

1. **원고 본문 4000자 제한(D5)** — 착수 전 "일단 테스트": `GET /writing/budget` 로 검색 조각
   예산을 재고, 본문이 프롬프트에 안 실린다는 사실을 실측으로 확인한 뒤 계약을 박는다. 넣을 때는
   서버 `max_length` + 422 + 프론트 사전 차단·카운터 경고 + 양방향 회귀가 **한 슬라이스**로 간다.
2. **`unit_kind` 존치 판단(D6)** — 유지·제거·계층화. 제거는 계약 변경 + Mongo 마이그레이션 +
   `start_next_unit` 의 `next_unit.unit_kind` 동반 정리라 되돌리기가 비싸다.
3. **`test_the_whole_writing_track_is_declared` 등재 누락(D7, 유예)** — 그 셀의 `EXPECTED` 에
   `DELETE …/writing/scratch/{scratch_id}` 를 등재하고 실제 에러 선언과 대조하면 닫힌다.
4. **신버전(슬라이드 탭) 대조**: 오너가 구버전 빌드로 본 지적이라, 배포 후 같은 자리를 다시 봐야
   한다. 특히 편집기 드로어와 설정 탭이 좁은 화면에서 겹치지 않는지.

---

## 세션 2 — 부채 처리: D7 폐쇄 + D5 선행 실측 ("일단 테스트")

착수 시 트리 clean(`39f4795`). 마감 커밋은 아래 각 항목에 있다.

### D7 — 기존 실패 셀 폐쇄 · 커밋 `04e0b7b`

- `WritingErrorContractDeclarationTest`의 `EXPECTED`에
  `("/projects/{project_id}/writing/scratch/{scratch_id}", "delete")` 등재
  (집합 `{401,403,404,503}` — `_owned(_ERRORS_404)`가 만드는 선언 그대로, 형제 경로와 동일)
  + 개수 핀 13 → 14.
- **재현 → 수정 → green**: 착수 전 `1 failed, 5 passed, 110 subtests` 실측 후
  `test_application_api.py` 전체 **124 passed · 498 subtests**(= 세션 1 기준 123+1failed와 정확히 합침).
- **뮤테이션(over-strict 방향)**: 새 등재 항목에서 `"503"` 제거 → lock-list 셀이
  `SUBFAILED(path='/projects/{project_id}/writing/scratch/{scratch_id}', method='delete')` 로 재실패
  확인 후 `git checkout` 원복, 트리 clean 재확인. under 방향은 착수 전 재현이 그 증거.
- **백엔드 전수가 이제 빨간 셀 0으로 돈다** — 이후 새 실패는 전부 새 결함이다.

### D5 선행 실측 — 오너 "일단 테스트" (2026-08-27, 알파, 외부 구글 API 배포)

스택 전체 기동(healthy 8 + 워커 2) 후 임시 계정 `budget_probe`(비관리자)로 관통 측정.
측정 뒤 프로브 정리: 프로젝트 `budget-측정용-프로브`(`6a8fd127048b122e35512a36`) 아카이브 +
계정 비활성화(mongosh 직접, 둘 다 soft·가역 — 08-23 정리 선례와 같은 형태).

| # | 측정 | 값 |
|---|---|---|
| 1 | `GET gateway /v1/capabilities` | `{"context_window":null}` — llama.cpp 전용 `/props`가 외부 API에 없음(문서화된 함정). `/health/ready` 503("llama upstream is not ready")도 같은 원인의 문서화된 동작 |
| 2 | `GET /projects/{id}/writing/budget` | `{"short":8192,"medium":8192,"long":8192}` — `derive_context_budget`의 `window is None → return requested_tokens`. **현재 배포의 예산 숫자는 서버 실측이 아니라 요청 상한(`DEFAULT_CONTEXT_BUDGET_TOKENS=8192`)** |
| 3 | 원고 본문(`raw_text`) 등장 지점 전수 | 저장(`api/models.py:679` `SaveDraftRequest`) · 읽기(`:494`·`routers/drafts.py:200`) · export(`core_sot/service.py:696`) · 저장소 해시·블록분해(splitter). **LLM 프롬프트 0곳** |
| 4 | 생성 프롬프트 구성(`writing/prompt.py::build_writing_request`) | system 템플릿 + instruction + ContextPackage(**검색 조각**) + `draft_excerpt` — 프론트는 `draft_excerpt`를 **항상 `""`**로 보낸다(`WritingPanel.tsx:347,412,535`·`ScratchRecovery.tsx:171`). gate·report·accept가 싣는 `candidate_text`는 AI 산출물이지 본문이 아니다 |
| 5 | accept 합성 방식 | [`accept.py:150`](../../services/application/app/writing/accept.py#L150) `_append_patch` — **후보를 본문에 append**. 본문은 채택마다 자라며 `long` 프리셋(4096 tok ≈ 최대 ~6,963자) 산출물 채택 가능 |

**오너 질문("4000자가 8000 컨텍스트 안에 들어갈지")에 대한 답**: **들어갈 일이 없다** — 본문은
어떤 프롬프트에도 통째로 실리지 않는다. 창 예산이 실제로 구속하는 것은 검색 조각(ContextPackage)이고,
현재 배포에서 그 8192라는 값은 요청 상한일 뿐 서버 실측이 아니다(외부 API에선 창을 못 잰다).
4000자 ≈ 2,353 tok(1.7자/tok).

**예외 축 하나(본문이 아니라 자료)**: `analysis_extract`는 **source 스냅샷의 `raw_text`를 통째로**
싣는다([`extractor.py:73`](../../services/application/app/analysis/extractor.py#L73)). 오너가 말한
"본문"(원고)이 아니라 자료 축이지만, **긴 텍스트가 창에 직접 부딪히는 유일한 LLM 경로**다 —
길이 제한 논의를 나중에 자료 축으로 확장할 때 이 자리부터 시작한다.

### 세션 2 오너 결정 대기 — 4000자 제한의 적용 범위

실측이 오너 지시의 전제("본문이 창에 실린다")를 부정했고, accept-append 설계와 4000자가 충돌할 수
있어 **적용 범위는 오너 결정**으로 넘겼다(선택지 ⓐ~ⓓ — HANDOFF "Owner Decisions Needed" ⓪ 갱신분
참조). 결정 전에 계약을 박지 않는다(D5의 "테스트 선행" 조건이 그 뜻이다).

## 세션 2 다음 단계

1. **D5 범위 오너 결정 수령** → 서버 `max_length` + 422 + 프론트 사전 차단·카운터 경고 +
   양방향 회귀를 한 슬라이스로 시행.
2. **D6(`unit_kind`)·신버전 육안 대조** — 세션 1 다음 단계 2·4 그대로(오너 몫).
