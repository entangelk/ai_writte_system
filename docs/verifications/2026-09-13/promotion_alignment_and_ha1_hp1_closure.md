# 선재 5건 판정 줄 정합(`a1d71fc`) + 미수리 둘 폐쇄(`5a8e8c7`) — 독립 검증

**합격** — 승격 귀속 다섯 건이 전부 1차 자료에서 재유도됐고(승격 기록 다섯이 실재하며 각각 명시적으로 승격을 선언한다), 발행 시점 판정 원문은 **바이트 단위로 보존**됐으며, 구현 세션이 잰 변이 넷을 diff 원문 그대로 **전건 재현**했다. 대상이 재지 않은 변이 여덟을 더 찍어 **조용한 방향 하나(MS-4)** 를 찾았고 — 그것과 짝 셀 이름 오기, 승격 뒤 거짓이 된 문장 셋을 이 검증에서 닫았다(`d3ef8cd`). 차단 없음.

## Subject metadata

- **일시**: 2026-09-13 · **검증자**: 독립 세션 — `a1d71fc`·`5a8e8c7`·`9ccf9c7` 어느 것도 만들지 않았다.
- **대상**: `a1d71fc`(승격 기록 선재 5건 본문 판정 줄 정합) · `5a8e8c7`(HA-1 휴면 절 앵커 실효화 · HP-1 replay 행 정체 단정) · `9ccf9c7`(세션 76 작업 로그).
- **정본 참조**: [`docs/guides/verification.md`](../../guides/verification.md) §Required sections(판정 어휘 셋 · 인덱스 일치) · §"boundary matrix has no empty cells" · §Mutation testing. 미수리 둘의 원 등재: [`activity_replay_c1_promotion_audit.md`](../2026-09-12/activity_replay_c1_promotion_audit.md) §3 HA-1 · §6 HP-1.
- **검증 트리**: 변이는 **전부 탈치 워크트리**에서만 했다(`git worktree add --detach` — `5a8e8c7`·`a1d71fc`·`d3ef8cd`·`9ccf9c7`·`1f4f95a` 다섯). 검증 창 내내 같은 트리에서 **다른 검증 AI 가 `activity_replay_c1_promotion_audit.md` 승격 작업 중**이었다 — 그 파일 무접촉, 본 트리에서 `git checkout`·`restore`·`stash`·`reset` 미사용.
- **환경**: WSL2 · `python3 -m pytest`(초점 3파일, test-mongo 미도달 셀은 범위 밖). 백엔드 전수는 공유 트리 과부하 오탐 때문에 돌리지 않았다 — 대신 문서 가드 둘을 **다섯 리비전에서 양단 실측**했다.

## Scope

1. **승격 귀속의 사실성** — 다섯 건 각각의 폐쇄 커밋 해시·승격 기록 링크를 1차 자료(`git show`, 승격 기록 본문)에서 재유도. 인덱스 행 서술을 베끼지 않는다.
2. **원문 보존** — 발행 시점 판정이 내용 손실 없이 인용으로 남았는가(바이트 대조).
3. **선례 정합** — `2e025dc`(4/4)의 모양과 어긋나는 곳.
4. **부채 서술 정정의 사실성** — *"다섯이 두 등급이었다"* 를 편집 전 상태(`a1d71fc^`)에서 재확인.
5. **HA-1 처방** — 대상이 잰 MA·MA-over 재현 + 앵커를 깨려는 자체 공격(★ 불릿 *모양* 의존이 가장 그럴듯한 구멍이라는 대상의 자기 지목).
6. **HP-1 처방** — MB·MB2 재현 + 폐쇄 전 리비전 양단 대조(갭 실재 증명) + `target_type` 단정의 실효성 + **오너 결정 D2 선점 여부**.

## Methodology

```bash
git worktree add --detach /tmp/claude-1000/wt-ha1 5a8e8c7      # 폐쇄 후
git worktree add --detach /tmp/claude-1000/wt-pre  a1d71fc     # 폐쇄 전(갭 증명용)
git worktree add --detach /tmp/claude-1000/wt-post d3ef8cd     # 이 검증의 보강 후
# 매 변이: 원본 문자열 출현 수 1 확인 → 치환 → 초점 실행 → 원문 복원 → 바이트 대조 + git status 무출력
```

