# 독립 검증 기록 — 계정 탈퇴 Slice 0: 상태 축과 경계 판정

## Subject metadata

- **일자**: 2026-09-08 · **요청자**: 오너("작업ai가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?") · **검증자**: 독립 검증 세션(구현 세션 39와 다른 세션)
- **대상 슬라이스**: 계정 탈퇴 Slice 0 — 상태 축과 계약("상태만 만들고 아무것도 지우지 않는다"). 커밋 `9e2bb94`(코드)·`10845f9`(기록). 소스 = main HEAD `10845f9`, 트리 clean, origin보다 2커밋 선행(push 대기 — 주장과 일치).
- **정규 스펙**: [`plans/account-withdrawal-implementation-phases.md`](../../plans/account-withdrawal-implementation-phases.md) Slice 0(**2026-09-08 정정판** — §6 승격 이관 포함) + D1~D6 확정 표 · [`service-policy-contract.md`](../../service-policy-contract.md) §8(계정 탈퇴 행 + 30일 문단) · SoT **v1.8.45** 변경이력 행.

## Scope

★ = 가장 의심스러운 축.

1. ★ **코드-계약 정합** — 세 번째 축·상수 한 곳·산술 한 곳·`>=` 경계·전이 계약(멱등은 첫 시각 유지, 취소는 스탬프 제거)·`LastActiveAdmin` 재사용 주장.
2. ★ **계획서 두 줄 충돌의 정정(§6 승격을 Slice 5 로 이관)** — 충돌이 실제로 있었는지, 심판 근거(정책 문서 자신의 §1~7/§8 지위 규칙)가 실재하는지, 이관이 유일한 정돈인지.
3. Mongo 저장면 — `$set: None`·`.get` 기본값·naive→UTC 재라벨링("일관성이 아니라 수정" 주장 + "fake collection 은 못 본다" 주장).
4. 셀 26의 경계 행렬 — 범위 계약이 요구하는 분기 전부가 기명 셀인지(빈 칸 없는지).
5. 구현자 변이 7종(MV-1~7) 재유도 + **검증자 자체 대항 변이** — `_doc` 쓰기면·축소 변이의 셀 수 재현.
6. 초점 전수·백엔드 전수 재실측과 산술(26셀·229/1054·전수 기대값).
7. 기록 일관성 — SoT v1.8.45·정책 §8·HANDOFF 11번·plans 인덱스·README·work_log 세션 39의 착수 전 실측 주장 셋.

## Methodology

전수·초점 모두 전량 파일 캡처 + 요약 라인 판독(`grep FAILED`만 안 읽음 — subTest 실측 교훈). 변이는 매번 프리플라이트 `git status --short` 공백 확인 → **assert 로 유일성을 검증한 일회 치환**(python heredoc, 바늘 문자열 그대로 기록) → 두 파일 실행 → `git checkout --` 원복 → clean 확인(8회 전부). 트리는 구현 커밋이 이미 HEAD 라 clean-tree branch 다.

```bash
git status --short                      # 공백(8회 변이 전 전부 확인)
python3 -m pytest -q tests/test_auth_users.py tests/test_auth_users_mongo.py tests/test_auth_api.py \
  tests/test_create_user_script.py tests/test_service_policy_contract.py tests/test_typecheck.py \
  > /tmp/verify_slice0_focused.txt 2>&1; echo EXIT=$?   # → 229 passed, 1054 subtests, 98.82s
# 백엔드 전수: 구현 세션이 캡처한 파일을 검증자가 직접 판독 + 산술 대조
#   /tmp/claude-1000/…/scratchpad/backend_full.txt → "2936 passed, 1 skipped, 3876 subtests in 1892.75s" EXIT=0
# 변이(예: V1): python3 heredoc 로 timedelta(days=30)→days=60 치환(assert count==1)
#   → pytest -q tests/test_auth_users.py tests/test_auth_users_mongo.py → git checkout -- <파일>
# 환경: WSL2 · test-mongo(rs-test, 127.0.0.1:27020, healthy) 가동 중 · 개발 스택은 검증 도중 복구(Outstanding 참조)
```

## Findings

### F1. ★ 코드-계약 정합 — 주장 전부 원문 확인

