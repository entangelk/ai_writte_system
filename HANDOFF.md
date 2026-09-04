# HANDOFF

> **다음 작업자가 지금 일을 시작하는 데 필요한 것만.** 이력이 아니다.
> **공개 저장소 보안 규칙:** 원격 배포 대상의 IP·호스트명·계정명·SSH 키 경로·서버 내부 절대경로·구체 토폴로지·비밀값을 `HANDOFF.md`·`docs/daily_logs/`·`docs/verifications/`·`CHANGELOG.md` 등 저장소 문서에 기록하지 않는다. 배포 기록은 역할 별칭과 민감정보를 제거한 결과만 남기고, 실제 접속 정보는 저장소 밖에서 관리한다.
> **완료 서술도, 근거·측정치·발견 경위도 여기 쓰지 않는다** — `docs/daily_logs/`(상세) · `docs/system-contract-sot.md` 변경이력 · `CHANGELOG.md`(마일스톤) · `docs/verifications/`(독립 검증) · `docs/plans/*-decisions.md`(왜 그렇게 정했는가)에 있다. **여기 남는 것은 "지키지 않으면 깨지는 것"과 "어디를 보면 되는가"뿐이다.**
> 편집 규칙은 `CLAUDE.md`·`AGENTS.md`의 "HANDOFF.md" 절에 있다. **~200줄을 넘으면 자가 검수**하고(그 뒤로는 ~100줄마다) 결과를 아래 한 줄로 남긴다.
>
> 마지막 자가 검수: **2026-09-05 · 742줄/222KB → 354 → 244줄/48KB**(2차, 오너 지시 *"착수할 수 있는 문서"*. +4줄은 같은 날 docs 고아 전수와 서비스 정책 문서 등재) — 1차는 완료 서술 12개 메모(336줄)와 닫힌 부채 12항목을 걷었고, 2차는 **분류를 고쳤다**: ① 부채 절에 있던 11항목이 실은 계약·규칙·주의였다 → 각 절로 이관 ② "지금 상태"의 절차·하우투 5건을 "코드를 만질 때의 규칙"으로 분리 ③ 모든 항목에서 **근거·측정치·발견 경위를 걷어내고** 정본 포인터로 대체 ④ 낡은 사실 정정(`AUTH_SESSION_TTL_HOURS` 부채는 이미 닫혀 있었다 · `docs/plans` 106/88 → **121/100** · 4000 상수는 `DraftEditor` 가 아니라 `tokenEstimate.ts`).

## 머신 · 기동

이 프로젝트는 성격이 다른 세 머신을 옮겨 다닌다. **문서가 "환경과 안 맞는다"고 느껴지면 먼저 지금 어느 머신인지 본다.** 표는 각 머신이 *무엇을 띄울 수 있는지*(항구적 성질)이지 *지금 무엇이 떠 있는지*가 아니다 — 후자는 `docker compose ps` 로 그 자리에서 잰다.

| 머신 | 역할 | LLM | GPU |
|---|---|---|---|
| **알파** | 서비스 배포용 | in-stack llama(`docker-compose.llama.yml`) | RTX 3060 12GB |
| **베타** | 테스트·개발용 | 외부 LLM(gemma-4-12B, LAN) — 주소·context는 `.env`·`/props` 로 잰다 | GTX 1060 3GB(12B 못 올림) |
| **감마** | 사이드 개발용(노트북) | 없음 — LLM 관통 작업 불가 | — |

- **2026-09-05 현재 알파다**(오너 확인). 09-04 까지의 작업·회귀 기준선은 베타에서 잰 것이고, 두 라벨은 충돌이 아니라 전환이다. **머신-로컬 수치(전수 소요·VRAM)를 다른 머신 값과 비교하지 말 것.**
- **어느 머신에서든 `docker compose up` 만으로 같은 포트로 뜬다.** 머신별로 달라지는 것은 **LLM을 어디서 얻느냐**뿐이다.

| 기동 방식 | 명령 | 모델을 어디서 |
|---|---|---|
| **기본**(베타·감마) | `docker compose up -d` | 외부 LLM(`.env` 의 `LLAMA_BASE_URL`) + in-stack 임베딩·ES·chroma |
| **in-stack 모델**(알파) | `… -f docker-compose.llama.yml up -d` | 전부 스택 안. **`LLAMA_CTX_SIZE=16384` 확인**(함정 절) |
| **외부 API 전용**(배포) | `… -f docker-compose.external.yml up -d` | 전부 밖. `embedding`·`chroma`·`elasticsearch` 가 profile 뒤로 가 **기동도 빌드도 안 된다** |

**★ LLM을 어디서 얻는지는 빌드 옵션이 아니라 *어느 override를 얹느냐* 이고, 모델은 빌드가 아니라 첫 기동에 받는다.** 오너 규칙: ① env에 외부 API가 있으면 그것 ② 없으면 내부 모델 다운로드 시도 ③ 실패하면 기동 중단. **"별도 compose"를 완전한 두 벌로 만들지 말 것** — 복제는 dev 수정이 배포에 안 따라가고 배포에서만 드러난다.

**포트**(repo 고정, 근거는 [`.env.example`](.env.example) 상단): application 8520 · gateway 8521 · embedding 8522 · chroma 8523 · elasticsearch 9520 · frontend 5520 · mongo 27520 · test-mongo 27020 · **admin 은 게시 없음**(nginx `/api/admin/` 경유 전용).

**테스트**
- 백엔드: `docker compose -f docker-compose.test.yml up -d` 후 `python3 -m pytest -q`. **`pytest` 가 아니라 `python -m pytest`.** `python3 -m pip install -r requirements-dev.txt` 선행(안 하면 `test_typecheck.py` 가 skip이 아니라 **실패**).
- 프론트: `cd frontend && npm run gen:api && npx tsc --noEmit && npm run build && npx vitest run`.
- live Chroma(호스트에서 항상 skip되는 1건): `docker compose run --rm --no-deps -v "$PWD/tests:/app/tests" -e CHROMA_TEST_URL=chroma:8000 application python -m unittest tests.test_chroma_adapter.ChromaAdapterLiveTest -v`
- 창 가드 라이브(K-3): `docker compose run --rm --no-deps -v "$PWD/scripts:/app/scripts" -e PYTHONPATH=/app application python scripts/gateway_generate_live_smoke.py --gateway-base-url http://gateway:8001`. `context_window_guard.exercised: false` 는 실패가 아니라 **창을 아직 몰라 판정 대상이 아니었다**는 뜻이다.

**스택 health**: 정상은 **healthy 8**(application·**admin**·gateway·mongo·elasticsearch·embedding·chroma·frontend) + **healthcheck 없는 2**(worker·generation_worker — by design, "Up"이지 healthy 아님). **"전부 healthy"라고 쓰지 않는다.**