승격 해시는 `git rev-parse --verify <해시>^{commit}` 로 **개별 확인**했고, 코퍼스 전체(`docs/verifications/**/*.md` 의 `` `<7~40 hex>` `` 토큰 672종)를 같은 방법으로 일괄 판정해 날짜별 해소율을 냈다.

## Findings

### 1. 승격 귀속 다섯 건 — **전부 사실이다**(해시 표기 한 축은 아래 §2)

| 기록 | 조건 | 승격 근거 기록 | 그 기록이 실제로 하는 말 | 판정 |
|---|---|---|---|---|
| `2026-09-11/landing_l2_terms_privacy.md` | LB1 | [`2026-09-12/landing_l2_promotion.md`](../2026-09-12/landing_l2_promotion.md) | Verdict **합격** · *"선행 기록 … 의 판정 조건부 합격을 합격으로 승격한다"* | ✔ |
| `2026-08-20/mypy_guard_slice.md` | B1 | [`2026-08-20/mypy_guard_closure.md`](../2026-08-20/mypy_guard_closure.md) | Verdict **합격** · *"첫 검증 기록(mypy_guard_slice.md)의 판정을 `조건부 합격` → `합격` 으로 승격한다"* | ✔ |
| `2026-08-20/embedding_adapter_slice.md` | B1 | `reranker_slice.md` §Findings 7 | *"폐쇄 세션이 자체 승격을 선언했으나 독립 재검이 없는 승격이었으므로, 이 재실행으로 승격이 확정됐다"*(V1 뒤집힘 실측) | ✔ |
| `2026-08-20/reranker_slice.md` | C1 | [`2026-08-21/reranker_c1_h1_h2_closure.md`](../2026-08-21/reranker_c1_h1_h2_closure.md) | Verdict **합격** · *"→ reranker_slice.md 의 조건부 합격을 승격 확인"* | ✔ |
| `2026-08-23/llm_key_fallback_slice.md` | B1 | 같은 기록 §사후 재검 | R1~R4 뮤테이션 양축 재실패 · 전수 `2493/4/2720` 재현 · Outstanding 의 B1 항목이 **해소로 취소선** | ✔ |

인덱스 다섯 행도 전부 판정 열 `**합격**` 이고, 본문 Verdict 섹션 선두 토큰도 다섯 다 `**합격**` 이다 — **§30 이 요구하는 "같은 말" 이 성립한다.**

### 2. ★ 폐쇄 커밋 해시 — 다섯 중 넷이 이 저장소에서 **해소되지 않는다**(선재 조건이지 위조가 아니다)

`git rev-parse --verify` 결과: `7be433e` ✔(landing_l2 — 커밋 제목 *"랜딩 ② 검증 조건 LB1 폐쇄 + H3 범위 교정"* 로 정확히 일치). `a9bca6d`·`92b9b24`·`5182cad`·`d71294a`·`b2be4ad` **전부 미해소**.

**원인을 코퍼스 전수로 갈랐다** — `docs/verifications/` 의 해시 인용을 날짜 디렉터리별로 세면 경계가 칼같다:

| 기록 날짜 | 해소되는 인용 |
|---|---|
| 2026-06-24 ~ 2026-07-05 | **65 / 66** |
| **2026-07-06 ~ 2026-08-23** | **1 / 264** |
| 2026-08-24 ~ 2026-09-13 | **269 / 272** |

경계는 2026-08-23 `git filter-repo` 이력 재작성이다([`daily_logs/2026-08-23/work_log.md`](../../daily_logs/2026-08-23/work_log.md) 세션 16 — *"★ 커밋 해시 전체가 바뀌었다 — 종전 해시 인용(검증 기록·work_log …)은 사본 번들이 원본"*). 즉 **넷은 구현 세션이 만든 오기가 아니라 대상 기록이 이미 들고 있던 재작성 전 해시**이고(편집 전 본문에서 그대로 확인), 같은 병이 코퍼스에 **377종** 있다.

