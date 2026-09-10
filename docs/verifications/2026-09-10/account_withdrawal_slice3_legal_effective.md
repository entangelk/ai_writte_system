# 세션 49 산출물 독립 검증 — 계정 탈퇴 Slice 3 · 약관·방침 시행 표기

## Subject metadata

- **검증일**: 2026-09-10 · **요청자**: 오너(2026-09-09 지시 — "다음 작업은 세션 49 산출물 독립 검증부터", HANDOFF Next Tasks 1번)
- **검증자**: 독립 세션(세션 49 구현자와 다른 세션)
- **대상**:
  1. **계정 탈퇴 Slice 3** — 커밋 `0919f95`(deletion)·`8f182bf`(scripts·compose)·`e9110a9`(청구 셀), SoT **v1.8.51**
  2. **약관·방침 시행 표기** — 커밋 `559c310`(시행)·`b6c5aa5`(값 셋+가드)·`c8f106e`(가드 사각 폐쇄), SoT **v1.8.50**
- **정규 스펙(계약 범위)**: [`docs/plans/slice3-withdrawal-purge-daemon-decisions.md`](../../plans/slice3-withdrawal-purge-daemon-decisions.md) ⓑ·ⓔ 확정 계약(후속 계약 4조) · SoT v1.8.50·v1.8.51 변경이력 · [`docs/legal/README.md`](../../legal/README.md) §8·값 넷 표 · 정책 문서 [`docs/service-policy-contract.md`](../../service-policy-contract.md) §1~§8
- **작업 소스**: 커밋 트리 — 검증 트리 `20a9049`+재현 스크립트 커밋 `dec3808`(코드·셀 무변, `docs/verifications/2026-09-10/` 신규 1파일만 추가). 기준선 트리 `ad8e86a`와 테스트 대상 동일(`20a9049`는 docs-only — `git show --stat` 실측).
- **환경**: 알파(개발 스택 10컨테이너 기동 중 · **`withdrawal_worker` 컨테이너 없음 — Slice 3 이전 컨테이너들, 재생성 전**) · test-mongo `rs-test` 단일노드 27020(PRIMARY) · 호스트 `/usr/bin/python3`(pymongo 등 `~/.local` user-site) · 호스트 셸에 `CORE_SOT_*`·`CHROMA_*`·`EMBEDDING_*` env 없음(실측)

## Scope

1. **구현 코드** — `deletion/{account_purge,account_axis_sweep,user_name_history,user_name_history_mongo}.py` · `auth` seam(`users.py`·`users_mongo.py`의 `claim_for_purge`·`list_withdrawing`·`delete`·`purge_started_at`) · `scripts/{account_withdrawal_worker,account_purge_reconciler}.py` · compose `withdrawal_worker`
2. **새 회귀 셀** — `tests/test_account_purge.py`(26셀)·`tests/test_account_withdrawal_worker.py`(12셀)·`tests/test_service_policy_contract.py` 신규 2셀(가드 본문 감사)
3. **★실 mongod 파기 경로**(구현자 신고 약점 ①) — fake/in-memory 없이 청구→묘비→프로젝트(본체)→계정 축 스윕→계정 행 + reconciler 수습 3단계
4. **★실 DB `_id` 충돌·스윕 도달 범위**(약점 ②) — 개발 DB(27520) 읽기 전용 실측
5. **수습 통로의 운영 지위**(약점 ③) — 판단 제시
6. **변이 — 새 셀 자신 포함**(약점 ④) — 신규 5종(갭 탐침 2 + 교합 재확인 3)
7. **약관 문서 서술·핀 셀**(약점 ⑤) — 두 문서 전문·대조표·상수 대조
8. **백엔드 전수** — 기준선 3017/1/4113 재현

## Methodology

계약 범위를 먼저 읽고 경계 행렬을 세운 뒤 코드·셀에 대조했다(가이드 §"spec/implementation/test/fixture stack as one whole"). 명령과 실측:

