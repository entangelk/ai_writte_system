# 2026-09-10 work log

## 세션 50 — 세션 49 산출물 독립 검증 (오너 지시 2026-09-09)

계정 탈퇴 Slice 3(SoT v1.8.51)·약관·방침 시행 표기(v1.8.50)의 독립 검증. 기록: [`docs/verifications/2026-09-10/account_withdrawal_slice3_legal_effective.md`](../verifications/2026-09-10/account_withdrawal_slice3_legal_effective.md) — 판정 **조건부 합격(조건 셋)**.

### Completed work

- **계약 정독 → 경계 행렬 → 코드·셀 대조**: 브리프 ⓑ·ⓔ 후속 계약 4조와 SoT v1.8.50/51 대조 — 구현은 전 축 일치(식별 규칙 한 문장·묘비 키 모양·청구 원자성·파기 본체 한 벌·compose 필드·reconciler 보존 조건).
- **실 mongod 파기 경로 재현**(구현자 신고 약점 ①·② 닫음): 재현 스크립트 [`repro_live_account_purge.py`](../verifications/2026-09-10/repro_live_account_purge.py)(커밋 `dec3808`)가 **워커 진입점 자체**를 test-mongo replica set에서 돌려 **21/21 단정 통과**. 청구→묘비→본체→스윕→계정 행·reconciler 수습 3단계·naive→UTC 재라벨링 전부 무결. compose 최소 env(`CORE_SOT_MONGO_*` 3개)만으로 조립 성립 — 배포 가능성 실증. **실 개발 DB(사용자 4·컬렉션 35)에서 user id `_id` 충돌 0건** — `user:<hex>` 안전 근거 실데이터 성립. 제3축(`request_locks`·`quota_replay_responses`)은 TTL 자정리로 잔류 무해, 무-TTL 잔류는 `login_failures` 뿐(브리프 예고대로).
- **변이 신규 5종**(약점 ④): 새 셀 교합 재확인 3종(MU-9·10·11) 각 1실패로 물음. **갭 2종 실증 — MU-7(스윕↔계정 행 순서 교환)·MU-8(stop_check 제거)이 38셀 전건 초록.** 구현자가 예고한 "MU-1·MU-3 계열"의 잔존다.
- **약관 축**(약점 ⑤): 핀 셀·§8 전제 서술 정상 확인. **차단 2 발견 — ① 양 문서 부칙에 `draft-0 (미시행)` 잔류**(머리말 `시행·1.0`과 자기모순 — 결합 가드가 옛 상태줄 정확 문구만 봄) **② 제5조 1항 4,000자**(시행값 6,000자, 상향 `97bc149` 미반영). 패턴 스윕: 다른 모든 숫자는 일치.
- **전수 3017 passed / 1 skipped / 4114 subtests · EXIT=0**(2171초) — 주장(3017/1/4113, `ad8e86a`)과 셀·skip 일치, **subtest +1은 임시 워크트리 양단 실측으로 재현 스크립트 회계로 귀속**(`test_repo_hygiene` 603→604, `test_docs_indexes` 304 무변).
- **기록·등재**: 검증 기록+재현 스크립트 커밋(`dec3808`)·검증 인덱스 신규 단면(70일치·295건, 분포 194/**96**/5, 33%)·루트 README 분포 문장·HANDOFF("검증자에게"→검증 결과 조건 셋·Next Tasks 1번·회귀 기준선·health 3·이미지 공유 다섯)·CHANGELOG.

### Issues found

| 문제 | 원인 | 해결 | 결과 |
|---|---|---|---|
| 부칙 `draft-0 (미시행)` 잔류(양 문서) | 시행 표기 커밋이 머리말·상태줄만 고침 | **미수리 — 검증 조건 ①로 인계**(오너/다음 세션 몫) | 차단 B1 |
| 제5조 4,000자 | 상한 상향(`97bc149`, 09-08)이 문서 작성(09-07) 뒤에 와 값 채우기(09-09)가 대괄호만 고침 | **미수리 — 조건 ②** | 차단 B2 |
| 파기 순서 4→5단계 미잠금 | 실패 픽스처가 프로젝트 축에만 있고 스위퍼 실패 셀 없음 | **미수리 — 조건 ③**(처방: 스위퍼 실패 시 계정 행 생존 단정 셀) | 차단 B3 |
| stop_check 경계 정지·one-shot apply 무셀 | 워커 테스트가 loop·dry-run만 커버 | 하드닝 H1·H2로 기록 | 비차단 |
| work_log auth 묶음 "262/1207" 재현 불가 | (원인 불명 — 실측 241/1205, collect 241) | 기록 H3 | 비차단 |
| HANDOFF 기준선 줄·health·이미지 수 낡음 | 세션 49가 셀만 더하고 줄을 안 고침 | **검증자가 갱신** | 폐쇄 |
| 개발 스택에 `withdrawal_worker` 없음 | 컨테이너가 Slice 3 이전 상태(재생성 필요 함정) | Outstanding 으로 인계 | 운영 |