다만 `a1d71fc` 가 그 해시들을 **새 머리 문장에 "…가 닫았고" 라는 단정형으로 다시 적었다**. 기존 본문의 인용을 옮긴 것이라 새 거짓은 아니지만, 해소되지 않는다는 사실은 어디에도 적히지 않았다 — 아래 Outstanding 1.

### 3. 원문 보존 — 바이트 일치

편집 전 Verdict 줄을 편집 후 인용 블록(+ 분리된 뒷문단)으로 **재조립해 문자열 비교**했다.

- `embedding_adapter_slice.md` · `reranker_slice.md`: 재조립 결과 **원문과 완전 일치**(인용부 + 공백 하나 + `**[→ 승격 …]**` 문단).
- `llm_key_fallback_slice.md`: 원문이 두 줄이었고 인용 블록도 두 줄 — 각 줄이 `"> " + 원문 줄` 로 정확히 일치. 원문 158행 꼬리의 `**[→ 승격 2026-08-23 · 판정 합격]**` 은 손실 없이 별도 줄로 옮겨졌다.
- `mypy_guard_slice.md` · `landing_l2_terms_privacy.md`: 한 줄 원문이 `"> " + 원문` 으로 그대로.

**내용 손실 0.**

### 4. `mypy_guard_slice.md` 의 *"발행 시점 문구는 그대로 둔다"* 선언 — **양립한다**

그 선언은 재검 세션이 인용 블록(`:105`) 안에 쓴 것이고, 그것이 지키려던 것은 **판정을 사후에 고쳐 쓰지 않는 것**이다(같은 파일 `:113` *"판정을 사후에 고쳐 쓰면 기록이 아니라 변명이 된다"*). 이번 편집은 발행 시점 문구를 **한 글자도 바꾸지 않고** 인용으로 보존한 채 선두 토큰만 최종 판정으로 올렸으므로, 고쳐 쓴 것이 아니라 **덧붙인 것**이다. 그리고 선례 `2e025dc` 가 4/4 로 같은 형태를 이미 확정했고, 가이드 §30 의 *"인덱스 판정 열과 Verdict 첫 줄이 같은 말을 해야 한다"* 는 선언보다 상위 규범이다. **위반 아님.**

### 5. 부채 서술 정정 *"두 등급이었다"* — **사실이다**

`a1d71fc^` 본문 grep 결과:

- `landing_l2_terms_privacy.md`: `승격` 3회 — 전부 *"승격은 다음 검증 세션이 … 판단한다"* 계열이고 **승격이 났다는 서술은 없다**. 오히려 `:93` 이 *"위 Verdict 는 **조건부 합격 그대로**"* 라고 못 박는다.
- `embedding`·`reranker`·`llm_key`: 셋 다 Verdict 줄 **같은 줄에** `**[→ 승격 YYYY-MM-DD · 판정 합격]**`.
- `mypy`: `:101` 인용 블록에 `**★ 승격 — 합격 …**`.

**정정은 정확하다** — 갈라져 있던 것은 승격 사실이 아니라 선두 토큰이었고, 사실 자체가 없던 것은 landing_l2 하나뿐이다.

### 6. ★ 선례 대비 어긋난 곳 — landing_l2 의 자기모순(이 검증이 닫음)

위 `:93` 문장이 승격 뒤에도 남아 **자기 Verdict(`**합격**`)와 정면으로 모순**한다. 편집 전에는 참이었으므로 **`a1d71fc` 가 만든 것**이다. 같은 병을 스윕해 선재 둘을 더 찾았다: [`2026-09-10/account_withdrawal_slice3_legal_effective.md:142`](../2026-09-10/account_withdrawal_slice3_legal_effective.md) · [`2026-09-11/withdrawal_slice4_screen.md:105`](../2026-09-11/withdrawal_slice4_screen.md) — 둘 다 Verdict 는 이미 합격이다. 셋 다 발행 시점 문장을 지우지 않고 `**[정정 2026-09-13 …]**` 을 이어 붙여 닫았다(`d3ef8cd`).

### 7. HA-1 — 변이 표(대상 둘 재현 + 자체 공격 여섯)