- 초점: `python3 -m pytest -q tests/test_account_purge.py tests/test_account_withdrawal_worker.py` → **38 passed / 2 subtests · EXIT=0**
- 정책 가드: `python3 -m pytest -q tests/test_service_policy_contract.py` → **7 passed / 44 subtests** (주장과 일치)
- auth 묶음: `python3 -m pytest -q tests/test_auth_users.py tests/test_auth_users_mongo.py tests/test_auth_api.py` → **241 passed / 1205 subtests**(2회 · `--collect-only` 241로 확정 — ★주장 262/1207과 불일치, Hardening H3)
- 실 Mongo 재현: `python3 docs/verifications/2026-09-10/repro_live_account_purge.py --mongo-uri "mongodb://127.0.0.1:27020/?replicaSet=rs-test"` → **21/21 단정 통과 · `RESULT: PASS`**(대상 DB `v49_slice3_verify` — 분리 이름, 종료 시 자체 삭제 · 개발 스택 데이터 미접촉)
- 실 DB 스캔(읽기 전용): pymongo로 `list_collection_names()`·`user_id` 필드 보유 컬렉션·user id `_id` 충돌 전건 질의
- 변이: 프리플라이트 `git status --short` 무출력(사전 커밋 `dec3808`) → 파일별 편집 → 초점 실행 → `git checkout -- <path>` → `git status --short` 무출력 확인(5회 전부). 결과는 요약줄+`FAILED|SUBFAILED`로 판독
- 전수: `python3 -m pytest -q > /tmp/backend_fullsuite_v49.log 2>&1; echo EXIT=$?`(test-mongo ON, PRIMARY 된 뒤)

## Findings

### 1. 구현 코드 ↔ 브리프 ⓑ·ⓔ 계약 — 일치

- **식별 규칙 한 문장** 그대로 — `account_axis_sweep.py:60-61`의 `delete_many({"user_id": uid})` + `delete_one({"_id": uid})`, `NEVER_SWEPT={"users"`}(`account_purge.py:41`).
- **묘비 키 모양** — `_id` = `user_name:<user id>`(`user_name_history.py:35-39`), 문서 키 집합 `{_id, target_user_id, username, purged_at}`, `user_id` 필드 없음(`user_name_history_mongo.py:48-54`). 선례 이탈의 이유가 파일 머리말에 있다(브리프 후속 계약 1 이행).
- **`request_quota_policies` 쓸이 편입** — `_id` 규칙으로 도달(브리프 실측 1의 구멍이 닫혔다).
- **청구** — `users_mongo.py:116-120` `find_one_and_update({"_id": uid, "purge_started_at": None}, {"$set": …})` 원자 조건부 갱신. `None` 매칭이 필드 없는 레거시 행도 포함하는 BSON 의미론(`set_withdrawal_requested_at` 주석과 같은 근거).
- **파기 순서·실패 규칙** — `account_purge.py:134-172` 청구→묘비→프로젝트(archive 선행)→스윕→계정 행. 프로젝트 실패 시 그 계정에서 멈춘다(다음 프로젝트 금지 — MU-5 대응 셀 있음).
- **파기 본체 한 벌** — 워커 `purge_services()`의 키 16개가 `execute_project_purge` 시그니처와 정확 일치(셀이 `inspect.signature`으로 잠금). `_project_purge_boundary`가 `HTTPException`→`RuntimeError`(상태코드·detail 보존).
- **compose** — `image: ai_writte_system-app` 공유·mongo만 의존·`stop_grace_period: 120s`·`ACCOUNT_PURGE_INTERVAL:-3600`·`restart: unless-stopped`(SoT v1.8.51 서술과 전부 일치).
- **reconciler** — `reconcile()`가 `not projects and has_tombstone`일 때만 계정 행 삭제(`scripts/account_purge_reconciler.py:74-77`). 기본 dry-run.

### 2. 실 mongod 파기 경로 — 구현자 신고 약점 ① **닫힘**

재현 스크립트([`repro_live_account_purge.py`](repro_live_account_purge.py), 커밋 `dec3808`)가 **워커 스크립트 진입점 자체**(`main(["--mongo-uri", …])`)를 실 replica set에서 돌렸다. 21단정 전부 통과:

