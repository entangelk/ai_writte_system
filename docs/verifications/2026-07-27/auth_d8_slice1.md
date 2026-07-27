# 검증 기록 — 인증 D8 슬라이스 1 (User·세션·로그인 API) 2026-07-27

## Subject metadata
- **날짜**: 2026-07-27
- **요청자**: 오너 ("다음 작업 검증해줘. ... 커밋 5개 ... 검증할 때 신경 써서 해줘. 서브에이전트 OK")
- **검증자**: Claude(독립 검증, max effort) — 4개 서브에이전트 병렬 투입 + 직접 실측
- **대상 작업**: 인증 D8 슬라이스 1(1a User+Argon2id · 1b 서버 세션 · 1c 엔드포인트·쿠키 · tz 버그 수정). 커밋 `bd702c4`(1a)·`451c8ef`(1b)·`5db69b0`(1c)·`fb83fc4`(버그 수정)·`ab9eb7b`(기준선). 직전 `b471f51`이 D1~D8 오너 결정 확정.
- **정본 계약 참조**: `docs/plans/multi-user-auth-cms-decisions.md` — D1=A(내부 모듈) · D2=A(서버 세션+HttpOnly 쿠키, 보안 하드닝: Argon2id·HttpOnly/Secure/SameSite=Lax·서버측 세션 즉시무효화·CORS 닫음) · line 220-221("해시 함수 손로 짜는 것 금기", 라이브러리 Argon2/bcrypt) · D7=A(인가 시행 — 본 슬라이스 범위 밖, D8-3) · D8 step1("인가는 아직 없음, 표면 무변") · Deferred.
- **작업 출처**: 커밋 `bd702c4..ab9eb7b`(HEAD). 본 검증은 커밋된 코드를 기준.

## Scope
스펙 governed 기능 슬라이스. boundary matrix를 D1/D2/D8 계약 조항 + 작업자가 "제 판단"이라 명시한 보안 조치에서 세웠다.

점검 표면(서브에이전트 분담 + 직접):
1. 1a — `password.py`(Argon2id, Type.ID) · `users.py`(UserService·authenticate·열거 방지) · `users_mongo.py`(unique 색인) · `models.py` · 3개 테스트
2. 1b — `sessions.py`(token_hash·entropy·clock·revoke) · `sessions_mongo.py`(user_id 색인·TTL) · 2개 테스트
3. 1c — `main.py` 엔드포인트(login/logout/me·CORS·비-목표) · `cookies.py` · `create_user.py` · `test_auth_api.py`(SliceBoundaryTest 포함)
4. tz 버그 수정 `fb83fc4` — 메커니즘·실 Mongo 라이브·mutation(양방향)
5. 패턴 sweep — 후보 3곳 + `tz_aware` 전역 상태 + 프론트 변경 inventory
6. 기준선 — 백엔드 전체 스위트 재실행(1609/1/623) + 라이브 8단계

## Methodology
독립 재도출. 서브에이전트는 코드·테스트를 읽고 file:line 인용, 본 검증자는 그 핵심 주장을 직접 재확인(회의적).

- 커밋: `git show --stat` / `git show <c> -- <path>` (5개 전수)
- 정본: `docs/plans/multi-user-auth-cms-decisions.md` D1·D2·D7·D8·Deferred 절 end-to-end
- 코드/테스트: `Read` (sessions.py:85 resolve, sessions_mongo `_aware`, users.py:101 열거 방지, cookies.py, main.py auth 섹션)
- **tz mutation**: `_aware` 호출을 naive passthrough로 되돌려 4건 회귀 실행 → TypeError 재현 → `cp` 백업으로 복원(미커밋 작업 보호)
- **실측 기준선**: test-mongo(rs-test, 27020) 기동 → `PYTHONPATH=. python3 -m pytest tests/ -q -rs`(439s)
- **라이브 8단계**: 실 스택(8520, 실 Mongo·실 Argon2id 23.1.0)에서 `scripts/create_user.py`로 사용자 생성 → login→me→401→오답/미존재→logout→ revoke→/projects 비-목표
- 서브에이전트가 실행한 단위 테스트: fake collection 사용(실 Mongo 불필요) — `test_auth_password/users/users_mongo`, `test_auth_sessions/sessions_mongo`, `test_auth_api`

## Findings

### 1. 기준선 — 실측 정확 일치(재실행)
- 백엔드 전체: **1609 passed / 1 skipped / 623 subtests**(439.41s). 잔여 skip 1 = live Chroma(`CHROMA_TEST_URL`/`chromadb` 필요, 상시 skip). 작업자 주장과 **정확 일치**. +53 분해(신규 auth 50 + 이 머신 ES 패키지 존재로 skip 안 되는 lexical 3)도 정합.

