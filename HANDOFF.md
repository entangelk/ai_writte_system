# HANDOFF

> **다음 작업자가 지금 일을 시작하는 데 필요한 것만.** 이력이 아니다.
> 완료 서술은 여기 쓰지 않는다 — `docs/daily_logs/`(상세) · `docs/system-contract-sot.md` 변경이력 · `CHANGELOG.md`(마일스톤) · `docs/verifications/`(독립 검증)에 이미 있다.
> 편집 규칙은 `CLAUDE.md`·`AGENTS.md`의 "HANDOFF.md" 절에 있다. **길이 상한은 없다** — 대신 **~200줄을 넘으면 자가 검수**하고(그 뒤로는 ~100줄마다) 결과를 아래 한 줄로 남긴다. 길어야 할 이유가 있으면 길어도 된다. 안 보는 것이 문제다.
>
> 마지막 자가 검수: 2026-07-27 · 177줄 (D8-3a 시행 반영 — 인증 관련 절은 새로 쓰고 완료 서술은 남기지 않았다. 다음 검수 트리거는 200줄)

## 머신 구성 (알파 · 베타 · 감마)

이 프로젝트는 성격이 다른 세 머신을 옮겨 다닌다. **HANDOFF·문서가 "환경과 안 맞는다"고 느껴지면 먼저 지금 어느 머신인지부터 본다.** 아래는 각 머신이 *무엇을 띄울 수 있는지*(항구적 성질)이지, *지금 무엇이 떠 있는지*(머신-로컬 관측치)가 아니다 — 후자는 각 절에서 날짜를 달아 따로 적는다.

| 머신 | 역할 | LLM | 띄울 수 있는 것 |
|---|---|---|---|
| **알파(Alpha)** | 서비스 배포용 | **in-stack llama**(GPU 3060 Ti 12GB, `docker-compose.llama.yml`) | 전체 스택 + 자체 GPU LLM |
| **베타(Beta)** | 테스트·개발용 (**지금 이 머신**) | **외부 LLM**(gemma-4-12B, LAN) — 현행 주소는 `.env`·머신-로컬(2026-07-27 `192.168.1.22:9080`) | 전체 스택. gateway는 `.env`의 `LLAMA_BASE_URL`로 외부 서버를 가리킨다 |
| **감마(Gamma)** | 사이드 개발용 (노트북) | **없음** — LLM을 못 띄운다 | CPU 기반 컨테이너·DB 정도(mongo/test-mongo·ES·chroma). LLM 관통 작업은 불가 |

- **어느 머신에서든 `docker compose up`만으로 같은 포트로 뜬다**(포트는 repo에 고정, 아래 "기동·실행법"). 머신별로 달라지는 것은 **LLM을 어디서 얻느냐**뿐이다:
  - 알파: `docker compose -f docker-compose.yml -f docker-compose.llama.yml up`(in-stack llama 9080).
  - 베타: `.env`에 `LLAMA_BASE_URL=http://192.168.1.22:9080`(커밋 금지 — gateway 기본값 `host.docker.internal:9080`을 외부 서버로 덮는다).
  - 감마: LLM 관통이 필요 없는 작업(회귀·저장소·색인)만. 필요하면 알파/베타로 옮긴다.
- **함정**: HANDOFF가 "스택이 내려가 있다/떠 있다"고 적었으면 그건 **그 시점 그 머신의 관측치**다. 다른 머신에서 그대로 믿지 말고 `docker compose ps`로 직접 확인한다(memory 규칙 "verify-machine-state-before-claiming-blocked").

## 지금 상태

- 정본은 `docs/system-contract-sot.md` **v1.7.52**(Approved). 미확정 항목은 추측 구현하지 않는다.
- **진행 중 페이즈 = 다중 사용자 인증(D8).** 오너 지시로 **슬라이스를 잘게 쪼개 진행 중**이다(한 번에 큰 덩어리 금지). 진행표:

  | 슬라이스 | 상태 | 내용 |
  |---|---|---|
  | 1a·1b·1c | **완료** | User 저장(Argon2id) · 서버 세션 · `/auth/login`·`/auth/logout`·`/auth/me` (operation 62→**65**), 실 스택 관통 검증 |
  | **2a** | **완료** | `Project.owner_id: str \| None` 필드 + Mongo 왕복. `create_project(name, owner_id=None)`. **공개 API 무변** |
  | **2b** | **완료** | `POST /projects`가 세션이 있으면 생성자를 owner로 **기록**. 세션 없으면 unowned로 **여전히 200** |
  | 2c(선택) | 미착수 | `owner_id`를 공개 payload에 노출할지 — **프론트가 읽을 이유가 생길 때** 하면 된다(schema.d.ts 변경이므로 공짜 아님) |
  | **D8-4 선행** | **완료·검증 합격** | 프론트 로그인·세션 만료·route guard |
  | **3-a** | **완료** | 인증 dependency + 61 operation 401 선언 + 두 겹 전수 가드 |
  | **3-b (다음)** | 미착수 | project 소유권(403) + `GET /projects` 저장소 필터. `owner_id=None` 항상 deny |
  | **3-c** | 미착수 | 최종 전수 가드(401·403 양쪽) |