- **dry-run**: 대상 = 만료 계정(alice)만. 이미 청구된 bob(부분 파기)·미신청 carol은 제외.
- **apply**: 청구 1·파기 1·실패 0. alice 계정 행 소멸 · 묘비 보존(`user_name:` 접두·`target_user_id`·username) · 세션 2건 소멸(필드 규칙) · quota policy 소멸(`_id` 규칙) · **원장·감사 보존** · 프로젝트 실 파기(본체 경유) · **파기 감사 행이 탈퇴 사유 리터럴과 함께 스윕을 생존**(보존 표식의 실증).
- **reconciler**: dry-run 보고(잔여 프로젝트·묘비 존재) → 잔여 있는 apply는 계정 행을 보존하면서 계정 축만 쓸음 → 잔여 제거 후 apply가 계정 행 마감(묘비·원장 보존).
- **naive→UTC 재라벨링**: BSON 왕복 뒤 `is_purge_due` 비교에서 `TypeError` 없음(`users_mongo._entry`의 `_aware` 수정이 실몽고에서 유효).
- **조립 env 최소성**: 호스트에 관련 env가 전혀 없는 상태에서 `CORE_SOT_MONGO_URI/DB/TRANSACTIONS` 세 개만으로 워커 조립이 성립 — compose의 `withdrawal_worker` env 집합이면 데몬이 뜬다는 배포 가능성의 실증.

### 3. 실 DB `_id` 충돌·스윕 도달 범위 — 약점 ② **닫힘(충돌 0건)**

개발 DB `ai_writing_system`(사용자 4·컬렉션 35개) 읽기 전용 실측:

- **"user id와 같은 `_id`를 가진 문서가 `users` 밖에 있는가" → 0건.** `user:<hex>` 접두 안전 근거(브리프 후속 계약 3)가 실데이터로 성립한다.
- **두 규칙의 실제 도달**: 현재 DB에서 `user_id` 필드를 가진 문서는 0건(세션 컬렉션이 비었고 `writing_generation_jobs` 17건은 필드 없는 구형 문서 — 어댑터는 신규 job에 `user_id`를 쓴다[`generation_job_mongo.py:150`] — 신규는 필드 규칙이 잡고 구형은 프로젝트 축이 가져간다). `request_quota_policies` 컬렉션 자체가 없다(회원별 정책 행이 아직 만들어진 적 없음 — `_id` 규칙의 실전 표적은 첫 회원별 정책 설정과 함께 생긴다).
- **제3의 축(문자열 접두)**: `request_locks`(`_id` 접두에 user 축 · TTL `expires_at`)·`quota_replay_responses`(`_id` = `user:action:dedupe` · TTL 24h) — 두 규칙 다 안 걸리지만 **TTL이 자정리**하므로 잔류가 무해하다. TTL 없는 제3축은 `login_failures`(`_id`=username) 하나뿐 — 브리프 후속 고려의 예고 그대로.

### 4. 새 셀 감사 — 구조·셀 수 주장과 일치, 경계 행렬에 빈 칸 한 곳

26셀+12셀 구조 확인(클래스별 5/5/5/5/5/1 + 3/3/2/4). 강한 셀: `test_the_document_id_is_prefixed_and_carries_no_user_id_field`(저장 모양+행위 두 축) · `test_the_id_rule_rests_on_the_user_id_prefix`(실제 `UserService`로 id를 주조해 접두 단정) · `test_the_mongo_claim_query_carries_the_condition`(질의 모양 직접 핀) · `BoundarySignatureTest`(본체 시그니처와 조립 키 집합 비교). **경계 행렬의 빈 칸** — 아래 B3.

### 5. 변이 — 신규 5종 (약점 ④)

| # | 방향 | 적용한 diff | 결과 |
|---|---|---|---|
| **MU-7** | under(순서) | `account_purge.py::purge_account`에서 스윕 블록과 `self._users.delete(user.id)` 블록을 **교환**(delete 먼저) | **초록 통과(38 passed) — 잠금 없음 → B3** |
| **MU-8** | under | `run_once`의 `if stop_check is not None and stop_check(): break` 두 줄 삭제 | **초록 통과(38 passed) — 잠금 없음 → H1** |
| MU-9 | under | `account_purge_reconciler.py:74` `if not projects and has_tombstone:` → `if not projects:` | **1 실패** `ReconcilerTest::test_a_missing_tombstone_also_holds_the_user_row_back` ✓ |
| MU-10 | under | `account_axis_sweep.py::sweep`의 `if name in NEVER_SWEPT: continue` 두 줄 삭제(Mongo 어댑터만) | **1 실패** `MongoSweeperShapeTest::test_the_adapter_issues_both_rules_against_every_collection` ✓ |
| MU-11 | under | `users_mongo.py:117` 청구 필터 `{"_id": user_id, "purge_started_at": None}` → `{"_id": user_id}` | **1 실패** `PurgeClaimTest::test_the_mongo_claim_query_carries_the_condition` ✓ |

