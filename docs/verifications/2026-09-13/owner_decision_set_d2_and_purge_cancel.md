# 오너 결정 셋 시행 독립 검증 — 활동 로그 D2=ⓑ · 파기 청구 뒤 탈퇴 취소 거부(ⓐ) · 기록

**합격** — 조건 **C1** 은 폐쇄 커밋 `867ba15`(이 검증 세션 자신의 폐쇄)이 닫았고, 승격 재검([`owner_decision_set_promotion.md`](owner_decision_set_promotion.md) — 변이 재적용 다섯 종 전건 일치)이 판정을 올렸다. 아래 본문은 발행 시점 그대로다.

## Subject metadata

| 항목 | 값 |
|---|---|
| 날짜 | 2026-09-13 |
| 요청자 | 오너(구현 세션 경유 — *"적대적으로 검증하고, 보강할 곳이 있으면 직접 보강까지"*) |
| 검증자 | 독립 세션(세션 79). **구현 세션 78 과 다른 세션**이고 대상 커밋을 한 줄도 쓰지 않았다 |
| 대상 | `267ba22`(활동 로그 D2=ⓑ) · `463a042`(파기 청구 뒤 취소 409) · `d9a1bd2`(기록 — SoT v1.8.66 · 옛 해시 주석 · HANDOFF 표) |
| 정본 스펙 | [`../../system-contract-sot.md`](../../system-contract-sot.md) **v1.8.66** · 브리프 [`../../plans/activity-log-replay-and-partial-decisions.md`](../../plans/activity-log-replay-and-partial-decisions.md) §D2 · [`../../plans/slice5-withdrawal-cancel-after-purge-claim-decisions.md`](../../plans/slice5-withdrawal-cancel-after-purge-claim-decisions.md) · 정책 [`../../service-policy-contract.md`](../../service-policy-contract.md) §6 |
| 출처 | 커밋(전부 `main`). 검증 착수 시 트리 clean |
| 보강 커밋 | `867ba15`(코드+셀+브리프) · 이 기록과 기록 갱신 커밋 |

## Scope

1. **★ 활동 로그 D2=ⓑ 의 경계 행렬** — 계약이 열거한 replay 표면이 **전부** 행위 셀을 갖는가, 그 셀이 실제로 무는가(양방향).
2. **★ 502 partial 경로를 안 건드린 판단이 옳은가** — D3=ⓐ 가 그 자리를 정말 덮는가. replay 가 그 분기에 도달할 수 있는가.
3. `result.idempotent_replay` 가 accept 결과에 실재하고 replay 를 정확히 가리키는가.
4. 특성 셀 둘을 뒤집으며 **잃은 커버리지**가 있는가(HP-1 하드닝의 `action`·`target_type` 축).
5. **파기 청구 뒤 취소 거부** — 양방향(막힌다/청구 전은 여전히 200) · 거부가 아무것도 되돌리지 않는가 · 파기 완료 계정 · 경계가 `purge_started_at` 하나로 충분한가 · 선언(`responses=`)·tier 가드 정합 · 유예 중 쓰기 차단(403)과의 충돌.
6. **기록** — SoT v1.8.66 리터럴(operation 107 · 공개 계약면) · 옛 해시 수치의 독립 재현 · 브리프 상태 줄 ↔ `plans/README.md` 상태 열 · 정책 §6 · legal 대조표.
7. 회귀 — 초점 + **백엔드 전수**(코드가 바뀌었으므로 유도 금지) · 프런트 무변 확인.

## Methodology

- 1차 소스는 `git show <sha>` 와 현행 파일. 구현자 보고·work_log 는 **가설로만** 받았다.
- **변이는 전부 탈치 워크트리**에서 돌렸다 — `git worktree add --detach /tmp/claude-1000/vsess-wt <리비전>` → 변이 → 초점 실행 → `git checkout -- <경로>`(워크트리 안) → `git status --short` 공백 확인. **본 트리에는 `checkout`·`restore`·`stash`·`reset` 을 한 번도 쓰지 않았다**(같은 트리에서 다른 세션이 돌 수 있는 창).
- 변이 적용은 `pathlib.write_text` 기반 헬퍼로 하고 **치환 횟수가 정확히 1 임을 단정**했다(`sed -i`·`perl -i` 는 이 저장소에서 파일을 손상시킨 적이 있어 금지).
- 결과는 **요약 줄의 건수**로 읽었다(`grep FAILED` 는 `SUBFAILED` 를 놓친다 — 가이드 §★).
- 환경: 호스트 pytest · `docker-compose.test.yml` 의 `test-mongo`(mongo:7, 단일 노드 replica set `rs-test`, 포트 27020) **healthy = writable PRIMARY 확인 후** 전수 착수(`db.hello().isWritablePrimary` → `true`). 프로젝트 `.env` 존재(30줄) — 중화하지 않았고 compose 가 그대로 읽었다.