초점 `tests/test_docs_indexes.py`(기준 **20 passed / 324 subtests**). 대상 파일은 `docs/README.md` 휴면 절.

| 변이 | 적용한 diff(원문) | 폐쇄 전(`a1d71fc`) | 폐쇄 후(`5a8e8c7`) | 기명 셀 |
|---|---|---|---|---|
| **MA**(under, 대상) | ``**[`verifications/`](verifications/README.md) 의 전신이고`` → ``**앞선 관행의 전신이고`` | **20 passed — 조용** | **1 failed** | `test_the_dormant_section_says_what_the_old_name_was` |
| **MA-over**(대상) | `의 전신이고 더는 쓰지 않는다` → `의 전신이며 지금은 쓰지 않는다` | — | **20 passed** | — (수사 편집 통과) |
| **MC-1**(신규, under) | ``](verifications/README.md) 의 전신이고 더는`` → ``](verifications/README.md) 의 선행 관행이고 더는`` | **1 failed** | **1 failed** | 같은 셀 — `전신` 방향은 양쪽에서 문다 |
| **MS-1**(신규, 모양) | `- **[`verification_briefs/2026-06-24/`]` → `* **[`verification_briefs/2026-06-24/`]` | — | **1 failed** | 같은 셀 — `assertIsNotNone` 이 문다(조용하지 않다) |
| **MS-2**(신규, 모양) | 같은 행 앞에 공백 2칸 들여쓰기 | — | **1 failed** | 같은 셀 |
| **MS-3**(신규, 절 제거) | `## 휴면 디렉터리 (한 번 쓰고 멈춘 것)` → `## 한 번 쓰고 멈춘 디렉터리` | — | **1 failed** | 같은 셀(`_dormant_section` 의 `assert`) |
| **MS-5**(신규) | `의 전신이고 더는 쓰지 않는다**(이름이 닮아` → `이고 더는 쓰지 않는다**(이름이 닮아` | — | **1 failed** | 같은 셀 |
| **MS-6**(신규, 행 삭제) | `verification_briefs/2026-06-24/` 불릿 행 **전체 삭제** | **2 failed** | **2 failed** | 같은 셀 + `test_every_dormant_document_is_reachable_from_the_index` |
| **★ MS-4**(신규, 미끼) | 대상 행 **앞에** `- 참고: [`verification_briefs/`](verification_briefs/) 는 [`verifications/`](verifications/README.md) 의 전신이다.` 한 줄 삽입 + 대상 행의 지시 문장을 `**앞선 관행이고 더는 쓰지 않는다**` 로 무력화 | — | **20 passed — 조용** | **없음(사각)** |

**대상이 지목한 "불릿 모양 의존" 구멍은 없다** — MS-1·MS-2·MS-3 은 전부 `assertIsNotNone` 이 큰 소리로 잡는다(조용한 초록 아님). **실제 사각은 다른 데 있었다**: `next()` 가 고르는 것은 *"그 행"* 이 아니라 *"첫 행"* 이므로, 미끼 `- ` 행을 **앞쪽에** 끼우면 앵커가 옮겨 가고 지시받은 문장을 통째로 걷어도 조용하다(MS-4). docstring 이 *"범위는 … 행 하나다"* 라고 적은 것보다 실제 범위가 한 칸 헐겁다.

**처방(이 검증이 적용, `d3ef8cd`)**: 후보를 리스트로 모아 **정확히 하나**임을 먼저 단정한다. 재측: MS-4 **1 failed**(사각 폐쇄) · MA **1 failed** 유지 · MA-over **20 passed** 유지 · MS-1 **1 failed** 유지 — **양방향 무회귀.**

### 8. HP-1 — 변이 표(대상 둘 재현 + 갭 증명 + 자체 공격)

초점 `tests/test_activity_api.py tests/test_docs_indexes.py tests/test_repo_hygiene.py`(기준 **50 passed / 952 subtests** — 대상 보고와 일치). 대상 자리는 [`services/application/app/routers/drafts.py:652`](../../../services/application/app/routers/drafts.py).