구현자 표 6종(MU-3~MU-6·MO-2·MO-3)은 재유도하지 않았으나 대응 셀 본문을 읽어 조항-셀 대응을 확인했다. **MU-7·MU-8이 "MU-1·MU-3 계열"(처음에 통과하는 변이)의 잔존다** — 구현자가 스스로 예고한 자리였고 하나(MU-7)는 실제로 열려 있었다.

### 6. 약관 축 — 서술·핀 셀 (약점 ⑤: 두 차단 발견)

- **핀 셀은 값을 잡는다** — `_PROCURED` 넷(entangelk · kdtyohan@gmail.com · Google · 2026-09-08)과 `_ENFORCED_VERSION="1.0"`·`_ENFORCED_DATE`가 양 문서에 실재(제1조 · 제11조/방침 제8조 5항/부칙 · 방침 제4조 3항 · 부칙/제3조 안내 상자 각각 확인).
- **§8 전제 서술도 사실 그대로** — 두 문서 머리말이 "제8조 3·4항(방침 제3조 안내 상자·제5조 3항)은 아직 코드가 하지 않는다"라고 적고 legal/README §8 표가 `시행 전제` 열을 가진다(오너 "포트폴리오" 결정과 그 지위를 명기).
- **★B1 — 부칙 잔류**: 양 문서의 부칙이 아직 `이 약관(방침) 버전: draft-0 (미시행)` 이라고 적는다(약관 102행 · 방침 94행). 머리말은 `시행 — 2026-09-08 · 버전 1.0` — **문서가 자기 지위를 두 가지로 말한다**(결합 가드 스스로 금지한 바로 그 상태). SoT v1.8.50의 "`draft-0`·`미시행` 표식을 걷었다"는 부칙에 대해 사실이 아니다. 부칙의 시행일 줄(`- 시행일: 2026-09-08`)은 갱신됐는데 바로 옆 버전 줄이 그대로 남은 우발적 잔류다(work_log·브리프·README 어디에도 부칙 유지 언급 없음 — 실측). 결합 가드가 옛 상태줄의 **정확한 문구**(`Draft — 법률 검토 전 · 미시행`)만 부정하므로 부칙 표기는 전부 새 간다.
- **★B2 — 낡은 수치**: 약관 제5조 1항 "원고 한 단위의 본문은 **4,000자**" — 실제 시행값은 **6,000자**(`env.py::DRAFT_RAW_TEXT_MAX_CHARS`, 커밋 `97bc149` 2026-09-08 상향 · 정책 문서와 가드는 6000자로 최신). 약관 작성(09-07)이 상향(09-08)보다 앞서고 09-09 값 채우기는 대괄호만 고쳤다. legal/README 대조표가 이 축을 "코드가 지금 시행하는 것" 절에 두므로 문서↔정책 계약 모순이다. **패턴 스윕**: 법률 문서의 다른 모든 숫자(사용자명 64자 · 비밀번호 12/256자 · 대기 200건 · 5건/3,600초 · 5회/300초 · 세션 7일 · 하루 20/주 100 · KST · 장면 메모 12,000자 · 승격 1시간 · 유예 30일)는 정책 문서·상수와 전부 일치 — 낡은 것은 이 하나뿐이다.

### 7. 백엔드 전수 — 기준선 재현(증분 귀속 포함)