**이미지**: `application`·`admin`·`worker`·`generation_worker` 네 서비스가 **같은 `image: ai_writte_system-app` 태그**를 공유하므로 `docker compose build` 한 번이면 넷이 갱신된다. **새 서비스가 이 Dockerfile 을 쓰면 `image:` 를 함께 적는다.** 인증 백엔드 변경은 application, 로그인 UI 변경은 frontend rebuild가 필요하다.

## 지금의 계약

정본은 [`docs/system-contract-sot.md`](docs/system-contract-sot.md) **v1.8.29**(Approved). **미확정 항목은 추측 구현하지 않는다.** 아래는 코드를 만지기 전에 알아야 하는 요약이다.

- **배포되는 앱이 둘이다.** `/admin` **17 operation**은 포트를 게시하지 않는 `admin` compose 서비스가 서빙하고 도달 경로는 nginx `location /api/admin/` 하나다. 제품 앱에는 그 route가 **없으므로** LAN에서 치면 가드가 아니라 **라우터가 404**다. `create_app()` 은 **102 operation 합집합**이고 테스트·경계 행렬·`dump_openapi.py`(= 프론트 `schema.d.ts`)가 전부 그것을 쓴다 — 브라우저는 nginx 뒤에서 한 origin만 보므로 **계약은 하나여야 한다**. 세 factory(`create_app`·`create_product_app`·`create_admin_app`)는 **한 함수 본문**이고 플래그로만 갈린다. 가드 [`test_admin_surface_separation.py`](tests/test_admin_surface_separation.py).
- **operation tier = 전체 102 · project 76 · admin 17**([`test_auth_api.py:1910`](tests/test_auth_api.py#L1910) 핀이 정본).
- **인증·인가.** 세션 없는 요청은 `/health` 와 공개 `/auth` 를 빼고 401. project-scoped 76은 타인 소유·`owner_id=None` 에 403(**`owner_id=None` 은 항상 deny**). `GET /projects` 는 Mongo `owner_id` 쿼리 경계에서 본인 소유만 반환한다. **403 생산자는 넷** — 소유권([`dependencies.py:132`](services/application/app/api/dependencies.py#L132)) · 관리자([`:291`](services/application/app/api/dependencies.py#L291)) · 가입 승인 대기/거절([`routers/auth.py:115`](services/application/app/routers/auth.py#L115)) · quota 정지([`:163`](services/application/app/api/dependencies.py#L163)). 가드는 `test_auth_api.py` 의 세 클래스(`AuthenticationBoundaryTest`·`ProjectAuthorizationTest`·`CombinedBoundaryMatrixTest`)이며 **새 endpoint는 셋이 모두 본다**.
- **관리자 경계.** 관리자는 project 내용에 자동 접근하지 않는다 — 내용 조회는 **사유 필수·1시간·읽기 전용 승격**만 가능하고 `owner_id=None` 은 승격으로도 안 열린다. 승격 사용 감사(`access_grant_uses`)는 **fail-closed**. **마지막 활성 관리자는 비활성화되지 않고**(409) 비활성화는 **단방향**이다(재활성화 API 없음). 첫 관리자는 부트스트랩 스크립트로만 만든다: `docker exec -e PYTHONPATH=/app -e AUTH_BOOTSTRAP_PASSWORD='…' <application> python scripts/create_user.py <username> --admin` — **`PYTHONPATH=/app` 이 필수**이고 그 비밀번호는 **1회용**(첫 로그인에 12자 이상 `new_password` 동반).
- **저장소는 LAN에서 안 보인다 — 그러나 인증된 것은 아니다.** `mongo`·`chroma`·`elasticsearch`·`gateway`·`embedding`·`test-mongo` 가 **`127.0.0.1:` 바인드**다. **저장소 자체는 여전히 무인증이라 바인드가 유일한 방어**이고, 일부러 공개인 것은 셋뿐이다(`application`·`frontend` = 세션 뒤 제품 표면 · **`llama` 9080** = 12B를 못 올리는 머신에 모델을 주는 유일한 크로스머신 의존). 가드 [`test_compose_exposure.py`](tests/test_compose_exposure.py) 는 **새 서비스가 포트를 게시하면 분류를 강제**한다. **★ 이것은 파일 수준 시행이라 이미 만들어진 컨테이너는 재생성 전까지 안 닫힌다.**
- **`/docs`·`/redoc`·`/openapi.json` 은 비공개다**(SoT v1.7.98). `create_app` 의 `FastAPI(docs_url/redoc_url/openapi_url=None)` **한 곳**으로 셋 다 차단된다([`main.py:1777`](services/application/app/main.py#L1777)). **env 토글 없음** — 공개가 필요하면 명시 결정으로 연다. 스키마 소비자는 전부 import 방식이라 계약 생성은 무변이다.
- **quota.** 유료 경로에 `Depends(enforce_quota)` 가 붙고 `_REQUIRE_PROJECT_OWNER_BILLABLE` = **소유권 → 시행** 순서다(그 순서가 곧 "404·403은 무과금"). **차감은 `2xx` 그리고 provider 호출이 있었을 때만**(replay처럼 아무 일도 안 한 200은 안 센다). **정산은 dependency의 `yield` 뒤가 아니라 `QuotaSettledRoute` wrapper에 있다 — 벗기면 잠금이 영영 안 풀린다.** 기본 한도는 **일 20 / 주 100**이고 진행 중 요청·대기 job이 그 한도를 차지한다. **관리자도 신분으로는 면제가 아니다**(면제는 `limit=None` 정책 행). 같은 동작 **5초 최소 창**이 있어 스크립트를 연달아 돌리면 429다 — `X-Confirm-Duplicate` 헤더나 5초 대기. **★ [`quota/policy.py`](services/application/app/quota/policy.py) 가 이 저장소의 유일한 지역 시간대(KST) 지점이다** — 창 키 계산을 다른 곳에서 또 하면 화면과 시행이 다른 "오늘"을 말한다. **`policy.limits` 는 유효 한도가 아니다** — 읽기는 항상 `effective_limits`/`limits_for` 를 지난다.
- **파기(purge)와 이름 이력.** 삭제 표면은 셋이다 — 원고 하드 삭제 `POST …/drafts/{did}/purge`(아카이브 선행 409 · **active** 잡 409, **종료된 잡은 막지 않는다**) · 소유자 프로젝트 purge · 관리자 아카이브. **소유자 purge와 admin purge는 `execute_project_purge` 한 벌을 공유한다 — 새 서비스가 파기 그래프에 들어오면 그 함수만 고친다.** UI 503 계약은 양 면 대칭이다: **파기 단계 503 = uncertain 잠금(재시도 금지 · reconciler 확인)**, 재파기 404 = 성공 처리, **보관 단계 실패만** 재시도를 되살린다. **★ `project_name_history` 에 `project_id` 필드를 절대 더하지 말 것** — reconciler가 그 필드로 sweep 대상을 발견하므로 더하는 순간 이 컬렉션이 지워진다. **이름 스냅샷은 파괴 앞이고 fail-closed**(뒤로 옮기거나 `try/except` 로 감싸면 이름 없이 사라지는 프로젝트가 생긴다). **`_id` 충돌은 "잠겨 있음"의 증거가 아니라 신호다** — 충돌 뒤 살아 있음을 다시 확인하고 없거나 만료면 원자적으로 재차지한다.
- **활동 로그.** `activity_events` 는 `project_id` 필드를 쓰고 **파기와 함께 사라진다**(위 `project_name_history` 와 **정반대** — 그쪽의 `_id` 트릭을 여기 복사하면 D8-6이 무너진다). 분류표 [`activity/actions.py`](services/application/app/activity/actions.py) 가 정본이고 **미등재 mutating route는 가드가 실패시킨다**. **기록은 handler 본문에서 결과를 안 뒤**(dependency로 옮기면 404·409가 "했다"로 남는다). **기록 실패는 요청을 안 죽이지만 파기 실패는 삼키지 않는다.** `before`/`after` 는 라벨만(200자) — 본문을 넣으면 `draft_versions` 와 두 정본이 된다.
- **관측(KPI).** LLM 호출부 9종이 seam C(provider 데코레이터)로 계측된다. **실패한 호출도 센다**(성공만 세면 성공률이 영구히 100%). **scope 밖 호출(worker·script)은 기록하지 않는다**(추측 `project_id` 는 오염). per-project와 전역이 `kpi.py` 의 `_fold` **한 곳을 공유**한다 — 한쪽만 고치면 두 화면이 다른 사실을 말한다.
- **에러 계약(H3).** 본문은 균일 `{"detail": <string>}`. 상태코드=기계용·`detail`=사람용이라 **`detail` 문자열로 분기하면 안 된다**. 균일 본문의 유일한 예외는 **partial envelope**이고 허용 지점은 **정확히 6곳**(revise-and-gate 4 · accept 1 · auto-promote 1). 새 endpoint는 `responses=` 와 dependency를 함께 붙이고 tier 전수 가드에 등재한다.
- **길이 상한.** 유닛 본문 **4000자** · 브리프 스칼라(premise·genre·tone·pov) **1000자**. 상수는 [`app/env.py::draft_raw_text_max_chars`](services/application/app/env.py) **하나**이고 저장 축(422)과 accept 축(400)이 같은 상수를 읽는다. **accept의 검증은 provider 호출 앞**이다(상한 넘을 몸에 유료 호출이 돈을 쓰면 안 된다). **프론트는 경고+저장 차단이지 잘라내기가 아니다 — textarea `maxLength` 금지**(정본 보존, no-maxlength 셀이 문다).
- **Chapter/Scene 계층.** metadata-only Chapter + Scene(Draft), parent별 연속 순열, AI는 같은 장의 다음 Scene만. **legacy 평면 Draft는 CRUD·accept가 503 fail-closed(2층)이고 export·versions만 대피 경로로 200**이다 — 대피 경로를 막으면 이관 못 한 데이터가 갇힌다. 공개 `unit_kind` 는 제거됐고 `core_sot` 의 legacy migration 입력으로만 남아 있다.
- **검색과 리랭커.** 벡터(Chroma/BGE-m3-ko) + lexical(ES/nori)을 RRF(`1/(k+rank)`, k=60)로 융합하고 리랭커는 **그 뒤에** 걸린다. **★ 리랭커 표기는 세 조각이고 "있음" 한 단어로 쓰면 거짓이다** — *"외부 API 리랭커 붙일 수 있음(**기본 꺼짐**) · self-host 미구현 · **품질 평가 미실시**"*. `RERANK_API_URL` 이 비면 조립이 감싸지 않고 검색은 RRF까지만으로 동작한다. **실패는 열려 있다(fail-open) — 프로바이더가 아니라 *단계 전체*가 그렇다**(순열 아닌 응답·텍스트 투영 예외 포함). 다만 **조용히 삼키지 않는다**(`logging.WARNING` + `exc_info`) — fail-open이 조용하면 리랭킹이 영원히 no-op인 채로 아무도 모른다.
- **회귀 기준선**: backend **test-mongo ON 2803 passed / 1 skipped / 3189 subtests**(2026-09-04 베타). **skip 1 = live Chroma**이며 **전수 판정은 `passed` 가 아니라 `skip` 수를 먼저 본다.** **★ 최상위 [`README.md`](README.md) 절차 표의 `N passed / N subtests` 는 아무 가드도 안 잡는다** — 기준선을 갱신하는 슬라이스가 그 한 줄도 함께 고친다.

## 함정 (모르면 시간을 잃는 것들)

**기동·환경**
- **`test.yml up -d` 직후 곧바로 전수를 돌리면 Mongo 셀 11개가 조용히 skip 된다 — 요약줄은 초록이다.** 복제셋이 writable PRIMARY가 될 때까지 기다린다.
- **오래된 `application` 이미지는 죽지 않는다. 조용히 *인증 없는 제품*으로 뜬다.** auth 이전 이미지는 `argon2` import 자체가 없어 healthy를 보고하는데 `/auth/login` 이 404이고 `GET /projects` 가 세션 없이 200이다. **규칙: 스택을 올린 뒤 `curl :8520/projects` 가 401인지 먼저 본다.** 트리 마운트는 코드만 덮고 파이썬 패키지는 이미지 것이다.
- **알파에서는 `.env` 에 `LLAMA_CTX_SIZE=16384`.** 기본은 [`docker-compose.llama.yml:29`](docker-compose.llama.yml#L29) 의 8192이고 `.env.example` 에 항목이 없다. R-e 이후 이유가 바뀌었다 — "안 죽게"가 아니라 **"K-3 가드에 400으로 거부당하지 않으려고"**다.
- **외부 API 배포에서 `.env` 에 `LLAMA_DEFAULT_MODEL` 이 없으면 앱이 `gemma-local` 을 명시해 LLM 호출이 전멸한다.**
- **compose의 포트 매핑 변경은 이미 만들어진 컨테이너에 적용되지 않는다 — `up -d` 로도 안 된다.** 재생성이 필요하다.
- **compose의 `${}` 표기는 취향이 아니라 코드가 그 변수를 읽는 방식을 따라간다.** `if not os.environ.get(name)` 로 읽으면 **dash `${VAR-default}`**, `os.environ.get(name, DEFAULT)` 로 읽으면 **콜론 `${VAR:-default}`**. 다른 40여 항목이 콜론이라 "통일"하고 싶어지는데 **그 통일이 곧 회귀**이고 양방향 다 셀이 문다. **두 방향 모두 배포에서만 드러난다.**
- **`CHROMA_PORT` 를 env화하지 말 것** — 같은 이름이 host publish에서는 호스트 포트를, environment에서는 컨테이너 내부 포트를 뜻한다. 외부 Chroma는 override 파일로 붙인다.
- **`ulimits.nofile` 은 튜닝이 아니라 필수다**(기본 1024면 WiredTiger가 mongod를 죽인다).
- **출시된 프롬프트 본문은 immutable이다** — 오래된 데이터 볼륨과 현행 프롬프트 핀이 충돌하면 `PromptTemplateConflict` 로 앱이 죽는다. 볼륨을 비우는 것이 처방이다(embedding 모델 캐시는 보존).
- **`docker-compose.llama.yml` 의 `-hf …:Q4_0` 은 리비전을 고정하지 않는다** — 캐시에 온전한 모델이 있어도 업스트림 `refs/main` 이 움직이면 **~6.5GB를 다시 받는다**. llama healthy가 `up -d` 전체의 관문이라, 급하면 `--no-deps` 로 분리 기동한다.
- **호스트 도구 공백**: 일부 호스트에 `python` 이 없고 `python3` 만 있다 · `pyflakes` 가 없고 `pip install --user` 가 PEP 668로 거부된다(**`--break-system-packages` 말고 scratchpad venv**) · **Mongo DB 이름은 `ai_writing_system`** 이다(`ai_writing` 아님 — 그 이름으로 조회해 "DB가 비었다"는 거짓 판독을 한 번 냈다).
- **첫 `docker` 명령이 30초 넘게 안 돌아올 수 있다**(데몬 워밍업). **라이브 검증은 재빌드 말고 작업 트리를 마운트해 돌린다**: `docker compose run --rm --no-deps -v "$PWD/services:/app/services" …`.
- **외부 API 벤더에 붙일 때 넷**: ① OpenAI 호환 벤더엔 `LLAMA_API_FORMAT=openai` **필수**(llama.cpp 전용 필드를 400으로 거부 — 추론 금지) ② 그 형식에서 게이트웨이가 `<thought>` 를 걷는데 **짧은 `max_tokens` 로는 사고가 예산을 다 써 빈 답**이 온다 ③ **임베딩은 `EMBEDDING_API_FORMAT=openai` 로 명시해야 외부 API로 나간다 — 키만 넣으면 안 바뀐다**(일부러 그렇다. 키 유무로 형식을 추론하면 키를 지운 순간 형식이 조용히 바뀌고 그 실패는 원인에서 가장 먼 자리에 404로 떨어진다). 차원 전환 절차는 README에 있다 — **규칙은 "차원이 바뀌면"이 아니라 "모델이 바뀌면 재색인"**이다(차원이 다르면 fail-fast로 멈추지만 **차원이 같은 다른 모델이면 아무 일도 안 일어나고 품질만 조용히 떨어진다**) ④ 무료층 한도는 **프로젝트 단위 집계일 수 있다**(키 회전이 한도를 곱하지 않을 수 있다).
- **`/props`·`/tokenize`·`/apply-template` 는 llama.cpp 전용이고 셋 다 예외를 삼켜 `None` 을 반환한다** — 외부 API로 바꾸면 **에러가 아니라 조용한 품질 저하**로 예산 가드가 실측에서 추정으로 내려간다(추정은 과소평가 방향 = 가드가 늦게 걸린다). **"뜨긴 뜬다"로 끝내지 말고 토큰 계수가 살아 있는지 따로 확인한다.** 위치는 줄 번호가 아니라 **함수 이름으로 찾는다**([`client.py`](services/llm_gateway/app/client.py) 의 `_probe_context_window`·`count_tokens`).

**검증·회귀**
- **★ 뮤테이션 원복에 `git checkout -- <file>` 을 쓰면 미커밋 작업이 사라진다.** 순서는 **커밋 → 변형 → 원복 → 트리 clean 확인**이고, **첫 변형 전 `git status --short` 가 비어 있어야 한다**(이 저장소에서 아홉 번 어겼다). **★ 그 게이트를 실제로 무력화하는 것은 `cwd` 다** — 셸의 작업 디렉터리는 명령 사이에 남으므로 원복 명령은 항상 절대경로(`cd /mnt/f/devel/ai_writte_system && …`)로 쓴다. 남의 미커밋 트리를 감사할 때는 `git checkout` 을 아예 쓰지 말고 `cp` 백업 + 역방향 편집(→ [`guides/verification.md`](docs/guides/verification.md) §"Mutation testing").
- **뮤테이션 결과를 `grep FAILED` 로 읽으면 subtest 실패를 통째로 놓친다**(`pytest-subtests` 는 `SUBFAIL` 로 낸다).
- **mutation이 통과하면 가드가 약한 것일 수도, mutation이 안 먹은 것일 수도 있다 — 먼저 후자를 의심한다.**
- **미검증 구간은 인계 문구에서 베끼지 말고 git에서 유도한다**: `git log --diff-filter=A -1 --format='%h %s' -- 'docs/verifications/*.md'`. **`--diff-filter=A` 를 빼면 폐쇄 주석 커밋이 답으로 나와 미검증이 0으로 계산된다.** 개수는 구조적으로 낡으므로 **"코드 N커밋 + 기록 계열" + 유도 명령**으로 적는다.
- **셀 수를 적을 때는 "무엇을 돌린 수인지" 를 같은 줄에 적는다**(이 저장소의 확인법이 "그 파일을 열어 세어 보기"라, 세트 수를 파일 행에 적으면 재현이 안 된다).
- **계약에 "…는 잠기지 않는다 / …해도 안 깨진다" 류의 방어적 단언을 쓰면, 그 단언을 지나는 셀이 있는지 그 자리에서 확인한다.**
- **계약 문언이 검사보다 넓으면 그 차이가 다음 사람의 오해다** — 폐쇄는 **문언을 줄이는 대신 검사를 넓혀서** 한다(문언을 줄이면 계약이 약해진 채 합의된다). 다만 **가드를 조이다가 개선 경로를 잠그지 말 것**(`disable_error_code` 는 부분집합만 단정한다).
- **8.3 동시성 셀은 바쁜 머신에서 흔들린다 — 제품 결함이 아니다.** `admitted == 1` 은 지켜지고 흔들리는 것은 거절 *사유*뿐이다. **실패 메시지에 `AdmissionUnavailable` 이 섞였으면 부하이고, `admitted` 가 2 이상이면 그때가 진짜 결함이다.** 먼저 단독 재실행한다.
- **이 머신에서 backend 전수와 frontend 전수를 겹쳐 돌리지 말 것**(과부하 타임아웃 오탐).
- **pymongo는 BSON 날짜를 naive로 돌려준다** — aware `datetime.now(UTC)` 와 비교하면 `TypeError` 다.
- **쿠키 인증 테스트는 `TestClient(app, base_url="https://testserver")` 로 만든다**(세션 쿠키는 `Secure` 기본 on).
- **문서를 쓸 때 `abstract.md` 를 그대로 인용하면 거짓이 된다** — 초안(2026-06)에서 달라진 다섯을 [`docs/product-overview.md`](docs/product-overview.md) §5가 모아 두었다(단일→다중 사용자 · 추출 5종→**관찰 3종** · Gate 4종→**Writing Gate 하나** · 문체는 학습이 아니라 **선언** · 관측이 제품 기능으로 추가). 그런 문서의 숫자는 **날짜 스냅샷**이고 살아 있는 정본은 README·SoT다.
- **검증 기록의 판정 어휘는 `합격`·`조건부 합격`·`불합격` 셋뿐이고** 첫 줄 형식까지 [`guides/verification.md`](docs/guides/verification.md) 가 규정한다. **분류를 정규식에 맡기지 말 것** — 분류는 사람이 하고 가드는 구조만 잠근다.

## 코드를 만질 때의 규칙

**라우터·모듈 구조** — 공개 operation 전부가 `routers/` 11모듈에 있고 `main.py` 에는 조립 코드만 있다.
- **`routers/*` 에 `from ..main import` 를 되살리면 안 된다**(원래 순환이었고 [`test_app_import_paths.py`](tests/test_app_import_paths.py) 가 문다).
- **`main.py` 에 재수출 shim을 두지 않는다** — 두면 핸들러는 새 모듈을 보는데 테스트는 `main` 을 patch해 **조용히 빗나간다**. 심볼이 옮겨가면 import를 따라 옮긴다.
- **`main.py` 의 routers import는 상대 경로를 유지한다**(절대면 라우터 사본이 둘 생긴다). **`register_*` 호출 순서를 재배열하지 말 것** — route 순서가 OpenAPI `paths` 순서이고 그것이 프론트 생성물의 입력이다.
- **[`api/`](services/application/app/api/) 의 의존 방향은 단방향 `errors → models → env` 이고 `dependencies` 는 독립**이다. `app/env.py` 가 `api/` 밖인 것도 그 방향 때문이다.
- **공유 직렬화기는 [`api/payloads.py`](services/application/app/api/payloads.py), 한 도메인 전용은 그 라우터 모듈.** 전부 모으면 `payloads.py` 가 두 번째 `main.py` 가 된다. **`_require_project_exists` 를 새로 쓰지 말고 [`project_existence_check`](services/application/app/api/dependencies.py) 를 부른다.**
- **import를 재작성할 때 `as` 별칭을 버리지 말 것.** **`main.X` 를 patch하는 자리는 저장소 전체에 셋뿐**(`connect_chroma_collection`·`_build_embedding_provider`·`GatewayGenerateProvider`) — 심볼을 지울 때 이 스윕을 먼저 한다.

**새 것을 더할 때 — 함께 가야 하는 것들**
- **새 LLM 호출부**: ① 조립 지점에서 `ObservedProvider(inner, call_site=…)` 로 감싼다 ② 그 요청 경로에서 `llm_call_scope(...)` 를 연다 — **감싸기와 scope 개방은 항상 함께 간다. 빠뜨리면 레코드가 조용히 0건인데 스위트는 green이다** ③ **조립 가드도 함께 넣는다**(하네스는 `ObservedProvider` 를 직접 만들기 때문에 조립에서 벗겨도 green이고 **배포에서만** 계측이 사라진다) ④ 도메인 판정은 `scope.annotate_last(...)`, 최종 도메인 거부는 `scope.reclassify_last_as_parse_error(...)`.
- **새 mutating route**: [`activity/actions.py`](services/application/app/activity/actions.py) 에 `logged` 또는 `EXCLUDED(사유)` 로 등재해야 전수 가드가 통과한다. **★ 전수 가드는 배선의 *존재*만 보고 *분기*는 못 본다** — 한 handler에 기록 분기가 여럿이면 **분기마다 행위 셀**이 필요하다.
- **새 유료 경로**: 분류표([`quota/billable_actions.py`](services/application/app/quota/billable_actions.py) 가 정본) · 시행 dependency · 402/429 선언 · 확인 헤더가 함께 간다(넷 다 전수 가드). **원장 필드명은 반드시 `target_project_id`** — `project_id` 로 적으면 purge reconciler가 **과금 기록을 지운다**. **입장 뮤텍스 임계 구역에 provider 호출을 넣지 말 것**(한 회원 요청이 91초씩 직렬화된다).
- **새 endpoint**: `responses=` + dependency + `test_auth_api.py` tier 전수 가드 등재. 저장소 예외는 광의 `except Exception` 보다 먼저 503으로 보존한다.
- **새 결정 브리프·검증 기록**: [`plans/README.md`](docs/plans/README.md)·검증 인덱스에 등재해야 한다 — [`test_docs_indexes.py`](tests/test_docs_indexes.py) 가 **미등재 문서와 깨진 링크를 양방향으로 막는다**(규칙이 아니라 강제). 같은 가드가 "검증 기록 N건" 류 숫자 주장도 디스크 실측에 묶는다.

**도메인 계약 — 고치기 전에 알아야 하는 것**
- **컨텍스트 항목 렌더링은 한 정의다** — [`context_search/item_render.py`](services/application/app/context_search/item_render.py) 를 프롬프트와 예산 회계가 **함께** 쓴다. 항목 렌더링을 바꾸면 예산이 자동으로 따라오지만 **정확히 한 곳에 여유가 있다**: 회계는 인용 번호를 모르므로 `_BUDGET_CITATION_NUMBER=999` 로 센다(항목당 최대 1토큰 과대평가). **여유를 넓히려면 `0 ≤ 여유 ≤ 항목수` 를 단정하는 세 셀을 함께 고친다** — 밴드 뒤에 숨기면 항목을 두 번 세는 과잉 교정이 통과한다.
- **`GET …/memory` 의 `scope: null` 은 결측이 아니라 계약된 값이다**(`event_observation`·`open_question_observation` 은 엔티티 id가 없다). *"비었으니 채우자"* 는 과잉 교정을 셀이 문다.
- **재색인 enqueue는 무조건 choke point다** — canonical을 만드는 모든 경로가 `MemoryService._enqueue_reindex` 를 지난다. **memory는 append-only**이고 canonical만 색인된다.

**CSS·프론트**
- **기본 동작 버튼의 겉모습을 자리마다 쓰지 말 것** — 색·테두리·커서·모션은 **base·hover·disabled 세 규칙 한 묶음**에서만 정하고 **새 버튼은 세 규칙 전부에 선택자를 더한다**(base에만 넣으면 hover·disabled 반응을 못 얻는데 화면을 열기 전에는 안 보인다). **패딩은 공통 규칙에 넣지 말 것**(자리마다 다르다). 가드 [`buttonAppearance.test.ts`](frontend/src/buttonAppearance.test.ts).
- **페이지 폭을 화면마다 정하지 말 것** — `main` 의 상한과 같은 폭(**실측 76rem**)을 **한 규칙에서만** 정한다. 좁은 측정폭이 필요하면 그 블록이 스스로 제한한다. [`pageLayout.test.ts`](frontend/src/pageLayout.test.ts) 는 값이 아니라 **규칙성**을 재므로 값 인용은 `styles.css` 를 본다.
- **색을 직접 쓰지 말 것**(semantic 토큰만) · **`:root` 의 hex를 손으로 고치지 말 것**([`10_palette_contrast.py`](docs/plans/10_palette_contrast.py) 가 만들고 [`test_design_token_provenance.py`](tests/test_design_token_provenance.py) 가 양방향으로 잠근다) · **`font-size` 리터럴 금지**(`--type-*` 8계단, 새 계단은 지수 주석을 함께 적는다) · **hover 색은 본색과 램프 두 단계 이상** · **`:disabled` 농도는 `--disabled-opacity: 0.45` 하나**(의도된 예외 둘 — `.session-menu button:disabled` 는 `cursor: wait`, `.login-form input:disabled` 는 버튼이 아니다. 접으면 over-strict 셀이 문다).
- **`position: fixed` 표면을 `.page-enter` 아래 두지 말 것** — 값이 0이어도 fixed 자손의 containing block이 뷰포트에서 페이지 박스로 바뀐다.
- **차트 색은 `:root` 에서 읽고 fallback이 없다.** 계열색 기준은 배경 대비가 아니라 **서로 구별되는가**(색각 이상 포함)이고 **앱 상태색을 그대로 쓰면 떨어진다**. 검산 배경은 `--surface-raised`. `<Tooltip>`·`<Legend>` 는 스타일 prop을 반드시 준다. **렌더 테스트는 이 자리에 장님이다**(jsdom이 스타일시트를 로드하지 않아 빈 값이어도 green).
- **새 표면을 만들면 대비를 다시 계산한다** — 최악 배경은 "주로 쓰는 면"이 아니라 **정의된 표면 전체의 최소**다. **가드가 못 보는 것은 의미의 오배정**이다(정의된 토큰끼리 잘못 바꾸면 전부 green) — 표면을 바꿨으면 화면을 연다.
- **원고 내보내기의 zip 경로는 여전히 `manifest: true` 를 청한다**(포함 단위·version이 거기에만 있다) — manifest 옵션을 없앴다고 요청까지 지우면 **zip이 빈다**.
- **드로어 배지 acknowledge 조건은 `drawerOpen && activePanel === "writing"`** — 빼면 닫힌 드로어 뒤에서 배지가 조용히 꺼진다. 패널은 닫힘에도 **마운트를 유지**한다.
- **활동 화면**: 행위자 열이 없는 것은 의도(S3=ⓑ) · **"최근 100건" 문구는 두 겹으로 잠겨 있다**(백엔드 `list_for_project(limit=…)` 기본값을 바꾸면 [`test_activity_ui_labels.py`](tests/test_activity_ui_labels.py) 가 실패한다 — F1 커서 페이징이 여기서 걸리고 그때는 문구도 함께 고치라는 뜻) · `draft_version` 행은 payload에 `draft_id` 가 없어 비링크(F7) · **선택 영역 단정은 `waitFor` 여야 한다**.
- **`AdminUserPayload.status` 라벨 순서는 "비활성 > 승인 대기 > 거절됨 > 활성"**(단방향 축 D6이 앞선다). 대기 행은 `is_active=True` 로 저장되므로 **`False` 로 "고치는" 교정은 D6 위반**이다.
- **화면 지도**: `/projects/:id/settings`(brief·export·activity 탭) · `/admin/users/:userId` · 옛 `/overview`·`/activity` 는 **리다이렉트로만** 산다.

**스크립트**
- 앱 route를 치는 9종에는 세션 로그인이 붙어 있다([`scripts/script_auth.py`](scripts/script_auth.py)). 운영자용 8종은 `--username` + **`APPLICATION_PASSWORD` env**(비밀번호 argv 금지), in-process smoke 1종은 일회용 계정을 스스로 발급한다. **새 스크립트는 레지스터에 넣는다 — 안 넣으면 가드 ②가 실패한다.**
- **세션 쿠키를 httpx jar의 자동 왕복에 맡기면 안 된다**(`Secure` 라 plain http에서 조용히 안 실린다). 명시 `Cookie` 헤더 또는 `client.cookies.set(...)` — **헤더 전용으로 조이지 말 것**(정상 구현을 깨는 과잉 교정).

## 열린 것 — 부채 · 결정 대기

**⚠️ 오너 결정이 있어야 움직이는 것**

| 항목 | 무엇을 정해야 하나 | 정본 |
|---|---|---|
| **랜딩 기획 · 약관 · 개인정보 처리방침** | 공개 전 법적 요건이고 **정본은 오너만 쓸 수 있다**(원고가 구글 API로 나가는 고지 포함 여부 포함). 병목이 여기다 | — |
| **N2** Scene 목록의 finality·분석 표시 | 계약 제7조 문언과 긴장 — *현행 유지=문언 수정* 또는 *배지 구현* | `final_save_d5_closure.md` |
| **N3** 같은 finalize key 재전송이 활동 행 중복 | ⓐ 그대로 ⓑ 생략(accept 선례) — UI는 매 클릭 새 UUID라 도달 불가 | 같음 |
| **idempotent replay가 활동 이벤트를 매번 추가** | ⓐ 그대로 ⓑ replay 제외 ⓒ replay 표식 | 2026-08-09 검증 |
| **auto-promote 503 partial 미기록** | ⓐ 그대로(권장) ⓑ 승격 memory마다 한 행 ⓒ 개수 한 행 | `routers/analysis.py` |
| **K-3: 창을 모르는 호출은 가드 밖** | ⓐ 그대로 ⓑ 짧은 대기 허용(v1.7.60 개정) ⓒ `/props` 1회 재시도 | v1.7.60 |
| **`analysis_extractor` D4 정렬 / loop round별 gate decision 노출** | 둘 다 dogfood 데이터가 쌓인 뒤 판단 가치가 올라간다(지금 표본 0) | v1.7.47 |
| **문서 고아·낡은 상태 마커 처리**(2026-09-05 전수) | ① **부모 계획 12건이 `Draft` 에 멈춰 있다**(`00-foundations`~`08-member-request-quota` · `implementation-plan` · `product-shell` · `flat-loop-gate` · `llm-gateway`) — 기술한 시스템은 대부분 구현·검증 완료인데 마커만 6~7월 그대로다. **[`plans/README.md`](docs/plans/README.md) 자신도 `Draft`** ② **`docs/verification_briefs/2026-06-24`(3건)은 어떤 인덱스에도 없다** — `verifications/` 로 대체된 초기 실험 ③ `benchmarks/2026-07-15`·`live_review_briefs/2026-07-18` 은 인덱싱은 됐지만 **한 번 쓰고 멈췄다** ④ **`docs/contracts.md`** 등 아이디에이션 원본 4건에 `chat-revision-ideation.md` 같은 **"승격됨·보존" 배너가 없다** — 특히 `contracts.md` 는 이름이 `system-contract-sot.md` 와 혼동돼 **신규 작업자가 6월 계약을 현재형으로 읽을 수 있다**. 선택지: ⓐ 배너만 단다 ⓑ `archive/` 로 옮긴다 ⓒ 그대로 둔다 | — |
| **`docs/plans` 디렉터리 재편** | 브리프 경로 인용 1,083건/253파일 중 183개가 과거 검증 기록 — **"지금 하지 않는다"가 근거 있는 판단**이고 남은 동기는 미학뿐 | — |
| **llama `-hf` 리비전 고정** | 최신 추종 vs 현행 고정. 새 리비전이 프롬프트 sha 핀·gate 동작에 주는 영향 미측정 | — |

**🔧 미수리 — 알고 있고 아직 안 고친 것**

| 항목 | 상태 | 위치 |
|---|---|---|
| 프론트가 `detail` 문자열로 분기(H3 위반) | 세 사건이 전부 502라 코드로 구분 불가. 닫으려면 H3 개정 또는 상태코드 분리 | [`client.ts:1088`](frontend/src/api/client.ts#L1088) |
| `/writing/generate` 만 provider TIMEOUT을 502로(나머지는 504) | 선언 surface와 잠긴 셀을 함께 바꿔야 함 | [`writing.py:469`](services/application/app/routers/writing.py#L469) |
| 결정적 `provider_error` 에도 "다시 시도" 버튼 | 게이트웨이의 `retryable=False` 가 화면까지 안 온다 | `GenerationPad.tsx` |
| `llm_call_audits` 로 "출력이 잘렸다"를 못 본다 | `finish_reason`·`truncated` 없음(실측 0건). 헤드룸만 계산 가능 | `observability/` |
| 자료(source) 원문 길이 상한 없음 | `analysis_extract` 가 `snapshot.raw_text` 를 **통째로** 싣는다 — 검색 조각 예산의 보호를 안 받는 유일한 LLM 경로 | [`extractor.py`](services/application/app/analysis/extractor.py) |
| 프론트 4000 상수가 서버 env override와 미동기화 | 서버 422·400이 최종 방어. 해소하려면 public 설정 계약 위치를 먼저 결정 | [`tokenEstimate.ts:23`](frontend/src/writing/tokenEstimate.ts#L23) |
| 정본 SoT §"현재 구현 상태" 표가 자기모순 | 같은 표가 "구현"과 "미구현"을 함께 말한다. 정정은 버전 개정 사안 | `system-contract-sot.md:821` |
| `00-foundations.md` 착수 전 체크박스 미갱신 | 실제로는 확정된 항목들이 미체크 — 거짓 단언이 아니라 미갱신 | `docs/plans/00-foundations.md` |
| `activity/actions.py` 주석의 "기록하지 않는 21" | 실제 29건. 가드는 등재 여부만 보고 개수를 안 본다 | `actions.py:173` |
| `docs/README.md` 의 "브리프 96개" | 실측 **100**. 최상위 `README.md` 의 같은 주장은 가드가 잡는데 **이 줄은 가드 밖**이다 | `docs/README.md:11` |
| `chat-revision-ideation.md`·`dogfood-checklist.md` 가 문서 지도에 없다 | 후자는 HANDOFF 가 실제로 가리키는 살아 있는 문서다 | `docs/README.md` |
| 미사용 import에 회귀 가드 없음 | 유일한 신호가 스위트 밖 linter. **ⓐ(정리 슬라이스마다 수동 측정)가 현 단계에 맞다** | — |
| 프론트 기존 결함 2건 | `typeScale.test.ts` 이관 목록 49↔54 · `designTokens.test.ts` `--type-body` 미정의. **사전존재 확인됨** | — |
| `scripts/` 를 pytest가 실행하지 않는다 | CI 없음(`.github` 부재). 부분 방어가 `mypy.ini`(`call-arg`+`misc`) 가드다 — **`misc` 를 disable 목록에 넣으면 표적 결함이 조용해진다** | `tests/test_typecheck.py` |

**⏸ 유예 — 트리거가 오면 연다** *(트리거 없는 유예는 망각이다)*

| 항목 | 트리거 |
|---|---|
| 배포 서버를 외부 API로 실제로 물리기 | **오너가 외부 API를 준다** |
| 리랭커 self-host + 품질 평가 | 하네스는 선작성됨, **정답은 오너가 붙인다**(구현자가 붙이면 "리랭커가 구현자 생각과 같은가"를 재게 된다) |
| Phase 10 ③ 목록 행 간격(T1) · ④ **비활성 버튼의 색**(농도가 아니라 색이 문제) | **육안 확인** — 가장 싼 자리다 |
| Phase 9 화면 후확장 F1~F6(커서 페이징·필터 등) | 각 행에 트리거가 붙어 있다 → [`09-1-…-decisions.md`](docs/plans/09-1-activity-timeline-screen-decisions.md) §"나중에 여는 문" |
| 패드 항목의 채택 전 Gate 사전 표시 | 오너가 "채택 눌렀다 반려되는 빈도가 높다"고 관측할 때 |
| AdSense 광고 단위 배치(자동/수동) | **심사 승인**. 광고는 승인 전엔 게시되지 않는다(로더가 있어도 안 보이는 것이 정상). `adsbygoogle.js` 에 SRI를 안 붙인 것은 의도다 |
| quota 상수 셋 재측정(5초 창·lease 180초·일20/주100) | 외부 API로 응답이 수초로 줄면. **설계는 안 바뀐다** |
| D8-6 D4-D purge operation journal/saga | 원격 저장소·다중 worker 또는 수동 reconciler가 실제 부담이 될 때 |
| D8-7 G2~G6 자격증명(SCRAM·keyfile·basic auth) | 원격·다중 호스트 배포. **각하가 아니라 유예** |
| 2c `owner_id` 공개 payload 노출 | 프론트가 읽을 이유가 생길 때(`schema.d.ts` 변경이라 공짜 아님) |
| 공유·협업 글쓰기 | 미래 확장. D3=A가 그 문을 닫지 않게 설계돼 있다 |
| 프론트 스타일 나머지 축 | 다른 지점 줄바꿈·넘침 · 좁은 화면 표 넘침 · 실패 UX 문구 |
| 사용자 가이드 | 도그푸드에서 UI가 안정되면. **공개 전** 최신 화면 기준으로 |
| Phase 8.6 결제 seam | 결제 도입이 계기일 때(오너: *"당장은 안 붙일 것 같다"*) |
| 관측 화면 확장 | API에 시간 창(`?since=`)이 생긴 뒤. 무엇을 더하든 **`React.lazy` 경계 안** |

## Next Tasks

1. **정체성 그룹 Slice 5 독립 검증** — Slice 0~5 구현 완료, 0~4는 검증 폐쇄, **5만 대기**. 대상은 git에서 유도한다(기준점 = 마지막 검증기록 발행 커밋). 볼 축: revision 멱등 key · step 진행 저장(`candidate_identity_group_approvals`) · 채택 규칙 · **유료 10번째 경로 fan-out** · 그룹 행 한 줄 활동 기록(변경 ≥1일 때만). 브리프 [`pending-candidate-identity-grouping-decisions.md`](docs/plans/pending-candidate-identity-grouping-decisions.md), 페이즈 [`구현 페이즈 문서`](docs/plans/pending-candidate-identity-grouping-implementation-phases.md).
2. **최종 저장·분석 연동 5차(승격) 재검증** — 4차 조건부 합격의 조건 N1은 닫혔다. **집중 셀 + 변이로 충분**(4차 판정문).
3. **Slice 6(grouped Inbox UI)** — 1번 통과 후. 착수 전 위 표의 프론트 기존 결함 2건을 먼저 본다.
4. **장면 메모 Slice 3~4(화면 둘)** — API는 완결(Slice 0~2). **Slice 3는 API 계약을 안 바꾼다** — 목록은 미리보기(200자)만 싣고 전문은 단건 GET이 주므로 **화면이 목록에서 전문을 기대하게 만들지 말 것**. 저장 화면은 **요청 중 저장 버튼 비활성화**. 확정값 [`scene-note-decisions.md`](docs/plans/scene-note-decisions.md).
5. **육안 확인(누적)** — 프론트 재빌드 선행. Phase 10 마감 다섯(첫 화면 콘텐츠 · 오른쪽 끝 정렬 · 목록 행 간격 · 차트 막대 테두리 · 버튼 hover) · 비활성 버튼 색 · 편집기 드로어와 설정 탭이 좁은 화면에서 겹치는지 · 관측 화면과 비동기 패드 렌더 · **최종 저장·분석 연동의 첫 실사용**(운영 이력 0건).
6. **dogfood 관찰**: `report field must be an array` 실패율 · `analysis_extract` 의 `aspect` 오분류 빈도 · scratch per-draft 상한(기본 20) 밀어냄. 체크리스트 [`docs/dogfood-checklist.md`](docs/dogfood-checklist.md).
7. **정리 대상**: 확인용 계정 `timeline_demo` 와 프로젝트 `6a795ab928e4a53aa000a824`(활동 5건).
8. **★ 서비스 정책 계약 문서를 만든다(오너 지시 2026-09-05).** **찾아봤고 없다** — 정책이 브리프 8~9개와 SoT 절에 흩어져 있어 *"이 서비스가 회원에게 무엇을 약속하는가"* 를 한 장으로 답할 수 있는 문서가 하나도 없다. **지금 흩어져 있는 자리**: 요청 한도·정지(`08-1`·`08-3`·`08-5` 브리프) · 승인제 가입(`auth-signup-approval-decisions.md`) · 삭제·파기와 이름 보존(`auth-d8-6-purge-ui-decisions.md`·`08-2c`) · 관리자 열람과 승격(`multi-user-auth-cms-decisions.md`) · 원고 길이 상한(D5-2) · 광고(AdSense). **아직 아무 데도 없는 것**: 원고가 외부 LLM API로 나간다는 **고지**, 데이터 보존 기간, 계정 삭제 시 처리. **이 문서는 약관·개인정보처리방침(오너 정본)의 *입력*이지 대체물이 아니다** — 법적 문서는 오너가 쓰고, 이 문서는 **코드가 실제로 시행하는 정책값**을 모아 그 근거를 준다. 값의 정본은 계속 SoT·브리프이고 이 문서는 **한 장 요약 + 포인터**다(값을 여기 복사하면 두 번째 정본이 된다).

**Deferred(오너 결정 선행)**: Chapter 위의 part/volume 계층 · ProjectBrief→Draft provenance · 관계 graph/완전 timeline · saved publication manifest · Phase 7 대화형 수정.

## Project Structure

```text
docker-compose.yml            # 배포 스택: application·mongo(rs0)·gateway·embedding·chroma·elasticsearch(nori)·worker·admin·frontend
docker-compose.test.yml       # 테스트 전용 단일노드 RS mongo(27020) — 명시 -f 로만 뜬다
docker-compose.llama.yml      # opt-in: in-stack llama.cpp GPU 서버(9080)
docker-compose.external.yml   # 외부 API 전용: 모델 들고 오는 셋을 profile 뒤로
.env.example                  # 호스트 게시 포트 전용 대역 + 근거
CLAUDE.md / AGENTS.md         # 작업 규칙(동일 내용). HANDOFF 편집 규칙·자가 검수 트리거 포함
docs/
├── system-contract-sot.md    # ★ 정본 계약 + 변경이력(버전별)
├── plans/                    # 계획 + 착수 결정 브리프(*-decisions.md)
├── daily_logs/YYYY-MM-DD/    # 작업 상세 이력
├── verifications/YYYY-MM-DD/ # 독립 검증 기록
├── guides/                   # 기록·인계 규칙, 독립 검증 절차
├── runbooks/                 # 로컬 llama 등 운영 절차
└── abstract.md 등            # 보존된 아이디에이션 원본
schemas/                      # W0 등 계약 schema
scripts/                      # 마이그레이션·live smoke·worker 엔트리포인트
services/
├── application/app/          # FastAPI 본체
│   ├── main.py               # 조립 + 에러 선언 상수(_ERRORS_*)
│   ├── api/                  # 공유 prelude(errors → models → env, dependencies 독립)
│   ├── routers/              # 11 모듈, 공개 operation 전부
│   ├── auth/                 # 사용자·Argon2id·서버 세션·쿠키 정책
│   ├── core_sot/             # 정본 저장(project/chapter/draft/version/snapshot/source_ref)
│   ├── analysis/ memory/     # 추출·후보·비교·승격·정체성 그룹
│   ├── context_search/       # ContextPackage 구성 + Gate + 리랭커 seam
│   ├── writing/              # 생성·Gate·revise·accept·scratch·생성 job
│   ├── quota/                # 유료 분류·원장·정책·입장 뮤텍스
│   ├── activity/             # 활동 로그 + 분류표(actions.py)
│   ├── indexing/             # vector/lexical 색인, embedding provider
│   └── observability/        # per-LLM-call 감사 + ObservedProvider/llm_call_scope(seam C)
├── llm_gateway/              # LLM 경계(ProviderError taxonomy · 키 폴백)
└── embedding/                # 임베딩 서비스(BGE-m3-ko, 1024-dim)
frontend/                     # React+TS+Vite SPA (recharts는 관측 화면 전용·lazy)
├── src/api/schema.d.ts       # gen:api 생성물 — 손으로 고치지 않는다
├── nginx.conf                # /api 리버스 프록시(변수 upstream + resolver)
└── src/{auth,drafts,writing,observability}/
tests/                        # 백엔드 회귀(python -m pytest)
```