| 변이 | 적용한 diff(원문) | 폐쇄 전(`a1d71fc`) | 폐쇄 후(`5a8e8c7`) | 기명 셀 |
|---|---|---|---|---|
| **MB**(under, 대상) | `action="draft_version_saved", target_type="draft_version",` → `action="draft_version_touched", target_type="draft_version",` | — | **2 failed** | `test_resending_the_same_save_key_still_records_a_second_row` **+** `test_saving_a_draft_version_records_who_and_when` — 분리 증명 안 됨 |
| **MB2**(under, 분리 증명, 대상) | 같은 자리를 `action=("draft_version_touched" if result.idempotent_replay else "draft_version_saved"), target_type="draft_version",` | **50 passed — 조용** | **1 failed** | `test_resending_the_same_save_key_still_records_a_second_row` **단독** |
| **MB3**(신규, `target_type` 만) | `target_type="draft_version",` → `target_type=("draft" if result.idempotent_replay else "draft_version"),` | **50 passed — 조용** | **1 failed** | 같은 셀 단독 — **`target_type` 단정은 실효다**(`action` 단정에 가려지지 않는다) |

**갭은 실재했다** — MB2·MB3 둘 다 폐쇄 전 리비전에서 **전건 초록**이고 폐쇄 후에만 문다. 양단 탈치 워크트리 실측.

**짝 셀 이름 오기(이 검증이 정정)**: docstring 이 짝으로 적은 `test_the_first_final_save_is_recorded` 는 **finalize 축**(`POST …/finalize` · `draft_finalized`)이고, 이 셀은 **수동 저장 축**(`POST …/versions` · `draft_version_saved`)이다. 같은 축의 짝은 `test_saving_a_draft_version_records_who_and_when` 이며 — 대상 자신의 MB 변이가 함께 물린 셀이 바로 그것이다. `d3ef8cd` 에서 정정했다.

### 9. ★ D2 선점 여부 — **선점하지 않는다**(그러나 오너에게 알릴 것)

재감사 §6 은 *"replay 행의 action 리터럴은 계약이 침묵하는 축"* 이라 적었고, 대상 docstring 은 *"계약이 명시적으로 요구하는 것은 행을 남기는가 와 `idempotent_replay` 둘이므로 이 단정은 하드닝이지 계약 확장이 아니다"* 라 적는다 — **두 문장은 같은 말이다**(요구되지 않는다 ⇒ 더해도 계약 확장이 아니다). 가이드는 그런 것을 정확히 "Hardening recommendation" 으로 부르고, 더하는 것을 막지 않는다.

세 층에서 확인했다: ① `draft_version_saved` 는 [`activity/actions.py:95`](../../../services/application/app/activity/actions.py) 의 **택소노미 등재 리터럴**이라 자유 문자열이 아니다. ② 같은 축 첫 저장 셀이 **이미 같은 리터럴을 핀** 하고 있다(MB 가 그 셀을 물어 실증) — 새 단정은 "replay 행이 첫 저장 행과 **같은 종류의 행**"이라는, SoT v1.8.64 *"세 갈래"* 산문과 같은 주장이다. ③ **D2 가 결정하는 것은 행의 존재 여부**이고, D2=ⓑ 면 `len(events) == before + 1` 부터 뒤집히므로 새 두 줄은 셀과 함께 사라진다 — 잠글 것이 남지 않는다.

**다만 재감사 `:189` 는 HP-1 을 *"오너 결정 D2 와 같은 자리"* 로 묶어 미뤄 두었다.** 그 묶음을 구현 세션이 단독으로 풀었으므로, D2=ⓑ 일 때 함께 뒤집힐 표면이 **두 줄 늘었다는 사실**은 오너가 알아야 한다(Outstanding 2).

### 10. 회귀·범위