- **세 번째 축**: `models.py:41` `withdrawal_requested_at: datetime | None = None`. 기본값 `None` 은 `must_change_password`·`status` 와 같은 마이그레이션 자세(주석이 스스로 밝힘). 라우트·`AdminUserPayload`(`api/models.py:205` 명시 열거 — 새 필드 없음) 무변 → operation 102·응답 계약 무변 주장 성립.
- **상수·산술 한 곳**: `users.py:109` `WITHDRAWAL_GRACE_PERIOD = timedelta(days=30)` 유일. `users.py:112-119` `purge_due_at()` 이 유일한 산술(`+ WITHDRAWAL_GRACE_PERIOD`). 전 구조에서 산술 2곳째 없음(도출 함수 `is_purge_due` 는 `purge_due_at` 을 부른다 — `users.py:134`).
- **`>=` 경계**: `users.py:134` `now >= due`.
- **전이**: `request_withdrawal`(`users.py:392-417`) — 스탬프 있으면 **저장된 것 그대로 조기 반환**(첫 시각 유지 멱등) · `cancel_withdrawal`(`users.py:419-437`) — 스탬프 없으면 `WithdrawalNotRequested`(409 계열, `SignupNotPending` 선례 명시), 있으면 `at=None` 쓰기.
- **D6 재사용 주장 — 조건까지 동일**: `users.py:407` `if stored.is_active and self._is_last_active_admin(stored):` ≡ `deactivate_user` 의 `users.py:373`(메시지 문구까지 동일). "재사용, 재유도 아님" 주장 그대로.
- **Mongo**: `users_mongo.py:86-98` `$set`(None 포함, `$unset` 아님인 이유 주석) · `_doc` 등재(`:111`) · `_entry` 의 `.get` + `_aware()`(`:142`, `:146-149`).

### F2. ★ 계획서 충돌 정정 — 충돌 실재 · 심판 규칙 실재 · 이관 정당

- **충돌은 실제로 있었다**: `git show 10845f9` diff 에 정정 전 문언 *"유예 기간 30일은 상수 한 곳에 두고 **정책 문서 §6 이 그것을 가리키게 한다**(§1~7 과 같은 방식이라 값 대조 가드가 그 순간 자동으로 잠근다)"* — Slice 5(§8→§6 승격 + 정본 포인터)와 같은 편집을 둘 다 자기 몫으로 적고 있었다.
- **심판 규칙 실재**: 정책 문서가 머리말(`service-policy-contract.md:7`)과 §8 절 머리(`:91`)에 *"§1~§7 은 코드가 지금 시행하는 것, §8 은 정했지만 아직 코드에 없는 것"* 을 두 번 박아 두었다. Slice 0 뒤에도 셀프 경로도 파기 데몬도 없으므로 탈퇴는 시행 중이 아니다 — 지금 §6 로 올리면 문서가 없는 기능을 시행 중이라고 말한다.
- **오너 판단 불필요 판단에 동의**: 두 문서의 충돌이 아니라 **계획서 한 줄이 정책 문서의 확정 규칙을 몰랐던 것**이고 규칙 쪽이 명시적 정본이다(오너 결정을 요구하는 이류가 아님). 정책 문서의 개정(§8 상태 칸 "미구현"→"미시행(상태 축만)" + 30일 문단에 핀 셀 지정, `:98`·`:100`)이 이관와 모순 없이 정합.
- **핀 셀 대체는 선례 정합**: `MIN_PASSWORD_LENGTH` 계열 관례 그대로(값을 직접 박는 셀 — 상징 참조 셀은 60일로 바꿔도 자기 자신과 비교해 초록). docstring 이 "§6 승격 시 `test_service_policy_contract.py` 가 대조를 맡는다"고 예고해 Slice 5 의 중복 정본을 막는다.

### F3. Mongo 저장면 — "수정" 주장의 근거가 코드·드라이버 사실과 일치

