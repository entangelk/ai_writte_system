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
| **전수를 문서 편집과 겹쳐 돌렸다** | 기준선을 빨리 얻으려고 전수를 띄운 채 SoT·README 를 고쳤다 — 가드가 편집 중인 트리를 읽어 `test_the_readme_names_the_current_contract_version` 이 실패했다(SoT 버전만 올라간 순간을 읽었다) | 그 회차를 **버리고** 문서 커밋 뒤 고정 트리에서 다시 돌렸다 | 37분 재실행. **선례 셋째** — 09-04·09-09 에 이미 같은 일이 있었다(`docs/` 만이 아니라 **추적되는 모든 문서**가 대상이다) |

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

- **전수 3023 passed / 1 skipped / 4117 subtests · EXIT=0**(2271초, 알파·호스트, test-mongo ON, 커밋 `f37fab0`). 직전 기준선 3017/1/4114(`dec3808`)와의 차를 **양쪽 실측으로 갈랐다**: **셀 +6 = 이번 세션**(`--collect-only` 3018→3024) · **subtest +3 = 검증 기록 커밋 `a3d6cf2` 몫**(a3d6cf2 워크트리에서 `test_repo_hygiene` 606 · `test_docs_indexes` 305 로 **현행과 같다** → 이번 세션 기여 0. 세션 50 이 잰 604/304 는 자기 기록이 커밋되기 전 트리의 값이다).

### Next steps

- **승격 재검**(다음 검증 세션): 변이 재적용 + 이 세션이 더한 다섯 셀의 교합 확인 → 검증 기록 판정 갱신.
- 그다음 **Slice 4(화면)**. 개발 스택 재생성(`withdrawal_worker` 동반 기동)은 그대로 남아 있다.

## 세션 52 — 승격 재검(변이 재적용) · 선행 기록 판정 승격 (오너 지시 "핸드오프 확인해서 다음작업 진행해줘")

HANDOFF Next Tasks 1번이 가리킨 **승격 재검**. 세션 51 이 닫은 조건 셋의 폐쇄분은 **미검증 구간**이었다 — 조건을 닫은 세션이 자기 판정을 못 올리기 때문이다(세션 51 Decisions). 이 세션은 구현(49)·검증(50)·폐쇄(51) 어느 쪽도 아니므로 그 승격 권한을 가진다. 기록 [`slice3_closure_promotion.md`](../verifications/2026-09-10/slice3_closure_promotion.md) · 커밋 `4f451c4`.

### Completed work

- **전수 재현 먼저, 문서는 그 뒤** — 고정 트리 `c1cb282` 에서 **3023 passed / 1 skipped / 4117 subtests · EXIT=0**(1618초). 세션 51 주장과 **셀·skip·subtest 전건 일치**. 문서는 전수가 끝난 뒤에 한 자도 고쳤다(세션 51 이 겹쳐 돌려 37분을 버린 선례 넷째를 피했다).
- **지정 변이 재적용 아홉 종**(MU-7·8·12~16 + over MU-7b·8b) — **전부 세션 51 이 적은 기명 셀·개수 그대로 재실패**. 한 셀이 여럿을 흡수한 자리 없음(표는 아래).
- **반증 시도 신규 여섯** — 다섯은 폐쇄를 더 굳혔고 **하나(MU-20)가 새 갭을 열었다**.
- **조건 폐쇄 ↔ 처방 대조** — B1 은 처방(권고한 `draft-0` 토큰 부재)보다 **넓게** 닫혔고(머리말 버전 **줄 전체** 대조 추가), B2·B3 은 처방 그대로. B3 이 처방에 없던 `purge_started_at` 표식까지 단정한 것이 옳다 — 결함 서술이 *"reconciler 가 못 찾는다"* 이고 그 질의 조건이 `{"purge_started_at": {"$ne": None}}` 이다([account_purge_reconciler.py:56](../../../scripts/account_purge_reconciler.py)).
- **판정 승격** — 선행 기록 [`account_withdrawal_slice3_legal_effective.md`](../verifications/2026-09-10/account_withdrawal_slice3_legal_effective.md) 를 `조건부 합격` → **`합격`** 으로. 발행 시점 판정 원문은 인용 블록으로 보존(선례 2026-08-10). 인덱스 분포 합격 194 → **196** · 조건부 96 → **95** · 건수 295 → **296**, 루트 README 백분율 33% → **32%** 동반.