### Decisions

- 없음(오너 결정 필요 사항은 조건 폐쇄 후 승격 재검·Slice 4 착수 순서뿐 — HANDOFF Next Tasks 1번에 적음).

### Next steps

- **조건 셋 폐쇄**(HANDOFF "세션 49 검증 결과" 절) → 승격 재검(변이 재적용 포함) → Slice 4.
- 개발 스택 재생성(`withdrawal_worker` 동반 기동)·배포 시 `migrate_ledger_user_axis.py` 선행.

### Verification (세션 50)

- 초점 38/2 · 정책 가드 7/44 · auth 묶음 241/1205(주장과 불일치 — H3).
- 실몽고 재현 21/21 `RESULT: PASS` · 실DB 스캔 충돌 0.
- 변이 5종(표는 검증 기록 §5) — 원복 5회 전부 `git status --short` 무출력.
- 전수 3017/1/4114 EXIT=0(위).
- 문서 가드(편집 뒤): `test_docs_indexes`·`test_repo_hygiene` 초록 — 커밋 전 최종 확인.

## 세션 51 — 검증 조건 셋 폐쇄 + 하드닝 둘 (오너 지시 "검증 기록 확인해서 보강")

세션 50 독립 검증([기록](../verifications/2026-09-10/account_withdrawal_slice3_legal_effective.md), 조건부 합격)이 지목한 **차단 셋(B1·B2·B3)** 과 셀이 비어 있던 **하드닝 둘(H1·H2)** 을 닫았다. 커밋 `b23f689`(법률 축)·`7e07b37`(파기 축).

### Completed work

- **B1 — 부칙 시행 표기**: 양 문서 부칙의 `이 약관(방침) 버전: draft-0 (미시행)` → **`1.0`**. 머리말(`시행 — 2026-09-08 · 버전 1.0`)과의 자기모순을 없앴다. **가드도 함께 조였다** — 종전 결합 가드는 옛 상태줄의 *정확한 문구* 만 부정하고 버전은 **어디든** 문자열이 있으면 통과시켜, 부칙 잔류가 그대로 새 갔다. 지금은 셋을 함께 본다: ① `draft-0` 토큰이 문서 어디에도 없다 ② 머리말 버전은 **줄 전체**로 대조한다(부분 문자열로 재면 부칙 줄이 머리말을 대신 만족시킨다 — MU-15 로 실증) ③ 부칙 버전 줄도 같은 리터럴을 든다.
- **B2 — 약관 제5조 1항 4,000자 → 6,000자**(시행값 `env.py::DRAFT_RAW_TEXT_MAX_CHARS`, 상향 `97bc149`). **그 축을 상수와 대조하는 셀을 새로 넣었다** — 핀이 아니라 **상징 참조**라 상수가 움직이면 문서가 자동으로 따라가야 한다. 정책 문서의 같은 축은 정본 포인터가 있어 잠겨 있었지만 **약관 본문의 수는 아무도 안 보고 있었다**(대조표는 *어느 조항이 받는지* 만 잰다).
- **B3 — 파기 순서 4→5단계 잠금**: 스윕이 실패하는 픽스처에서 **계정 행 생존 + `purge_started_at` 표식**을 단정하는 셀. 순서가 바뀐 채 스윕이 실패하면 표식이 행과 함께 사라져 reconciler 의 `stalled_user_ids` 질의가 그 계정을 영영 못 찾는다 — 재는 것이 실패 라벨이 아니라 **그때 무엇이 살아 있는가** 인 이유다.
- **H1 — `run_once(stop_check=…)` 경계 정지 두 셀**(양방향): 정지 요청이면 다음 청구 경계에서 나가고(청구 안 한 계정에는 표식도 안 찍힌다), 요청이 없으면 배수를 끝까지 한다.
- **H2 — 일회성 apply 요약 두 셀**: `failures` 가 실패만·전부 싣는가, 그리고 실패가 없을 때 **키가 있는 채로** 비는가. 워커가 재시도하지 않으므로(D3=ⓐ) 이 목록이 운영자의 유일한 수습 통로다.
- **패턴 스윕(B1 계열)**: 시행 표기를 안 따라간 색인 셋을 함께 고쳤다 — 루트 [`README.md`](../../../README.md) 문서 표 · [`docs/README.md`](../../README.md) 정책 행 · SoT 문서 색인의 `legal/README.md` 상태 열이 아직 *"초안(미시행)"* 이라고 적었다(`docs/legal/README.md` 자신은 이미 `시행 — 2026-09-08 · 버전 1.0`). 상태 열 가드는 `docs/plans/` 만 보므로 이 셋은 기계가 안 잡는다.