- 가짜 컬렉션(`tests/test_auth_users_mongo.py:21-70`)은 넣은 문서를 그대로 돌려준다(`find_one` 이 저장 dict 반환) — **"fake collection 은 naive 재라벨링을 못 본다" 주장이 구조적으로 사실**. pymongo 기본(`tz_aware=False`)이 BSON 날짜를 naive 로 돌려주는 것과 대조해, 셀 `test_a_naive_stored_stamp_reads_back_aware`(`:316-329`)이 **드라이버의 tzinfo 벗기기를 직접 시뮬레이션**(naive 로 주입)하고 `is_purge_due` 비교까지 실행한다 — "재라벨링 빼면 파기 데몬이 TypeError" 주장의 잠금 장치가 맞다.
- `cancel` 셀이 **저장면까지** 본다(`collection.docs["user:1"]["withdrawal_requested_at"] is None`, `:300`) — 서비스 반환값만 맞고 저장이 안 되는 구현을 못 잡는 빈칸 없음.
- 레거시 행 셀(`:304-314`)이 탈퇴 키 없는 행을 먹이고, C-6·status 선례 셀과 같은 계열로 `.get` 하드화를 잠근다.

### F4. 경계 행렬 — 26/26, 빈 칸 없음

범위 계약(계획 Slice 0 + D1/D5/D6)이 요구하는 분기를 전수 대조: 신규 26셀 = `test_auth_users.py` 21(전이 14·경계 6·핀 1 — `def test_` 60개에서 전후 차등 21 확인) + `test_auth_users_mongo.py` 5. 각 분기→셀 매핑: 제3축 기본 None·요청 스탬프+저장·**요청이 아무것도 안 지우고 로그인 유지(D1=C 의 과잉교정 방어)**·취소 스탬프 제거·**취소≡미요청(D5=A)**·취소 후 재요청=새 유예·**재요청 첫 시각 유지(under-strict)**·없는 계정 양방향 UserNotFound·미요청 취소 거부·**마지막 활성 관리자 거부+스탬프 미잔류(D6)**·**둘째 관리자면 해제(over-strict)**·일반 회원 불가 없음·미요청 due 없음/never due·due=요청+30일·29일 아님·**정확히 30일(over-strict 짝)**·31일·30일 직전 1μs·30일 핀·Mongo 왕복/취소 None/없는 계정 None/레거시 행/naive→aware. **계약 요구 분기 중 기명 셀 없는 것 0건.**

### F5. 변이 재유도 — 구현자 7종 전부 재현(셀 수까지) + 대항 1종

| 변이 | 적용 diff(그대로) | 결과 | 구현자 표와 |
|---|---|---|---|
| V1 | `timedelta(days=30)`→`days=60` (`users.py:109`) | **5실패**(핀·due_date·day30·day31·mongo naive) | MV-1 "5실패" ✓ |
| V2 over-strict | `now >= due`→`now > due` (`users.py:134`) | **2실패**(exactly_day_30·mongo naive) | MV-2 "2실패" ✓ |
| V3 | 재요청 조기 반환 2줄 삭제(`users.py:405-406`) | **1실패**(repeat stamp) | MV-3 "1실패" ✓ |
| V4 | `_aware(doc.get(…))`→`doc.get(…)` (`users_mongo.py:142`) | **1실패**(naive) | MV-4 "1실패" ✓ |
| V5 | `_aware(doc.get(…))`→`_aware(doc[…])` (같은 줄) | **3실패**(C-6·status·withdrawal 레거시 셋) | MV-5 "3실패" ✓ — ★아래 참조 |
| V6 over-strict | 탈퇴 쪽만 `stored.is_active and _is_last_active_admin(…)`→`stored.is_admin` (`users.py:407`, deactivate 미손상 assert) | **1실패**(second admin) | MV-6 의 기명 셀 단독 물림 ✓ (구현자는 sed 가 deactivate 까지 바꿔 4실패였다고 기록 — 정직) |
| V7 | `set_withdrawal_requested_at(…, at=None)`→`updated = stored` (`users.py:435`) | **3실패**(clears·indistinguishable·re-request) | MV-7 "3실패" ✓ |
| **X1 대항** | `_doc` 에서 `"withdrawal_requested_at": …,` 줄 삭제(`users_mongo.py:111`) | **0실패(82 passed)** | 표에 없음 → 하드닝 H1 |