### Issues found

| 문제 | 원인 | 해결 | 결과 |
|---|---|---|---|
| **★ `run_loop` → `run_once` 정지 배선이 무셀**(MU-20 초록) | H1 폐쇄가 **피호출자**만 닫았다. `LoopTest` 의 대역 `_FakeService.run_once` 가 `stop_check` 를 **받고 버려서**([test_account_withdrawal_worker.py:110](../../../tests/test_account_withdrawal_worker.py)) 배선을 끊어도 `calls`·`slept`·`events` 가 전부 그대로다 | **비차단 H1' 로 기록**(선행 기록이 이 축 전체를 H1=비차단으로 분류했고 이것은 그 이음매다). 처방은 한 줄이고 **저장소에 선례가 있다** — 형제 워커가 `self.last_stop_check = stop_check` + `assertIsNotNone(...)` 로 같은 축을 잠근다([test_index_sync_worker_script.py:294·341](../../../tests/test_index_sync_worker_script.py)) | Slice 4 에 얹는다(같은 워커 축·셀 하나 — 독립 슬라이스를 열 크기가 아니다) |
| 인덱스 판정 열에 승격 사유를 붙였더니 가드가 물었다 | `test_every_record_row_states_a_verdict` 는 판정 열이 `*` 를 벗기면 **정확히 세 토큰 중 하나**여야 한다 — `**합격**(발행 시점 조건부 합격 → 승격)` 은 알 수 없는 값이다 | 판정 열은 `**합격**` 만, 승격 경위는 설명 칸으로 | 가드가 의도대로 물었다. **판정 열은 분류값이지 서술 자리가 아니다** |
| 분포표를 안 고쳐 두 셀이 물었다 | 검증 인덱스의 **분포표(38~40행)가 분포의 정본**이고 루트 README 문장은 그것을 되뇐다 — 건수만 고치면 합이 안 맞는다 | 분포표·README 문장·백분율 셋을 함께 | `test_the_verdict_distribution_adds_up_to_the_total`·`..._repeats_the_distribution_verbatim` 초록. **승격은 건수가 아니라 분포를 움직인다** — 등재보다 고칠 자리가 하나 많다 |
| 법률 축 변이가 `SUBFAILED` 로만 나온다 | 결합 가드가 `subTest(document=…)` 로 문서 둘을 돈다 | 요약 카운트 줄 + `FAILED\|SUBFAILED` 양쪽으로 판독 | 가이드 §"`grep FAILED` misses subtest failures" 가 실제로 적용된 자리 — `FAILED` 만 걸렀으면 넷 다 *"안 물었다"* 로 오독했다 |

### Decisions

- **MU-20 을 차단이 아니라 하드닝으로 분류했다.** 선행 기록이 정지 경계 축 **전체**를 H1(비차단)으로 판단했고, 이 발견은 그 축의 남은 절반이다. 여기서 등급을 올리면 이미 내려진 분류를 재심하는 것이 되고, 승격 판정(조건 B1·B2·B3 의 폐쇄 여부)과도 무관하다. **판정은 합격, 부채는 명시**가 정직한 조합이다.
- **반사실 변이(MU-15r)를 넣었다** — 세션 51 의 *"종전 가드로는 초록이던 자리"* 는 **주장**이지 재현된 측정이 아니었다. 변이를 적용한 채 **가드만** 옛 형태로 되돌려 초록을 확인했다. 폐쇄가 실제로 하중을 받는지는 이렇게만 알 수 있다.
- **subtest 증분을 예고로 두지 않고 실측했다** — 워크트리 양단(`c1cb282` 305/606 · 현행 306/607)으로 갈라 **다음 기준선은 3023/1/4119** 이고 그 +2 의 주인이 이 기록 파일임을 확정했다.

### Verification (세션 52)

- 프리플라이트 `git status --short` 무출력 → 변이 15회, 매번 `git checkout -- <path>` 뒤 무출력 확인. 마지막에 `git diff --stat HEAD` 도 무출력(내용까지 원복 확인). 초점 51셀(43 + 8) 초록.