**3017 passed / 1 skipped / 4114 subtests · EXIT=0**(알파·호스트, 2171초, test-mongo ON). 주장(3017/1/**4113**, `ad8e86a`)과 **셀·skip 정확히 일치**. **subtest +1은 워크트리 대조로 귀속했다** — 기준선 커밋 `ad8e86a` 임시 워크트리에서 문서 가드 둘이 907 subtest(`test_repo_hygiene` 603 + `test_docs_indexes` 304), 현행 트리(재현 스크립트 커밋 `dec3808`)에서 908(604+304) — 차이는 전부 `test_repo_hygiene`(+1)이며 두 트리 사이에 추가된 파일은 이 검증의 재현 스크립트 1개뿐이다. skip 1 = live Chroma(함정 절 규칙 준수).

## Issues / Risks

### Blocking (계약 의무 — 판정을 결정)

- **B1** 법률 문서 부칙 `draft-0 (미시행)` 잔류(양쪽). 버전 문자열 `1.0`은 계약 리터럴(동의 게이트가 동의 시각과 함께 저장할 값)인데 문서 자신이 마지막 줄에서 다른 값을 말한다. 결합 가드의 사각(옛 상태줄의 정확 문구만 부정). [`terms-of-service-draft.md:102`](../../legal/terms-of-service-draft.md) · [`privacy-policy-draft.md:94`](../../legal/privacy-policy-draft.md)
- **B2** 약관 제5조 1항 **4,000자** — 시행값 6,000자와 모순(상향 `97bc149` 미반영). [`terms-of-service-draft.md:45`](../../legal/terms-of-service-draft.md)
- **B3** 파기 순서 **4→5단계(계정 축 스윕→계정 행) 미잠금** — SoT v1.8.51이 5단계 순서를 계약으로 적고 `account_purge.py` 머리말·`NEVER_SWEPT` 주석이 "계정 행은 마지막(스윕이 먼저 지우면 실패를 표시할 자리가 사라진다)"이라고 되풀이하지만, 순서를 바꾸는 MU-7이 38셀 전건 초록이었다. 실제 결함 형태: 순서가 바뀐 채 스윕이 실패하면 계정 행이 이미 지워져 `purge_started_at` 표식이 사라지고 **reconciler의 `stalled_user_ids` 질의가 그 계정을 영영 못 찾는다**(잔여 = 조용한 고아, D5 금지). 처방은 한 셀: 스위퍼가 실패하는 픽스처에서 계정 행 생존 + `failed_at="account_axis_sweep"` 단정.

### Hardening (비차단)

- **H1** `run_once(stop_check=…)` 경계 정지 무셀(MU-8 초록). compose의 `stop_grace_period: 120s`와 "진행 중인 계정 하나는 끝내고 다음 청구 경계에서 나간다"(워커 docstring·compose 주석)가 이 메커니즘에 걸려 있다 — 없으면 SIGTERM이 최대 `limit`(기본 10) 계정을 다 돌거나 그라이스 만료로 SIGKILL·부분 파기가 된다.
- **H2** `run_worker` one-shot apply 모드(`_summary_doc`의 failures 추출 포함) 무셀 — dry-run·loop에만 셀이 있다. 운영자가 실패를 아는 통로가 요약 JSON의 `failures`뿐이라는 서술(`account_purge._failure` 주석)과 대비되는 빈 칸.
- **H3** work_log 측정 불일치 — "auth 묶음(3파일) **262 passed / 1207 subtests**"가 재현되지 않는다(실측 **241/1205**, `--collect-only` 241로 확정 · `20a9049`는 docs-only라 개정 불가능). 다른 조합으로 쟀을 가능성은 있으나 기록된 선택 문자열로는 거짓이다.
- **H4** HANDOFF "회귀 기준선" 줄이 2964/4089(`422e79c`)에 멈춰 있었다 — 그 줄 스스로의 주문("+40셀을 더한 슬라이스가 갱신한다") 미이행. 3017/4113은 "검증자에게" 절에만 있었다. **검증자가 이번에 갱신함.**
- **H5** HANDOFF 스택 health 서술 "healthcheck 없는 2(worker·generation_worker)" — `withdrawal_worker` 추가로 **3**. **검증자가 갱신함.**
- **H6** 약점 ③ 판단: **현 단계 수용** — 실패 계정은 `purge_started_at` 표식 + 워커 요약 `failures` + reconciler dry-run으로 발견 가능하고 Slice 4(ⓔ)가 관리자 화면을 맡는다. 다만 Slice 4 전까지 stalled 계정을 보는 공식 표면이 스크립트뿐이라는 운영 사실은 남는다(Outstanding 참조).

## Verdict

**합격** — 발행 시점 판정은 `조건부 합격`(조건 원문 아래)이었고, **그 조건 셋이 닫힌 것을 2026-09-10 독립 세션(세션 52)이 변이 재적용으로 재현해 승격했다**(오너 결정 2026-08-06: *"판정 열은 그 기록의 **최종** 판정이다"*). 승격 근거 기록: [`slice3_closure_promotion.md`](slice3_closure_promotion.md) — 지정 변이 **MU-7·8·12~16 + over 둘이 전부 기명 셀 그대로 재실패**했고, 반사실 변이(MU-15r)가 결합 가드 조임이 하중을 받음을, 신규 변이 넷이 새 셀들이 주장보다 넓게 묾을 실측했다. 전수 3023/1/4117 도 셀·skip·subtest 전건 재현.

> **발행 시점 판정(원문, 보존)** — `**조건부 합격**` — 닫아야 할 조건 셋: ① 양 법률 문서 부칙의 `draft-0 (미시행)` 잔류 정리(결합 가드가 `draft-0` 토큰 잔류도 보게 조이는 것을 권장) ② 약관 제5조 1항 4,000자→6,000자 ③ 파기 순서 4→5단계 잠금 셀(스윕 실패 시 계정 행 생존 단정) 추가.
>
> 조건 셋은 같은 날 세션 51 이 닫았고(아래 §폐쇄 보고), **승격을 그때 하지 않은 것은 폐쇄를 조건 낸 세션이 아닌 다른 세션이 했더라도 판정 갱신에는 또 한 번의 독립 검증이 필요했기 때문**이다 — 폐쇄분 자체가 미검증 구간이다.

근거(발행 시점): 런타임 동작은 실 mongod 전 경로에서 무결(재현 21/21 · 실DB 충돌 0 · `user:<hex>` 안전 근거 성립)이고 구현은 브리프 ⓑ·ⓔ 계약과 일치한다. 그러나 산출물 둘 중 하나(법률 문서)가 자기모순과 시행값 모순을 지니고, 파기 순서 계약의 마지막 두 단계가 변이에 열려 있다. 셋 다 소규모 폐쇄 커밋으로 닫히는 종류다(구조 재작업 아님).

## Outstanding items

- **조건 셋 폐쇄 전 Slice 4(화면) 착수 여부는 오너 판단.** 파기 축은 되돌릴 수 없으나 현재 발견은 전부 문서·잠금 축이고 런타임은 실측 무결 — B3의 결함은 순서가 바뀌어야 발현되는 잠재 결함이다.
- **개발 스택(알파) 재생성 필요** — 현재 컨테이너들이 Slice 3 이전 상태라 `withdrawal_worker`가 떠 있지 않다(compose 함정: 새 서비스는 재생성 전까지 안 생긴다). 배포도 대기(HANDOFF 5번 절차 — `migrate_ledger_user_axis.py` 선행 · `up -d`로 워커 동반 기동).
- 조건 폐쇄 시 이 기록의 판정 승격은 폐쇄 재검(변이 재적용 포함)으로 갱신한다.

## 폐쇄 보고 (2026-09-10, 세션 51 — 검증자와 다른 세션)

**조건 셋이 닫혔고 하드닝 H1·H2 도 함께 닫혔다.** 커밋 `b23f689`(법률 축)·`7e07b37`(파기 축) · SoT **v1.8.52** · 상세는 [`daily_logs/2026-09-10/work_log.md`](../../daily_logs/2026-09-10/work_log.md) 세션 51.

| 조건 | 처방대로인가 | 무엇을 했는가 | 변이 재확인 |
|---|---|---|---|
| **B1** 부칙 `draft-0` 잔류 | ✔ (권고한 토큰 조이기 포함) | 양 문서 부칙 버전 줄 → `1.0`. 결합 가드가 ① `draft-0` 토큰 부재 ② **머리말 버전 줄 전체 대조** ③ 부칙 버전 줄을 함께 본다 | MU-12·13(부칙 복원) 각 1실패 · **MU-15(머리말만 `2.0`) 1실패 — 종전 가드로는 초록** |
| **B2** 제5조 1항 4,000자 | ✔ + 잠금 | 6,000자로 정정하고 그 축을 `env.py::DRAFT_RAW_TEXT_MAX_CHARS`·`core_sot/service.py::SCENE_NOTE_MAX_CHARS` 와 대조하는 **상징 참조 셀** 추가 | MU-14(4,000자 복원) 1실패 |
| **B3** 파기 순서 4→5 미잠금 | ✔ (처방한 셀 그대로) | 스위퍼 실패 픽스처에서 **계정 행 생존 + `purge_started_at` 표식** 단정 | **MU-7(순서 교환) 1실패** · MU-7b(스윕 실패 삼킴, over) 1실패 |
| H1 stop_check 무셀 | 함께 닫음 | 양방향 두 셀(정지 요청 → 다음 청구 경계에서 나감 · 요청 없음 → 배수 완료) | **MU-8 1실패** · MU-8b(값과 무관하게 끊음, over) 2실패 |
| H2 apply 무셀 | 함께 닫음 | `failures` 가 실패만·전부 싣는가 + 실패 0일 때 **키가 있는 채로** 비는가 | MU-16(필터 제거) 2실패 |

**전수(폐쇄 트리)**: **3023 passed / 1 skipped / 4117 subtests · EXIT=0**(2271초, 커밋 `f37fab0`). 위 §7 의 3017/1/4114(`dec3808`)와의 차는 **셀 +6 = 이번 폐쇄**(`--collect-only` 3018→3024), **subtest +3 = 이 검증 기록 커밋 `a3d6cf2` 자신의 몫**(a3d6cf2 워크트리에서 `test_repo_hygiene` 606 · `test_docs_indexes` 305 로 현행과 같다 — §7 이 잰 604/304 는 기록이 커밋되기 전 트리의 값이었다).

**이 절이 하지 않는 것 — 판정 승격.** 조건을 닫은 세션이 자기 판정을 올리면 독립성이 사라진다. 위 Verdict 는 **조건부 합격 그대로**이며, 승격은 다음 검증 세션이 변이를 재적용해 판단한다(Outstanding 3번의 뜻대로).

**남은 것**(위 Outstanding 에 더한다):
- **약관·방침의 나머지 수는 여전히 무잠금이다.** 이번에 잠근 것은 길이 제한 한 축뿐이고, 축마다 조항 앵커가 달라 일반화하려면 *조항 ↔ 상수* 표가 따로 필요하다. 검증 세션의 손 스윕(§6)이 현재 전부 일치임을 확인한 상태이므로 **부채이지 결함은 아니다**.
- 비차단 H3(work_log auth 묶음 262/1207 재현 불가)은 `20a9049` 가 docs-only 라 개정 불가능 — 기록으로만 남는다.
- 개발 스택 재생성(`withdrawal_worker` 미기동)은 그대로 남아 있다.

## Reproduction

```bash
# 초점·가드·auth 묶음
python3 -m pytest -q tests/test_account_purge.py tests/test_account_withdrawal_worker.py
python3 -m pytest -q tests/test_service_policy_contract.py
python3 -m pytest -q tests/test_auth_users.py tests/test_auth_users_mongo.py tests/test_auth_api.py

# 실 mongod 파기 경로(test-mongo PRIMARY 상태 · 분리 DB 자체 삭제)
python3 docs/verifications/2026-09-10/repro_live_account_purge.py \
    --mongo-uri "mongodb://127.0.0.1:27020/?replicaSet=rs-test"

# 변이(프리플라이트 git status 무출력 → 편집 → 초점 실행 → git checkout -- → clean 확인)
# MU-7: account_purge.py purge_account 의 sweep 블록과 delete 블록 교환 → 38 passed(갭)
# MU-9: account_purge_reconciler.py reconcile 조건에서 " and has_tombstone" 제거 → 1 failed

# 전수
docker compose -f docker-compose.test.yml up -d   # PRIMARY 대기
python3 -m pytest -q > /tmp/fullsuite.log 2>&1; echo EXIT=$?
```

환경 민감 항목: 실측은 모두 알파·호스트(test-mongo 27020 `rs-test`)이고 개발 DB 스캔은 27520 읽기 전용이다. 재현 스크립트의 대상 DB(`v49_slice3_verify`)는 분리 이름이며 종료 시 스스로 지운다.