- 초점 3파일: `5a8e8c7` **50 passed / 952 subtests**(대상 보고와 일치) · 현행 HEAD **50 passed / 955 subtests**.
- **문서 가드 둘 양단 실측**: `5a8e8c7` **952** → `9ccf9c7` **953**(work_log 신규 +1) → `1f4f95a` **955**(검증 기록 +1·인덱스 행 +1 = +2). **HANDOFF 기준선은 `5a8e8c7` 4229 → `1f4f95a` 4232 로 +3** — 실측 +3 과 정확히 일치한다(어긋남 없음).
- 프런트: 세 커밋 + 이 검증의 보강 모두 `frontend/` **무변**(`git diff --name-only 88a16fe..HEAD` 에 프런트 0파일).
- 백엔드 전수 미실행(공유 트리 규칙). `passed` 는 이 슬라이스 전체에서 무변이다 — 셀이 하나도 늘지 않았고(기존 셀 안의 단정만 늘었다) 양단 실측 50/50 이 그것을 확인한다.

## Issues / Risks

### Blocking (계약 의무)

**없음.** 경계 행렬에 빈 칸이 생기지 않는다 — 승격 귀속 다섯은 1차 자료에서 재유도됐고, 미수리 둘의 처방은 양방향(under 재실패 · over 초록)으로 실증됐으며, 폐쇄 전 리비전 대조로 갭의 실재까지 증명됐다.

### Hardening (비차단 — 이 검증이 닫은 것 셋은 아래 Outstanding 3)

- **선재 해시 377종 미해소**(§2). 이 슬라이스가 만든 것이 아니고 이 슬라이스 범위도 아니다. 처방 후보: `docs/verifications/README.md` 머리에 *"2026-08-23 이력 재작성 이전 기록의 커밋 해시는 현행 저장소에서 해소되지 않는다(사본 번들이 원본)"* 한 줄. **오너 결정 감** — 코퍼스 전체에 닿는 주장이라 여기서 임의로 적지 않는다.
- **다섯 기록 머리의 *"아래 본문은 발행 시점 그대로다"***. Verdict 선두 토큰은 올랐으므로 엄밀히는 반만 참이다. 다만 선례 `2e025dc` 의 네 기록이 **같은 문장**을 쓰고, 바로 다음 줄이 발행 시점 원문을 인용하므로 독자가 오독할 여지가 없다. **고치면 선례 넷과 어긋나므로 고치지 않았다** — 형식을 바꾸려면 아홉 건을 한 번에 가야 한다.
- **`mypy_guard_closure.md` 의 검증자는 첫 검증과 같은 세션**이다(그 기록 스스로 그렇게 적는다 — *"이 세션(첫 검증과 같은 세션 — 폐쇄 커밋을 만들지 않았다)"*). 다섯 중 유일하게 제3 세션이 아니다. 폐쇄 커밋을 만들지 않았으므로 독립성의 핵심은 지켜졌고 기록도 숨기지 않았다 — 서술만 남긴다.

## Verdict

**합격** — 세 축 전부 성립한다.

1. **승격 귀속 다섯 건이 전부 1차 자료에서 재유도됐다**(§1). 근거 없이 올라간 것은 **하나도 없다**. 해시 넷이 해소되지 않는 것은 2026-08-23 이력 재작성이 코퍼스에 남긴 선재 조건이고, 날짜 경계 실측(2026-07-06~08-23 구간 **1/264**, 그 뒤 **269/272**)으로 원인을 갈랐다.
2. **원문 보존이 바이트 단위로 성립**하고(§3), *"발행 시점 문구는 그대로 둔다"* 선언과도 양립하며(§4), 부채 서술 정정도 편집 전 상태에서 사실로 확인된다(§5).
3. **미수리 둘의 처방이 양방향으로 문다**(§7·§8). 대상이 잰 변이 넷을 diff 원문 그대로 전건 재현했고(건수·기명 셀까지), 폐쇄 전 리비전 대조로 **갭의 실재를 양단으로 증명**했다. `target_type` 단정도 무가드가 아니다(MB3).

**대상이 틀린 것 넷**(전부 비차단, 이 검증이 셋을 닫음): **① landing_l2 의 자기모순 문장**(§6 — `a1d71fc` 가 만들었다) · **② HA-1 docstring 의 범위 주장이 실제보다 한 칸 강하다**(§7 MS-4 — 조용한 사각이 실재했다) · **③ HP-1 docstring 의 짝 셀이 다른 축이다**(§8) · **④ 폐쇄 해시 넷을 단정형으로 다시 적으며 해소 불가를 표기하지 않았다**(§2 — 선재 조건이라 닫지 않고 Outstanding 으로).