### Issues found

| 문제 | 원인 | 해결 | 결과 |
|---|---|---|---|
| 결합 가드가 머리말 버전을 **부분 문자열**로 재고 있었다 | `버전: \`1.0\`` 이 부칙 줄(`- 이 약관 버전: \`1.0\``)의 부분 문자열이라 한쪽이 다른 쪽을 대신 만족시킨다 | 줄 전체 대조로 전환 | MU-15(머리말만 `2.0`)가 재실패 — 종전 가드로는 초록이었다 |
| 약관 본문의 수를 아무도 안 본다 | 대조표는 *어느 조항이 받는지* 만 재고 조항 내용은 사람이 읽는다 | 길이 제한 축만 상수 대조 셀로 잠금 | **나머지 수는 여전히 무잠금**(아래 부채) |

### Decisions

- **약관 수치 가드를 한 축만 만들었다** — 축마다 조항 앵커가 다르고, 전부 잠그려면 *조항 ↔ 상수* 표가 따로 필요하다(대조표의 셋째 표 격). 이번에 실제로 틀린 축 하나만 잠그고 나머지는 부채로 남긴다(HANDOFF). 검증 세션이 손으로 훑어 **현재는 전부 일치**함을 확인한 상태다.
- **판정 승격은 하지 않았다** — 조건을 닫은 세션이 자기 판정을 올리면 독립성이 사라진다. 검증 기록에는 **폐쇄 보고 절**만 덧붙이고, 승격 재검(변이 재적용)은 다음 검증 세션 몫으로 남긴다.

### Verification (세션 51)

- 초점: `tests/test_account_purge.py tests/test_account_withdrawal_worker.py` **38 → 43 passed / 2 subtests** · `tests/test_service_policy_contract.py` **7 → 8 passed / 44 subtests** · 문서 가드 `test_docs_indexes`·`test_repo_hygiene` **25 passed / 911 subtests**.
- **변이 9종 — 전부 기명 셀 재실패**(프리플라이트 `git status --short` 무출력 → 편집 → 초점 실행 → `git checkout --` → clean 확인, 9회 전부 clean):

| # | 방향 | 적용한 diff | 기명 재실패 |
|---|---|---|---|
| MU-7 | under | `account_purge.py::purge_account` 의 스윕 블록 ↔ `self._users.delete` 블록 교환 | `test_a_failed_sweep_leaves_the_account_row_alive_and_stamped` 1실패 |
| MU-7b | over | 스윕 실패를 삼키고(`except: swept = {}`) 계정 행을 그대로 삭제 | 같은 셀 1실패 |
| MU-8 | under | `run_once` 의 `if stop_check is not None and stop_check(): break` 두 줄 삭제 | `test_a_stop_request_ends_the_pass_at_the_next_claim_boundary` 1실패 |
| MU-8b | over | 같은 자리를 `if stop_check is not None: break`(값과 무관하게 끊음) | 위 셀 + `test_without_a_stop_request_the_pass_drains_everything` 2실패 |
| MU-16 | under | `_summary_doc` 의 `if not result.succeeded` 필터 제거(성공까지 실음) | `ApplyModeTest` 2셀 실패 |
| MU-12 | under | 약관 부칙을 `draft-0` (미시행) 로 복원 | `test_both_documents_carry_the_enforced_version_and_date` 1실패 |
| MU-13 | under | 방침 부칙을 `draft-0` (미시행) 로 복원 | 같은 셀 1실패 |
| MU-14 | under | 제5조 1항을 4,000자로 복원 | `test_the_length_limits_in_the_terms_match_the_constants` 1실패 |
| MU-15 | over | 머리말 버전만 `2.0` 으로(부칙은 `1.0` 유지) | `test_both_documents_carry_the_enforced_version_and_date` 1실패 — **종전 가드로는 초록이던 자리** |

- 전수: 아래 "전수" 절.

### Next steps

- **승격 재검**(다음 검증 세션): 변이 재적용 + 이 세션이 더한 다섯 셀의 교합 확인 → 검증 기록 판정 갱신.
- 그다음 **Slice 4(화면)**. 개발 스택 재생성(`withdrawal_worker` 동반 기동)은 그대로 남아 있다.