| # | 방향 | 적용한 diff | 실측 |
|---|---|---|---|
| MU-7 | under | `purge_account` 의 sweep 4줄 ↔ delete 4줄 교환 | 1 failed `test_a_failed_sweep_leaves_the_account_row_alive_and_stamped` |
| MU-7b | over | 같은 자리를 `except Exception: swept = {}` 로 | 1 failed 같은 셀 |
| MU-8 | under | `run_once` 의 `if stop_check is not None and stop_check(): break` 두 줄 삭제 | 1 failed `test_a_stop_request_ends_the_pass_at_the_next_claim_boundary` |
| MU-8b | over | 같은 자리를 `if stop_check is not None:` | 2 failed 위 셀 + `test_without_a_stop_request_the_pass_drains_everything` |
| MU-16 | under | `_summary_doc` 의 `if not result.succeeded` 제거 | 2 failed `ApplyModeTest` 두 셀 |
| MU-12 | under | 약관 부칙 버전 줄 → `` `draft-0` (미시행) `` | 1 failed(SUBFAILED terms) `test_both_documents_carry_the_enforced_version_and_date` |
| MU-13 | under | 방침 부칙에 같은 복원 | 1 failed(SUBFAILED privacy) 같은 셀 |
| MU-14 | under | 제5조 1항 6,000자 → 4,000자 | 1 failed `test_the_length_limits_in_the_terms_match_the_constants` |
| MU-15 | over | 머리말 `버전: \`1.0\`` → `\`2.0\``(부칙 유지) | 1 failed(SUBFAILED) 결합 셀 |
| **MU-15r** | 반사실 | MU-15 를 둔 채 **가드만** 폐쇄 이전 형태로(부분 문자열 대조) | **8 passed — 초록.** 세션 51 주장이 실측으로 참 |
| MU-17 | under | 약관 상태줄 시행일만 `2026-10-01` 로 | 1 failed(SUBFAILED) 결합 셀 — 날짜도 두 자리가 함께 잠긴다 |
| MU-18 | over/순서 | `run_once` 의 정지 확인을 루프 머리 → 꼬리로 **이동** | 1 failed — H1 셀은 **위치**까지 잠근다 |
| MU-19 | over | `env.py::DRAFT_RAW_TEXT_MAX_CHARS` 6000 → 5000(문서 유지) | 2 failed — 정책 축(SUBFAILED) + 새 약관 셀. 상수→문서 방향도 문다 |
| **MU-20** | under | `run_loop` 의 `run_once(..., stop_check=stop.is_requested)` **인자 삭제** | **43 passed — 초록(갭 → H1')** |
| MU-22 | under | `purge_account` 의 `self._users.delete(user.id)` → `pass` | 4 failed, 그중 `test_a_due_account_is_purged_end_to_end` — 새 셀 docstring 의 *"반대편은 그 셀이 받는다"* 가 참 |

- 문서 가드(편집 뒤): `test_docs_indexes` + `test_repo_hygiene` **25 passed / 913 subtests**.
- 전수 **두 번** 돌렸다: 문서 편집 전 `c1cb282` **3023/1/4117**(1618초) · 기록까지 전부 실린 `3644147` **3023/1/4119**(1534초). 편집분은 셀을 안 늘리고 subtest 만 +2 하며, 그 +2 는 워크트리 양단 귀속(305→306 · 606→607)과 **직접 측정이 일치**한다. **소요 1618 vs 1534 초는 같은 날 같은 머신 값이다** — 소요로 회귀를 판정하지 말 것.

### Next steps

- **Slice 4(화면) 착수 가능** — 승격 전 금지가 해제됐다. 요청·취소·남은 일수 배너 + D3 관리자 잔여 정리.
- **H1'(정지 배선 셀)을 Slice 4 에 얹는다** — 선례 복사 한 줄.
- 개발 스택 재생성(`withdrawal_worker` 미기동)·배포 대기는 그대로.

## 세션 53 — 승격 재검 2차 독립 재검 (오너 지시 "작업 Ai가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래")

세션 52 산출(승격 재검 기록·판정 승격·기준선 4119 확정)을 다른 독립 세션이 다시 뜯었다. 기록 [`slice3_promotion_recheck.md`](../verifications/2026-09-10/slice3_promotion_recheck.md).

### Completed work

- **변이 재표집 둘** — MU-20(정지 배선 인자 삭제 → **43셀 전건 초록**, 갭 실재)·MU-8(정지 확인 두 줄 삭제 → **기명 셀 정확히 1 실패**, 폐쇄 셀 실효). 프리플라이트·원복 무출력 각 2회.
- **양단 산술 독립 재현** — `git worktree add --detach /tmp/wt_c1cb282 c1cb282` 에서 문서 가드 **305/606**, 현행 **306/607**(+2=4119 정확).
- **서류 전건 대조** — 세 커밋 문서 전용(코드는 `7e07b37` 이후 무변)·본문↔인덱스 판정 일치·분포 산술(196+95+5=296, 32%)·선례 인용 행 번호(`test_index_sync_worker_script.py:294·341`)·대역 버림(`:110`)·production 배선(`:257-259`)·`withdrawal_worker` 부재(`docker ps -a` 0건).
- **전수 재실행(HEAD `7f30027`)** — **1 failed · 3022 passed · 1 skipped · 4119 subtests**(1712초). 셋 수는 주장과 일치, **EXIT=0 은 이 시도에서 재현 못함**.

### Issues found

| 문제 | 원인 | 해결 | 결과 |
|---|---|---|---|
| **전수 1실패 — `final_save S13 unknown draft status: expected=404 observed=503`** | 503 은 SoT v1.7.38 의 전역 저장-오류 얼굴(`PyMongoError` 핸들러) — 일시 저장 계층 오류가 404 자리를 대신. 프로브는 InMemory core_sot 를 주입하지만 모든 의존성까지는 아니다 | **단독 재실행으로 가름** → 2 passed·7.9초 초록. 코드 동일성(`7e07b37` 이후 문서 커밋만)+셋 수 일치 → **회귀 아닌 전수 한정 플레이크** | **미수리 표에 등재**(프런트 둘에 이어 셋째 — "전수 1실패를 만나면 알려진 플레이크부터" 지침의 근거 표가 드디어 백엔드 플레이크도 가짐) |
| 루트 README 절차 표 ②행 subtest **4,117** 낡음 | HANDOFF 기준선 줄이 "*아무 가드도 안 잡는다 — 기준선을 갱신하는 슬라이스가 그 한 줄도 함께 고친다*"고 자기 규정한 바로 그 줄인데 `7f30027` 이 세 곳만 고치고 놓침 | 이 세션에서 **4,121** 로 동기화 | 가드가 없는 산문 숫자는 절차 문장으로만 잡힌다 |
| 검증 인덱스 자신의 분포 문장 **33%** 낡음 | `4f451c4` 가 루트 README 백분율만 고치고 분포표가 사는 그 파일의 문장은 안 고침(커밋 메시지는 "백분율 32% 동반 갱신" — 절반만 참) | **32%** 로 수정 | 같은 부류: **표**를 지키는 가드는 있어도 **산문**을 지키는 가드는 없다 |

### Decisions

- **EXIT=0 미재현을 차단이 아니라 플레이크로 분류했다.** 근거 셋: 코드 동일성(`7e07b37` 이후 문서 커밋만 — 세션 52 초록 트리와 같은 코드)·단독 재실행 초록·셀·skip·subtest 셋 수 일치. 오너가 이 판정에 동의하지 않으면 S13 저장 경로 조사 슬라이스를 여는 것이 다음 갈림길이다.
- **H1' 등급은 오너 결정으로 열어뒀다.** 세션 52 가 서피스한 그대로 — 이 재검은 사실 관계만 확인했다(갭 실재·production 배선 존재·선례 존재). 등급을 올리면 HANDOFF Next Tasks 순서 한 줄이면 된다.

### Verification (세션 53)

- 변이: MU-20 → 43 passed·EXIT=0(갭) · MU-8 → 1 failed `GracefulStopTest::test_a_stop_request_ends_the_pass_at_the_next_claim_boundary`. 원복 후 `git status --short`·`git diff --stat HEAD` 무출력.
- 문서 가드(이 세션 기록 실은 뒤): `test_docs_indexes` **307** · `test_repo_hygiene` **608**(각 +1 = 이 기록 파일의 몫).
- 전수 **두 번**: HEAD `7f30027` — 위 Issues 표 첫 행(S13 플레이크) · 커밋 `8990fbc` — **3023/1/4121 · EXIT=0**(2133초, 기준선 직접 실측 확정·S13 미재발). 소요는 머신-로컬 값(같은 날 1618·1534·1712·2133초).

### Next steps

- ~~커밋 후 전수 직접 실측~~ 완료(위 Verification) — **3023/1/4121 · EXIT=0**(2133초).
- H1' 등급(하드닝 유지 vs Slice 4 게이트) 오너 결정 대기.
- Slice 4 착수 — 이 세션이 바꾼 것은 없다.


## 세션 54 — 승격 재검 2차가 남긴 하드닝 둘 폐쇄 (오너 지시 "검증기록 확인해서 보강할 부분 보강해줘")

세션 53 재검([기록](../verifications/2026-09-10/slice3_promotion_recheck.md), **합격 · 차단 0**)이 비차단으로 남긴 것 중 **닫을 수 있는 둘**을 닫았다. 커밋 `85259d6`(배선 셀)·`9e2e5cf`(문서 가드) · SoT **v1.8.53**.

### Completed work

- **H1' — 탈퇴 워커의 정지 배선 잠금.** v1.8.52 의 H1 폐쇄가 **피호출자**(`run_once` 가 `stop_check` 를 존중하는가)만 닫았고, `run_loop` 이 그 인자를 **넘기는 문장**은 무셀이었다 — 두 세션(52·53)이 각각 인자 삭제 변이로 **43셀 전건 초록**을 재현했다. 대역이 `last_stop_check` 를 받아 두고, 셀이 **정지를 세운 뒤 넘겨받은 호출자에게 물어본다**.
  **★ 선례를 따르되 한 곳을 바꿨다** — 형제 워커는 `assertIsNotNone(last_stop_check)` 로 존재만 본다([`test_index_sync_worker_script.py:341`](../../../tests/test_index_sync_worker_script.py)). 여기서는 **동작**으로 잰다(정지를 세우고 물어본다). 이유: `assertIsNotNone` 은 *다른* 플래그를 넘겨도 통과하고, 동일성(`assertEqual(…, stop.is_requested)`)으로 재면 **등가 재배선(람다 래핑)에서 깨진다**. 둘 다 피하는 것이 동작 단정이다 — MU-20b(다른 플래그) 1실패 · MU-20c(등가 람다) 초록으로 양쪽을 실증했다.
- **산문 숫자 둘을 가드 안으로.** 세션 53 이 손으로 고친 값 둘은 같은 부류였다 — **가드가 지키는 표 바깥의 산문**. 값만 고치면 다음 슬라이스에서 또 샌다.
  ① **백분율**: 셀이 루트 README 만 봐서, 승격 커밋이 **분포표가 사는 바로 그 파일**의 같은 문장을 `33%` 로 남겨도 초록이었다 → 두 자리를 subTest 로 함께 본다.
  ② **README 절차 표 기준선**: HANDOFF 가 스스로 *"아무 가드도 안 잡는다 — 기준선을 갱신하는 슬라이스가 그 한 줄도 함께 고친다"* 고 **규정만 해 둔** 자리라 실제로 안 지켜졌다 → **HANDOFF 회귀 기준선 줄을 정본으로** 잠근다(`test_the_readme_names_the_current_contract_version` 이 SoT 헤더를 정본으로 삼는 것과 같은 모양).
  ③ **스윕을 실제로 돌렸더니 셋째 자리가 나왔다** — [`docs/README.md`](../../README.md) 결정 행이 브리프를 **112개**라 적는 동안 디스크는 **115**였다. 같은 수를 말하는 다른 두 자리(루트 README 절차 표·`docs/plans/README.md`)는 `_PLANS_BRIEF_CLAIMS` 안이라 정확했다 — **가드 밖 자리만 3 만큼 뒤처져 있었다.** 값을 고치고 그 자리를 가드에 넣었다(커밋 `bd96758`).

### Issues found

| 문제 | 원인 | 해결 | 결과 |
|---|---|---|---|
| 기록에 **커밋 해시를 지어 썼다 — 한 세션에 두 번** | 기록을 커밋 **전에** 쓰면서 해시 자리를 임시값으로 채웠다. 한 번 잡고도 30분 뒤 같은 자리에서 반복했다 | `git log` 로 실제 해시(`85259d6`·`9e2e5cf`·`bd96758`)를 넣었다 | **둘 다 자기 점검에서 잡았지만 재발했다는 것이 요점이다.** 이 저장소가 기록에 거는 요구(측정·식별자는 그 자리에서 잰다)의 정확히 반대 행동이다 — **해시 자리는 비워 두고 커밋 뒤에 채운다.** 임시값을 적는 순간 그것은 검증되지 않은 주장이 되고, 다음 사람은 그 해시를 `git show` 로 찾다 실패한다 |
| 선례를 그대로 베끼면 약한 셀이 된다 | 형제 워커의 `assertIsNotNone` 은 *넘겼는가* 만 본다 — 다른 플래그를 넘겨도 통과 | 동작 단정으로 바꾸고 **양방향 변이로 확인** | MU-20b 1실패(다른 플래그) · MU-20c 초록(등가 람다). 선례는 출발점이지 정답이 아니다 |

### Decisions

- **S13 플레이크는 안 건드렸다.** 세션 53 이 트리거를 달아 유예했고(*"재발이 쌓이면 404/503 재분류 또는 프로브의 저장 백엔드 완전 주입"*), 현 근거는 2회 중 1회다. 트리거 없이 지금 손대면 **원인 없이 기대값을 바꾸는 일**이 된다 — 미수리 표 등재를 그대로 둔다.
- **"14컨테이너" 표기도 안 건드렸다** — 세션 53 의 판단(발행된 타 세션 기록은 정정하지 않는다)을 따른다.
- **H1' 등급 질문은 소멸했다.** 오너에게 열려 있던 *"하드닝 유지 vs Slice 4 게이트"* 는 **셀이 들어오면서 올릴 대상이 없어졌다.** 결정을 받아 처리하는 대신 원인을 없앴다.

### Verification (세션 54)

- 프리플라이트 `git status --short` 무출력(각 변이 전) → 변이 6회, 매번 `git checkout --` 뒤 무출력 확인.

| # | 방향 | 적용한 diff | 실측 |
|---|---|---|---|
| **MU-20** | under | `run_loop` 의 `run_once(..., stop_check=stop.is_requested)` 인자 삭제 | **1 failed** `LoopTest::test_the_loop_threads_its_stop_flag_into_run_once` — **두 세션이 초록으로 재현했던 자리가 닫혔다** |
| MU-20b | over | 같은 자리를 `stop_check=lambda: False`(다른 플래그) | **1 failed** 같은 셀 |
| **MU-20c** | over(등가) | 같은 자리를 `stop_check=lambda: stop.is_requested()`(등가 재배선) | **44 passed — 초록.** 과잉 아님 실증 |
| MU-23 | under | README 절차 표만 `4,117` 로 되돌림 | **1 failed** `test_the_readme_repeats_the_regression_baseline` |
| MU-23b | over | HANDOFF 기준선만 `4199` 로 | **1 failed** 같은 셀 — *어느 쪽이 맞는가* 가 아니라 *같은 수를 말하는가* 를 잰다 |
| MU-24 / 24b | under | 인덱스 백분율만 / 루트 README 백분율만 `33%` 로 | 각자 **자기 subTest 실패**(`document='docs/verifications/README.md'` / `'README.md'`) — 두 자리가 독립으로 잠긴다 |
| MU-25 | under | `docs/README.md` 브리프 수를 `112개` 로 되돌림 | **자기 subTest 실패**(`kind='브리프', document='docs/README.md'`) |

- 초점: 워커 축 43 → **44 passed** · `test_docs_indexes` 16 → **17 passed / 307 → 310 subtests**(백분율 +2 · 브리프 주장 +1).

### Next steps

- **Slice 4(화면) — 선행 조건 없음.** 요청·취소·남은 일수 배너 + D3 관리자 잔여 정리.
- 개발 스택 재생성(`withdrawal_worker` 미기동)·배포 대기는 그대로.