## Outstanding items

1. **선재 해시 377종** — 오너 결정 감(위 Hardening). 코퍼스 전체 주장이라 검증자가 임의로 적지 않았다.
2. **오너 D2 알림** — HP-1 을 *"D2 와 같은 자리"* 로 묶어 둔 재감사의 배치를 구현 세션이 단독으로 풀었다. 계약 선점은 아니지만(§9), D2=ⓑ 일 때 함께 뒤집힐 줄이 둘 늘었다.
3. **이 검증이 닫은 것**(`d3ef8cd`) — MS-4 사각 폐쇄(가드) · HP-1 짝 셀 이름 정정(docstring) · 승격 뒤 거짓이 된 문장 셋 정정(기록 3파일, 발행 시점 문장은 보존하고 `**[정정 …]**` 을 이어 붙였다).
4. **다른 검증 AI 와 공유한 트리** — 검증 창 대부분에서 `activity_replay_c1_promotion_audit.md` 가 미커밋이었다. 그 파일은 읽기만 했고, 개수 주장 가드는 그 세션이 `1f4f95a` 로 커밋한 뒤 전건 초록이라 **남의 미커밋 때문에 못 잰 것은 없다.**

5. **★ HANDOFF 미수리 표가 아직 둘을 열린 채로 적고 있다** — [`HANDOFF.md:201`](../../../HANDOFF.md)(HP-1)·`:202`(HA-1) 두 행은 *"알고 있고 아직 안 고친 것"* 표에 있는데 **둘 다 `5a8e8c7` 이 닫았다**(HA-1 의 잔여 사각 MS-4 는 `d3ef8cd`). 구현 세션이 `9ccf9c7` 커밋 메시지에 *"같은 트리에 다른 검증 AI 의 미커밋 작업이 있어 HANDOFF·CHANGELOG·README·검증 인덱스는 건드리지 않았다"* 고 적었으므로 **그 세션이 아직 하려는 편집**으로 보고 검증자가 손대지 않았다. 기준선 줄만 이 기록 등재분(+2)으로 유도해 올렸다(4232 → **4234**, README 절차 표 ②행 동반 — 두 자리가 같은 수를 말해야 하는 가드 때문).

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system
git rev-parse --verify 7be433e^{commit}     # ✔  — 나머지 넷(a9bca6d·92b9b24·5182cad·d71294a·b2be4ad)은 미해소
git worktree add --detach /tmp/wt-pre  a1d71fc   # 폐쇄 전
git worktree add --detach /tmp/wt-post 5a8e8c7   # 폐쇄 후
# HA-1 / MA(under): docs/README.md 의 휴면 절 불릿에서
#   **[`verifications/`](verifications/README.md) 의 전신이고  →  **앞선 관행의 전신이고
python3 -m pytest tests/test_docs_indexes.py -q   # 폐쇄 전 20 passed · 폐쇄 후 1 failed
# HA-1 / MS-4(사각): 같은 불릿 **앞에** 두 낱말을 다 가진 `- ` 행 하나를 끼우고 대상 문장을 무력화
#   → 보강 전 20 passed(조용) · 보강 후(d3ef8cd) 1 failed
# HP-1 / MB2: routers/drafts.py:652 의 action= 을
#   action=("draft_version_touched" if result.idempotent_replay else "draft_version_saved"),
python3 -m pytest tests/test_activity_api.py tests/test_docs_indexes.py tests/test_repo_hygiene.py -q
#   → 폐쇄 전 50 passed · 폐쇄 후 1 failed(test_resending_the_same_save_key_still_records_a_second_row)
# HP-1 / MB3: 같은 자리의 target_type 만 replay 경로에서 "draft" 로 → 같은 결과(단정 실효)
# 매 변이: 탈치 워크트리에서만. 복원 후 파일 바이트 대조 + git status --short 무출력.
git worktree remove --force /tmp/wt-pre && git worktree remove --force /tmp/wt-post
```
