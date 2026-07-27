# 2026-07-27 작업 로그

## Task — 베타 머신 스택 기동 + HANDOFF 머신 구분 절 + 검증 지적 반영

### Goals

- HANDOFF Next Tasks #1(스택을 올리면 바로 할 것 — 관측 화면 육안 확인)의 선행: 이 **베타 테스트
  머신**(외부 LLM `192.168.1.22`)에서 배포 스택을 실제로 기동한다.
- 오너 요청: HANDOFF 상단에 머신 구분(알파·베타·감마) 기록을 남겨 "환경과 안 맞는다"는 오해를 없앤다.
- 오너의 독립 검증(조건부 합격)이 지적한 차단 1건·보강 3건을 반영하고 커밋한다.

### Completed work

- **HANDOFF 머신 구분 절 신설** [`HANDOFF.md`](../../../HANDOFF.md): 상단에 알파(배포·in-stack GPU
  llama)·베타(지금 이 머신·외부 LLM `192.168.1.22:9080`)·감마(노트북·LLM 불가, CPU 컨테이너/DB만) 표와,
  "무엇을 띄울 수 있는지(항구적 성질) vs 지금 무엇이 떠 있는지(머신-로컬 관측치)"를 구분하라는 규칙.
- **베타 머신 `.env` 생성**(커밋 금지 — gitignore 확인): `LLAMA_BASE_URL=http://192.168.1.22:9080`.
  gateway 기본값 `host.docker.internal:9080`(= 호스트 로컬)을 외부 12B 서버로 덮는다.
- **전체 스택 기동**: `docker compose up -d --build`(3~4일 전 이미지가 관측 코드 이전이라 재빌드).
  기동 중 발생한 `PromptTemplateConflict`를 해소(아래 Issues) 후 재기동.
- **frontend healthcheck 결함 수정** [`docker-compose.yml`](../../../docker-compose.yml) `:360-364`:
  probe URL `http://localhost/` → `http://127.0.0.1/`. 근거는 아래 Issues.

### Issues found — PromptTemplateConflict (기존에 문서화된 함정)

