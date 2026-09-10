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