★ **V5 셀 수 의심과 기각**: 처음엔 "탈퇴 줄만 하드화했는데 3실패라는 표가 이상하다"(C-6·status 선례 셀은 다른 필드를 보지 않는가)고 의심했으나 — **레거시 행은 세 키를 전부 결여**하므로 탈퇴 줄만 하드화해도 선례 셀 둘이 함께 KeyError 로 물린다. 표의 3실패는 정확했고, 검증자의 초기 의심이 틀렸다. (`_aware` 까지 함께 제거한 넓은 변이는 4실패 — V4 와 겹쳐 naive 셀이 추가로 물림.)

### F6. 전수·초점 재실측과 산술

- **초점 6파일: 229 passed / 1054 subtests · EXIT=0 · 98.82s** — 구현자 주장(229/1054, 110초)과 **정확히 일치**(시간차는 부하).
- **백엔드 전수(구현 세션 캡처 파일 판독 + 산술 대조): 2936 passed / 1 skipped / 3876 subtests · EXIT=0 · 1892.75s.** 산술: 기준선 2903(v1.8.43, 알파) **+7(중간 커밋 — `git diff db19e30 9e2bb94^ -- tests/` 로 실측: v1.8.44 마이그레이션 +2 · 진입점 정적 가드 `test_script_entrypoints.py` 신설 · actions 개수 가드) + 26(본 슬라이스) = 2936 ✓.** subtests 3839→3876(+37)도 중간 커밋 3건의 가드 루프에서 온다(슬라이스 기여분 **0** — 두 파일 `subTest` 사용 0건 확인). skip 1 = 관례의 live Chroma.
- ★ README 절차 표의 기준선(**2903 / 3839**)은 v1.8.43 시점에 얼어 있다 — 구현자가 세션 마감에 갱신한다고 예고한 바로 그 수치(Outstanding 참조). 본 검증 시점 실측은 위와 같다.
- 신규 셀 수 주장(26 = 전이 13·경계 7·핀 1·Mongo 5)과 `def test_` 증감(test_auth_users 39→60, _mongo 17→22) 전부 재계산 일치. 착수 전 실측 주장 셋도 전부 사실: `UserRepository` 구현체 정확히 둘(`InMemoryUserRepository`·`MongoUserRepository`) · `AdminUserPayload` 명시 열거 · 가입 재요청 경로는 `request_signup`(`users.py:312-332`)이 fresh `User` 를 만들어 스탬프가 자연히 `None`.

### F7. 기록 일관성

SoT v1.8.45(헤더 버전·갱신일·변경이력 행 — 내용이 코드와 대응) · HANDOFF("지금의 계약" v1.8.45 · 착수 지점 Slice 1 · 계약 주의 넷) · plans 인덱스 상태 갱신 · README SoT 버전 bump(`test_docs_indexes` 가 잡은 자리) · work_log 세션 39(목표·실측·설계 판단 6·구현 표·변이 표·Verification) — 상호 모순 0건. 법률 대조표(`legal/README.md:66`)의 시행 전제 열은 Slice 5 전까지 그대로가 맞음(미갱신이 정상).

## Issues / Risks

### Blocking (contract obligations)

**없음.** 범위 계약이 요구하는 분기 전부 기명 셀에 잠겼고, 구현자 변이 표는 셀 수까지 정직했으며, 문서·코드·테스트가 서로 모순하지 않는다.

### Hardening recommendations (non-blocking)

- **H1 — `_doc` 쓰기면 무가드(X1 변이 0실패로 실증)**. `users_mongo.py:111` 에서 탈퇴 필드 등재를 삭제해도 **아무 셀이 물지 않는다**(82 passed). 현재 프로덕션 흐름이 스탬프가 든 `User` 를 `insert`/`replace` 로 쓰는 일이 없어(`create_user`·`request_signup` 는 항상 `None`) 계약 위반이 아니지만, Slice 1+ 에서 스탬프를 든 객체를 통째로 쓰는 흐름이 생기는 순간 조용한 유실로 바뀐다. **처방**: 스탬프를 든 `User` 를 `insert` 하고 읽어 돌아오는 왕복 셀 1개(Slice 1 착수 시).
- **H2 — `request_withdrawal` 읽기-쓰기 경쟁에서 첫 시각 보존이 원자적이지 않다**. `users.py:401-415` 는 읽고 검사한 뒤 쓴다 — 같은 계정의 첫 요청 둘이 동시에 들어오면 둘 다 `None` 을 보고 나중 시각이 이긴다(밀리초 단위로 "첫 시각 유지" 위반). 연속 클릭(계약이 금지하려던 것)은 잠겨 있고, 동시성은 spec 이 다루지 않는다. `deactivate_user` 와 같은 구조라 배포 형태(단일 프로세스)에서는 도달 어렵다. 처방을 원하면 `find_one_and_update` 필터에 `withdrawal_requested_at: None` 을 넣어 첫 스탬프를 원자화(Slice 1 라우트 설계와 함께 볼 것).