## Findings

### 1. ★ 활동 로그 D2=ⓑ — 열거된 세 경로는 전부 무는 셀을 갖는다 (무셀 0)

세 경로 각각을 **개별적으로** 벗겨 어느 셀이 무는지 기명 확인했다. 전부 under·over 양방향이 있다.

| 경로 | 배선 | under 셀 | over 셀 |
|---|---|---|---|
| `drafts/{id}/finalize` | [`routers/drafts.py:713`](../../../services/application/app/routers/drafts.py#L713) | `test_activity_api.py::ActivityRecordingTest::test_resending_the_same_final_save_key_leaves_no_second_row` | `…::test_the_first_final_save_is_recorded` |
| `writing/accept`(성공) | [`routers/writing.py`](../../../services/application/app/routers/writing.py) 성공 분기 | `test_writing_accept.py::WritingAcceptApiTest::test_resending_the_same_accept_key_leaves_no_second_row` | `…::test_a_saved_accept_is_recorded_in_the_activity_log` |
| `drafts/{id}/versions`(수동 저장) | [`routers/drafts.py:656`](../../../services/application/app/routers/drafts.py#L656) | `test_activity_api.py::ActivityRecordingTest::test_resending_the_same_save_key_leaves_no_second_row` | `…::test_saving_a_draft_version_records_who_and_when` |

변이 M1~M6 (§변이 표). **하나도 등가 변이가 아니었고 하나도 다른 셀이 대신 받지 않았다** — 각 변이가 정확히 1셀만 실패시켰으므로 세 경로가 **분리 소유**된다.

### 2. ★★ Blocking C1 — 계약이 열거한 **넷째 표면**(accept 502 partial)이 무셀이었고, D3 귀속은 오귀속이다

구현자 주장: *"502 partial 경로(`WritingAcceptAnalysisError` → `exc.saved`)는 D3=ⓐ 로 별개 축이라 건드리지 않았다"*(커밋 메시지 · 라우터 주석 · SoT v1.8.66 · 브리프 §D2 결정 — **네 자리에 같은 주장**). **이 주장은 성립하지 않는다.**

**(a) D3 은 다른 endpoint 의 축이다.** 브리프 §D3 원문: *"`POST …/analysis/jobs/{id}/auto-promote` 는 후보를 하나씩 승격하는데 **트랜잭션이 없다** … 그때 … **활동 로그에는 한 행도 안 남는다**"*. D3 의 선택지 ⓐ·ⓑ·ⓒ 는 전부 auto-promote 의 **503** partial 을 다루고, 문제의 형태도 **침묵**(행이 0)이지 **중복**이 아니다. `writing/accept` 의 502 는 다른 경로·다른 상태코드·반대 증상이다.

**(b) 반대로 D2 는 이 표면을 명시적으로 열거했다.** 브리프 §D2 첫 문장: *"실측(검증자 프로브): `writing/accept`(성공)·**`writing/accept`(502 partial)**·`drafts/{id}/versions` 셋 다 3회 POST → **이벤트 3건 / 대상 1개**"*. 즉 오너가 ⓑ 로 답한 D2 의 실측 근거 **셋 중 하나가 바로 이 자리**다. 시행이 그 자리를 빠뜨렸다.

**(c) 도달 가능하고, 실제로 중복이 남았다.** `WritingAcceptService.accept` 는 replay 를 만나면 `_finalize(..., replay=True)` 로 들어가고([`writing/accept.py:139-142`](../../../services/application/app/writing/accept.py#L139)), `_finalize` 는 **replay 여부와 무관하게** `_create_job` 을 부르며 그것이 실패하면 `WritingAcceptAnalysisError` 를 낸다([`accept.py:249-258`](../../../services/application/app/writing/accept.py#L249)). 기존 셀 `test_partial_failure_is_502_and_retry_converges` 자체가 *"실패한 키를 다시 보내도 502 로 같은 version 에 수렴한다"* 를 이미 잠그고 있어 **도달성은 계약이 이미 인정한 것**이다.

폐쇄 전 실측(검증 프로브 — 실패 분석 주입 + 같은 키 2회 POST):

```
first : 502 rows= 1
replay: 502 rows= 2
same saved version id: True
actions: ['draft_version_accepted', 'draft_version_accepted']
target_ids distinct: 1
```

**저장된 version 1개에 활동 행 2건** — ⓑ 가 없애려던 바로 그 중복이다. 그리고 이 자리는 **정본이 바뀌지 않았다**(같은 `draft_version.id`)이므로 502 분기가 근거로 삼는 A7=A(*"상태코드가 아니라 정본이 바뀌었는가로 기록한다"*)의 기록 조건 자체가 서지 않는다 — D2=ⓑ 와 A7=A 는 여기서 충돌하지 않고 **같은 답**을 말한다.

**왜 차단인가.** SoT v1.8.66·브리프·CHANGELOG 가 *"replay 는 활동 행을 안 남긴다(세 경로가 한 답)"* 를 **계약으로 새로 적었는데** 코드에는 한 표면이 반대로 남아 있었다. 산문으로만 적힌 replay 처분 주장이 한 달 동안 틀려 있던 것이 **이 슬라이스 계열의 발원**이고(§착수가 반증한 것), 같은 병을 같은 자리에 다시 심은 셈이다. 가이드 §*"boundary matrix has no empty cells"* 가 정확히 이 형태를 차단으로 규정한다.

**폐쇄**(`867ba15`): 502 분기의 `activity.record` 를 `if not exc.saved.idempotent_replay:` 로 감싸고, 신규 under 셀 `test_a_replayed_partial_accept_leaves_no_second_row` 를 세웠다(over 짝은 기존 `test_a_partial_accept_still_records_the_saved_version`). 변이 M14·M15 로 양방향 실효 확인. 브리프 §D2 결정 표를 **네 행**으로 고치고 오귀속에 표식을 달았다(원문은 이력이라 보존).

★ **왜 이 자리가 오너 결정이 아니라 시행 누락인가**: D2 의 선택지는 *"replay 가 행을 남기는가"* 하나이고 오너가 ⓑ 로 답했다. 이 표면은 **그 D2 의 실측 근거로 브리프에 이미 열거된 자리**이므로 새 갈래가 아니라 같은 결정의 미시행분이다(HANDOFF `d9a1bd2` 가 세운 규칙 — *"브리프에 추천이 있고 기존 결정의 뜻을 잇는 것이면 묻지 말고 진행한다"*). 다만 **구현자가 명시적으로 반대 판단을 적었으므로** 이 판단 자체를 오너가 볼 수 있게 §Outstanding 에 올린다.

### 3. `result.idempotent_replay` 는 replay 를 정확히 가리킨다

- `WritingAcceptResult.idempotent_replay` 는 실재한다([`accept.py:83`](../../../services/application/app/writing/accept.py#L83)) — 기본값 `False`.
- replay 경로는 전부 `_replay()` → `_save_result()` 를 지나고, 그것이 `SaveDraftResult(…, True)` 를 돌려준다([`accept.py:281-282`](../../../services/application/app/writing/accept.py#L281)). **두 intent(append·start_next) 모두** 그렇고, `DuplicateWritingAcceptReceipt` 경합 수렴 분기도 `replay=True` 로 `_finalize` 를 부른다. 그래서 `exc.saved.idempotent_replay` 도 502 분기에서 정확하다(§2 폐쇄가 그것에 기댄다).
- **409 로 막힌 경우와 구분되는가**: 세 under 셀 중 200 을 내는 둘(finalize·수동 저장·accept 성공)은 응답의 `idempotent_replay: true` 를 함께 단정하므로 구분된다. 502 경로는 envelope 이 그 키를 싣지 않아 신규 셀이 **`saved.draft_version_id` 동일**을 대신 단정한다(공개 신호로는 그것뿐이다 — 근거는 셀 docstring).

### 4. 특성 셀 둘을 뒤집으며 잃은 커버리지는 없다 — 구현자 주장이 변이로 성립한다

구현자 주장: *"HP-1 로 더한 `action`·`target_type` 단정은 replay 행 자체가 사라져 함께 걷혔고, 그 축은 over-strict 짝 `test_saving_a_draft_version_records_who_and_when` 이 계속 잠근다."* — **변이로 반증을 시도했고 실패했다**(주장이 맞다).

- M7: 수동 저장 경로의 `action="draft_version_saved"` → `"draft_finalized"` → **1 failed**, 기명 `test_saving_a_draft_version_records_who_and_when`.
- M8: 같은 자리의 `target_type="draft_version"` → `"draft"` → **1 failed**, 같은 셀.

두 축 모두 살아 있다. 또한 replay 방향의 단정이 **개수뿐**인 것은 이제 장님이 아니다 — 기대값이 *"행이 늘지 않음"* 이므로 replay 가 **어떤** 행을 남기든(엉뚱한 action 포함) 개수가 올라가 잡힌다. HP-1 이 닫았던 사각(행이 있는데 정체를 안 봄)은 D2=ⓑ 로 구조적으로 사라졌다.

### 5. 파기 청구 뒤 취소 거부 — 양방향 성립, 되돌림 없음, 경계 충분

- **under**: 경계를 벗기면(M9) 3셀 재실패 — 서비스 2 + HTTP 1.
- **over(더 나쁜 결함 방향)**: 항상 거부로 바꾸면(M10) **6셀 재실패**. 그중 `test_cancelling_removes_every_grace_period_restriction`·`test_cancelling_returns_the_account_to_never_having_asked`·`test_cancelling_clears_the_stamp` 이 *"청구 전 취소는 여전히 200 이고 제한이 전부 풀린다"* 를 직접 든다. **회원이 유예 중에 되돌릴 수 없게 되는 사고는 여섯 겹으로 막혀 있다.**
- **거부가 아무것도 되돌리지 않는가**: M12(거부 직전에 유예 스탬프를 지우는 과잉 교정)가 2셀 재실패 — `test_the_refused_cancel_leaves_both_stamps_intact`(서비스) + `test_cancelling_after_the_purge_was_claimed_is_409`(HTTP over-strict 짝). 파기 표식 존치는 같은 셀이 `purge_started_at == _FIXED_TIME` 으로 단정한다(SoT v1.8.52 의 계약 — 표식은 reconciler 의 유일한 단서).
- **파기가 끝난 계정(행 없음)**: `cancel_withdrawal` 의 검사 순서는 `stored is None → UserNotFound` **먼저**, 그 다음 `withdrawal_requested_at is None`, 마지막이 새 `purge_started_at` 검사다([`auth/users.py:538-574`](../../../services/application/app/auth/users.py#L538)). **409 로 바뀌지 않았다.** 어느 문서도 이 경우에 404 를 약속하지 않는다(정책 §6 은 *"되살릴 수 없다(행이 없다)"* 까지만 적고, 실제로는 세션이 함께 사라져 401 이 먼저 온다) — 이 결정이 건드린 축이 아니다.
- **경계가 `purge_started_at` 하나로 충분한가 (브리프 §Follow-up 의 물음) — 충분하다.** `claim_for_purge` 가 표식의 **유일한 writer** 이고, 파기 그래프의 **1단계**다([`deletion/account_purge.py:135`](../../../services/application/app/deletion/account_purge.py#L135) — 머리말의 순서 1~5 중 청구가 첫째, 사용자명 묘비가 둘째). **표식이 찍히기 전에는 아무것도 파괴되지 않는다.** 따라서 "파괴가 시작됐는가"와 "표식이 있는가"는 동치이고 둘째 조건이 필요 없다.
- **선언 정합**: `_ERRORS_WITHDRAWAL` 이 이미 `409` 를 담고 있어([`api/errors.py:242`](../../../services/application/app/api/errors.py#L242)) **선언 누락은 없다**. 경계 셀 `test_no_withdrawal_operation_declares_a_403` 이 `/me/withdrawal` 의 모든 method 에 대해 401·409 존재 + 403 부재를 subTest 로 잠근다. M11(라우터 매핑에서 신규 예외를 뺌)은 1셀 재실패로 HTTP 얼굴이 잠겨 있음을 확인.
  - **다만 그 선언의 주석이 거짓이 됐다** — *"409 는 **두 생산자**를 갖는다"* 인데 이제 셋이다. 이 저장소가 가장 싫어하는 *산문이 코드보다 낡은 자리*라 `867ba15` 가 셋으로 정정했다(선언 자체는 무변).
- **유예 중 쓰기 차단(403)과 충돌하지 않는다**: `/me/withdrawal` 의 POST·DELETE 는 `_REQUIRE_AUTH_DURING_WITHDRAWAL`(인증만)을 쓰고, `test_every_protected_operation_declares_the_grace_period_guard` 가 그 둘을 **명시 예외 집합**으로 두고 `seen_exemptions == exemptions` 까지 단정한다(예외가 조용히 늘거나 줄면 실패). 거부는 서비스 층에서 나므로 이 축과 독립이다.

### 6. 기록

- **operation 107 무변 · 공개 계약면 무변** — 독립 재계산: 제품 앱의 `APIRoute` × method 조합 **107**. 새 상태코드 0(409 는 기존 선언). 프런트 무변(`git diff --stat 55bfda3..HEAD -- frontend/` **무차분**).
- **브리프 둘 상태 줄 ↔ `plans/README.md` 상태 열** — 두 쌍 다 문자열 동일. ✔
- **정책 §6** — 새 문장의 주장 넷을 코드로 각각 확인: 409 ✔ · 스탬프 둘 존치 ✔ · *"파기가 실패해 표식만 남은 계정도 같은 답"* ✔(표식 유무만 보므로) · *"파기가 끝난 계정은 되살릴 수 없다(행이 없다)"* ✔.
- **legal 대조표의 새 `미기재` 행** — 약관 제8조 3항 원문은 *"30일 이내에는 탈퇴를 취소할 수 있습니다"* 로 끝나고 경계 조건이 **없다**([`legal/terms-of-service-draft.md:61`](../../legal/terms-of-service-draft.md)). 방침 제5조 3항도 동일([`legal/privacy-policy-draft.md:50`](../../legal/privacy-policy-draft.md)). **`미기재` 는 정확하다.**
- **SoT v1.8.66 의 근거 링크가 틀렸다(H1 — 정정함)**: 행 끝이 `daily_logs/2026-09-13/work_log.md` **세션 76** 을 가리키는데, 세션 76 은 *다른 슬라이스*(승격 기록 선재 5건 + HA-1·HP-1 폐쇄)이고 이 슬라이스의 work_log 절은 **세션 78** 이다(CHANGELOG 는 78 로 맞게 적었다). 출처 포인터가 엉뚱한 곳을 가리키면 다음 독자가 근거를 못 찾는다.
- **★ 옛 해시 수치는 독립 재현되지 않았다(H2)** — §Hardening 참조. 질적 주장(경계가 2026-08-23 재작성에서 칼같이 갈린다)은 **정확히 재현**됐다.

## Issues / Risks

### Blocking (계약 의무)

- **C1 — 활동 로그 D2=ⓑ 가 `writing/accept` 502 partial 표면에 시행되지 않았다**(§2). 브리프 §D2 가 실측 근거로 열거한 세 표면 중 하나이고, D3=ⓐ 귀속은 **다른 endpoint 의 축**을 잘못 가져다 쓴 것이다. 폐쇄 전 실측 = 같은 키 2회 → **저장 version 1개 / 활동 행 2건**. 계약 문장(*"세 경로가 한 답"*·*"replay 는 행을 안 남긴다"*)이 코드에서 거짓이었다.
  **→ 이 검증이 `867ba15` 로 닫았다**(배선 + under 셀 신설 + 브리프 정정 · 변이 M14·M15 양방향 확인). **판정 승격은 이 기록이 하지 않는다** — 조건을 닫은 세션이 자기 판정을 올리면 독립성이 사라진다(v1.8.52·v1.8.63 선례).

### Hardening (비차단)

- **H1 — SoT v1.8.66 근거 링크의 세션 번호 오기**(76 → 78). 이 검증이 정정했다.
- **H2 — 옛 해시 주석의 *구간별 수치* 가 재현되지 않는다.** `docs/verifications/README.md` 머리와 HANDOFF 함정 절이 **둘 다** *"2026-07-06~08-23 은 264개 중 1개, 08-24 이후는 272개 중 269개"* 로 적는데, 원 측정 기록이 스스로 밝힌 방법(*"`docs/verifications/**/*.md` 의 `` `<7~40 hex>` `` 토큰"*)으로 재측정하면 값이 다르다:

  | 구간 | 발행된 값 | 이 검증의 재측정 |
  |---|---|---|
  | 2026-06-24~07-05 | 65 / 66 | **69 / 70** |
  | **2026-07-06~08-23** | **1 / 264** | **1 / 371** |
  | 2026-08-24~ | 269 / 272 | **229 / 239** |
  | 미해소 총계 | 377종 | **376종** |

  두 리비전(`3681d77`·`d9a1bd2`)에서 같은 값이 나와 코퍼스 드리프트가 원인이 아니다. **분자 `1` 과 경계의 날카로움은 정확히 재현**되고 총계도 1 차이라 **질적 주장은 성립**하지만, 분모는 어떤 변형(백틱 7~12 hex · 정확히 7자 · 백틱 없는 토큰)으로도 맞출 수 없었다. 원인은 발행된 두 자리 **어디에도 유도 명령이 없다**는 것이다 — 가이드 §*"Recording a measurement"* 가 정확히 금지하는 형태(*"숫자는 맞는데 라벨이 불완전하고, 그 틈이 다음 독자에게 안 보인다"*). **처방: 두 자리에 유도 명령 한 줄을 붙이거나, 방법을 고정해 수치를 재측정해 맞춘다.** 이 검증은 수치를 임의로 바꾸지 않고 **유도 명령과 재측정값을 병기**했다 — 발행값은 오너 결정 ⓒ 로 들어간 문장이라 지우지 않는다.
- **H3 — `_ERRORS_WITHDRAWAL` 주석의 생산자 수**(두 → 셋). 이 검증이 정정했다(`867ba15`).

- **★ H4 — 패턴 스윕이 *다섯째* 표면을 찾았다: `PUT /projects/{id}/brief`**(`routers/projects.py:211`). 응답이 `idempotent_replay` 를 싣는데([`routers/projects.py:218`](../../../services/application/app/routers/projects.py#L218)) `activity.record` 는 **무조건** 돈다 — D2=ⓑ 가 고친 수동 저장 경로와 **글자 그대로 같은 모양**이다. 검증 프로브 실측:

  ```
  first : 200 idempotent_replay=False rows=2
  replay: 200 idempotent_replay=True  rows=3   ← +1 (project_brief_saved 2건)
  ```

  `git blame` → `d422bc4`(2026-08-09, *"서비스 활동 로그 — 저장·배선·조회 Phase 9 Slice 9.0"*) — **의도적 이탈이 아니라 D1·D2 이전의 기본값**이 그대로 남은 것이다.

  **왜 이 검증이 고치지 않았는가**: §2(C1)의 502 표면은 **브리프 §D2 의 실측표가 명시 열거**했고 구현자가 그 축을 *다뤘다고 주장* 한 자리라 미시행분이 분명했다. 이 자리는 **어느 브리프도 열거한 적이 없다** — D2 의 뜻(*"재전송이 타임라인을 두 번 채우지 않는다"*)은 문자 그대로 여기에도 닿지만, 열거되지 않은 표면까지 검증자가 넓히는 것은 **오너 결정의 범위를 대신 늘리는 것**이다. 부채로 등재하고 오너에게 올린다(§Outstanding 4). 고치는 비용은 **한 줄 + 행위 셀 한 쌍**으로 D2 시행과 같다.

## Verdict

**합격**(승격 — 2026-09-13 승격 재검 [`owner_decision_set_promotion.md`](owner_decision_set_promotion.md) 이 변이 재적용 다섯 종 전건 일치로 조건 폐쇄를 확증). 발행 시점 판정 원문:

> **조건부 합격** — 조건 **C1**: 활동 로그 D2=ⓑ 가 계약이 열거한 넷째 표면(`writing/accept` 502 partial)에 시행되지 않아 replay 가 활동 행을 2건 남겼고, 그 자리를 D3=ⓐ 로 돌린 것은 **다른 endpoint 의 축을 가져온 오귀속**이다. **이 검증이 `867ba15` 로 닫았으므로 조건은 해소 상태이며, 합격 승격은 다음 독립 세션의 변이 재적용 몫이다.**

받치는 이유:

1. **열거된 세 경로는 흠이 없다** — 여섯 변이(M1~M6)가 전부 **정확히 1셀씩** 기명 재실패해 세 경로가 분리 소유됨이 실증됐다. 무셀도, 한 셀이 여럿을 흡수하는 자리도 없었다.
2. **파기 청구 뒤 취소 거부는 양방향으로 단단하다** — 특히 *더 나쁜 결함* 인 over 방향(유예 중 취소가 막히는 사고)이 **6셀**로 막혀 있고, 거부가 스탬프를 되돌리지 않는 것과 파기 완료 계정이 이 결정에 안 걸리는 것까지 확인됐다. 경계 `purge_started_at` 하나로 충분함을 파기 그래프 1단계에서 유도했다.
3. **막은 것은 단 하나, 계약이 새로 적은 문장이 코드에서 거짓이었던 자리다.** 그리고 그것은 이 슬라이스 계열이 태어난 이유와 **같은 병**이라 비차단으로 내릴 수 없었다.
4. 기록 축의 리터럴(operation 107 · 공개 계약면 · 상태 줄 정합 · legal `미기재`)은 전부 1차 소스에서 재유도돼 성립했고, 틀린 것은 근거 링크 하나(H1)와 재현 안 되는 수치(H2)다.

## Outstanding items

1. **★ 오너가 볼 것 — 구현자의 명시적 반대 판단을 이 검증이 뒤집었다.** 구현자는 네 자리에 *"502 partial 은 D3=ⓐ 로 별개 축"* 이라고 적었고, 이 검증은 그것을 오귀속으로 판정해 **D2=ⓑ 를 그 자리까지 시행**했다. 근거는 §2 (a)(b)(c) 다. 오너가 *"502 partial 은 그래도 replay 에도 행을 남겨라"* 로 보신다면 되돌릴 곳은 `867ba15` 한 커밋이다.
2. **H2 의 발행 수치** — 유도 명령을 붙였지만 **발행된 분모 셋은 여전히 재현되지 않는다.** 원 측정을 한 세션(세션 76)만이 자기 분류 규칙을 안다. 수치를 재측정값으로 교체할지는 기록 정정 정책이 걸린 자리라 오너/후속 세션 몫으로 남긴다.
3. **★ 오너 결정 감 — D2=ⓑ 를 *열거되지 않은* 표면까지 넓히는가**(H4). `PUT /projects/{id}/brief` 가 같은 키 재전송에 `project_brief_saved` 를 2건 남긴다(실측). 갈래 둘 — **ⓐ 넓힌다**(라우터 한 줄 + 행위 셀 한 쌍 · 규칙이 진짜로 하나가 된다 · D2 의 뜻 그대로) · **ⓑ 열거된 넷으로 둔다**(비용 0 · 다만 같은 개념에 답이 다시 둘이 된다 — 이번 슬라이스가 없애려던 상태). **구현자 추천은 ⓐ** 지만, 브리프가 열거한 적 없는 축이라 검증자가 임의로 시행하지 않았다. ※ `analysis.py` 의 나머지 `activity.record` 자리들은 확인 결과 **멱등 키가 없거나**(후보 승격·확정·거부·편집은 상태 전이라 재전송이 409 로 걸린다) **이미 분기가 있다**(`analysis.py:497`·`analysis.py:994`) — 스윕에서 나온 실제 구멍은 이 하나다.
4. 검증 기록 313 → **314건**.

## Reproduction

```bash
# 1) 대상 확인
git show 267ba22 463a042 d9a1bd2 867ba15

# 2) 폐쇄 전 502 partial replay 실측(867ba15^ 에서)
git worktree add --detach /tmp/wt d9a1bd2 && cd /tmp/wt
PYTHONPATH=$PWD python3 - <<'PY'
import asyncio
from tests.test_writing_accept import WritingAcceptApiTest, _FailingAnalysis
from services.application.app.analysis.service import InMemoryAnalysisRepository
from services.application.app.activity.log import InMemoryActivityLogRepository
class P(WritingAcceptApiTest):
    def runTest(self): pass
p=P(); repo=InMemoryActivityLogRepository()
c,pr,d,b,_=p._setup(analysis=_FailingAnalysis(InMemoryAnalysisRepository()),activity_repo=repo)
r1=p._post(c,pr,d,b.draft_version.id); print(r1.status_code,len(repo.events))
r2=p._post(c,pr,d,b.draft_version.id); print(r2.status_code,len(repo.events))
asyncio.run(c.aclose())
PY
# → 502 1 / 502 2   (폐쇄 후 867ba15 에서는 502 1 / 502 1)

# 3) 변이(전부 탈치 워크트리에서, §변이 표의 diff 그대로)
#    복원은 워크트리 안에서 git checkout -- <경로> 후 git status --short 공백 확인

# 4) 옛 해시 수치 재현
python3 - <<'PY'
import re,pathlib,subprocess,collections
pat=re.compile(r'`([0-9a-f]{7,40})`'); seen=collections.defaultdict(set)
for f in sorted(pathlib.Path("docs/verifications").rglob("*.md")):
    parts=f.relative_to("docs/verifications").parts
    if len(parts)<2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",parts[0]): continue
    b="a" if parts[0]<="2026-07-05" else ("b" if parts[0]<="2026-08-23" else "c")
    seen[b].update(pat.findall(f.read_text(encoding="utf-8")))
for b in "abc":
    ok=sum(1 for h in seen[b] if subprocess.run(["git","cat-file","-e",h+"^{commit}"],capture_output=True).returncode==0)
    print(b,ok,"/",len(seen[b]))
PY

# 5) 회귀
python3 -m pytest tests/test_activity_api.py tests/test_writing_accept.py \
  tests/test_auth_users.py tests/test_auth_api.py tests/test_service_policy_contract.py \
  tests/test_docs_indexes.py tests/test_repo_hygiene.py -q
docker compose -f docker-compose.test.yml up -d   # healthy = writable PRIMARY 확인 후
python3 -m pytest -q
```

## 변이 표 — diff 원문 · 실패 건수 · 기명 셀

패러프레이즈 없이 적용한 치환을 그대로 적는다. 전부 **치환 횟수 1** 을 단정하고 적용했다.

| # | 파일 | 적용한 diff(원문) | 결과 | 문 셀(기명) |
|---|---|---|---|---|
| **M1** | `routers/drafts.py` | `if not result.idempotent_replay:` → `if True:` | **1 failed** / 76 passed / 19 subtests | `test_activity_api.py::ActivityRecordingTest::test_resending_the_same_save_key_leaves_no_second_row` |
| **M2** | `routers/drafts.py` | `if not result.idempotent_replay:` → `if False:` | **1 failed** / 76 passed | `test_activity_api.py::ActivityRecordingTest::test_saving_a_draft_version_records_who_and_when` |
| **M3** | `routers/writing.py` | `if result.saved is not None and not result.idempotent_replay:` → `if result.saved is not None:` | **1 failed** / 76 passed | `test_writing_accept.py::WritingAcceptApiTest::test_resending_the_same_accept_key_leaves_no_second_row` |
| **M4** | `routers/writing.py` | 같은 줄 → `if False:` | **1 failed** / 76 passed | `test_writing_accept.py::WritingAcceptApiTest::test_a_saved_accept_is_recorded_in_the_activity_log` |
| **M5** | `routers/drafts.py` | `if not finalized.idempotent_replay:\n            activity.record(` → `if True:\n            activity.record(` | **1 failed** / 20 passed | `test_activity_api.py::ActivityRecordingTest::test_resending_the_same_final_save_key_leaves_no_second_row` |
| **M6** | `routers/drafts.py` | 같은 자리 → `if False:\n            activity.record(` | **1 failed** / 20 passed | `test_activity_api.py::ActivityRecordingTest::test_the_first_final_save_is_recorded` |
| **M7** | `routers/drafts.py` | 저장 경로의 `action="draft_version_saved"` → `action="draft_finalized"` | **1 failed** / 76 passed | `test_activity_api.py::ActivityRecordingTest::test_saving_a_draft_version_records_who_and_when` |
| **M8** | `routers/drafts.py` | 저장 경로의 `target_type="draft_version"` → `target_type="draft"` | **1 failed** / 76 passed | 같은 셀 |
| **M9** | `auth/users.py` | `if stored.purge_started_at is not None:` → `if False:` | **3 failed** / 222 passed / 1222 subtests | `test_auth_users.py::WithdrawalCancelAfterPurgeClaimTest::test_cancelling_is_refused_after_the_purge_was_claimed` · `…::test_the_refused_cancel_leaves_both_stamps_intact` · `test_auth_api.py::SelfWithdrawalApiTest::test_cancelling_after_the_purge_was_claimed_is_409` |
| **M10** | `auth/users.py` | 같은 줄 → `if True:` | **6 failed** / 219 passed | `test_auth_users.py::WithdrawalStateAxisTest::test_a_cancelled_account_is_indistinguishable_from_one_that_never_asked` · `…::test_cancelling_clears_the_stamp` · `…::test_cancelling_then_requesting_again_starts_a_new_grace_period` · `test_auth_api.py::SelfWithdrawalApiTest::test_a_withdrawing_member_can_sign_in_again` · `…::test_cancelling_removes_every_grace_period_restriction` · `…::test_cancelling_returns_the_account_to_never_having_asked` |
| **M11** | `routers/auth.py` | `except (WithdrawalNotRequested, WithdrawalPurgeAlreadyClaimed) as exc:` → `except (WithdrawalNotRequested,) as exc:` | **1 failed** / 224 passed | `test_auth_api.py::SelfWithdrawalApiTest::test_cancelling_after_the_purge_was_claimed_is_409` |
| **M12** | `auth/users.py` | 거부 직전에 `self._repo.set_withdrawal_requested_at(user_id, at=None)` **한 줄 삽입**(제거가 아니라 삽입 — 과잉 교정 방향) | **2 failed** / 223 passed | `test_auth_users.py::WithdrawalCancelAfterPurgeClaimTest::test_the_refused_cancel_leaves_both_stamps_intact` · `test_auth_api.py::SelfWithdrawalApiTest::test_cancelling_after_the_purge_was_claimed_is_409` |
| **M14** | `routers/writing.py`(폐쇄 후 `867ba15`) | `if not exc.saved.idempotent_replay:` → `if True:` | **1 failed** / 87 passed / 113 subtests | `test_writing_accept.py::WritingAcceptApiTest::test_a_replayed_partial_accept_leaves_no_second_row` |
| **M15** | `routers/writing.py`(폐쇄 후) | 같은 줄 → `if False:` | **1 failed** / 87 passed | `test_writing_accept.py::WritingAcceptApiTest::test_a_partial_accept_still_records_the_saved_version` |

**등가 변이 0 · 흡수 0.** 모든 변이가 자기 축의 셀만 물었고, 복원 뒤 워크트리 `git status --short` 는 매번 공백이었다.