### 2. tz 버그 수정(fb83fc4) — 메커니즘·라이브·mutation 삼중 확인
- **메커니즘**: `sessions.py:85` `if session.expires_at <= self._clock()`. `_clock()`=aware `datetime.now(UTC)`, `expires_at`은 repo에서. pymongo는 BSON 날짜를 naive로 반환(`tz_aware=False` 기본)하므로 실 Mongo에서 `naive <= aware` → TypeError → 500.
- **수정**: `sessions_mongo.py:11-21` `_aware()`가 `_entry`(`:64-70`) 경계에서 UTC 재부착. 전역 `tz_aware=True` client 대신 경계를 고른 근거(주입 client도 커버)가 docstring에 명시.
- **mutation 실증(직접)**: `_aware`를 naive passthrough로 되돌리면 → **3 failed, 1 passed**. 실패 3건 = `test_read_back_timestamps_are_utc_aware`·`test_resolve_works_against_naive_stored_dates`·`test_normalization_does_not_shift_the_instant`. 4건째(`test_already_aware_dates_pass_through_unchanged`)는 naive 경로를 안 타므로 그대로 통과 — 이 역시 올바른 양상. TypeError 위치 = **`sessions.py:85`: `can't compare offset-naive and offset-aware datetimes`** — 작업자 주장("3건 실패 + sessions.py:85 동일 TypeError")과 **정확 일치**. 복원 확인(`_aware(doc)` 2줄 복귀, 9 passed).
- **라이브(직접, 실 Mongo)**: STEP 2 `GET /auth/me`(유효 쿠키) → **200**. 이것이 tz-fix-임계 단계(세션을 실 Mongo에서 읽어 resolve). 수정이 없었으면 500. 즉 단위 fake가 못 잡은 배포 결함을 **실 DB에서** 확인.
- **전역 `tz_aware` 미설정 확인**(서브 D): MongoClient 생성 13곳 전부 bare(인자 없음) → production naive는 실제 상황. 근거가 실증적임.

### 3. 1a — User + Argon2id (서브 A, 핵심 직접 재확인)
- Argon2id(`password.py:31` `_Argon2Hasher(type=Type.ID)`, digest `$argon2id$`). 라이브러리 `verify`(상수시간), 손수 해시/`==` 없음 → line 220-221 "금기" 준수.
- 파라미터: `type=Type.ID`만 명시, 나머지 argon2-cffi 기본값(m=65536,t=3,p=4) — OWASP 정합.
- 예외 catch `(Argon2Error, InvalidHashError)` 완전(`InvalidHashError`는 `Argon2Error` 아님을 확인).
- `users_mongo.py:18-20` 실 unique 색인, `DuplicateKeyError→DuplicateUsername` 정확.
- requirements `argon2-cffi>=23,<24`.

### 4. 1b — 서버 세션 (서브 B)
- **토큰 엔트로피**: `sessions.py:65` `secrets.token_urlsafe(32)` = 256-bit CSPRNG. `hash_token`=sha256(`:23`)는 "256비트 CSPRNG라 단일 sha256이 맞는 원시"라는 docstring 정당화 — 비밀번호가 아니므로 slow hash 불필요. **raw 토큰은 Mongo에 저장 안 함**(`_doc`는 token_hash만).
- clock 주입(`:64`), resolve 만료 검사(`:85`), `revoke`/`revoke_all_for_user`.
- `sessions_mongo`: user_id 색인(`:28-30`, force-logout) + TTL 색인 `expireAfterSeconds=0`(`:33-35`, 실 TTL). 즉시 무효화(D2) 충족.