## Verdict

**합격**

- 범위 계약(계획 Slice 0 정정판 + D1/D5/D6)의 분기 26개가 전부 기명 셀에 추적 — 빈 칸 0.
- 구현자 변이 7종을 검증자가 독립 재유도해 **전부 기명 셀 재실패, 셀 수까지 일치**(V5 셀 수 의심은 재유도로 기각 — 표가 정확했다).
- 초점 229/1054·전수 2936/1/3876 EXIT=0 산술 정합(슬라이스 기여 +26 정확).
- 계획서 충돌 정정(§6 승격 → Slice 5 이관 + 핀 셀)은 충돌·심판 규칙·처방 모두 원문 확인 — 오너 재판단 불요에 동의.
- 하드닝 2(H1 쓰기면 가드·H2 첫 시각 원자화)는 계약 요구 밖의 보강 후보.

## Outstanding items

- **push 대기**: 구현 2커밋(`9e2bb94`·`10845f9`) + 본 검증 기록 커밋. 오너가 push 한다.
- **README ② 기준선 갱신**: "2,903 passed / 3,839 subtests" → **2936 / 3876**(+26 본 슬라이스 · +7/+37 은 v1.8.44·진입점·actions 가드). 구현 세션이 검증 도중 디스크에 올린 편집으로, 검증 실측과 일치함을 확인해 **본 검증 커밋에 함께 실었다**(구현 세션의 마감 커밋은 이 행을 제외하고 남는다). CHANGELOG 행은 구현자 마감 커밋에서 함께 오는지 확인할 것(D4 선례는 행이 있다).
- **개발 스택 8일 다운 상태를 검증 도중 복구함(슬라이스와 무관)**: 인프라 6컨테이너(mongo·application·gateway·chroma·elasticsearch·embedding)가 8일 전 exit 255 로 내려간 뒤 재시작 정책이 `no` 라 안 올라왔고, 재시작 정책이 있는 워커들이 mongo 부재로 크래시 루프였다. `docker compose start` 로 5개 복구, `application` 만 데몬 레벨 start 행으로 `rm`+`up -d` 재생성(설정은 compose 기본값과 동일임을 inspect 확인; **이미지 재빌드 없음** — 코드는 8일 전 것). 전 서비스 healthy·`/health` 200 확인. **재발 방지(인프라에 `restart: unless-stopped`)는 오너 판단 사항.**
- Slice 1 착수 시 H1 셀 추가 권장(위).

## Reproduction

```bash
git status --short   # 공백이어야 변이 가능
# 초점(≈99초): 229 passed / 1054 subtests
python3 -m pytest -q tests/test_auth_users.py tests/test_auth_users_mongo.py \
  tests/test_auth_api.py tests/test_create_user_script.py \
  tests/test_service_policy_contract.py tests/test_typecheck.py
# 변이 예시(V1): 아래 heredoc 실행 → pytest -q tests/test_auth_users.py tests/test_auth_users_mongo.py
#   → 5 failed → git checkout -- services/application/app/auth/users.py → git status --short 공백
python3 - <<'EOF'
import pathlib
p = pathlib.Path("services/application/app/auth/users.py")
s = p.read_text(); assert s.count("timedelta(days=30)") == 1
p.write_text(s.replace("timedelta(days=30)", "timedelta(days=60)"))
EOF
# 백엔드 전수(test-mongo 27020 기동 후): 2936 passed / 1 skipped / 3876 subtests
docker compose -f docker-compose.test.yml up -d && python3 -m pytest -q > /tmp/full.txt 2>&1; echo EXIT=$?
# 산술: git diff db19e30 9e2bb94^ -- tests/ | grep -c '^+.*def test_'  # → 7 (2903+7+26=2936)
```