- 스택 기동 시 `application`·`generation_worker`가 `PromptTemplateConflict`로 죽었다. 원인은 dev
  `mongo_data` 볼륨에 굳은 **구 `analysis_extract_v3` 프롬프트 본문**이 현재 코드의 canonical v3와
  달라서다([`prompt_templates.py:118-121`](../../../services/application/app/analysis/prompt_templates.py#L118):
  같은 version인데 body가 다르면 충돌).
- **코드 회귀가 아님**을 확인: canonical v3 sha256을 재계산 → `4376310…`이고
  [`tests/test_prompt_templates.py:36-38`](../../../tests/test_prompt_templates.py#L36)의 pin과 정확히 일치.
  코드↔테스트는 자기일관적이고, 저장 볼륨만 stale했다. 이 실패 양상은 테스트가 "2026-07-22 boot
  failure"로 명시해 둔 기존 패턴(HANDOFF 함정 절).

### User Decisions and Rationale — 데이터 볼륨 초기화

- 해소 방식으로 오너에게 3안(구 v3 문서 1건만 삭제 / mongo 볼륨 전체 초기화 / 보류)을 물었고,
  **오너가 "mongo 볼륨 전체 초기화"를 선택**했다 — fresh 상태에서 관측 화면을 확인하려는 의도.
- 구현 판단으로 `down -v`(모든 볼륨) 대신 **데이터 볼륨(mongo·es·chroma)만 제거하고 embedding 모델
  캐시(`embedding_cache`)는 보존**했다. 오너 의도(fresh 데이터)는 그대로 충족하면서 BGE-m3-ko
  재다운로드 비용을 피한다.
- **소거된 것**: 이전 dev DB 전체(drafts·versions·source_refs·memory·llm_call_audits·gate_findings 등)와
  ES/chroma 색인. 보존: embedding 모델 캐시. 즉 관측 화면·모든 데이터는 **빈 상태부터** 시작한다.
- 재기동 후 9개 서비스가 뜨고 application이 healthy, `/health` 200 확인.

### Issues found — 검증이 잡은 차단 1건: HANDOFF에 거짓 관측치

- 오너 요청 독립 검증(`docs/verifications/2026-07-27/stack_bringup_handoff_machine_section.md`,
  **조건부 합격**)이 **B-1**을 지적: 내가 HANDOFF에 "9개 서비스 전부 Up·healthy"라고 적었으나 실측은
  **healthy 6 / unhealthy 1(frontend) / healthcheck 없음 2(worker·generation_worker)**. `up` 출력에서
  추론하고 `docker compose ps`로 확인하지 않은, CLAUDE.md가 정확히 금지하는 실패 양상. 내가 같은
  HANDOFF에 "머신-로컬 관측치를 믿지 말라"는 절을 쓰면서 저지른 것이라 특히 반영이 필요했다.
- **직접 재측정으로 확인**(검증자 진술도 회의적으로): `docker compose ps` → healthy 6
  (application·gateway·mongo·elasticsearch·embedding·chroma), frontend unhealthy(FailingStreak 65),
  worker·generation_worker는 Health 컬럼 공란(healthcheck 미정의, async 워커라 by design).

### Issues found — frontend healthcheck 근본 원인 (사전 존재 결함)

- **직접 재현**: frontend 컨테이너 안에서 `wget http://localhost/` → exit 1 "Connection refused",
  `wget http://127.0.0.1/` → exit 0. `/etc/hosts`가 `::1 localhost`를 함께 매핑해 busybox wget이
  IPv6를 먼저 시도하는데 nginx는 `listen 80;`(IPv4 `0.0.0.0`만) → refused. **기능은 정상**(host
  `curl localhost:5520` → 200), healthcheck만 거짓 보고.
- `nginx.conf`·frontend Dockerfile은 `46f6009`(frontend 첫 슬라이스) 이후 미변경 → 내 `--build`가
  유발한 것이 아니라 **사전 존재 결함**. 검증자도 같은 결론.
- **수정**: healthcheck probe를 `http://127.0.0.1/`로 변경(IPv4 강제, nginx `listen 80`과 일치).
  `listen [::]:80;` 추가 대신 이 최소 수정을 택한 이유는 nginx의 서빙 동작(IPv4 전용)을 바꾸지 않고
  healthcheck의 거짓 보고만 교정하기 때문(§3 surgical). 수정 후 frontend가 healthy로 전환됨을 확인.

### Verification

- **검증자 판정**: 조건부 합격. 진짜로 맞는 것(재확인 완료) — `/health` 200 · operation 62개 ·
  관측 route 등록 · gateway 컨테이너에서 `192.168.1.22:9080` TCP+/health 200 종단 도달 ·
  PromptTemplateConflict 진단이 코드 메커니즘·테스트 pin·알려진 패턴과 일치. 조건 = B-1 정정.
- **비검증 한계(검증자 명시)**: 저장돼 있던 구 v3 sha `fb4e272…`는 볼륨 초기화로 증거가 소거되어
  재확인 불가. 진단의 저장 측은 내 진술에 의존(정본 측 재확인 + 알려진 패턴 + 코드 일치로 개연성은 충분).
- **반영 후 재측정**: frontend healthcheck 수정 후 재생성 → healthy 전환 확인. 최종 상태 =
  **healthy 7**(application·gateway·mongo·elasticsearch·embedding·chroma·frontend) + **healthcheck
  없음 2**(worker·generation_worker, by design). "9개 전부 healthy"라고 쓰지 않는다 — 워커 2종은
  구조적으로 healthcheck가 없다.

### Decisions (구현자 판단)

- **볼륨 초기화 범위를 데이터 볼륨으로 국한**(embedding 캐시 보존): 오너 의도 충족하면서 재다운로드 회피.
- **frontend healthcheck는 URL 최소 수정**(nginx listen 미변경): 서빙 동작을 넓히지 않고 거짓 보고만 교정.
- **`.env`는 커밋하지 않는다**: 외부 LLM IP는 베타 머신-로컬 배선이라 repo 정본이 아니다. HANDOFF
  머신 표에는 성질("외부 LLM")로 적고 구체 IP는 머신-로컬로 마킹.

### Next steps

- **A/B 갈림길(오너 대기)**: (A) 실 12B로 파이프라인을 관통시켜 `llm_call_audits`를 적재 → 관측 화면
  육안 검증 가능화 / (B) 빈 상태로 오너가 UI에서 dogfood. 검증자·나 모두 A를 권하되, B-1 정정이 선행.
- 관측 화면 URL: `http://localhost:5520/projects/:id/observability`. DB가 fresh라 지금은 빈 상태만 보인다.

---

## Task — 외부 API 확장성 확인 + 인증/외부 API 브리프 결정 확정 (문서만)

### Goals

- 오너가 인증 착수 전에 "임베딩·리랭커·LLM을 외부 API로 붙일 수 있는 확장성"을 확인 요청.
- 확인 결과를 바탕으로 외부 API 확장 계획(결정 브리프)을 세우고, 인증 브리프의 D1~D8까지 함께 확정.

### 확장성 확인 결과 (코드 실측)

- **LLM**: gateway 경계·OpenAI 호환 wire는 있으나 **인증 헤더 주입 지점 없음**([`httpx_transport.py:37`](../../../services/llm_gateway/app/httpx_transport.py#L37))·provider 선택 config 없음(`LlamaCppProvider` 하드코딩) → keyless OpenAI 호환만 지금 됨(베타 12B가 그 경로).
- **임베딩**: `EmbeddingProvider` Protocol seam 있음, `RemoteEmbeddingProvider`는 인하우스 `/embed` 계약 전용·인증 없음 → 외부는 어댑터 1개 추가 필요.
- **리랭커**: **뉴럴 cross-encoder 리랭커는 없음.** 현재 리랭킹은 **RRF 융합만**([`context_search/service.py:279`](../../../services/application/app/context_search/service.py#L279)). 내가 처음 "리랭커 개념 자체가 없다"고 답한 것은 **틀렸고**(RRF 융합 리랭킹은 있음), 오너 지적으로 정정 — 정확히는 "뉴럴 cross-encoder 리랭커가 없다".
- **Elasticsearch/검색엔진**: 있음(lexical + nori). 벡터(Chroma)+lexical(ES)+RRF 융합이 실제 RAG 구성.

### User Decisions and Rationale — 외부 API 확장 브리프 (신규 `plans/external-api-expansion-decisions.md`)

- **D1 = 세 축 전부 확장, 슬라이스 분리**(LLM → 임베딩 → 리랭커 각각 독립). 오너: "모두 확장이 맞는데 LLM과 임베딩 슬라이스는 별도로." wire·실패모드·조달이 축마다 달라 묶으면 성격이 섞인다.
- **D2=A**(generic OpenAI 호환), **D3=A**(env 키, 인증 시크릿 재사용), **D4=A**(전역 기본 + site별 후속) — 추천안 수용.
- **D5 = 리랭커 포함(유예 해제)**. 로컬 self-host **`dragonkue/bge-reranker-v2-m3-ko`**(임베딩 서비스 패턴) + 외부 리랭커 API도 붙일 `RerankProvider` seam. 오너: "로컬엔 이거 쓰고, 외부꺼도 쓸 수 있게 뚫어놓기." **이 모델은 2026-07-05에 임베딩으로 잘못 지목됐다 유예됐던 바로 그 cross-encoder**가 제 역할로 복귀한 것. 리랭커 API는 공통 wire 표준이 없어(Cohere·Jina·Voyage 각자) provider별 어댑터로 붙는다.

### User Decisions and Rationale — 인증 브리프 D1~D8 (`plans/multi-user-auth-cms-decisions.md`)

- **D1=A**(Application 내부 모듈), **D2=A**(세션+HttpOnly 쿠키) **+ 보안 하드닝**(오너 "인증은 곧 보안"): Argon2id 해시·HttpOnly/Secure/SameSite=Lax·Mongo 서버측 세션(즉시 무효화)·CORS 계속 닫음.
- **D3=A**(`Project.owner_id` 격리). **공유·협업 글쓰기는 미래 확장으로 유예**(오너 "생각 안 해봤다, 나중에") — D3=A가 `members[]`/workspace 승격 문을 닫지 않음. HANDOFF에 미래확장 메모 남김.
- **D4 = 마이그레이션 불요, 개발 데이터 폐기 허용**. 오너: "개발단계라 기존 데이터 싹 날려도 됨, 굳이 하면 A." 정본 보존 정책은 *실 창작물* 보호이지 *개발 테스트 데이터*가 아니며 오늘 볼륨을 이미 초기화해 귀속 대상이 사실상 없다. **실 데이터가 쌓인 뒤면 A(부트스트랩 관리자 귀속)로 되돌린다**는 조건 명시.
- **D5=A**(2단계 archive→관리자 영구삭제) **+ 파기=all delete(전체 그래프)**. 오너: "영구보존은 *작업* 층위, CMS 삭제는 *관리* 층위(작업 상위)라 진짜 삭제, all delete가 맞다." 부분 삭제(고아 데이터) 금지가 이 결정으로 확정.
- **D6=A**(최소 관리자, additive).
- **D7=A**(dependency + 전수 가드) — **오너가 "보안 중점으로 구현자 선택" 위임**. 보안 근거: 실패 모드가 데이터 유출이라, 미들웨어(B)는 소유권(데이터 기반) 검사 불가·신규 경로 조용히 열림, 서비스층(C)은 시그니처 오염. A만이 authn+authz를 경계에서 강제하고 누락을 green으로 통과 못 하게 하는 fail-closed 전수 가드를 얹는다(H3·관측 조립 가드 선례).
- **D8 = 브리프 7단계 유지**(D4가 마이그레이션 불요라 2단계 축소). 오너 미명시 → 구현자 제안 유지, 이견 시 조정.

### Decisions (구현자 판단)

- **두 브리프 다 "결정됨/착수 대기"로 상태 전환**하되 코드·스키마·정본은 안 건드렸다 — 착수는 인증 슬라이스이고, 각 슬라이스가 자기 계약을 정본에 함께 적는 것이 이 repo 규칙이라 지금 정본을 미리 고치면 "문장뿐인 계약"과 "선 코드"가 섞인다.
- **D7·D4·Argon2id·D8은 구현자 판단이 들어간 지점**이라 브리프·work_log에 근거를 명시하고 오너가 veto할 수 있게 남겼다.

### Next steps

- 오너 확인 후: 인증 슬라이스 D8-1(사용자·세션 저장 + 로그인 API)부터 착수. 그 뒤 외부 API(LLM→임베딩→리랭커), 시크릿은 인증 산출물 재사용.
- dogfood(★)와 인증의 선후는 아직 열려 있음(오너 "인증 먼저"지만 dogfood를 앞에 끼울지 미결).

---

## Task — 인증 D8 슬라이스 1 구현 (1a 저장 · 1b 세션 · 1c 엔드포인트)

### Goals

- 오너 "준비되었으면 작은거부터 진행하자" → D8 슬라이스 1을 세 증분으로 쪼개 착수.
- **비-목표(의도적)**: 인가는 넣지 않는다. 소유권(D3)·시행(D7) 전에 잠그면 `owner_id`가 없는
  기존 데이터에서 오너가 잠긴다. 이 비-목표를 회귀로 못박았다(`SliceBoundaryTest`).

### Completed work

- **1a — User 저장 + Argon2id**(커밋 `bd702c4`): `auth/models.py`(User) ·
  `auth/password.py`(`PasswordHasher` Protocol + `Argon2PasswordHasher`, `Type.ID` 명시 고정) ·
  `auth/users.py`(Protocol repo · InMemory fake · `UserService`) · `auth/users_mongo.py`
  (username unique 색인, `DuplicateKeyError`→`DuplicateUsername`). requirements에 `argon2-cffi`.
- **1b — 세션 저장**(커밋 `451c8ef`): `Session`은 **raw 토큰이 아니라 `token_hash`(sha256)만** 보관
  — DB 유출이 live 세션을 넘기지 못한다. `SessionService`(create/resolve/revoke/revoke_all_for_user),
  Mongo는 `user_id` 색인(force-logout) + `expires_at` TTL 색인.
- **1c — 엔드포인트**(커밋 `5db69b0`): `POST /auth/login`(HttpOnly 쿠키 발급) ·
  `POST /auth/logout`(서버측 폐기, 세션 없어도 200 멱등) · `GET /auth/me`.
  `auth/cookies.py`가 쿠키 정책 단일 지점(HttpOnly·SameSite=Lax·Secure·path).
  `scripts/create_user.py`(관리자 API 전까지 첫 계정을 만드는 유일한 경로, 비밀번호는 env로).
  operation 62→65, `schema.d.ts` +194.

### Issues found — 라이브 검증이 유닛 테스트가 못 잡은 배포 파손을 잡았다

**증상**: 실 스택에서 `GET /auth/me`가 유효 쿠키로 **500**. 로그인(쓰기)은 정상이라 겉보기엔 동작.

**원인**: **pymongo는 BSON 날짜를 naive로 돌려준다**(client가 `tz_aware=True`가 아닌 한).
`SessionService.resolve`가 그 naive `expires_at`을 aware `datetime.now(UTC)`와 비교 →
`TypeError: can't compare offset-naive and offset-aware datetimes` → 500.
**즉 실 Mongo에서 세션 인증이 통째로 불능**이었다.

**왜 스위트가 green이었나**: fake collection 테스트가 aware datetime을 넣고 aware로 돌려받았다.
fake가 드라이버의 실제 동작을 재현하지 않아 **배포만 깨진 채 초록**이었다 — 이 저장소가 반복해서
배운 "green이 계약을 검증한다는 뜻은 아니다"의 저장소 계층판.

**수정**: BSON→도메인 경계(`_entry`)에서 UTC 재부착. `tz_aware=True` 클라이언트 대신 이 지점을 고른
이유는 **주입된 client도 커버**하기 때문이다(`from_uri` 설정은 주입 경로를 놓친다). BSON이 UTC를
저장하므로 이것은 변환이 아니라 **재라벨링**이다.

**회귀**: fake collection이 이제 **드라이버처럼 naive를 돌려주고**, 4건으로 양방향을 잠갔다 —
① 읽은 값이 aware인가 ② 서비스 `resolve`가 안 터지는가(실패 경로 그대로) ③ **순간이 이동하지
않는가**(tz *변환*이었다면 만료가 조용히 밀린다) ④ 이미 aware인 값은 안 건드리는가.
**mutation 실증**: 수정을 되돌리면 3건이 실패하고 `sessions.py:85`에서 라이브와 **동일한
TypeError**가 재현된다. 복원은 `cp`(백업)로 했다 — `git checkout <path>`는 미커밋 작업을 지운다(07-26 교훈).

### Issues found — 패턴 sweep (§4)

같은 "Mongo 날짜를 파이썬에서 now와 비교" 패턴을 repo 전체에서 훑었다. 후보 3곳
(`writing/generation_job.py:195`, `indexing/service.py:819`·`:821`)은 **전부 무해**했다 —
그 비교는 **in-memory repo 구현 안**에 있고, Mongo 경로는 같은 판정을 **쿼리 서버측**
(`{"$lte": ...}`)에서 한다(`generation_job_mongo.py:85`, `indexing/mongo_repository.py:130-136`).
즉 Mongo 날짜를 파이썬으로 끌어와 비교하던 곳은 내 세션 코드가 유일했다. 기존 결함 0건.
`users_mongo.py`의 `created_at`은 비교하는 곳이 없어 버그는 아니나, 같은 슬라이스에서 내가 쓴
코드라 동일하게 정규화해 두었다(향후 비교가 이 버그를 재도입하지 못하게).

### Verification

- **라이브 관통**(베타 머신, 실 Mongo·실 Argon2id): 이미지 rebuild → `argon2-cffi 23.1.0` 이미지 내
  확인 → `scripts/create_user.py`로 첫 관리자 생성 → 8단계 전부 통과: 로그인 200(Set-Cookie에
  `HttpOnly; Max-Age=604800; Path=/; SameSite=lax; Secure` 확인) · 쿠키로 me 200 · 쿠키 없이 401 ·
  오답 401 · 미존재 사용자 **동일 메시지** 401 · 로그아웃 200 · 로그아웃 후 me 401 ·
  **세션 없이 `/projects` 200(비-목표 확인)**.
- **회귀 전량**(naive datetime 수정 반영 후): backend **1609 passed / 1 skipped / 623 subtests**.
  직전 커밋 기준선 1556/612 대비 **+53 passed / +11 subtests**. 분해: 신규 auth **50**(1a~1c 46 +
  naive datetime 회귀 4) + **skip 정책 차이 3**(이 베타 머신에는
  `elasticsearch` 파이썬 패키지가 있어 HANDOFF가 적어 둔 lexical 3건이 skip되지 않는다).
  `-rs`로 잔여 skip 1건이 상시 skip인 live Chroma임을 확인했다. 설명되지 않는 증감 0.
- **프론트**: `gen:api` 후 `tsc` 0 · build 성공(**진입 401.19 kB 무변** — 이 슬라이스는 프론트 코드 0,
  로그인 화면은 D8-4) · `vitest` **207 passed / 14 files**(기준선과 동일).
  (참고: 이 머신은 `node_modules` 미설치라 `npm install`이 선행 필요했다 — recharts 부재로 tsc가
  실패했던 것이며 코드 문제가 아니었다.)

### Decisions (구현자 판단)

- **`Secure` 쿠키 기본 on**(fail closed). 브라우저가 `http://localhost`를 신뢰 출처로 취급하므로
  로컬 http 개발도 그대로 동작한다 — 기본값을 낮추지 않고도 개발이 되는 드문 경우라 그렇게 했다.
  해제는 `AUTH_COOKIE_SECURE`로만. **테스트는 `https://testserver` base_url을 쓴다** — http였다면
  httpx가 Secure 쿠키를 조용히 버려 세션 테스트가 엉뚱한 이유로 통과/실패했을 것이다(실제로 처음
  4건이 그렇게 실패했고, 그래서 배포 구성을 그대로 시험하는 쪽으로 고쳤다).
- **로그인 실패 메시지를 하나로 통일**하고 `UserService.authenticate`에 **열거 방지 더미 verify**를
  넣었다. 미존재/비활성이 오답보다 빠르면(Argon2는 의도적으로 느리다) 사용자명 존재가 타이밍으로
  샌다. 메시지 동일성은 over-strict 회귀로 잠갔다.
- **`AUTH_SESSION_TTL_HOURS`가 0 이하면 기동 거부**. 조용한 fallback은 무한 세션을 만들 수 있고,
  그건 보안 결함이라 fail-fast가 맞다.
- **부트스트랩 스크립트를 이 슬라이스에 포함**했다. 관리자 API(D8-5) 전까지 계정을 만들 방법이
  없으면 로그인 엔드포인트가 배포에서 검증 불가능한 죽은 코드가 된다. 비밀번호는 argv가 아니라
  env로 받는다(shell history·`ps` 노출).

### Next steps

- **D8-2**: `Project.owner_id` + (D4에 따라 마이그레이션 없이) 필드 도입. 그다음이 **D8-3 인가 시행 +
  전수 가드**로 가장 큰 단계.
- 실행 메모: 컨테이너에서 스크립트를 돌릴 때 **`PYTHONPATH=/app`이 필요하다**(이미지에 PYTHONPATH가
  없고 `python scripts/x.py`는 CWD를 sys.path에 넣지 않는다).

### 독립 검증 반영 — 슬라이스 1 (조건부 합격 → 조건 B-1 해소, 비차단 2건 함께 조치)

오너 요청 독립 검증(`docs/verifications/2026-07-27/auth_d8_slice1.md`)이 **조건부 합격**.
검증자가 서브에이전트 4개 + 직접 실측으로 적대 검증했고, 기준선(1609/1/623)·tz 수정(메커니즘·실
Mongo 라이브·mutation 삼중)·Argon2id·토큰 엔트로피·쿠키 정책·비-목표·CORS 폐쇄·패턴 sweep을 전부
재도출해 **작업자 주장과 일치**함을 확인했다. 조건 1건만 남았다.

- **B-1(차단, 해소함) — 타이밍 열거 방지가 코드는 시행되나 회귀로 안 잠겨 있었다.** 내가
  `users.py`의 더미 verify를 **배포 보안 조치로 주장**해 놓고, 테스트 fake가 호출을 기록하지 않아
  **그 줄을 통째로 지워도 스위트가 green**이었다. 세 실패 경로가 전부 `None`을 반환하므로
  `assertIsNone` 계열로는 원리적으로 안 잡힌다 — **"verify가 실제로 수행됐는가"로만 잠긴다**.
  - `_FakeHasher`가 `verify_calls`를 기록하게 하고 `EnumerationHardeningTest` 3건 추가:
    ① **오답·미존재·비활성의 verify 횟수가 동일**(성질 자체) ② 더미 verify가 **실 사용자 해시가
    아닌 throwaway**를 쓴다(over-strict — 실 해시로 맞추면 운 좋은 비밀번호가 비활성 계정에
    맞을 수 있다) ③ **정상 로그인은 여전히 저장된 해시로 검증**한다(over-strict 반대 방향 — 가드가
    실 검사를 대체하면 안 된다).
  - **mutation 실증**: 가드 줄을 지우면 ①③ 중 2건이 실패한다(미존재/비활성의 verify 수가 0으로
    떨어짐). 복원은 `cp` 백업.
- **H-1(비차단, 조치) — 기본 토큰 엔트로피 미잠금.** 다른 모든 테스트가 `token_factory`를 주입해
  기본값이 저엔트로피로 바뀌어도 green이었다. D2가 "DB 유출로 live 세션 부활 불가"를 토큰 추측
  난이도에 의존하므로 기본 팩토리의 **유일성 + 길이 43자**(`token_urlsafe(32)`)를 잠갔다.
- **H-2(비차단, 조치) — 비-목표를 전수로 잠갔다.** `SliceBoundaryTest`가 62개 중 3개만 표본이었다.
  OpenAPI를 순회해 **비-`/auth` operation에 `security` 키도 401 선언도 없음**을 단언한다. 401을
  함께 본 이유는 H3가 realistic 상태의 전수 선언을 강제하므로 **인가가 들어오면 401이 반드시
  나타나기** 때문 — FastAPI가 `security` 키를 안 내는 dependency 형태여도 잡힌다.
  **mutation**: 비-auth endpoint 하나에 401 선언을 붙이면 이 테스트가 실패한다.
  D8-3이 오면 이 테스트는 **실패하는 것이 정상**이고, 그 실패가 비-목표 종료의 표지다(삭제가
  아니라 역명제로 다시 쓰라고 본문에 적었다).
- **미조치(근거 있음)**: H-3(login이 기존 세션 revoke 안 함 → 동시 세션)은 정본이 single-session을
  요구하지 않고 D6/D7에서 볼 설계 사안이라 두었다. H-4(세션 없는 logout의 `Set-Cookie`)는 미관.
  H-5(Argon2 파라미터 단언)는 라이브러리 기본값을 테스트에 박는 것이라 업그레이드마다 깨질 수 있어
  두었다. H-6(다른 repo의 naive 날짜)는 비교처가 없어 무해하며 **HANDOFF 함정 절에 이미 규칙으로
  적혀 있다**(향후 비교 추가 시 `_entry` 경계에서 재부착).
- **정리**: 검증자가 라이브 검증용으로 만든 `liveprobe` 사용자를 dev DB에서 삭제했다(`owner`만 남음).
- **회귀**: **1614 passed / 1 skipped / 623 subtests**. 검증 시점 1609 대비 **+5 = 신규 5건**(열거 방지 3 · 토큰 엔트로피 1 · 비-목표 전수 1)과 정확히 일치. subtests 무변. 설명되지 않는 증감 0.

---

## Task — 인증 D8-2 소유권 기록 (2a 필드 · 2b 배선)

### Goals

- 오너 지시: **"한번에 너무 많은 슬라이스를 하려고 하지 말고 작은 단위로 차례차례."** 그래서 D8-2를
  다시 둘로 쪼갰다 — **2a(필드·저장)** 와 **2b(세션에서 채우기)** 를 각각 독립적으로 green·커밋.
- 비-목표(유지): 인가는 여전히 없다. 소유자는 **기록만** 되고 아무도 그것으로 접근을 막지 않는다.

### Completed work — 2a (커밋 `7ffd615`)

- [`core_sot/models.py`](../../../services/application/app/core_sot/models.py) `Project.owner_id:
  str | None = None`. **nullable이 의도**다 — 인증 이전 프로젝트는 소유자가 없고 시행은 D8-3이다.
- [`mongo_repository.py`](../../../services/application/app/core_sot/mongo_repository.py)
  `_project_doc`/`_to_project`. 읽기는 **`.get`** — 배포 DB의 기존 문서에는 키 자체가 없다.
- [`service.py`](../../../services/application/app/core_sot/service.py)
  `create_project(name, owner_id=None)`. optional이라 worker·script·기존 테스트가 전부 무변.
- **회귀 신규 3(실 Mongo)**: 소유자 왕복(**get·list 두 디코더 각각**) · 미지정 시 None 유지
  (over-strict — 자리표시자를 넣으면 D8-3이 "소유자 없음"을 실제 user id로 오인한다) ·
  **`owner_id` 키가 아예 없는 legacy 문서가 unowned로 읽힌다**(배포 DB의 현재 모양 그대로).
- **공개 API 무변** 실측: `gen:api` 후 `schema.d.ts` no diff.

### Completed work — 2b

- [`main.py`](../../../services/application/app/main.py) `POST /projects`가 `_current_user`로 세션을
  해석해 **있으면 생성자를 owner로 기록, 없으면 unowned**. **401로 만들지 않은 것이 핵심** — 인증은
  D8-3 전까지 선택이고, 여기서 필수로 만들면 이 슬라이스가 실수로 시행 슬라이스가 된다.
- **회귀 신규 4**: 로그인 후 생성 → owner 기록 · **익명 생성이 401이 아니라 200 + unowned**
  (over-strict, 슬라이스 경계) · **owner_id를 공개 payload에 노출하지 않음**(노출은 공개 계약 변경이라
  프론트가 읽을 이유가 생길 때 = 2c) · **로그아웃 후 생성은 unowned**(소유자는 *살아 있는 세션*에서
  오지 "한때 로그인했었다"에서 오지 않는다).
- **mutation**: owner 배선을 `owner_id=None`으로 되돌리면 해당 회귀 1건이 정확히 실패한다.
- **공개 API 무변** 실측: `gen:api` 후 `schema.d.ts` no diff.

### Decisions (구현자 판단)

- **2c(소유자 공개 노출)를 하지 않았다.** `owner_id`를 payload에 넣으면 `schema.d.ts`가 바뀌는
  공개 계약 변경인데, 지금 그것을 읽을 소비자가 없다(§2). 프론트가 "내 프로젝트" 같은 화면을 요구할
  때 그 슬라이스와 함께 넣는 것이 맞다.
- **`create_project`의 `owner_id`를 optional로 뒀다.** required로 만들면 worker·script·기존 테스트가
  전부 깨지고, 그건 이 슬라이스가 감당할 범위가 아니다. required 승격은 D8-3의 판단.

### Next steps — D8-3 착수자에게

- 재료는 다 있다: `_current_user(request)` + `project.owner_id`.
- **첫 결정**: `owner_id=None`인 legacy 프로젝트를 어떻게 다룰지. "소유자 불일치면 거부"만 쓰면
  주인 없는 데이터가 **아무에게도 안 열리거나 모두에게 열린다**. D4가 "개발 데이터 폐기 허용"이라
  폐기 후 시작도 선택지다.
- 잠금은 dependency + **전수 가드**(D7). 그리고 `test_no_non_auth_operation_is_protected_yet`이
  **그때 실패하는 것이 정상**이다 — 삭제하지 말고 역명제로 다시 쓴다.

### Verification (2a·2b 합산)

- **회귀 전량**: **1627 passed / 1 skipped / 623 subtests**. 직전 1614 대비 **+13**이고 분해가
  정확히 맞는다 — 2a의 신규 3건이 `_MongoContractMixin`의 **서브클래스 3개**(Fallback·Transaction·
  WritingIntent)에서 각각 도는 **9** + 2b의 **4**. subtests 무변. 설명되지 않는 증감 0.
- **공개 계약**: 2a·2b 각각 `gen:api` 후 `schema.d.ts` **no diff**(두 슬라이스 다 API 무변이 성공 기준).

### 독립 검증 반영 — D8-2 (합격·차단 0건, 전향 보강 1건 조치) + D8-3 브리프

오너 요청 독립 검증(`docs/verifications/2026-07-27/auth_d8_slice2_owner_id.md`)이 **합격(차단 0)**.
검증자가 기준선 재실행(1627/1/623)·mutation·**병렬 디코더 sweep**(`Project(` 생성처가 정확히 2곳이며
둘 다 owner_id 처리 → owner_id를 조용히 떨구는 우회 디코더 부재)까지 독립 재도출해 전부 일치했다.
직전 슬라이스의 조건 B-1(+H-1·H-2)도 `c982ecd`로 닫힌 것이 함께 확인됐다(루프 클로즈).

- **H-2(전향 주의 → 구조적으로 해소).** 검증자는 "메모"로 남기자고 했으나 **가드 자체를 고쳤다**:
  `test_no_non_auth_operation_is_protected_yet`이 `401`에만 키를 두고 있어, D8-3이 **403만 쓰는
  설계**를 하면 비-목표 잠금이 **조용히 발화하지 않는다**. 신호에 `403`을 더해 세 신호
  (`security`·401·403) 중 무엇이든 걸리게 했다. 403은 현재 OpenAPI에 **0회** 등장하므로 필터가
  아니라 정확한 단언이다. **mutation**: 비-auth endpoint에 403 선언만 붙여도 가드가 실패하는 것을
  확인했다. 메모 대신 코드로 잠근 이유는 — 메모는 다음 작업자가 읽어야 작동하지만 가드는 안 읽어도
  작동하기 때문이다.
- **H-1(미조치, 근거)**: legacy 문서 회귀가 `self.repo._projects`로 private 컬렉션에 직접 심는다.
  공개 API로는 "owner_id 키가 없는 문서"를 만들 방법이 없고, **같은 파일의 기존 legacy brief 테스트가
  이미 같은 패턴**(`self.repo._project_briefs`)이라 저장소 관례에 맞다. 관례를 이 슬라이스에서 바꾸는
  것은 §3 위반이라 두었다.

**D8-3 결정 브리프 작성**(`plans/auth-d8-3-enforcement-decisions.md`): 검증자 권고대로 코딩 전에 썼다.
착수 전 실측 5건을 근거로 깔았는데 그중 둘이 계획을 바꿨다 —
① **워커는 HTTP API를 쓰지 않는다**(Mongo 직접, `index_sync_worker.py:85·261`) → 인증 브리프가 예상한
"서비스 계정"은 D8-3이 아니라 **인프라 인증(D8-7)** 사안이다.
② **프론트는 API를 쓴다** → D8-3이 들어가는 순간 로그인 화면이 없어 전부 401이 된다. 이 사실이
**E4(로그인 화면을 D8-3보다 먼저 할지)** 라는 결정 항목을 새로 만들었다 — 원래 D8 순서에는 없던
질문이고, 실측 없이 순서대로 갔으면 dogfood 불가 기간을 만들었을 것이다.
결정 4건(E1 legacy `owner_id=None` 처리 ★차단 · E2 인증 vs 소유권 범위 · E3 분할 방식 · E4 순서),
추천 각각 A. **E1은 어느 선택지든 코드가 `None`을 deny로 다루는 것이 필수**임을 명시했다 — 폐기는
"지금 그런 행이 없다"만 보장하고 "앞으로 안 생긴다"는 보장하지 않기 때문이다(2b가 익명 생성을
여전히 허용한다).