### 5. 1c — 엔드포인트·쿠키·비-목표 (서브 C, 비-목표 직접 재확인)
- **쿠키 정책 단일 지점 fail-closed**: `cookies.py:14-24` `cookie_secure()` 기본 True, `AUTH_COOKIE_SECURE`로만 해제. `cookie_kwargs()` = `httponly·secure·samesite=lax·path=/`. 라이브 Set-Cookie = `HttpOnly; Max-Age=604800; Path=/; SameSite=lax; Secure`(정확).
- login 200 + 쿠키, 실패 시 쿠키 안 줌, 세션 fixation 없음(매 로그인 fresh token).
- **logout 멱등 + 서버측 폐기**: `if raw_token: revoke`(레코드 삭제), 무조건 200. 라이브 STEP 6/7로 확인(logout 200 → 이후 me 401).
- /auth/me: 200/401, 401 body `{"detail":"not authenticated"}`. `UserPayload`는 `password_hash` 제외(`main.py:1278-1283`).
- **비-목표 잠김(직접 재확인)**: `test_auth_api.py:169-178` `SliceBoundaryTest`가 미로그인 클라로 `GET /projects == 200` 단언. 라이브 STEP 8로도 확인. OpenAPI introspect: 비-`/auth` 62 operation 중 `security` 키를 가진 것 0개.
- **CORS 닫힘(D2 조항)**: `main.py`에 CORSMiddleware/allow_credentials 없음(부재로 폐쇄). 이 슬라이스가 안 열었음.
- 비-`/auth` 경로에 auth dependency 추가 0건(`grep Depends` 해당 없음) → "표면 무변" 확인.
- `create_user.py`: 비밀번호 env(`AUTH_BOOTSTRAP_PASSWORD`), argv 아님; 비밀번호 로그 0건; username 필수.
- 테스트 `base_url=https://testserver`(httpx가 Secure 쿠키를 http에서 조용히 버리는 함정 능동 회피).
- `AUTH_SESSION_TTL_HOURS ≤ 0` 기동 거부(`main.py:458-465`); 로그인 후 비활성화 시 매 me맄재확인 → 세션 생존 불가(`test_auth_api.py:120-134`).

### 6. 패턴 sweep + 프론트 (서브 D)
- 후보 3곳 전부 무해: `generation_job.py:195`·`indexing/service.py:819/:821`은 **in-memory repo 안** 비교; Mongo 경로는 `$lte` **서버측** 쿼리(`generation_job_mongo.py:85`, `indexing/mongo_repository.py:131/136`)로 naive가 Python 비교에 도달 안 함.
- "auth가 유일한 비교처" 확인: repo 전역 grep 4 hit(위 3 + auth 수정 1). 제5의 장소 없음. 기존 결함 **0건**.
- 프론트: `git diff --stat b471f51..HEAD -- frontend/` = `schema.d.ts` +194만(openapi 생성 타입, 로직 0). "프론트 코드 0" 정확.

## Issues / Risks

### Blocking (계약 의무 / spec-silent-but-code-enforced)
- **B-1 (조건)**: **timing-side 열거 방지가 코드 시행되나 회귀로 안 잠겨 있다.** `users.py:101`이 미존재/비활성 사용자에 대해 `self._hasher.verify(self._enumeration_guard_hash(), password)`를 돌려 오답과 타이밍을 맞춘다(의도적 보안 조치, 작업자가 "열거 방지 더미 verify"라 **배포 기능으로 주장**). 그러나 테스트 fake `_FakeHasher`에 호출 추적이 없어 **line 101을 지워도 스위트가 green**이다. `test_unknown_username_returns_none`/`test_inactive_user_cannot_authenticate`는 `assertIsNone`만. CLAUDE.md "spec-silent-but-code-enforced ... 해소는 슬라이스 일부" — D2 명시 목록엔 없으나 코드 시행 + 작업자 주장이므로, **닫기 전** (a) verify-관측 fake로 line 101을 잠그거나(5줄 테스트), (b) 미잠금 하드닝으로 명시 수락(오너)해야 한다. 참고: 열거 방지의 **메시지 쪽**은 잠겨 있다(`test_auth_api.py:82-93` unified detail 단언 + 라이브 확인). 미잠금은 timing 쪽만.

### Hardening recommendations (비차단, 정본 밖)
- H-1: 기본 `token_factory` 엔트로피가 회귀로 안 잠김. `secrets.token_urlsafe(32)`가 정확하나, 누군가 저엔트로피 기본값으로 바꿔도 green. D2 "DB 유출로 live 세션 부활 불가"가 토큰 엔트로피에 의존하므로, 길이/유일성 단언 권장(B-1과 같은 맥락, 저심각도 — 기본값은 이미 맞음).
- H-2: SliceBoundaryTest가 62개 중 3개 엔드포인트만 표본. 비-`/auth` operation이 `security` 키를 가지지 않음을 OpenAPI로 순회 단언하는 메타 테스트로 비-목표를 전수 잠그길(오늘은 수동 introspect로만 확인).
- H-3: login이 기존 세션을 revoke하지 않음(`revoke_all_for_user`가 login에 미사용) → 동시 세션 적재. 정본이 single-session 요구 않음; D6/D7에서 검토.
- H-4: logout이 세션 없어도 `Set-Cookie`(만료) 발행. 미관상.
- H-5: Argon2 파라미터값이 테스트에 단언 안 됨(기본값 의존). 미래 기본값 열화 감지 불가.
- H-6: 다른 Mongo repo들도 naive 날짜를 반환하나 비교처가 없어 무해(gate_findings/scratch/loop_audit). 향후 비교 추가 시 같은 버그 재발 — B-1 처리 시 같은 규칙으로 일관 적용 권장.