- **D8-3 E1~E4 = 전부 A로 확정** — `plans/auth-d8-3-enforcement-decisions.md`(Resolved). `owner_id=None`은 탈퇴·삭제 누락 같은 미래 비정상 잔존도 **항상 deny**. project 경로는 소유권, 그 외는 인증이며 `GET /projects`는 저장소 조회에서 본인 소유만 반환한다.
- **⚠ 인증은 섰고 인가는 아직 없다.** 세션 없는 요청은 `/health`와 공개 `/auth` 두 곳을 빼고 전부 401이지만, **로그인만 하면 남의 project도 열린다** — `owner_id`를 읽어 접근을 막는 코드는 3-b에서 들어온다. `GET /projects`도 전부를 돌려준다. **다중 사용자 격리가 없으므로 외부 노출 금지는 유지.**
- **3-b 착수자를 위한 사실**: (a) 재료는 `require_authenticated_user`(모듈 수준, `main.py`)가 돌려주는 user + `project.owner_id`. 소유권 dependency는 `project_id`를 받는 경로에만 얹고, 인증 dependency를 대체하지 않고 그 위에 얹는다. (b) **워커는 HTTP API를 쓰지 않는다** — Mongo 직접 접근이라 서비스 계정은 D8-7 사안. (c) `AuthenticationBoundaryTest.PUBLIC`(`tests/test_auth_api.py`)이 공개 예외 4개를 열거한다 — 3-b가 403을 더할 때 이 가드의 형태(route 객체 검사 + 실제 호출)를 그대로 확장하는 것이 옳다. (d) 도메인 스위트는 `tests/auth_support.py`의 override로 인증 상태가 된다. **경계 테스트는 override 없는 앱으로만** 쓴다 — 그 파일을 "테스트에서 인증 끄기" 스위치로 쓰기 시작하면 전수 가드가 무력화된다.
- **첫 계정 만드는 법**(관리자 API는 D8-5라 아직 없다): `docker exec -e PYTHONPATH=/app -e AUTH_BOOTSTRAP_PASSWORD='…' ai_writte_system-application-1 python scripts/create_user.py <username> --admin`. **`PYTHONPATH=/app`이 필수다** — 이미지에 PYTHONPATH가 없고 `python scripts/x.py`는 CWD를 sys.path에 넣지 않는다.
- LLM 파이프라인 관측(KPI) 페이즈는 **계측·집계 API·대시보드까지 닫혔다**(2026-07-26). 그 결과물 위에서 다음 작업이 돈다.
- **관측 KPI 페이즈의 결과물**(다음 작업이 이 위에서 돈다): LLM을 부르는 **8개 호출부 전부**가 seam C(provider 데코레이터)로 계측되고 — `analysis_extractor`·`writing_gate`·`compare_judge`·`query_planner`·`writing_retrieval_planner`·`writing_generation`·`writing_revision`·`writing_report` — `GET /projects/{id}/observability/kpi`가 집계를 내고, `/projects/:id/observability` 화면이 그것을 그린다. QUAL-1(제품 품질·수기·dogfood)과 별개 트랙이며 운영기획 포트폴리오는 `docs/observability-kpi-rationale.md`.
- **새 호출부를 계측하는 법**(Phase 7 등): ① `main.py` 조립 지점에서 provider를 `ObservedProvider(inner, call_site=…)`로 감싼다(도메인 코드는 건드리지 않는다). ② 그 호출이 일어나는 요청 경로에서 `llm_call_scope(...)`를 연다 — **감싸기와 scope 개방은 항상 함께 간다. 빠뜨리면 레코드가 조용히 0건인데 스위트는 green이다**(scope 유닛 테스트로는 안 물리므로 배선 회귀를 함께 넣는다). ③ **조립 가드도 함께 넣는다** — 하네스는 `ObservedProvider`를 직접 만들기 때문에 `_default_*`가 감싸기를 빠뜨려도 green이고 **배포에서만** 계측이 사라진다(실측: gate 조립에서 wrapper를 벗겨도 56 passed). 가드는 **리터럴까지 단정한다** — 잘못된 site로 감싸는 것은 안 감싸는 것과 똑같이 틀렸다. ④ 도메인만 아는 판정(gate decision·파생점수)은 `scope.annotate_last(...)`, 최종 도메인 거부는 **`scope.reclassify_last_as_parse_error(...)`**(마지막 레코드가 `success`일 때만 동작 — `provider_error` taxonomy를 덮지 않기 위한 가드)로 flush 전에 얹는다. `ContextSearchFailed` 계열은 같은 모듈의 `reclassify_planner_parse_error(scope, exc)`가 `llm_error` 계보만 걸러 준다 — **endpoint와 worker가 같은 정의를 쓴다**(복제하면 두 정책이 조용히 갈라진다).
- **계측에서 지켜야 하는 계약**(SoT §"LLM 파이프라인 관측(KPI)"): ① 레코드는 **provider가 실제로 호출된 경우에만** — seam C에서는 구조적으로 참이다. ② **실패한 호출도 센다**(성공만 세면 성공률이 영구히 100%). ③ **scope 밖 호출(worker·script)은 기록하지 않는다** — 추측 `project_id`는 오염이다. ④ 격리(`_flush`)를 **좁히지 않는다** — 좁히면 감사 저장소의 pymongo 예외가 전역 handler(v1.7.38)에 도달해 **정상 200이 503으로 뒤집히고**, flush가 `finally`에 있어 요청의 원래 예외까지 덮어쓴다.
- **`parse_error` 재분류는 호출부가 명시할 때만 일어난다**(데코레이터는 도메인 거부를 모른다). v1.7.47부터 **`analysis_extractor`만 재분류하지 않고 나머지 7 site는 재분류한다** — 재분류가 마지막 호출 1건만 건드리므로 repair로 회수된 첫 호출은 `success`로 남고 repair 빈도 신호가 손상되지 않기 때문이다. 따라서 **extractor의 `parse_error`=0은 구조적 사실이지 데이터 부족이 아니다**(`outcome`이 `success`·`provider_error` 둘뿐). **같은 repair 구조인데 정책이 갈리는 상태**이며, 정렬 여부는 아래 오너 결정 대기 항목이다.
- **집계 API를 읽을 때의 함정 3가지**(v1.7.48, 전부 응답이 분모를 함께 실어 방어한다): ① `total_tokens`는 `success`+`parse_error` 행만 — 분모는 `tokens_counted_from`. ② **표본이 0이면 비율은 `null`이지 `0.0`이 아니다**(`gate.avg_quality_score`·`loop.non_convergence_rate`) — loop 감사는 opt-in(기본 off)이라 기본 배포에서 `loop.runs_considered`=0이 정상이다. ③ **`multi_call_correlations`는 repair 수가 아니다** — site 고정 후 레코드 2건 이상인 correlation 수이며, repair 구조 site(extractor·compare·planner)에서만 repair를 뜻하고 writing loop에서는 **설계된 라운드**다(gate 최대 3회).
- **loop 내부 gate 레코드에는 `decision`·`gate_quality_score`가 없다**(v1.7.47 알려진 공백): 파생점수는 endpoint가 `annotate_last`로 얹는데 revise loop이 round별 판정을 결과에 노출하지 않는다(`WritingLoopStage`는 stage/ordinal/status만). 그 필드는 **독립 `POST …/writing/gate` 호출에만** 채워지므로 집계가 전수 커버리지를 가정하면 안 된다.
- 공개 API 계약(H3)은 닫혀 있다: **`/health`를 제외한 64개 operation 전부**(전체 65 — 인증 3종 추가)가 realistic 에러 상태를 OpenAPI에 선언하고 **미매핑 500 부채는 0건**이다. 새 endpoint를 추가하면 **`responses=`와 `dependencies=_REQUIRE_AUTH`를 함께** 붙여야 하며(401 선언 자체는 `_protected()`가 `_ERRORS_*` 상수에 이미 얹어 준다), 트랙별 전수 선언 가드 테스트가 빠뜨림을 잡는다. 저장소 장애 503 face는 이제 **예외 없이 전 endpoint 균일**하다 — v1.7.40이 마지막 두 잔여(광의 catch가 pymongo를 삼켜 502로 내던 곳)를 닫았다: `POST …/analysis/jobs/{id}/run`과 `POST …/context-search`의 `persist_rejection`. 둘 다 광의 catch 앞에 `except _STORAGE_ERRORS`를 두어 저장소 예외를 503으로 보낸다. **주의**: 앞으로 endpoint body를 광의 `except Exception`으로 감싸면 그 순간 저장소 예외가 다시 502/도메인 에러로 새므로, 그런 catch를 둘 때는 반드시 그 앞에 `except _STORAGE_ERRORS`를 둔다.
- 회귀 기준선: backend **1631 passed / 873 subtests**(D8-3a 전수 가드가 61 operation × 3 검사로 subtests를 늘렸다), frontend **217 passed / 14 files**. build JS는 **진입 404.87 kB + 관측 화면 청크 385.71 kB**(차트는 `React.lazy`로 분리). **skip 수는 머신마다 다르다** — live Chroma 1건은 항상 skip이고, `elasticsearch` 파이썬 패키지가 없는 머신에서는 lexical retrieval 3건이 추가로 skip된다(베타 머신 2026-07-27 = **4 skipped**). 숫자가 안 맞으면 `-rs`로 skip 사유부터 볼 것. **백엔드는 `argon2-cffi`가 설치돼 있어야 한다** — 없으면 auth 관련 26개 모듈이 수집 단계에서 실패해 회귀처럼 보인다. 핀은 루트가 아니라 [`services/application/requirements.txt:1`](services/application/requirements.txt#L1)에 있다(`argon2-cffi>=23,<24`). **프론트는 `npm install`이 선행**돼야 한다.
- **[베타 머신 관측치, 2026-07-27, `docker compose ps` 실측]** 전체 스택이 `--build` 재빌드 후 떠 있다(외부 12B `192.168.1.22:9080` 배선). 정확한 health: **healthy 7**(`application`·`gateway`·`mongo`·`elasticsearch`·`embedding`·`chroma`·`frontend`) + **healthcheck 없는 2**(`worker`·`generation_worker` — async 배경 워커라 by design, "Up"이지 "healthy" 아님). **"전부 healthy"라고 쓰지 않는다** — 워커 2종은 구조적으로 healthcheck가 없다. `/health` 200, 관측 route(`/projects/{id}/observability/kpi`) 등록 확인. (frontend는 원래 unhealthy였다 — nginx `listen 80`이 IPv4 전용인데 healthcheck가 `localhost`→`::1`로 풀려 refused. 이번에 healthcheck를 `127.0.0.1`로 고쳐 healthy 전환 — `docker-compose.yml`에 반영, 46f6009 이후의 사전 존재 결함이었다.) **DB는 fresh다** — 기동 시 dev `mongo_data`의 구 `analysis_extract_v3` 본문(sha `fb4e272…`, 볼륨 소거로 재확인 불가)이 현재 canonical v3(sha `4376310…`)와 달라 `PromptTemplateConflict`로 app이 죽었고(코드 회귀 아님, 코드↔테스트 핀 일치), **오너 판단으로 데이터 볼륨(mongo·es·chroma)을 비우고**(embedding 모델 캐시는 보존) 재기동해 해소했다. 즉 관측 화면·모든 데이터는 **빈 상태부터** 시작한다.
- **관측 화면 육안 확인이 남은 미검증 항목**이다(로직은 회귀로 잠겨 있고 렌더만 미검증). URL `http://localhost:5520/projects/:id/observability`. **DB가 비어 있어 지금 열면 빈 상태**만 보이므로, 차트 배치·라벨 충돌을 보려면 먼저 파이프라인을 한 번 관통시켜(프로젝트 생성→분석/집필) `llm_call_audits`를 쌓아야 한다.
- 인증 백엔드 변경은 application, 로그인 UI 변경은 frontend 이미지 rebuild가 필요하다. 현재 베타 머신은 2026-07-27 D8-4 이미지까지 재빌드됐다.

## 기동 · 실행법

**포트는 전용 대역으로 repo에 고정돼 있다.** env 없이 `docker compose up`만으로 어느 머신에서든 같은 포트로 뜬다. 값과 근거는 [`.env.example`](.env.example)에 있고, 머신별로 바꿔야 하면 `.env`로 복사한다(커밋 금지).

| 서비스 | 포트 | 서비스 | 포트 |
|---|---|---|---|
| application | 8520 | chroma | 8523 |
| gateway | 8521 | elasticsearch | 9520 |
| embedding | 8522 | frontend | 5520 |
| mongo | 27520 | test-mongo | 27020 |

표준 포트(27017·8000~8003·9200·5173)를 쓰지 않는 이유는 `.env.example` 상단에 있다 — 여러 머신을 옮겨 다니는 프로젝트라 충돌하고, 임시 env 회피는 repo에 안 남아 문서에 머신-로컬 관측치가 사실처럼 적히게 된다.

**백엔드 테스트** — `docker compose -f docker-compose.test.yml up -d` 후 `python3 -m pytest -q`. env 불필요(기본 URI가 27020 replica set `rs-test`). 미기동이면 Mongo 테스트가 **skip**(실패 아님). 끝나면 `... down`.

**live Chroma 테스트**(호스트 `pytest`에서는 항상 skip되는 1건) — 호스트를 오염시키지 않고 이미 `chromadb`가 있는 application 이미지에서 돌린다:

```bash
docker compose up -d --no-deps chroma
docker compose run --rm --no-deps -v "$PWD/tests:/app/tests" \
  -e CHROMA_TEST_URL=chroma:8000 \
  application python -m unittest tests.test_chroma_adapter.ChromaAdapterLiveTest -v
```

**프론트** — `cd frontend && npm run gen:api && npx tsc --noEmit && npm run build && npx vitest run`.

## 함정 (모르면 시간을 잃는 것들)

- **출시된 프롬프트 본문은 immutable이다.** `tests/test_prompt_templates.py`가 `analysis_extract` v1/v2/v3 본문 sha256을 핀한다. 본문을 고치면 테스트가 깨지는데 **해시를 갱신하면 안 되고 새 버전을 만들어야 한다.** 어긴 결과: 기존 Mongo를 가진 배포가 `PromptTemplateConflict`로 전부 죽어 스택이 3일간 안 떴다. Mongo에 영속되는 프롬프트는 `analysis_extract` 하나뿐이라, 다른 프롬프트를 영속으로 옮기면 sha256 핀도 함께 확장해야 한다.
- **compose의 `ulimits.nofile`은 튜닝이 아니라 필수다.** Docker 기본 1024면 WiredTiger가 `Too many open files`로 mongod를 죽이는데, **test-mongo에서는 증상이 skip이 아니라 failure라 코드 회귀처럼 보인다.** 배포 `mongo`(64000)·`elasticsearch`(65535)에도 같은 이유로 들어가 있다 — 값이 다른 것은 각 데몬이 요구하는 최소치를 그대로 쓴 것이다.
- **백엔드는 `pytest`가 아니라 `python -m pytest`로 실행한다.**
- **pymongo는 BSON 날짜를 naive로 돌려준다**(client가 `tz_aware=True`가 아닌 한). 그것을 aware `datetime.now(UTC)`와 비교하면 `TypeError`다. **fake-collection 테스트는 이걸 재현하지 못한다** — aware를 넣으면 aware가 나오므로 **스위트는 green인데 배포만 깨진다**. 실측(2026-07-27): 세션 `expires_at` 비교가 실 Mongo에서 `GET /auth/me`를 전량 500으로 만들었는데 유닛 46건은 전부 통과했다. 규칙: **Mongo 날짜를 파이썬으로 끌어와 비교하면 `_entry` 경계에서 UTC를 재부착**하고(`auth/sessions_mongo.py`의 `_aware`), fake collection이 **드라이버처럼 naive를 돌려주는** 회귀를 함께 넣는다. 기존 코드가 무사한 이유는 같은 판정을 **쿼리 서버측**(`{"$lte": …}`)에서 하기 때문이다(`generation_job_mongo.py:85`·`indexing/mongo_repository.py:130-136`) — 그 방식을 따르면 이 함정 자체가 없다.
- **쿠키 인증 테스트는 `TestClient(app, base_url="https://testserver")`로 만든다.** 세션 쿠키는 `Secure`가 기본 on이라 http 클라이언트는 쿠키를 **조용히 버린다** — 세션 테스트가 엉뚱한 이유로 실패한다(실제로 처음 4건이 그렇게 실패했다).
- **pymongo는 BSON 날짜를 naive로 돌려준다**(client가 `tz_aware=True`가 아닌 한). 그것을 aware `datetime.now(UTC)`와 비교하면 `TypeError`다. **fake-collection 테스트는 이걸 재현하지 못한다** — aware를 넣으면 aware가 나오므로 **스위트는 green인데 배포만 깨진다**. 실측(2026-07-27): 세션 `expires_at` 비교가 실 Mongo에서 `GET /auth/me`를 전량 500으로 만들었고 유닛 46건은 전부 통과했다. 규칙: **Mongo 날짜를 파이썬으로 끌어와 비교하면 `_entry` 경계에서 UTC를 재부착**하고(`auth/sessions_mongo.py:_aware`), fake collection이 **드라이버처럼 naive를 돌려주는** 회귀를 함께 넣는다. 참고로 기존 코드가 무사한 이유는 같은 판정을 **쿼리 서버측**(`{"$lte": …}`)에서 하기 때문이다(`generation_job_mongo.py:85`·`indexing/mongo_repository.py:130-136`) — 그 방식을 따르면 이 함정 자체가 없다.
- **쿠키 인증 테스트는 `TestClient(app, base_url="https://testserver")`로 만든다.** 세션 쿠키는 `Secure` 기본 on이라 http 클라이언트는 쿠키를 **조용히 버린다** — 세션 테스트가 엉뚱한 이유로 실패(또는 통과)한다.
- live 작업 시 외부 llama(`192.168.1.22:9080`)가 죽어 있으면 in-stack llama로 돌린다. `-hf`는 재다운로드 정체가 잦아 캐시 blob을 `-m`으로 직접 지정해야 뜬 전례가 있다.

## Active Decisions (앞으로의 작업을 구속하는 것)

완료 이력이 아니라 **표준 제약**만. 근거는 각 `docs/plans/*-decisions.md`.

- **개발 단계(2026-07-20 오너)**: "Gate 우선" 단계는 끝났다. 지금은 **Gate ↔ UI/UX 왕복**이 주축이다.
- 아이디에이션·계획이 충돌하면 임의 구현 없이 오너 결정을 받는다. 나중 요청이 기록된 결정과 충돌하면 어느 쪽이 canonical인지 먼저 묻는다.
- monorepo + 독립 LLM Gateway/Worker, Application = FastAPI. 경계는 `project_id`이며 **모든 저장·검색·Gate·tool handler가 강제한다**.
- **개발 단계(2026-07-26 오너)**: MVP 단일 사용자 유예가 만료돼 **다중 사용자로 확장 중**이다(정본 v1.7.51). 사용자·세션·소유자 기록·프론트 로그인은 서 있으나 **백엔드 인가는 아직 없으므로 외부 노출 금지**. 소유권은 `project_id` 강제를 대체하지 않고 그 위에 얹힌다.
- frontend = React + TS + Vite, 서빙은 별도 compose 서비스(nginx). OpenAPI→TS 타입 생성 + 얇은 `fetch` 래퍼.
- **Core SOT**: offset = raw Unicode code point, `content_hash` = raw UTF-8 SHA-256. `source_ref` span은 단일 `source_block` 안에 든다. persistence는 Mongo transaction 기본이고 non-transaction fallback은 **single-writer local/test 전용**. project/draft는 archive(soft delete)하고 snapshot/version/source_ref는 보존한다(archive = 읽기 허용, 본문 쓰기·rename 409).
- **memory는 append-only**. AI가 직접 덮어쓰지 않고 검색·대조·Gate·검토·versioned upsert를 거친다. canonical만 `memory_vectors`에 색인하며 트리거는 async outbox→worker다. semantic 매칭은 **off 기본**.
- **재색인 enqueue는 무조건 choke point다**(v1.7.37): canonical을 만드는 모든 경로가 `MemoryService._enqueue_reindex`를 지나고 **idempotent replay도 재enqueue한다**. outbox가 PENDING/RUNNING 항목에만 dedup하므로 pending 중 replay는 no-op이고, drain된 뒤의 replay만 재색인을 한 번 더 돌린다(upsert라 오염 아님). **`promoted[]` 보고 의미론은 불변** — replay는 여전히 제외되며 바뀐 것은 색인 side-effect뿐이다.
- taxonomy 3종(`character_observation`/`event_observation`/`open_question_observation`), provenance `source_observed`/`ai_inferred`.
- **agent loop 계약층은 더 진행하지 않는다**(tool-call parsing·wire format 미계약). sub-agent spawn 없이 bounded flat loop만.
- **에러 계약(H3)**: 본문은 균일 `{"detail": <string>}`. 상태코드=기계용, `detail`=사람용이라 **`detail` 문자열로 분기하면 안 된다**. 503은 **세 얼굴** — 협력자 **미구성**(배포 구성) · 데이터 **무결성**(`scripts/migrate_ordered_units.py`) · **정본 저장소 장애**(v1.7.35, 복구 후 재시도가 유효한 유일한 얼굴). **상류가 없는 게 아니라 있는데 실패한 것은 502**이고, **정본 저장소는 상류가 아니라 503**이다. 저장소 face는 `create_app`의 **전역 exception handler**가 매핑하므로 새 endpoint가 자동 상속한다 — 다만 **`responses=`에 503을 붙이는 것은 여전히 수동**이고 전수 가드가 빠뜨림을 잡는다(`/health`만 제외).
- **균일 본문의 유일한 예외 = partial envelope**, 허용 지점 **정확히 6곳**(revise-and-gate 4 · accept 1 · auto-promote 1). 되돌릴 수 없는 성공 부분이 이미 영속된 실패 경로만 해당하며, 새 Union은 정본 목록을 함께 넓히는 명시 결정으로만 들어온다(트랙별 over-strict 가드가 drift를 막는다).

## 추적 부채

- **[미구현이나 구현 결정됨, 포트폴리오 정확성 주의] cross-encoder(뉴럴) 리랭커는 아직 없다.** 현재 RAG 리랭킹은 **RRF(Reciprocal Rank Fusion) 융합만**이다 — 벡터(Chroma/BGE-m3-ko) + lexical(ES/nori) 두 랭킹을 `1/(k+rank)`(k=60)로 합쳐 재정렬([`context_search/service.py:279`](services/application/app/context_search/service.py#L279)·[`:495`](services/application/app/context_search/service.py#L495), env `vector/lexical/hybrid`). query-document 쌍을 신경망으로 재채점하는 cross-encoder 리랭커는 2026-07-05에 유예됐다가([`plans/04-real-vector-backend-decisions.md:11`](docs/plans/04-real-vector-backend-decisions.md#L11)) **2026-07-27 구현하기로 결정**됐다(`plans/external-api-expansion-decisions.md` D5): 로컬은 self-host **`dragonkue/bge-reranker-v2-m3-ko`**(임베딩 서비스와 같은 패턴), 외부 리랭커 API도 붙일 수 있게 `RerankProvider` seam을 함께 뚫는다. **별도 슬라이스**(인증·외부 API LLM/임베딩 슬라이스 뒤). **삽입 자리**: RRF 융합 결과 뒤, `retrieve()` seam 다음. **포트폴리오/README 표기**: 현재 상태는 "RRF 하이브리드 융합 리랭킹 있음, 뉴럴 cross-encoder 리랭커는 미구현(구현 예정)"이 정확 — 코드가 붙기 전까지 "있음"으로 쓰면 거짓이다.
- **[미래 확장, 지금 범위 아님] 공유·협업 글쓰기.** 오너(2026-07-27)가 "생각 안 해봤다 — 나중에 한 번 생각해보자"며 유예. 다중 사용자 소유권은 **D3=A(`Project.owner_id` 한 필드 = 격리, 1 project 1 owner)**로 가되, 공유/협업(권한 등급·workspace·`members[]`)은 미래 확장이다. D3=A가 그 문을 **닫지 않게** 설계돼 있다(`owner_id`는 나중에 `members[]` 첫 원소나 workspace 소유로 승격 가능 — `plans/multi-user-auth-cms-decisions.md` D3). 착수 시점 아님.
- **[D8-3a가 깨뜨림, 미수리] `APPLICATION_BASE_URL`로 앱 HTTP API를 치는 운영 smoke 스크립트 4종은 이제 401을 받는다**: [`phase2a_deployed_e2e_smoke.py:33`](scripts/phase2a_deployed_e2e_smoke.py#L33) · [`phase3a_deployed_rebuild_smoke.py:36`](scripts/phase3a_deployed_rebuild_smoke.py#L36) · [`phase4_context_search_deployed_smoke.py:56`](scripts/phase4_context_search_deployed_smoke.py#L56) · [`phase6_gate_finding_live_smoke.py:71`](scripts/phase6_gate_finding_live_smoke.py#L71). 로그인 옵션(계정·비밀번호 전달 + 쿠키 유지)을 붙이는 별도 증분이 필요하다. **워커는 무관하다** — HTTP를 안 쓰고 Mongo에 직접 붙는다(그쪽은 D8-7).
- **[누수 아님, 의존성 주의] `context_search/service.py:199`·`:406`의 `embed()`**: 자체적으로 `EmbeddingProviderError`를 안 잡지만 호출자(step runner `:752`·`:835`)의 광의 `except Exception` → `BACKEND_ERROR` → 502가 이미 보호한다. **그 catch를 좁히면 그 순간 500 누수가 된다.**

## Owner Decisions Needed

- **★ dogfood 착수(GATE-1)** — 실 12B 풀스택 관통은 끝났고 기술적 선행 조건은 없다. 착수하면 `OPS-1` Ready 승격. 지금은 **인증(D8)이 진행 중**이라 그 뒤로 밀려 있다 — 인증 도중에 끼울지, 끝내고 할지는 오너 판단.

**결정 완료 — 오너 결정 대기 아님, 구현만 남음:**

- **다중 사용자 인증 D0~D8 + E1~E4 = 전부 결정됨**. 3-a(인증)까지 섰고 남은 것은 3-b 소유권·3-c 전수 가드다. Mongo·ES 인증은 별도 **D8-7**이며 HTTP 인가와 섞지 않는다.
- **외부 API 확장 D1~D6 = 전부 결정됨**(2026-07-27). `plans/external-api-expansion-decisions.md` §2: 세 축 전부 확장하되 **슬라이스 분리**(LLM → 임베딩 → 리랭커)·D2=A(generic OpenAI 호환)·D3=A(env 키, 인증 시크릿 재사용)·D4=A(전역 기본)·D5=리랭커 포함(self-host `bge-reranker-v2-m3-ko` + 외부 seam). 코드 실측 공백 = 인증 헤더 주입 지점·provider 선택 config. **착수는 인증 다음**.
- **`analysis_extractor`를 D4로 정렬할지**(v1.7.47): 지금 이 site만 최종 도메인 거부를 `parse_error`로 재분류하지 않아 같은 repair 구조인 `compare_judge`와 정책이 갈린다. 정렬하면 두 site가 같은 규칙을 따르고, 두면 v1.7.46 결정이 유지된다. 어느 쪽이든 이행 무손실 증명이 필요한 별도 증분.
- **loop의 round별 gate decision 노출 여부**(v1.7.47 공백): 노출하면 loop 내부 gate 레코드에도 파생점수를 얹을 수 있다. 도메인 계약(`WritingLoopStage`) 변경이라 D2-B(파생점수 정교화)와 함께 볼 사안.

## Next Tasks

**1번이 현재 진행 중인 트랙이다.** 나머지는 그와 무관하게 남아 있는 것들.

1. **인증 D8-3b — project 소유권(403) + `GET /projects` 저장소 경계 필터.** `owner_id=None`은 항상 deny(E1=A). 목록 필터는 응답 후 가공이 아니라 **저장소 조회 경계**에서 — 다른 사용자의 project id·이름·archive 상태 어느 것도 새지 않아야 한다(E2=A). 3-a의 전수 가드 두 겹을 403 쪽으로 확장한다. 이어서 3-c 최종 전수 가드.
2. **스택을 올리면 바로 할 것 — 화면 육안 확인 2건**(둘 다 로직은 회귀로 잠겨 있고 **렌더만** 미검증):
   (a) 관측 화면 `/projects/:id/observability` — 차트 라벨 충돌·막대 배치·좁은 화면 표 넘침.
   (b) 비동기 패드 — 렌더 · 이어쓰기 탭 완료 배지 · 5초 폴링 · "다시 시도" 버튼 · 탭 전환 후 폴링 생존.
3. **관측 화면을 더 키우는 것은 API에 시간 창(`?since=`)이 생긴 뒤**가 옳다 — 지금 차트가 그리는 것은 누적 스냅샷이라 추세가 없고 막대는 표와 같은 정보를 말한다. 무엇을 더하든 **`React.lazy` 경계 안**에 둘 것(밖으로 나가면 진입 번들이 다시 두 배가 된다).
4. **dogfood 관찰 항목**: `report field must be an array` 실패율(12B 간헐 비-배열, repair가 흡수 — 잦으면 repair 횟수/프롬프트 축 판단) · `analysis_extract_v4`의 `aspect` 오분류 빈도 · scratch per-draft 상한(기본 20) 밀어냄.
5. **Deferred(오너 결정 선행)**: 중첩 chapter→scene tree · ProjectBrief→Draft provenance · 관계 graph/완전 timeline · saved publication manifest · Phase 7 대화형 수정(`plans/07-conversational-authoring.md`).

## Project Structure

```text
docker-compose.yml            # 배포 스택: application·mongo(rs0)·gateway·embedding·chroma·elasticsearch(nori)·worker·generation_worker·frontend(nginx)
docker-compose.test.yml       # 테스트 전용 단일노드 RS mongo(27020) — 명시 -f 로만 뜬다
docker-compose.llama.yml      # opt-in: in-stack llama.cpp GPU 서버(9080)
.env.example                  # 호스트 게시 포트 전용 대역 + 근거
CLAUDE.md / AGENTS.md         # 작업 규칙(동일 내용). HANDOFF 편집 규칙·자가 검수 트리거 포함
docs/
├── system-contract-sot.md    # ★ 정본 계약 + 변경이력(버전별)
├── plans/                    # 계획 + 착수 결정 브리프(*-decisions.md)
├── daily_logs/YYYY-MM-DD/    # 작업 상세 이력
├── verifications/YYYY-MM-DD/ # 독립 검증 기록
├── runbooks/                 # 로컬 llama 등 운영 절차
└── abstract.md 등            # 보존된 아이디에이션 원본
schemas/                      # W0 등 계약 schema
scripts/                      # 마이그레이션·live smoke·worker 엔트리포인트
services/
├── application/app/          # FastAPI 본체
│   ├── main.py               # 전 endpoint + 에러 선언 상수(_ERRORS_*)
│   ├── auth/                 # 사용자·Argon2id·서버 세션·쿠키 정책 (인가는 D8-3에서)
│   ├── core_sot/             # 정본 저장(project/draft/version/snapshot/source_ref)
│   ├── analysis/ memory/     # 추출·후보·비교·승격
│   ├── context_search/       # ContextPackage 구성 + Gate
│   ├── writing/              # 생성·Gate·revise·accept·scratch·생성 job
│   ├── indexing/             # vector/lexical 색인, embedding provider
│   └── observability/        # per-LLM-call 감사 + ObservedProvider/llm_call_scope(seam C)
├── llm_gateway/              # LLM 경계(ProviderError taxonomy)
└── embedding/                # 임베딩 서비스(BGE-m3-ko, 1024-dim)
frontend/                     # React+TS+Vite SPA (recharts는 관측 화면 전용·lazy 로드)
├── src/auth/                 # 로그인·세션 확인/만료·route guard·서버 로그아웃
├── src/observability/        # KPI 대시보드(계약이 정한 오독 방어 3종을 화면이 물려받는다)
├── nginx.conf                # /api 리버스 프록시(변수 upstream + resolver)
└── src/api/schema.d.ts       # gen:api 생성물 — 손으로 고치지 않는다
tests/                        # 백엔드 회귀(python -m pytest)
```