## Verdict — **조건부 합격(Conditional pass)**
- **합격으로 인정되는 부분(압도적)**: 구현은 모든 적대 검증에서 정확 — Argon2id(라이브러리, 손수 해시 없음), 고엔트로피 토큰+sha256 저장, 서버 세션 즉시무효화(user_id+TTL 색인), 쿠키 정책 단일 fail-closed, 비-목표 잠김·CORS 폐쇄·표면 무변, 패턴 sweep 0 결함, 프론트 생성 타입만. 기준선 1609/1/623 실측 정확 일치. **tz 수정은 메커니즘·실 Mongo 라이브·mutation(양방향) 삼중 확인** — 작업자 주장과 한 치 오차 없이 일치.
- **조건(해소 전 합격 아님)**: **B-1**. `users.py:101` timing-side 열거 방지를 verify-관측 회귀로 잠가야 한다(작업자가 배포 기능으로 주장한 보안 조치이므로). 5줄 내외 테스트 한 건이면 닫힌다. 혹은 오너가 미잠금 하드닝으로 명시 수락. 메시지 쪽 열거 방지는 이미 잠겨 있으므로 조건은 timing 쪽 한 갈래만.
- 비고: B-1은 작업자의 자발적 추가 하드닝(D2 명시 의무 아님)이므로, 엄격히는 "PASS + 권고"로도 볼 여지가 있으나 — CLAUDE.md "spec-silent-but-code-enforced 해소는 슬라이스 일부"와 "잠기지 않은 보안 분기"를 근거로 **조건부**로 잡는다. 오너 판단으로 PASS로 넘기는 것도 합리적(그 경우 B-1은 H-1과 함께 후속 보강).

## Outstanding items
- 라이브 검증용 사용자 `liveprobe`(`user:8a9893...`)가 dev DB에 생성돼 있다(검증자가 만듦). 삭제 엔드포인트는 D6 이전 없으므로 mongo 직접 삭제 또는 차기 볼륨 초기화 시 소거. 기능 영향 없음.
- 본 검증은 test-mongo(27020)를 기동해 둔 상태. 컨테이너 `ai_writte_system-test-mongo-1` Up.
- 작업자의 A/B(다음 단계)는 본 검증 범위 밖. B-1 해소가 선행하면 D8-2(`owner_id`)로 진행 합리적.

## Reproduction
```bash
cd "/mnt/d/devel/에베베/ai_writte_system"
# 기준선(전체 스위트)
docker compose -f docker-compose.test.yml up -d
PYTHONPATH=. python3 -m pytest tests/ -q -rs | tail -2   # 1609 passed, 1 skipped, 623 subtests
# tz mutation(양방향)
cp services/application/app/auth/sessions_mongo.py /tmp/bak
sed -i 's/created_at=_aware(doc\["created_at"\]),/created_at=doc["created_at"],/; s/expires_at=_aware(doc\["expires_at"\]),/expires_at=doc["expires_at"],/' services/application/app/auth/sessions_mongo.py
PYTHONPATH=. python3 -m pytest tests/test_auth_sessions_mongo.py::NaiveBsonDatetimeTest -q --tb=line  # 3 failed, TypeError at sessions.py:85
cp /tmp/bak services/application/app/auth/sessions_mongo.py
# 라이브 8단계(실 Mongo)
docker exec -e AUTH_BOOTSTRAP_PASSWORD=p ai_writte_system-application-1 sh -c 'cd /app && PYTHONPATH=/app python3 scripts/create_user.py liveprobe'
curl -s -i -X POST -H 'Content-Type: application/json' -d '{"username":"liveprobe","password":"p"}' http://localhost:8520/auth/login   # Set-Cookie session=...
TOK=...; curl -s -H "Cookie: session=$TOK" http://localhost:8520/auth/me   # 200 (tz-fix 임계)
curl -s -o /dev/null -w '%{http_code}' http://localhost:8520/projects        # 200 (비-목표)
# 비-목표 잠김 + CORS
grep -n "SliceBoundaryTest\|GET /projects" tests/test_auth_api.py
grep -nE "CORSMiddleware|allow_credentials" services/application/app/main.py  # (no match = closed)
```
