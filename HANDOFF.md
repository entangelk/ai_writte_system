# HANDOFF

> **다음 작업자가 지금 일을 시작하는 데 필요한 것만.** 이력이 아니다.
> **공개 저장소 보안 규칙:** 원격 배포 대상의 IP·호스트명·계정명·SSH 키 경로·서버 내부 절대경로·구체 토폴로지·비밀값을 `HANDOFF.md`·`docs/daily_logs/`·`docs/verifications/`·`CHANGELOG.md` 등 저장소 문서에 기록하지 않는다. 배포 기록은 역할 별칭과 민감정보를 제거한 결과만 남기고, 실제 접속 정보는 저장소 밖에서 관리한다.
> **완료 서술도, 근거·측정치·발견 경위도 여기 쓰지 않는다** — `docs/daily_logs/`(상세) · `docs/system-contract-sot.md` 변경이력 · `CHANGELOG.md`(마일스톤) · `docs/verifications/`(독립 검증) · `docs/plans/*-decisions.md`(왜 그렇게 정했는가)에 있다. **여기 남는 것은 "지키지 않으면 깨지는 것"과 "어디를 보면 되는가"뿐이다.**
> 편집 규칙은 `CLAUDE.md`·`AGENTS.md`의 "HANDOFF.md" 절에 있다. **~200줄을 넘으면 자가 검수**하고(그 뒤로는 ~100줄마다) 결과를 아래 한 줄로 남긴다.
>
> 마지막 자가 검수: **2026-09-08 · 304줄** — 절별로 현재 착수에 필요한 계약·함정·열린 일만 남는지 다시 확인하고, Slice 2 완료 서술은 작업 로그·SoT로 보내며 Next Tasks와 11번을 Slice 3 기준으로 다시 썼다.

## 머신 · 기동

이 프로젝트는 성격이 다른 세 머신을 옮겨 다닌다. **문서가 "환경과 안 맞는다"고 느껴지면 먼저 지금 어느 머신인지 본다.** 표는 각 머신이 *무엇을 띄울 수 있는지*(항구적 성질)이지 *지금 무엇이 떠 있는지*가 아니다 — 후자는 `docker compose ps` 로 그 자리에서 잰다.

| 머신 | 역할 | LLM | GPU |
|---|---|---|---|
| **알파** | 서비스 배포용 | in-stack llama(`docker-compose.llama.yml`) | RTX 3060 12GB |
| **베타** | 테스트·개발용 | 외부 LLM(gemma-4-12B, LAN) — 주소·context는 `.env`·`/props` 로 잰다 | GTX 1060 3GB(12B 못 올림) |
| **감마** | 사이드 개발용(노트북) | 없음 — LLM 관통 작업 불가 | — |

- **2026-09-05 현재 알파다**(오너 확인). 09-04 까지의 작업·회귀 기준선은 베타에서 잰 것이고, 두 라벨은 충돌이 아니라 전환이다. **머신-로컬 수치(전수 소요·VRAM)를 다른 머신 값과 비교하지 말 것.**
- **★ 배포는 외부 API 로 돈다 — LLM 도 임베딩도**(오너 확인 2026-09-06: **배포 서버의 `.env` 가 이 머신과 같다**). 위 표의 알파 행 *"in-stack llama"* 는 **띄울 수 있는 것**이지 지금 도는 것이 아니다. 실효 축은 `.env` 넷이고 **값은 저장소에 적지 않는다**: `LLAMA_API_FORMAT=openai`(OpenAI 호환 벤더 — 함정 절 ①) · `LLAMA_DEFAULT_MODEL` 존재(없으면 `gemma-local` 을 명시해 호출이 전멸) · `EMBEDDING_API_FORMAT=openai`(키만 넣으면 안 바뀐다 — 함정 절 ③) · `LLAMA_KEY_RPM` 과 함께 **키가 복수**다(`LLAMA_API_KEYS`). **임베딩이 in-stack BGE-m3-ko(1024)가 아니라 외부 모델이고 차원도 다르다** — `EMBEDDING_DIMENSIONS` 를 `.env` 에서 그 자리에 확인하고, **모델을 바꾸면 재색인**이 규칙이다(차원까지 바뀌면 fail-fast 로 멈추지만 **차원이 같은 다른 모델이면 아무 일도 안 일어나고 품질만 조용히 떨어진다** — 절차는 [`README.md`](README.md)). 이 전환 자체는 새 일이 아니다(SoT **v1.7.99**, 2026-08-23 이 모델 교체가 드러낸 파싱 결함을 이미 기록한다).
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

**★ 배포 호스트가 실제로 쓰는 조합은 `docker-compose.yml` + `docker-compose.external-embedding.yml` 이다**(2026-09-06 컨테이너 생성 라벨 실측 — 위 표의 "외부 API 전용" 행이 가리키는 `external.yml` 이 아니다). **그 조합의 정상값은 healthy 8이 아니라 7이다** — `embedding` 이 profile 뒤로 가기 때문이다.

**스택 health**: 정상은 **healthy 8**(application·**admin**·gateway·mongo·elasticsearch·embedding·chroma·frontend) + **healthcheck 없는 2**(worker·generation_worker — by design, "Up"이지 healthy 아님). **"전부 healthy"라고 쓰지 않는다.**

**이미지**: `application`·`admin`·`worker`·`generation_worker` 네 서비스가 **같은 `image: ai_writte_system-app` 태그**를 공유하므로 `docker compose build` 한 번이면 넷이 갱신된다. **새 서비스가 이 Dockerfile 을 쓰면 `image:` 를 함께 적는다.** 인증 백엔드 변경은 application, 로그인 UI 변경은 frontend rebuild가 필요하다.

## 지금의 계약

정본은 [`docs/system-contract-sot.md`](docs/system-contract-sot.md) **v1.8.48**(Approved). **미확정 항목은 추측 구현하지 않는다.** 아래는 코드를 만지기 전에 알아야 하는 요약이다.

- **배포되는 앱이 둘이다.** `/admin` **17 operation**은 포트를 게시하지 않는 `admin` compose 서비스가 서빙하고 도달 경로는 nginx `location /api/admin/` 하나다. 제품 앱에는 그 route가 **없으므로** LAN에서 치면 가드가 아니라 **라우터가 404**다. `create_app()` 은 **105 operation 합집합**이고 테스트·경계 행렬·`dump_openapi.py`(= 프론트 `schema.d.ts`)가 전부 그것을 쓴다 — 브라우저는 nginx 뒤에서 한 origin만 보므로 **계약은 하나여야 한다**. 세 factory(`create_app`·`create_product_app`·`create_admin_app`)는 **한 함수 본문**이고 플래그로만 갈린다. 가드 [`test_admin_surface_separation.py`](tests/test_admin_surface_separation.py).
- **operation tier = 전체 105 · project 76 · admin 17**([`test_auth_api.py`](tests/test_auth_api.py) 의 tier 핀이 정본 — 줄 번호는 움직인다).
- **인증·인가.** 세션 없는 요청은 `/health` 와 공개 `/auth` 를 빼고 401. project-scoped 76은 타인 소유·`owner_id=None` 에 403(**`owner_id=None` 은 항상 deny**). `GET /projects` 는 Mongo `owner_id` 쿼리 경계에서 본인 소유만 반환한다. **403 생산자는 다섯** — 소유권 · 관리자 · 가입 승인 대기/거절 · quota 정지 · **탈퇴 유예 중 일반 쓰기**(`require_active_user_for_write`). 탈퇴 계정도 GET·HEAD, 로그인, `GET`·`POST`·`DELETE /me/withdrawal`은 가능하고, 유료 경로는 탈퇴 가드가 quota보다 먼저 막는다. 가드는 `test_auth_api.py` 의 경계 행렬과 withdrawal guard 셀이며 **새 endpoint는 모두 본다**.
- **관리자 경계.** 관리자는 project 내용에 자동 접근하지 않는다 — 내용 조회는 **사유 필수·1시간·읽기 전용 승격**만 가능하고 `owner_id=None` 은 승격으로도 안 열린다. 승격 사용 감사(`access_grant_uses`)는 **fail-closed**. **마지막 활성 관리자는 비활성화되지 않고**(409) 비활성화는 **단방향**이다(재활성화 API 없음). 첫 관리자는 부트스트랩 스크립트로만 만든다: `docker exec -e PYTHONPATH=/app -e AUTH_BOOTSTRAP_PASSWORD='…' <application> python scripts/create_user.py <username> --admin` — **`PYTHONPATH=/app` 이 필수**이고 그 비밀번호는 **1회용**(첫 로그인에 12자 이상 `new_password` 동반).
- **저장소는 LAN에서 안 보인다 — 그러나 인증된 것은 아니다.** `mongo`·`chroma`·`elasticsearch`·`gateway`·`embedding`·`test-mongo` 가 **`127.0.0.1:` 바인드**다. **저장소 자체는 여전히 무인증이라 바인드가 유일한 방어**이고, 일부러 공개인 것은 셋뿐이다(`application`·`frontend` = 세션 뒤 제품 표면 · **`llama` 9080** = 12B를 못 올리는 머신에 모델을 주는 유일한 크로스머신 의존). 가드 [`test_compose_exposure.py`](tests/test_compose_exposure.py) 는 **새 서비스가 포트를 게시하면 분류를 강제**한다. **★ 이것은 파일 수준 시행이라 이미 만들어진 컨테이너는 재생성 전까지 안 닫힌다.**
- **`/docs`·`/redoc`·`/openapi.json` 은 비공개다**(SoT v1.7.98). `create_app` 의 `FastAPI(docs_url/redoc_url/openapi_url=None)` **한 곳**으로 셋 다 차단된다([`main.py:1777`](services/application/app/main.py#L1777)). **env 토글 없음** — 공개가 필요하면 명시 결정으로 연다. 스키마 소비자는 전부 import 방식이라 계약 생성은 무변이다.
- **quota.** 유료 경로에 `Depends(enforce_quota)` 가 붙고 `_REQUIRE_PROJECT_OWNER_BILLABLE` = **소유권 → 시행** 순서다(그 순서가 곧 "404·403은 무과금"). **차감은 `2xx` 그리고 provider 호출이 있었을 때만**(replay처럼 아무 일도 안 한 200은 안 센다). **정산은 dependency의 `yield` 뒤가 아니라 `QuotaSettledRoute` wrapper에 있다 — 벗기면 잠금이 영영 안 풀린다.** 기본 한도는 **일 20 / 주 100**이고 진행 중 요청·대기 job이 그 한도를 차지한다. **관리자도 신분으로는 면제가 아니다**(면제는 `limit=None` 정책 행). 같은 동작 **5초 최소 창**이 있어 스크립트를 연달아 돌리면 429다 — `X-Confirm-Duplicate` 헤더나 5초 대기. **★ [`quota/policy.py`](services/application/app/quota/policy.py) 가 이 저장소의 유일한 지역 시간대(KST) 지점이다** — 창 키 계산을 다른 곳에서 또 하면 화면과 시행이 다른 "오늘"을 말한다. **`policy.limits` 는 유효 한도가 아니다** — 읽기는 항상 `effective_limits`/`limits_for` 를 지난다.
- **파기(purge)와 이름 이력.** 삭제 표면은 셋이다 — 원고 하드 삭제 `POST …/drafts/{did}/purge`(아카이브 선행 409 · **active** 잡 409, **종료된 잡은 막지 않는다**) · 소유자 프로젝트 purge · 관리자 아카이브. **소유자 purge와 admin purge는 `execute_project_purge` 한 벌을 공유한다 — 새 서비스가 파기 그래프에 들어오면 그 함수만 고친다.** UI 503 계약은 양 면 대칭이다: **파기 단계 503 = uncertain 잠금(재시도 금지 · reconciler 확인)**, 재파기 404 = 성공 처리, **보관 단계 실패만** 재시도를 되살린다. **★ `project_name_history` 에 `project_id` 필드를 절대 더하지 말 것** — reconciler가 그 필드로 sweep 대상을 발견하므로 더하는 순간 이 컬렉션이 지워진다. **이름 스냅샷은 파괴 앞이고 fail-closed**(뒤로 옮기거나 `try/except` 로 감싸면 이름 없이 사라지는 프로젝트가 생긴다). **`_id` 충돌은 "잠겨 있음"의 증거가 아니라 신호다** — 충돌 뒤 살아 있음을 다시 확인하고 없거나 만료면 원자적으로 재차지한다.
- **활동 로그.** `activity_events` 는 `project_id` 필드를 쓰고 **파기와 함께 사라진다**(위 `project_name_history` 와 **정반대** — 그쪽의 `_id` 트릭을 여기 복사하면 D8-6이 무너진다). 분류표 [`activity/actions.py`](services/application/app/activity/actions.py) 가 정본이고 **미등재 mutating route는 가드가 실패시킨다**. **기록은 handler 본문에서 결과를 안 뒤**(dependency로 옮기면 404·409가 "했다"로 남는다). **기록 실패는 요청을 안 죽이지만 파기 실패는 삼키지 않는다.** `before`/`after` 는 라벨만(200자) — 본문을 넣으면 `draft_versions` 와 두 정본이 된다.
- **관측(KPI).** LLM 호출부 9종이 seam C(provider 데코레이터)로 계측된다. **실패한 호출도 센다**(성공만 세면 성공률이 영구히 100%). **scope 밖 호출(worker·script)은 기록하지 않는다**(추측 `project_id` 는 오염). per-project와 전역이 `kpi.py` 의 `_fold` **한 곳을 공유**한다 — 한쪽만 고치면 두 화면이 다른 사실을 말한다.
- **에러 계약(H3).** 본문은 균일 `{"detail": <string>}`. 상태코드=기계용·`detail`=사람용이라 **`detail` 문자열로 분기하면 안 된다**. 균일 본문의 유일한 예외는 **partial envelope**이고 허용 지점은 **정확히 6곳**(revise-and-gate 4 · accept 1 · auto-promote 1). 새 endpoint는 `responses=` 와 dependency를 함께 붙이고 tier 전수 가드에 등재한다.
- **길이 상한.** 유닛 본문 **6000자**(오너 2026-09-08 에 4000 에서 상향 — 현재 장면이 검색 조각 예산의 ~29%→**~43%** 를 가져간다) · 브리프 스칼라(premise·genre·tone·pov) **1000자**. 상수는 [`app/env.py::draft_raw_text_max_chars`](services/application/app/env.py) **하나**이고 저장 축(422)과 accept 축(400)이 같은 상수를 읽는다. **accept의 검증은 provider 호출 앞**이다(상한 넘을 몸에 유료 호출이 돈을 쓰면 안 된다). **프론트는 경고+저장 차단이지 잘라내기가 아니다 — textarea `maxLength` 금지**(정본 보존, no-maxlength 셀이 문다).
- **Chapter/Scene 계층.** metadata-only Chapter + Scene(Draft), parent별 연속 순열, AI는 같은 장의 다음 Scene만. **legacy 평면 Draft는 CRUD·accept가 503 fail-closed(2층)이고 export·versions만 대피 경로로 200**이다 — 대피 경로를 막으면 이관 못 한 데이터가 갇힌다. 공개 `unit_kind` 는 제거됐고 `core_sot` 의 legacy migration 입력으로만 남아 있다.
- **검토함 그룹 읽기면.** `identity_group` payload 6키 중 **`group_revision` 만 표시 전용이 아니다** — 그룹 승인 body `expected_revision` 의 **유일한 조달 경로**이고(409 detail 에 값이 있으나 **H3 가 detail 분기를 금지**한다) 값은 살아 있는 그룹의 것 그대로여야 한다(파생 금지). **`revision` 은 `set_group_status` 에서만 오른다** — `add_member` 는 그룹 행을 안 건드리므로 실전 값은 대개 `0` 이고, 그래서 **셀 픽스처를 0 으로 두면 상수 박기가 전건 통과한다**(신규 셀이 상태 전이 2회로 revision 2 ≠ 멤버 3 을 만드는 이유). **그룹 액션 결과 상자는 페이지 수준에 둔다** — 그룹 행 안에 두면 끝난 그룹이 목록에서 빠질 때 결과도 사라지는데, 거절 요약과 부분 실패는 **재조회를 넘겨 살아야 하는** 사실이다. `applied`/`skipped` 아닌 step 을 "반영"으로 세면 D4=A 의 200 이 성공으로 닫힌다.
- **검색과 리랭커.** 벡터(Chroma/BGE-m3-ko — **다만 배포는 외부 임베딩이라 모델도 차원도 다르다**, 위 "머신 · 기동") + lexical(ES/nori)을 RRF(`1/(k+rank)`, k=60)로 융합하고 리랭커는 **그 뒤에** 걸린다. **★ 리랭커 표기는 세 조각이고 "있음" 한 단어로 쓰면 거짓이다** — *"외부 API 리랭커 붙일 수 있음(**기본 꺼짐**) · self-host 미구현 · **품질 평가 미실시**"*. `RERANK_API_URL` 이 비면 조립이 감싸지 않고 검색은 RRF까지만으로 동작한다. **실패는 열려 있다(fail-open) — 프로바이더가 아니라 *단계 전체*가 그렇다**(순열 아닌 응답·텍스트 투영 예외 포함). 다만 **조용히 삼키지 않는다**(`logging.WARNING` + `exc_info`) — fail-open이 조용하면 리랭킹이 영원히 no-op인 채로 아무도 모른다.
- **회귀 기준선**: backend **test-mongo ON 2964 passed / 1 skipped / 4089 subtests**(2026-09-09 **알파·호스트**, 2268초 — 계정 탈퇴 Slice 0·1·2 + 검증 하드닝(인덱스 단면 가드·주석 정정) 포함, 커밋 `422e79c`. **소요는 머신-로컬 값이라 333초와 비교하지 말 것**). **★ 이 줄은 세 슬라이스 동안 뒤처져 있었다**(종전 2903 은 D4 커밋 `6eeedf5` 의 값이고 그 뒤 `285205b`·`8083a94`·`5759d9e` 가 7셀을 더했다) — **갱신은 셀을 더한 슬라이스의 몫**이고, 어긋났을 때 유도하는 법은 `git worktree add --detach <경로> <리비전>` 뒤 양쪽에서 `python3 -m pytest --collect-only -q`(수집 수 = passed + skipped)다. 프런트는 **467 passed / 38 files**(2026-09-07, 오너 관측 2건 수정 포함). **전수 1실패를 만나면 위 미수리 표의 *알려진 플레이크* 부터 볼 것.** **전수 판정은 `passed` 가 아니라 `skip` 수를 먼저 본다 — `skip 1 = live Chroma` 하나뿐이고, 2 이상이면 호스트에 빠진 패키지가 있다는 뜻이다**(함정 절 "호스트 도구 공백"). **★ subtest 수가 하루 안에 3189 → 7881 → 3789 로 출렁였다 — 커버리지 변화가 아니다.** 위생 가드가 처음엔 (파일×금지값)마다 subtest 를 냈다가(단독 4665), 검증 조건 B1 을 닫으면서 **스캔을 회계로 바꿔** 위반이 있을 때만 subtest 를 낸다(단독 572). 파일별 검사는 그대로 돌고 **전건 방문 여부를 셀이 직접 단정하므로 오히려 강해졌다** — subtest 수를 커버리지 대리지표로 읽지 말 것. **★ 최상위 [`README.md`](README.md) 절차 표의 `N passed / N subtests` 는 아무 가드도 안 잡는다** — 기준선을 갱신하는 슬라이스가 그 한 줄도 함께 고친다.

## 표준 제약 (Active Decisions)

완료 이력이 아니라 **앞으로의 작업을 구속하는 것**만. 근거는 각 [`docs/plans/*-decisions.md`](docs/plans/README.md).

- **★ 정본을 나누는 것을 두려워하지 않는다**(2026-08-10 오너): *"서로 다른 섹션의 정본이면 정본은 몇 개가 되든 상관없어. **인덱싱만 제대로 되어 있고 연결만 되어 있으면**."* — 중복이 문제이지 분할이 문제가 아니다.
- **아이디에이션·계획이 충돌하면 임의 구현 없이 오너 결정을 받는다.** 나중 요청이 기록된 결정과 충돌하면 **어느 쪽이 canonical인지 먼저 묻는다.**
- **개발 단계**: "Gate 우선"은 끝났고 지금은 **Gate ↔ UI/UX 왕복**이 주축이다(2026-07-20 오너). MVP 단일 사용자 유예는 만료돼 **다중 사용자로 확장 중**이다(2026-07-26 오너, 정본 v1.7.49 = D0=A).
- **구조**: monorepo + 독립 LLM Gateway/Worker, Application = FastAPI. **경계는 `project_id` 이며 모든 저장·검색·Gate·tool handler 가 강제한다.** frontend = React + TS + Vite, 서빙은 별도 compose 서비스(nginx), OpenAPI→TS 타입 생성 + 얇은 `fetch` 래퍼.
- **제품명은 "에-라잇" 하나이고 대상은 화면만이 아니다**(D5). 새 서비스의 FastAPI `title=` 도 대상이고 오너가 정한 정확한 글자를 `_DECIDED_TITLES` 표에 더하는 것이 정상 경로다([`test_product_name.py`](tests/test_product_name.py) 가 세 서비스의 `app.title` 정확 일치와 옛 이름 재유입을 함께 단정한다). **★ 식별자는 표시명이 아니라 바꾸지 않는다**(`ai_writing_system` DB 이름 · npm 패키지명 · 이미지 이름). **★ 이력 문서는 대상이 아니다** — `HANDOFF.md`·`CHANGELOG.md`·`docs/` 에 옛 이름이 남는 것은 맞다(그것이 그때의 사실이다).
- **Core SOT**: offset = **raw Unicode code point**, `content_hash` = **raw UTF-8 SHA-256**. `source_ref` span 은 단일 `source_block` 안에 든다. persistence 는 Mongo transaction 이 기본이고 **non-transaction fallback 은 single-writer local/test 전용**이다.
- **memory 는 append-only.** AI 가 직접 덮어쓰지 않고 검색·대조·Gate·검토·versioned upsert 를 거친다. **canonical 만 `memory_vectors` 에 색인**하며 트리거는 async outbox→worker 다. **semantic 매칭은 off 가 기본.**
- **taxonomy 3종**(`character_observation`·`event_observation`·`open_question_observation`), provenance 는 `source_observed`·`ai_inferred`.
- **★ agent loop 계약층은 더 진행하지 않는다**(tool-call parsing·wire format 미계약). **sub-agent spawn 없이 bounded flat loop 만.**

## 함정 (모르면 시간을 잃는 것들)

**기동·환경**
- **`test.yml up -d` 직후 곧바로 전수를 돌리면 Mongo 셀 11개가 조용히 skip 된다 — 요약줄은 초록이다.** 복제셋이 writable PRIMARY가 될 때까지 기다린다.
- **오래된 `application` 이미지는 죽지 않는다. 조용히 *인증 없는 제품*으로 뜬다.** auth 이전 이미지는 `argon2` import 자체가 없어 healthy를 보고하는데 `/auth/login` 이 404이고 `GET /projects` 가 세션 없이 200이다. **규칙: 스택을 올린 뒤 `curl :8520/projects` 가 401인지 먼저 본다.** 트리 마운트는 코드만 덮고 파이썬 패키지는 이미지 것이다.
- **알파에서는 `.env` 에 `LLAMA_CTX_SIZE=16384`.** 기본은 [`docker-compose.llama.yml:29`](docker-compose.llama.yml#L29) 의 8192이고 `.env.example` 에 항목이 없다. R-e 이후 이유가 바뀌었다 — "안 죽게"가 아니라 **"K-3 가드에 400으로 거부당하지 않으려고"**다.
- **외부 API 배포에서 `.env` 에 `LLAMA_DEFAULT_MODEL` 이 없으면 앱이 `gemma-local` 을 명시해 LLM 호출이 전멸한다.**
- **compose의 포트 매핑 변경은 이미 만들어진 컨테이너에 적용되지 않는다 — `up -d` 로도 안 된다.** 재생성이 필요하다. **★ `restart` 정책도 같고, 이 함정은 이미 한 번 터졌다.** 2026-09-06 에 전 서비스로 통일했지만(가드 `ComposeRestartPolicyTest`) **그 시점에 떠 있던 컨테이너는 재생성 전까지 옛 정책(`no`)을 든다** — 2026-09-08 에 개발 스택의 **인프라 6컨테이너가 8일간 내려가 있는 것**이 그렇게 발견됐다(정책이 없던 다섯 = `mongo`·`application`·`gateway`·`chroma`·`elasticsearch`, `git show 1a0b94a` 가 그 목록의 정본). **이 머신은 재생성으로 닫혔다**(`docker inspect` 실측 2026-09-08, 여섯 다 `unless-stopped`). **배포 호스트는 미확인이고 여기서 잴 수 없다** — 다음 배포에서 `docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' <컨테이너>` 로 확인하고 `no` 면 재생성한다. 증상이 **조용한 장애**라는 것이 이 함정의 값이다: `frontend` 는 200 을 주는데 API 가 죽어 있다.
- **compose의 `${}` 표기는 취향이 아니라 코드가 그 변수를 읽는 방식을 따라간다.** `if not os.environ.get(name)` 로 읽으면 **dash `${VAR-default}`**, `os.environ.get(name, DEFAULT)` 로 읽으면 **콜론 `${VAR:-default}`**. 다른 40여 항목이 콜론이라 "통일"하고 싶어지는데 **그 통일이 곧 회귀**이고 양방향 다 셀이 문다. **두 방향 모두 배포에서만 드러난다.**
- **`CHROMA_PORT` 를 env화하지 말 것** — 같은 이름이 host publish에서는 호스트 포트를, environment에서는 컨테이너 내부 포트를 뜻한다. 외부 Chroma는 override 파일로 붙인다.
- **`ulimits.nofile` 은 튜닝이 아니라 필수다**(기본 1024면 WiredTiger가 mongod를 죽인다).
- **출시된 프롬프트 본문은 immutable이다** — 오래된 데이터 볼륨과 현행 프롬프트 핀이 충돌하면 `PromptTemplateConflict` 로 앱이 죽는다. 볼륨을 비우는 것이 처방이다(embedding 모델 캐시는 보존).
- **`docker-compose.llama.yml` 의 `-hf …:Q4_0` 은 리비전을 고정하지 않는다** — 캐시에 온전한 모델이 있어도 업스트림 `refs/main` 이 움직이면 **~6.5GB를 다시 받는다**. llama healthy가 `up -d` 전체의 관문이라, 급하면 `--no-deps` 로 분리 기동한다.
- **호스트 도구 공백**: 일부 호스트에 `python` 이 없고 `python3` 만 있다 · **Mongo DB 이름은 `ai_writing_system`** 이다(`ai_writing` 아님 — 그 이름으로 조회해 "DB가 비었다"는 거짓 판독을 한 번 냈다) · **★ 전수는 컨테이너가 아니라 호스트에서 돈다** — 앱이 lazy import 하는 패키지가 호스트에 없으면 그 셀은 실패가 아니라 **skip** 이고 요약줄은 초록이다(2026-09-06: `elasticsearch` 부재로 lexical retrieval 셀 3개가 그렇게 숨어 있었다 → `requirements-dev.txt` 에 프로덕션과 같은 핀으로 등재해 닫았다). **★ 이 호스트의 파이썬 의존성은 전부 `~/.local` user-site 에 있다**(`pytest`·`mypy`·`argon2`·`elasticsearch` …). PEP 668 때문에 맨 `pip install` 은 거부되므로 **`pip install --user --break-system-packages`** 로 넣는다 — 이름과 달리 `--user` 와 함께 쓰면 `/usr` 를 건드리지 않고 `~/.local` 에만 쓴다. **scratchpad venv 는 이 용도로 못 쓴다** — 전수를 `/usr/bin/python3` 로 돌리므로 venv 안의 패키지는 안 보인다(일회성 도구 하나를 격리해 돌릴 때만 venv 가 맞다).
- **첫 `docker` 명령이 30초 넘게 안 돌아올 수 있다**(데몬 워밍업). **라이브 검증은 재빌드 말고 작업 트리를 마운트해 돌린다**: `docker compose run --rm --no-deps -v "$PWD/services:/app/services" …`.
- **외부 API 벤더에 붙일 때 넷**: ① OpenAI 호환 벤더엔 `LLAMA_API_FORMAT=openai` **필수**(llama.cpp 전용 필드를 400으로 거부 — 추론 금지) ② 그 형식에서 게이트웨이가 `<thought>` 를 걷는데 **짧은 `max_tokens` 로는 사고가 예산을 다 써 빈 답**이 온다 ③ **임베딩은 `EMBEDDING_API_FORMAT=openai` 로 명시해야 외부 API로 나간다 — 키만 넣으면 안 바뀐다**(일부러 그렇다. 키 유무로 형식을 추론하면 키를 지운 순간 형식이 조용히 바뀌고 그 실패는 원인에서 가장 먼 자리에 404로 떨어진다). 차원 전환 절차는 README에 있다 — **규칙은 "차원이 바뀌면"이 아니라 "모델이 바뀌면 재색인"**이다(차원이 다르면 fail-fast로 멈추지만 **차원이 같은 다른 모델이면 아무 일도 안 일어나고 품질만 조용히 떨어진다**) ④ 무료층 한도는 **프로젝트 단위 집계일 수 있다**(키 회전이 한도를 곱하지 않을 수 있다).
- **★ 외부 API 배포에서는 컨텍스트 예산 가드가 사실상 걸리지 않는다 — 알고 두는 것이다**(오너 결정 2026-09-08, K-3=ⓐ). `/props` 가 없어 창을 **영영 모른 채** 돌 수 있고, 그때 `context_window_guard.exercised: false` 는 **과도기가 아니라 정상 상태**다. 따라서 **예산 초과는 가드가 아니라 벤더의 400 이나 잘린 출력으로**, 즉 **원인에서 가장 먼 자리**에서 드러난다. 겪으면 그때 브리프 [`k3-context-window-guard-decisions.md`](docs/plans/k3-context-window-guard-decisions.md) 의 ⓓ(설정 대체값)를 다시 연다.
- **`/props`·`/tokenize`·`/apply-template` 는 llama.cpp 전용이고 셋 다 예외를 삼켜 `None` 을 반환한다** — 외부 API로 바꾸면 **에러가 아니라 조용한 품질 저하**로 예산 가드가 실측에서 추정으로 내려간다(추정은 과소평가 방향 = 가드가 늦게 걸린다). **"뜨긴 뜬다"로 끝내지 말고 토큰 계수가 살아 있는지 따로 확인한다.** 위치는 줄 번호가 아니라 **함수 이름으로 찾는다**([`client.py`](services/llm_gateway/app/client.py) 의 `_probe_context_window`·`count_tokens`).

**검증·회귀**
- **★ 프런트 전수는 `frontend/` 안에서, 출력은 파일로 캡처해서 돌린다.** 저장소 루트에서 `vitest` 를 돌리면 jsdom 환경이 없어 `ReferenceError: document is not defined` 로 **전 파일이 죽는다**(2026-09-07 독립 검증 실측, 2회 재현). 그리고 `| tail` 로 요약만 보면 **Failed Tests 블록이 잘려 어느 셀이 실패했는지 영영 모른다** — 같은 날 실제로 정체 미상 1실패가 그렇게 남았고 16분짜리 전수를 두 번 더 돌렸다. `npx vitest run --reporter=basic > <파일> 2>&1; echo EXIT=$?` 로 돌리고 그 파일을 grep 한다.
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
- **event/open_question 의 그룹 판정은 벡터 다리가 있어야 돈다.** 후보 정체성 shortlist 는 `CHROMA_HOST` + `EMBEDDING_SERVICE_URL` 이 **둘 다** 있을 때만 조립되고, 없으면 `None` → **그 두 타입은 조용히 no-op**(실패가 아니다 — character 는 정규화 이름이라 계속 묶인다). *"왜 안 묶이지"* 를 만나면 먼저 이 env 를 본다. **★ dev 스택은 그 둘을 이미 갖고 있다** — 즉 **이미지 재빌드 시점에 즉시 켜진다**(2026-09-09 실측). 아직 실데이터에서 한 번도 안 돌았으므로 **첫 도그푸드에서 판정 팬아웃을 관측할 것**. **임계값은 없다** — 이웃 상위 K(기본 5, `ANALYSIS_CANDIDATE_SHORTLIST_LIMIT`)만 뽑고 판정은 judge 가 한다. **K 는 run 당 20쌍 상한을 character 와 나눠 쓴다** — 키우면 첫 focal 한둘이 run 예산을 다 쓰고 나머지가 전부 이월된다.
- **검증 기록의 판정 어휘는 `합격`·`조건부 합격`·`불합격` 셋뿐이고** 첫 줄 형식까지 [`guides/verification.md`](docs/guides/verification.md) 가 규정한다. **분류를 정규식에 맡기지 말 것** — 분류는 사람이 하고 가드는 구조만 잠근다.

## 코드를 만질 때의 규칙

**라우터·모듈 구조** — 공개 operation 전부가 `routers/` 11모듈에 있고 `main.py` 에는 조립 코드만 있다.
- **`routers/*` 에 `from ..main import` 를 되살리면 안 된다**(원래 순환이었고 [`test_app_import_paths.py`](tests/test_app_import_paths.py) 가 문다).
- **`main.py` 에 재수출 shim을 두지 않는다** — 두면 핸들러는 새 모듈을 보는데 테스트는 `main` 을 patch해 **조용히 빗나간다**. 심볼이 옮겨가면 import를 따라 옮긴다.
- **`main.py` 의 routers import는 상대 경로를 유지한다**(절대면 라우터 사본이 둘 생긴다). **`register_*` 호출 순서를 재배열하지 말 것** — route 순서가 OpenAPI `paths` 순서이고 그것이 프론트 생성물의 입력이다.
- **[`api/`](services/application/app/api/) 의 의존 방향은 단방향 `errors → models → env` 이고 `dependencies` 는 독립**이다. `app/env.py` 가 `api/` 밖인 것도 그 방향 때문이다.
- **공유 직렬화기는 [`api/payloads.py`](services/application/app/api/payloads.py), 한 도메인 전용은 그 라우터 모듈.** 전부 모으면 `payloads.py` 가 두 번째 `main.py` 가 된다. **`_require_project_exists` 를 새로 쓰지 말고 [`project_existence_check`](services/application/app/api/dependencies.py) 를 부른다.**
- **import를 재작성할 때 `as` 별칭을 버리지 말 것.** **`main.X` 를 patch하는 자리는 저장소 전체에 셋뿐**(`connect_chroma_collection`·`_build_embedding_provider`·`GatewayGenerateProvider`) — 심볼을 지울 때 이 스윕을 먼저 한다.

- **★ 수를 적은 주석·문서는 이제 가드가 센다(2026-09-07 신설 3종).** 빨개지면 *가드가 이상한 게 아니라 값이 뒤처진 것*이다. ① `activity/actions.py` 의 *"기록하지 않는 N"* 과 절 주석 수 — `test_activity_actions.py` 가 실제 항목 수와 대조한다(21 로 적힌 채 29 가 돼 있던 자리). ② [`docs/service-policy-contract.md`](docs/service-policy-contract.md) 의 정책값 — `test_service_policy_contract.py` 가 각 행의 `모듈::상수` 를 **import 해서** 대조하므로 **값을 고치려면 상수를 고친다**. 새 행에는 포인터를 함께 단다(포인터 없는 행은 안 잠긴다). ③ [`docs/legal/README.md`](docs/legal/README.md) 대조표 — 정책 문서의 **모든 표 축**이 여기 첫 칸에 있어야 한다(정책이 늘었는데 약관이 안 따라가는 것을 막는다).
**새 것을 더할 때 — 함께 가야 하는 것들**
- **새 LLM 호출부**: ① 조립 지점에서 `ObservedProvider(inner, call_site=…)` 로 감싼다 ② 그 요청 경로에서 `llm_call_scope(...)` 를 연다 — **감싸기와 scope 개방은 항상 함께 간다. 빠뜨리면 레코드가 조용히 0건인데 스위트는 green이다** ③ **조립 가드도 함께 넣는다**(하네스는 `ObservedProvider` 를 직접 만들기 때문에 조립에서 벗겨도 green이고 **배포에서만** 계측이 사라진다) ④ 도메인 판정은 `scope.annotate_last(...)`, 최종 도메인 거부는 `scope.reclassify_last_as_parse_error(...)`.
- **새 mutating route**: [`activity/actions.py`](services/application/app/activity/actions.py) 에 `logged` 또는 `EXCLUDED(사유)` 로 등재해야 전수 가드가 통과한다. **★ 전수 가드는 배선의 *존재*만 보고 *분기*는 못 본다** — 한 handler에 기록 분기가 여럿이면 **분기마다 행위 셀**이 필요하다.
- **새 유료 경로**: 분류표([`quota/billable_actions.py`](services/application/app/quota/billable_actions.py) 가 정본) · 시행 dependency · 402/429 선언 · 확인 헤더가 함께 간다(넷 다 전수 가드). **원장 필드명은 반드시 `target_project_id`** — `project_id` 로 적으면 purge reconciler가 **과금 기록을 지운다**. **입장 뮤텍스 임계 구역에 provider 호출을 넣지 말 것**(한 회원 요청이 91초씩 직렬화된다).
- **새 endpoint**: `responses=` + dependency + `test_auth_api.py` tier 전수 가드 등재. 저장소 예외는 광의 `except Exception` 보다 먼저 503으로 보존한다.
- **새 문서·스크립트에 주소를 적을 때**: 사설 호스트 주소·비밀값은 [`test_repo_hygiene.py`](tests/test_repo_hygiene.py) 가 문다(규칙과 유일한 예외는 아래 "🛡 보안 — Phase S" S-0 행). **역할 별칭으로 쓰고 값은 환경변수로 받는다.**
- **새 결정 브리프·검증 기록**: [`plans/README.md`](docs/plans/README.md)·검증 인덱스에 등재해야 한다 — [`test_docs_indexes.py`](tests/test_docs_indexes.py) 가 **미등재 문서와 깨진 링크를 양방향으로 막는다**(규칙이 아니라 강제). 같은 가드가 "검증 기록 N건" 류 숫자 주장도 디스크 실측에 묶는다.
- **★ 계획 문서는 머리에 `상태:` 를 선언하고, 그 값이 [`plans/README.md`](docs/plans/README.md) 상태 열과 같아야 한다**(2026-09-05 가드 신설). **어느 한쪽만 고치면 실패한다** — 상태 정본이 둘이라 갈라지던 것을 묶었다(신설 당시 120행 중 23행이 갈라져 있었고 13건이 두 달째 `Draft` 였다). **어휘는 통일하지 않았다**(오너 2026-08-06 소급 정리 없음 선례) — 요구는 통일이 아니라 **선언**이고, 새 값을 쓰려면 `_STATUS_VOCABULARY` 에 먼저 더한다. **비교는 선두 토큰뿐이라 인덱스 꼬리에 요약을 실을 자유는 남는다.** **★ 문서의 상태를 읽는 자리는 이 열 하나다** — HANDOFF 에 목록을 복사하지 말 것(세 번째 정본이 된다).
- **★ 설계 원본을 인용할 때는 `§` 번호로 인용하고, 그 문서를 옮기거나 절 번호를 바꾸지 말 것.** [`docs/contracts.md`](docs/contracts.md)·[`writing_agent_prompt.md`](docs/writing_agent_prompt.md)·[`plans/flat-loop-gate.md`](docs/plans/flat-loop-gate.md) 는 **현재 계약 정본이 아니지만 폐기되지도 않았다** — 프로덕션 코드가 절 번호로 인용하는 설계 근거다(각 문서 머리 배너에 인용처가 있다). **주석 인용이라 테스트가 안 잡으므로 이동은 조용히 끊긴다.**

**도메인 계약 — 고치기 전에 알아야 하는 것**
- **컨텍스트 항목 렌더링은 한 정의다** — [`context_search/item_render.py`](services/application/app/context_search/item_render.py) 를 프롬프트와 예산 회계가 **함께** 쓴다. 항목 렌더링을 바꾸면 예산이 자동으로 따라오지만 **정확히 한 곳에 여유가 있다**: 회계는 인용 번호를 모르므로 `_BUDGET_CITATION_NUMBER=999` 로 센다(항목당 최대 1토큰 과대평가). **여유를 넓히려면 `0 ≤ 여유 ≤ 항목수` 를 단정하는 세 셀을 함께 고친다** — 밴드 뒤에 숨기면 항목을 두 번 세는 과잉 교정이 통과한다.
- **`GET …/memory` 의 `scope: null` 은 결측이 아니라 계약된 값이다**(`event_observation`·`open_question_observation` 은 엔티티 id가 없다). *"비었으니 채우자"* 는 과잉 교정을 셀이 문다.
- **재색인 enqueue는 무조건 choke point다** — canonical을 만드는 모든 경로가 `MemoryService._enqueue_reindex` 를 지난다. **memory는 append-only**이고 canonical만 색인된다.
- **"stored" 재생 처분을 받는 신규 유료 경로는 응답이 표준 `Response`(`.body` 바이트)여야 한다** — `QuotaSettledRoute` 의 저장이 `getattr(response, "body", None)` 로만 읽으므로 스트리밍 등 다른 응답 형태는 **조용히 미저장**되고, 그 키의 재제출은 재생이 아니라 409 로 닫힌다(지금 경로 `writing_report` 는 전부 JSONResponse 라 무해 — S-1 검증 H3).

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

**⚠️ 오너 결정이 있어야 움직이는 것 — 2건(2026-09-09)**

| 막힌 것 | 무엇을 묻는가 | 브리프 |
|---|---|---|
| **약관·방침 시행일 재확정** | 오너가 정한 **2026-09-08 이 이미 지났는데 `시행 전제` 두 줄이 안 끝났다** — 파기 데몬(Slice 3~5)이 없어 약관 제8조 3항의 *"30일 뒤 파기"* 가 안 일어나고, 동의 게이트가 없어 방침 제3조의 *"시행일 이후 가입자에 한합니다"* 도 성립 안 한다. **채우면 문서가 없는 기능을 시행 중이라 말한다.** 값 셋은 반영됐고 시행일 자리만 남았다 | [`legal/README.md`](docs/legal/README.md) §초안이 일부러 비워 둔 것 · [`landing-page-scope-decisions.md`](docs/plans/landing-page-scope-decisions.md) |
| **계정 탈퇴 Slice 3(파기 데몬)** | 데몬이 계정 축 데이터를 **무엇으로 식별하는가**(필드 스윕이 `request_quota_policies` 를 못 본다 · `_id` 로 넓히면 사용자명 묘비를 스스로 지운다) + **슬라이스 범위**(D3 관리자 통제가 3인가 4인가) | [`slice3-withdrawal-purge-daemon-decisions.md`](docs/plans/slice3-withdrawal-purge-daemon-decisions.md) |

> **★ 이 표는 상태이지 완료가 아니다.** 2026-09-08 에 브리프 7건이 만들어지고 **같은 날 오너가 전부 답했다**(종전에는 선택지가 이 표 칸에만 있고 `docs/plans/*-decisions.md` 브리프가 **하나도 없었다** — 셋은 근거조차 `—` 였다). **결정은 브리프에 있다** — 여기 옮겨 적지 않는다(그것이 두 번째 정본이다). 새 결정 대기 항목이 생기면 **브리프를 먼저 쓰고** 이 표에 한 줄로 올린다.

| 결정된 것(2026-09-08~09) | 답 | 브리프 |
|---|---|---|
| 계정 탈퇴 Slice 2 읽기 표면 | **ⓑ 별도 `GET /me/withdrawal`** | [`slice2-withdrawal-grace-read-surface-decisions.md`](docs/plans/slice2-withdrawal-grace-read-surface-decisions.md) |
| 랜딩 범위·푸터 · **약관 값 넷** | **D1=ⓒ · D2=ⓐ** · `[운영자]`~`[추론 서비스 사업자]` 확정 | [`landing-page-scope-decisions.md`](docs/plans/landing-page-scope-decisions.md) |
| 활동 로그 셋(N3·replay·503 partial) | **D1=ⓑ · D2=유예(트리거) · D3=ⓐ** | [`activity-log-replay-and-partial-decisions.md`](docs/plans/activity-log-replay-and-partial-decisions.md) |
| K-3 창 미상 호출 | **ⓐ 유지** — ★ 아래 함정 절이 그 조건이다 | [`k3-context-window-guard-decisions.md`](docs/plans/k3-context-window-guard-decisions.md) |
| `analysis_extractor` D4 · gate 노출 | **둘 다 유예 · 트리거 확정** | [`analysis-extractor-alignment-and-gate-exposure-decisions.md`](docs/plans/analysis-extractor-alignment-and-gate-exposure-decisions.md) |
| 휴면 디렉터리 · `docs/plans` 재편 | **D1=ⓐ 휴면 명시 · D2=ⓐ 안 함** | [`docs-directory-dormant-and-restructure-decisions.md`](docs/plans/docs-directory-dormant-and-restructure-decisions.md) |
| llama `-hf` 리비전 | **ⓐ 최신 추종 유지** — ★ 브리프가 오너 근거의 전제 하나를 정정해 두었다 | [`llama-model-revision-pin-decisions.md`](docs/plans/llama-model-revision-pin-decisions.md) |
| event/open_question 정본 중복(09-09) | **ⓒ candidate 축 배선** — 구현 완료 | [`event-open-question-canonical-dedup-decisions.md`](docs/plans/event-open-question-canonical-dedup-decisions.md) |
| 압축 층(09-09) | **D1=파생+트리거 · D2=챕터 드릴다운 · D3=정본이 바뀔 때(D4 에 흡수) · D4=A · D5=A선 · D6=정본 16건** — 구현은 트리거 대기 | [`context-compaction-layer-decisions.md`](docs/plans/context-compaction-layer-decisions.md) |


**🔧 미수리 — 알고 있고 아직 안 고친 것**

| 항목 | 상태 | 위치 |
|---|---|---|
| **프런트 전수의 알려진 플레이크** | `me/PersonalHubPage.test.tsx > gives the remaining request budget a home`(2026-09-07 실측 5739ms) · `admin/AdminUserDetail.test.tsx > shows only this user's projects and filters them by name`(2026-09-08 실측 **11938ms** 타임아웃, 단독 **497ms** 초록) — 둘 다 **전수에서만**, **부하에서 느려지는 타이밍**이다. **★ 둘째 것은 다른 작업자의 백엔드 전수와 CPU 를 나눠 쓴 창에서 나왔다** — 동시 실행 중이면 전수 시간이 3~4배가 되고 이 계열이 늘어난다. 전수 1실패를 만나면 **먼저 이 표의 셀인지 보고**, 맞으면 **단독 재실행으로 가른 뒤** 회귀가 아님을 확인한다 | `daily_logs/2026-09-07/work_log.md` 세션 38 · `2026-09-08/work_log.md` 세션 46 |
| **배포 화면에 report-only CSP 가 붙어 있다** | 콘솔에 `connect-src 'none'`(report-only) 위반이 찍힌다 — **저장소의 nginx 에는 CSP 헤더가 없으므로**(S-2 가 지적한 공백) **앞단 프록시나 브라우저 확장이 넣은 것**이다. 지금은 차단 안 하지만 **enforcing 이 되면 API 호출이 전부 막힌다** — 출처 확인 필요 | 오너 콘솔 2026-09-07 |
| 프론트가 `detail` 문자열로 분기(H3 위반) | 세 사건이 전부 502라 코드로 구분 불가. 닫으려면 H3 개정 또는 상태코드 분리 | [`client.ts:1088`](frontend/src/api/client.ts#L1088) |
| `/writing/generate` 만 provider TIMEOUT을 502로(나머지는 504) | 선언 surface와 잠긴 셀을 함께 바꿔야 함 | [`writing.py:469`](services/application/app/routers/writing.py#L469) |
| 결정적 `provider_error` 에도 "다시 시도" 버튼 | 게이트웨이의 `retryable=False` 가 화면까지 안 온다 | `GenerationPad.tsx` |
| `llm_call_audits` 로 "출력이 잘렸다"를 못 본다 | `finish_reason`·`truncated` 없음(실측 0건). 헤드룸만 계산 가능 | `observability/` |
| 무순위 폴백은 관련도를 모른다 | 벡터·렉시컬 다리가 **둘 다 없는** 구성에서 `MongoDirect*MemoryRetriever` 가 `query` 를 무시하고 저장 순서 앞 8개를 자른다 — 정본이 상한을 넘으면 **오래된 것만 영원히 실린다**. 2026-09-09 에 **경고로 드러냈을 뿐 고친 것이 아니다**(`"… is unranked (mongo-direct backend)"` 가 뜨면 그 구성이라는 뜻) | [`context_search/service.py`](services/application/app/context_search/service.py) |
| 자료(source) 원문 길이 상한 없음 | `analysis_extract` 가 `snapshot.raw_text` 를 **통째로** 싣는다 — 검색 조각 예산의 보호를 안 받는 유일한 LLM 경로 | [`extractor.py`](services/application/app/analysis/extractor.py) |
| 프론트 6000 상수가 서버 env override와 미동기화 | 서버 422·400이 최종 방어. 해소하려면 public 설정 계약 위치를 먼저 결정 | [`tokenEstimate.ts:23`](frontend/src/writing/tokenEstimate.ts#L23) |
| 미사용 import에 회귀 가드 없음 | 유일한 신호가 스위트 밖 linter. **ⓐ(정리 슬라이스마다 수동 측정)가 현 단계에 맞다** | — |
| `scripts/` 를 pytest가 실행하지 않는다 | CI 없음(`.github` 부재). 부분 방어가 `mypy.ini`(`call-arg`+`misc`) 가드다 — **`misc` 를 disable 목록에 넣으면 표적 결함이 조용해진다** | `tests/test_typecheck.py` |

**🛡 보안 — Phase S**(2026-09-05 이중 다중 에이전트 감사. 기록 [`security_audit_dual_workflow.md`](docs/verifications/2026-09-05/security_audit_dual_workflow.md) 가 위치·근거 코드·공격 시나리오까지 담는다 — **여기 옮기지 않는다**)

**critical 0건.** 인터넷 직접 침투·인증 우회·대량 유출로 직결되는 경로는 미발견이고, 위험은 **quota 우회 체인**과 **문서 정보노출** 둘에 몰려 있다.

| # | 항목 | 왜 이 순서인가 | 자리 |
|---|---|---|---|
| **S-0** | **✅ 닫혔다(2026-09-06).** 실주소 3종이 **역할 별칭**(`<베타-LLM>`·`<구검증-LLM>`·`<알파-호스트-LAN>`)이 됐고 평문 비밀번호가 걷혔다. **★ 남는 것은 가드다** — 파일에서 지워도 git 이력에는 남으므로 값어치는 소급 삭제가 아니라 재유입 방지에 있다. [`test_repo_hygiene.py`](tests/test_repo_hygiene.py) 규칙 둘: **정확 일치는 추적 파일 전건**(`scripts/` 포함, `git add` 전 새 파일도) · **광의 RFC1918 은 `docs/` 와 루트 `*.md` 만**(`tests/` 픽스처가 일부러 사설 대역을 쓴다 — 전건에 걸면 정상 코드를 문다) | **★ 예외는 정확히 하나다** — 감사 기록 [`security_audit_dual_workflow.md`](docs/verifications/2026-09-05/security_audit_dual_workflow.md) 만 두 규칙에서 빠진다(발견의 근거라 오너 결정으로 원문 보존). **지우거나 넓히지 말 것.** 옥텟은 **4개를 정확히** 요구한다(3~4 허용하면 `npm 10.9.8` 이 잡힌다) · CIDR 표기는 계약 literal 이라 통과 | 브리프 [`security-phase-s0-docs-hygiene-decisions.md`](docs/plans/security-phase-s0-docs-hygiene-decisions.md) |
| **S-1** | **✅ 닫혔다(2026-09-05, SoT v1.8.32 — 브리프 참조).** 계약 문장이 갱신됐다: **같은 논리 요청은 한 번만 실행·과금된다** — 정산된 BODY dedupe 키 재제출은 실행 전 **409**, 진행 중은 잠금 429, 확인 재실행은 **+1 과금**(G4=A 를 원장이 처음 이행). `writing_report` 는 저장 응답 재생(국소 C, TTL 24h). retry 는 **상한 2회·쿨다운 60s·입장 게이트**. 판정 팬아웃은 **run당 20쌍+이월**. | 원장-키 신뢰는 `dedupe.KEY_REPLAY_ACTIONS` 표가 정본, literal 은 SoT v1.8.32 행 | 감사 §A.1~A.4 · 브리프 [`security-phase-s1-quota-dedupe-decisions.md`](docs/plans/security-phase-s1-quota-dedupe-decisions.md) |
| **S-2** | **인증 화면의 응답 보안 — 프론트 축**(사후 비평이 지적한 누락). `frontend/nginx.conf` 에 **`add_header` 가 0건**(CSP·X-Frame-Options·X-Content-Type-Options 전무, 2026-09-05 실측)이고, `index.html` 이 **모든 페이지**에서 AdSense 서드파티 스크립트를 로드한다 — **원고 편집 화면 포함** | 세션 쿠키는 **HttpOnly 라 스크립트가 읽지 못한다**(실측 `auth/cookies.py:30`). 그러나 **same-origin `fetch('/api/…')` 에는 자동으로 실린다** — 광고 스크립트나 크리에이티브가 오염되면 **원고 전문을 API 에서 긁어 밖으로 보낼 수 있다.** 이 제품의 핵심 자산이 미공개 원고라 **영향이 비용이 아니라 기밀성**이고, 광고를 **인증 화면에서도 로드한다는 사실 자체가 개인정보처리방침의 입력**이다(② 랜딩·약관과 같은 축) | 감사 §C |
| **S-3** | **미인증 표면 — ✅ signup 축은 닫혔다(2026-09-05, SoT v1.8.30).** 남은 셋(LLM 게이트웨이·in-stack llama `:9080`·embedding `/embed`)은 **호출자 인증이 없지만 loopback 바인드 뒤**다. **★ 만지기 전에 알아야 할 계약**: 발신 IP 해석은 `auth/client_ip.py` 이고 **XFF 를 오른쪽에서 읽는다**(엣지가 클라이언트가 보낸 값 오른쪽에 진짜 주소를 덧붙인다 — 왼쪽을 읽으면 IP 축이 조용히 0이 된다). **신뢰 대역에 LAN 을 넣으면 안 된다** — 앱이 `0.0.0.0:8520` 게시라 LAN 직결이 가능하고, 그 경로는 발신 주소가 SNAT 없이 도착하므로 신뢰 밖이어야 XFF 가 무시된다 | 남은 셋의 트리거는 **D8-7 G2~G6(자격증명) 유예와 같다**(원격·다중 호스트 배포)이며 llama `:9080` 만 의도적 LAN 공개다. signup 축 정본은 [`security-phase-s3-signup-throttle-decisions.md`](docs/plans/security-phase-s3-signup-throttle-decisions.md) | 감사 §A.5·8~11 |
| **S-5** | **알고 두는 것**(수리 대상 아님) — 관리자 행위 다수가 감사 원장에 안 남는다 · 저장소 장애 핸들러가 pymongo 메시지를 그대로 노출 · 가입 409 가 사용자 이름 열거 오라클(오너 문서화된 의도) · 외부 embedding/rerank 로 원고 전문이 평문 전송(설정 시) | 각각 오너 결정이 이미 있거나 트리거가 없다. **다만 마지막 항목은 개인정보처리방침에 들어가야 한다** | 감사 §A.14·19·B·§A.20~21 |
| **S-6** | **배포 호스트 노출면 — 2026-09-05 오너 승인 하에 원격 점검(읽기 전용).** **★ 인바운드 포트는 열려 있지 않다** — **Cloudflare Tunnel**(`cloudflared tunnel run`) 로 서비스하므로 공유기 포워딩이 아니라 **서버발 아웃바운드 터널**이 유일한 진입로다(오너 확인 + 프로세스 실측). 따라서 아래 노출은 전부 **LAN 한정**이다: ① `application`·`frontend` 가 `0.0.0.0` 게시라 **nginx 를 우회하는 경로가 LAN 에 열려 있다** ② **이 서버는 다른 프로젝트와 공유한다** — 타 프로젝트의 Mongo 2대·Redis 1대·공용 nginx 가 전부 `0.0.0.0` 게시 ③ **`ufw` 는 active 지만 Docker 게시 포트는 ufw 를 우회한다**(DOCKER 체인이 먼저 평가된다 — 다른 머신에서 실제로 도달 확인). **★ 이 프로젝트의 저장소는 설계대로 loopback 바인드였다**(mongo·ES·chroma·gateway) — **D8-7 G1=C 가 배포 서버에서도 성립한다.** | **✅ 터널 경로는 2026-09-05 에 실측으로 답했다 — 터널은 `frontend` nginx 로 간다**(공유 호스트의 공용 프록시는 **경로 밖**). 다만 origin 이 보는 `remote_addr` 는 터널 트래픽 전부가 **한 주소**라, real-ip 설정 없는 nginx `limit_req` 는 **전역 상한으로 퇴화한다** — nginx 앞단을 얹을 때 이것이 선행 조건이다. **★ 새 함정**: 공용 프록시에 이 프로젝트용 **낡은 vhost** 가 남아 있다(upstream 미해석 → 지금은 죽어 있음). 그 프록시의 네트워크를 누가 손대면 **살아나서 두 번째 진입로**가 된다 — 타 프로젝트 저장소 소관이라 여기서 못 고친다. ②는 이 프로젝트 범위 밖이지만 **같은 호스트라 함께 무너진다** — HANDOFF 가 오래 경고한 *"그 포트는 다른 프로젝트 것"* 함정이 배포 서버 규모로 재현된 것이다 | 원격 점검 |
| **S-7** | **✅ 닫혔다(2026-09-06, 오너가 배포 호스트에서 시행).** 터널 토큰이 `--token-file`(root `0600`, 디렉터리 `0700`)로 옮겨졌고 **세계 읽기 가능한 자리의 원시 토큰 0건**·서비스 active·터널 정상을 실측했다. **회전은 하지 않는다(오너 결정 2026-09-06)** — 값이 나간 범위가 오너 자신의 터미널과 작업 세션으로 한정되고, 이 계정의 대시보드에 **Refresh token 경로가 없어** 회전이 곧 터널 재생성(공개 호스트네임 라우트 전건 재등록)이라 비용이 맞지 않는다. | **★ 다음에 비밀값을 옮길 때 반드시 볼 것 — 이 슬라이스가 같은 자리에서 두 번 넘어졌다.** ① **백업이 처방의 구멍이다**: `cp -a` 는 권한까지 복사하므로 백업 파일이 원본의 세계 읽기 가능 권한과 비밀값을 그대로 들고 남는다(실제로 `0644`+토큰 1건으로 남았고, 지우기 전까지 노출은 파일명만 바뀐 상태였다). **백업 삭제는 정리가 아니라 처방의 마지막 단계**다. ② **오너에게 건네는 명령에 자리표시자를 두지 말 것**: 따옴표 안의 한글 자리표시자와 `read -rsp … VAR` 의 변수 이름 자리가 각각 그대로 붙여넣어져 **터널이 두 번 죽었다**(6개 호스트네임 동시 정지, 총 ~1시간). 값이 필요한 명령은 **고칠 곳이 없는 완성형**으로 주고, **재시작 전에 바이트 수를 먼저 확인**시킨다(빈 파일·자리표시자가 재시작 전에 잡힌다). **★ `Environment=` 는 `systemctl show` 로 드러나므로 못 쓴다.** `EnvironmentFile=`(0600)도 되지만 **`--token-file` 이 낫다** — 값이 프로세스 `environ` 에조차 안 들어가 자식 프로세스·코어덤프 경로가 하나 더 닫힌다. | 원격 점검 |

**⏸ 유예 — 트리거가 오면 연다** *(트리거 없는 유예는 망각이다)*

> **채택(accept) 은 화면에서 빠졌다(오너 2026-09-08).** 엔드포인트 `POST …/writing/accept`
> 와 클라이언트 `acceptWriting` 은 그대로 살아 있고 **완전 자동화가 쓸 통로**로 남겨 둔 것이다
> — 지우지 말 것. 사람이 쓰는 길은 복사 → 편집기 붙여넣기 → 저장이고 그 저장은 무료다.
> 되살릴 트리거: **완전 자동화(사람 승인 없이 도는 이어쓰기) 착수**.

| 항목 | 트리거 |
|---|---|
| 리랭커 self-host + 품질 평가 | **`RERANK_API_URL` 조달**(2026-09-06 실측 미설정 — LLM·임베딩 키는 왔지만 **이 축은 아직 안 왔다**. 그전에는 하네스가 no-op 대 no-op 비교다). 키가 오면 그 다음이 정답인데 **정답은 오너가 붙인다**(구현자가 붙이면 "리랭커가 구현자 생각과 같은가"를 재게 된다) — 하네스 [`eval_retrieval_ranking.py`](scripts/eval_retrieval_ranking.py) 가 그 순서를 파일 머리에 적어 두었다 |
| Phase 10 ③ 목록 행 간격(T1) · ④ **비활성 버튼의 색**(농도가 아니라 색이 문제) | **육안 확인** — 가장 싼 자리다 |
| Phase 9 화면 후확장 F1~F6(커서 페이징·필터 등) | 각 행에 트리거가 붙어 있다 → [`09-1-…-decisions.md`](docs/plans/09-1-activity-timeline-screen-decisions.md) §"나중에 여는 문" |
| AdSense 광고 단위 배치(자동/수동) | **심사 승인**. 광고는 승인 전엔 게시되지 않는다(로더가 있어도 안 보이는 것이 정상). `adsbygoogle.js` 에 SRI를 안 붙인 것은 의도다 |
| quota 상수 셋 재측정(5초 창·lease 180초·일20/주100) | **선행조건은 이미 성립했다** — 배포가 외부 API로 돈다(위 "머신 · 기동"). 남은 것은 *"응답이 실제로 수초로 줄었는가"* 를 **재는 것뿐**이고, 그 관측은 도그푸드에서 나온다. **설계는 안 바뀐다** |
| D8-6 D4-D purge operation journal/saga | 원격 저장소·다중 worker 또는 수동 reconciler가 실제 부담이 될 때 |
| D8-7 G2~G6 자격증명(SCRAM·keyfile·basic auth) | 원격·다중 호스트 배포. **각하가 아니라 유예** — **★ 이 트리거는 재해석이 필요하다**(2026-09-06): 원격 배포는 **이미 존재하고**(Cloudflare Tunnel), S-6 원격 점검이 그 자리에서 *"이 프로젝트의 저장소는 설계대로 loopback 바인드 — G1=C 가 배포 서버에서도 성립"* 이라고 답했다. 그런데 같은 점검이 **호스트를 다른 프로젝트와 공유한다**는 사실을 새로 드러냈으므로, 남은 질문은 "다중 **호스트**"가 아니라 **"다중 테넌트"** 다 — 그 축을 열지 말지는 오너 판단이다 |
| 2c `owner_id` 공개 payload 노출 | 프론트가 읽을 이유가 생길 때(`schema.d.ts` 변경이라 공짜 아님) |
| 공유·협업 글쓰기 | **공동 작업이 생기는 날** — Phase 9 **F4(행위자 열)와 같은 트리거**다(오너 2026-08-10: *"개인 시스템이라고 하면 되겠지"* — 즉 그 전제가 바뀌면 되살린다). 둘을 따로 열지 않는다. D3=A가 그 문을 닫지 않게 설계돼 있다 |
| 프론트 스타일 나머지 축(다른 지점 줄바꿈·넘침 · 좁은 화면 표 넘침 · 실패 UX 문구) | **육안 확인** — 위 Phase 10 ③④ 와 같은 트리거이고 같은 자리에서 함께 본다. *(2026-09-06 정정: 이 칸에는 트리거가 아니라 **범위 목록**이 들어 있었다 — 표 제목이 금지하는 바로 그 모양이라 범위를 항목 칸으로 옮겼다)* |
| 컨텍스트 압축 층(파생 요약) | **한 프로젝트의 canonical memory 총계가 16건을 넘는 순간**(검색 상한 8의 2배 = 랭킹이 무엇을 고르든 절반 이상이 잘리기 시작하는 지점) 또는 **오너가 "AI 가 앞 내용을 잊었다"를 실제로 만날 때**. 열 때 **먼저 풀 것**: 정본의 장 귀속 규칙 — `MemoryEntry` 에 chapter 축이 없고 `add_evidence` 의 source_ref union 이 장 경계를 흐린다 → [`context-compaction-layer-decisions.md`](docs/plans/context-compaction-layer-decisions.md) §후속 고려 |
| 사용자 가이드 | 도그푸드에서 UI가 안정되면. **공개 전** 최신 화면 기준으로 |
| Phase 8.6 결제 seam | 결제 도입이 계기일 때(오너: *"당장은 안 붙일 것 같다"*) |
| 관측 화면 확장 | **Phase 9 F1(커서 페이징)과 같은 트리거를 쓴다** — *"'최근 100건' 문구 아래가 궁금해지는 순간, 특히 하루 저작 뒤 타임라인이 그날 하루로 다 차면"*([`09-1-…-decisions.md`](docs/plans/09-1-activity-timeline-screen-decisions.md) §"나중에 여는 문"). **★ 둘을 따로 열지 않는다 — 먼저 여는 쪽이 페이징 관례를 정하고 다른 쪽이 따른다.** 무엇을 더하든 **`React.lazy` 경계 안**. *(2026-09-06 정정: 종전 트리거 "API에 시간 창 `?since=` 이 생긴 뒤"는 **순환이었다** — `?since=` 는 이 작업 자신의 API 축이라 그것을 만들어 줄 다른 작업이 없다. 실측: [`observability.py`](services/application/app/routers/observability.py) 의 KPI endpoint 는 `project_id` 하나만 받는다)* |

## Next Tasks

> **★ 다음 작업자에게 — "남은 일"은 이 절에만 있지 않다(2026-09-07 실수 기록).** 오너가 *"남은 거 뭐지?"* 라고 물었을 때 이 번호 목록만 세어 답했다가 **랜딩 페이지 기획을 통째로 빠뜨렸다.** 이 파일은 남은 일을 **세 곳**에 나눠 싣는다 — ① 이 번호 목록(착수 순서) ② 위 "열린 것"의 **⚠️ 오너 결정 표**(막힌 것 — 병목은 여기 산다) ③ 같은 절의 **🔧 미수리 표**(아는 결함). 셀 때는 `grep -n '^## ' HANDOFF.md` 로 **절부터 뽑고**, 답할 때 **집계 범위를 함께 말한다.**
>
> **★ 2026-09-09 현재 1번(Slice 3)이 브리프 대기다** — 나머지는 그대로 착수 가능하다. 2026-09-08 브리프 7건은 오너가 전부 답했고, 10·12번은 약관 값 넷이 왔다.
>
> | 순서 | 무엇 | 왜 이 순서인가 |
> |---|---|---|
> | **1** | **11번 계정 탈퇴 Slice 3~5** | Slice 2까지 닫혔다. **다만 Slice 3 은 오너 답을 기다린다**([브리프](docs/plans/slice3-withdrawal-purge-daemon-decisions.md), 2026-09-09) — 답이 오면 그 자리에서 이어진다 |
> | **2** | **12번 랜딩 + 10번 동의 게이트** | **한 창에서 본다.** 순서는 ① 약관 대괄호 넷 치환 + 시행 버전 문자열(+ 미시행 표식 제거, **가드 셀 동반 수정**) ② `/terms`·`/privacy` + 푸터 ③ 랜딩 본문 ④ 동의 게이트. **Phase S-2(nginx 헤더)·AdSense 화면별 제어도 같은 창** — 광고가 랜딩·로그인에도 뜬다 |
> | 3 | 2번 최종 저장·분석 6차 승격 재검증 | 셀은 이미 있고 MW-D 재적용만 남았다 |
> | 4 | 6번 육안 확인 · 8번 확인용 계정 정리 | 오너·운영 데이터 축 |
>
> **결정이 만든 작은 후속 둘**(독립 슬라이스를 열 크기가 아니라 다음 슬라이스에 얹는다): **활동 로그 D1=ⓑ** — finalize 재전송이 활동 행을 안 남기게 한다(★ 분기가 생기므로 **행위 셀이 따로** 필요하다) · **문서 D1=ⓐ** — 휴면 디렉터리 셋을 인덱스에 *휴면* 으로 올린다(끊긴 `verification_briefs/2026-06-24` 가 그때 그래프에 붙는다).
>
> **결정을 기다리지 않고 할 수 있는 것**: **2번 랜딩 + 10번 동의 게이트(위 표의 2번 — Slice 3 이 막히면 여기가 다음이다)** · S-2(nginx 보안 헤더 — 트리거 없이 일정만 안 잡혔다. 다만 **랜딩·광고 축과 한 창에서 보는 편이 싸다**) · 6번 육안 확인 · 8번 확인용 계정 정리. 그 밖은 오너 병목이거나 운영 데이터 대기다. **13·14 는 같은 날 고쳤다** — 남은 것은 14번의 재현 하나이고, 그것은 **오너가 다시 겪을 때 화면이 말하는 문구**를 받아야 진행된다.


> **★ 2026-09-05 보안 감사 후속(Phase S)이 진행 중이다.** 감사 판단 **critical 0건** + 오너 확인 둘(확인용 계정은 배포에 없었다 · 승인된 계정이 오너뿐이다). **S-3 signup 축과 S-1 quota 우회 체인(HIGH)이 같은 날 닫히고 그대로 배포됐다**(각각 SoT v1.8.30·v1.8.32, 배포 서버 HEAD `d37eb84` — 세부는 work_log 세션 11). **S-0 문서 위생·S-7 토큰 저장 방식이 2026-09-06 에 닫혔다**(S-0 = 스윕 + 재유입 가드 · S-7 = 오너가 배포 호스트에서 `--token-file` 로 시행). **남은 셋은 성격이 서로 다르다 — "전부 트리거 대기"가 아니다**(2026-09-06 정정): **S-2 는 트리거가 없다. 일정이 안 잡힌 것뿐이다** — 감사가 공격 경로까지 적어 두었고(광고 스크립트 오염 → same-origin `fetch` 로 원고 유출) 무엇이 일어나야 착수 가능한지가 없다. 굳이 묶자면 랜딩·약관 축(오너 병목)과 같은 자리다. **S-5 는 유예가 아니라 수용된 위험**이다(표 자신이 *"알고 두는 것 — 수리 대상 아님"*). **S-6 의 낡은 vhost 만 진짜 대기**인데 그것도 타 프로젝트 소관이라 **회신 경로가 없다**(아래 0번). S-7 회전은 2026-09-06 오너 결정으로 닫혔다. **4번(장면 메모 후속)은 2026-09-07 에 닫혔다 — 다음은 2번(최종 저장·분석 연동 6차 승격 재검증)이다.**

0. **★ Phase S — 보안 감사 후속**(기록 [`security_audit_dual_workflow.md`](docs/verifications/2026-09-05/security_audit_dual_workflow.md), 확정 39건 · critical 0 · HIGH 1). 아래 "🛡 보안 — Phase S" 표가 항목별 정본이다. **~~S-3 signup~~·~~S-1 quota dedupe~~·~~S-0 문서 스윕~~·~~S-7 토큰 저장 방식~~(닫힘) → **저장소·호스트 양쪽에 남은 착수 항목이 없다.** 나머지(S-2·S-5·S-6)는 트리거 대기.** S-2(nginx 보안 헤더)를 할 때는 **nginx 앞단 레이트리밋·`client_max_body_size` 와 한 슬라이스로 묶는 편이 싸다** — nginx 를 한 번만 연다.
   - **낡은 vhost(공용 리버스 프록시)**: 오너 확인 완료(2026-09-05) — **타 프로젝트 쪽 작업 AI가 처리 중**이다. 이 저장소 소관 아님(살아나면 두 번째 진입로인 구조는 그대로). **★ 이것은 회신 경로가 없는 위임이다** — 저쪽이 끝내도 여기에 알려 줄 사람이 없고 이 저장소에서는 고칠 수도 없다. **닫으려면 오너가 그쪽 결과를 물어다 이 줄을 지우는 수밖에 없다**(2026-09-06 분류).
1. **~~Slice 6(grouped Inbox UI)~~ 완료(2026-09-06)** — 구현(SoT v1.8.34) → 독립 검증 **조건부 합격**([`identity_group_slice_6.md`](docs/verifications/2026-09-06/identity_group_slice_6.md)) → **조건 B1·B2 폐쇄(같은 날, SoT v1.8.35 — B1 `pending` 잔여 셀 · B2 "1.3rem→1rem 가시 변화" 서술 반증·정정, `--type-base` 교정은 유지)**. 검증 하드닝 H1~H4(그룹 승인 유료 402/429 화면 처리가 `WritingPanel` 표준과 안 맞음 · 409 뒤 재동기화 없음 · `idempotent_replay` 표시 무셀 · outcome 단일 슬롯)는 **비차단으로 검증 기록에 남아 있다** — 완료 기준 #6("실패를 사람이 이해할 수 있다")과의 관계는 오너 판단 몫.
2. **최종 저장·분석 연동 — 5차 재검증(2026-09-06) 조건 B1 폐쇄, 6차(승격) 재검증 대기**([`final_save_n1_promotion.md`](docs/verifications/2026-09-06/final_save_n1_promotion.md), **조건부 합격** — 4차 조건 N1 은 폐쇄 확인). **B1** — 확정 계약 *"final marker 뒤의 일반 저장은 허용한다"* 의 **과잉교정 방향이 프런트 무가드**였다(일반 저장 버튼에 `isFinalized` 를 더해도 프런트 전수 418 전건 초록 — 백엔드는 프로브 S4 가 잠그는 한쪽만 잠긴 계약). **같은 날 처방 셀로 폐쇄**(`0a2fee4`): final 성공 직후 본문 수정 → 저장 버튼 활성·`/versions` POST 발송·배지 `최종 저장됨`→`최종 저장 후 수정됨` 전이(+분석 라벨 `필요` 복귀)를 한 셀에 단정. 양방향 변이: over(MV-D 저장 차단) 1 재실패 · under(배지 전이 파괴) 2 재실패. **6차는 그 셀 + MV-D 재적용만으로 승격 판정이 가능하다**(검증 기록 Outstanding). 하드닝 H1(finalize 키 상수 무물림)·H2(함수 층 가드)는 비차단·오너 값 인정 대기, N3 은 오너 결정 대기.
3. **~~장면 메모 Slice 3~4(화면 둘)~~ 완료(2026-09-06)** — 구현(SoT v1.8.36) → 독립 검증 **조건부 합격**([`scene_note_slices_3_4.md`](docs/verifications/2026-09-06/scene_note_slices_3_4.md)) → **조건 B1~B5 폐쇄(같은 날, SoT v1.8.37)**. 남은 하드닝 H2 는 이 슬라이스 밖 선결함이다(드로어 읽기 전용이 보관 3축 중 2축만 — `DraftPayload` 에 chapter 축이 없다). 남는 계약 주의: 목록은 미리보기(200자)만 싣고 전문은 단건 GET 이 준다 · 검색은 서버가 하고 화면은 다시 거르지 않는다 · **저장 버튼을 "변경 없음"으로 잠그지 말 것**(오너 결정 "같은 값 재저장도 활동 행을 남긴다"가 화면에서 도달 불가가 된다 — 요청 중 잠금만 둔다) · 드로어의 편집 대상은 현재 Scene 하나다. 확정값 [`scene-note-decisions.md`](docs/plans/scene-note-decisions.md).
4. **~~장면 메모 후속(수정 시각 · "더 보기")~~ 완료(2026-09-07)** — 구현 SoT v1.8.38 → 독립 검증 **합격 · 차단 0**([`scene_note_follow_up.md`](docs/verifications/2026-09-07/scene_note_follow_up.md)) → **하드닝 H1~H3 폐쇄(같은 날, SoT v1.8.39)**. 남는 계약 주의: **"더 보기"는 단건 GET 한 번이지 목록의 전문이 아니다** · 펼침은 **두 화면에 똑같이** 있고 드로어에서 **편집 대상을 옮기지 않는다** · **늦게 도착한 펼침 응답은 버린다**(행마다 따로 나가는 요청이라 주인을 확인해야 한다 — 상태가 아니라 ref 로) · 목록이 새로 오면 접는다 · 새 CSS 규칙이 `var(--type-*)` 를 쓰면 **`typeScale.test.ts` 이관 목록에 등재**해야 한다(이번에 실제로 걸렸다).
5. **★ 배포 — 최신 배포는 2026-09-07**(원장 소유 축 개명 v1.8.43·v1.8.44 까지 나갔다: 마이그레이션 `renamed: 14` · 옛 인덱스 3개 제거 · 전 컨테이너 healthy). **그 뒤 미배포분이 쌓여 있다** — 진입점 부트스트랩 둘(`5759d9e`·`a207a7c`, **푸시는 됐고 배포가 안 됐다**)과 계정 탈퇴 Slice 0(v1.8.45). 그래서 **지금 서버의 스크립트로는 `-e PYTHONPATH=/app` 가 필요하고, 그 둘이 배포되는 순간부터 필요 없다.** **★ 미푸시 개수를 인계 문구에서 베끼지 말고 그 자리에서 잰다**: `git log --oneline origin/main..HEAD`(2026-09-08 실측 5커밋 — 종전 문구의 *"미푸시 둘"* 은 그 둘이 이미 푸시돼 낡아 있었다). 다음 배포 절차: `git pull --ff-only` → `build` → **마이그레이션이 필요한 슬라이스면 `run --rm --no-deps <서비스> python scripts/…`** → `up -d`. **★ `exec` 가 아니라 `run` 이다** — `scripts/` 는 이미지에 COPY 되므로 도는 컨테이너(옛 이미지)에는 새 스크립트가 없다.
6. **육안 확인(누적)** — 프론트 재빌드 선행. Phase 10 마감 다섯(첫 화면 콘텐츠 · 오른쪽 끝 정렬 · 목록 행 간격 · 차트 막대 테두리 · 버튼 hover) · 비활성 버튼 색 · 편집기 드로어와 설정 탭이 좁은 화면에서 겹치는지 · 관측 화면과 비동기 패드 렌더 · **최종 저장·분석 연동의 첫 실사용**(운영 이력 0건) · **장면 메모 행 꼬리줄**(좁은 드로어에서 수정 시각과 "더 보기"가 한 줄에 남는지 · 긴 전문을 펼쳤을 때 목록 스크롤).
7. **dogfood 관찰**: `report field must be an array` 실패율 · `analysis_extract` 의 `aspect` 오분류 빈도 · scratch per-draft 상한(기본 20) 밀어냄. 체크리스트 [`docs/dogfood-checklist.md`](docs/dogfood-checklist.md).
8. **정리 대상**: 확인용 계정 `timeline_demo` 와 프로젝트 `6a795ab928e4a53aa000a824`(활동 5건).
9. **~~서비스 정책 계약 문서~~ 만들었고 ~~미결 셋~~도 오너가 정했다(2026-09-07)** — 문서 [`service-policy-contract.md`](docs/service-policy-contract.md), 결정 [`plans/service-policy-decisions.md`](docs/plans/service-policy-decisions.md). **그 결정이 구현 슬라이스 둘을 새로 냈다 → 10·11번.** **문서를 고칠 때 주의**: §1~7 값은 파생본이라 `tests/test_service_policy_contract.py` 가 상수와 대조한다 — 값을 고치려면 **상수를** 고치고, 새 행에는 `모듈::상수` 포인터를 단다(포인터 없는 행은 잠기지 않는다). **§8 은 지위가 다르다**(정해졌으나 미시행) — 시행되면 §1~7 로 올리고 포인터를 단다. **보존 기간은 결정 2 로 닫혔다**(무기한 = 삭제 요청 전까지. 코드 무변이고 값이 *선택됐다*는 것이 변화다).
10. **★ 가입 동의 게이트(오너 결정 2026-09-07)** — 가입 절차에서 약관을 확인하게 하고 **동의 시각 + 약관 버전을 저장**한다. 기존 계정에 **소급 동의는 받지 않는다**(그래서 *"모든 회원이 고지를 봤다"* 고 말할 수 없다 — 시행일 이후 가입자만이다). **선행: 약관 초안은 나왔다**([`docs/legal/`](docs/legal/README.md), 2026-09-07 · 버전 `draft-0` · **미시행**) — 남은 것은 **오너 검토와 시행일·운영자 정보 확정**이다. 순서는 **오너 확정 → 버전 문자열(`draft-0` 이 아닌 시행 버전) → 게이트**이며, 코드 축(동의 시각·버전 필드, 가입 확인 단계)은 먼저 지을 수 있다. **초안의 대괄호 넷은 코드가 못 채운다** — 특히 `[추론 서비스 사업자]` 는 배포 `.env` 가 정한다. 근거: 원고가 이미 스택 밖으로 나간다(정책 문서 §8).
11. **★ 셀프 계정 탈퇴 + 30일 유예 파기(오너 결정 2026-09-07)** — **버튼 하나가 아니다.** 요청·유예 상태·**파기 데몬**·**취소**가 각각 있어야 성립하며, 구현 순서는 [`plans/account-withdrawal-implementation-phases.md`](docs/plans/account-withdrawal-implementation-phases.md) (Slice 3~5 가 남았다)에 있다. **D1~D6 는 확정됐다**(2026-09-07). Slice 3 을 좌우하는 실측 셋: ① 파기 본체 `routers/admin.py::execute_project_purge` 는 **한 벌뿐이니 반드시 재사용**한다(세 벌째를 만들면 조용한 고아) — 다만 `HTTPException` 을 던져 데몬에서 그대로는 못 쓴다 ② **파기 재시도는 멱등이 아니다**(core_sot 을 먼저 지워 재시도가 404 로 끝난다) → 데몬을 *실패하면 재시도* 로 짜면 안 되고 부분 파기를 표시하고 멈춰야 한다(수습은 `scripts/purge_reconciler.py`) ③ **★ 사용량 원장이 `user_id` 를 쓰는데 우리는 원장을 남기기로 했다** — 파기 대상의 표식이 **필드 이름**이라(프로젝트 축은 `target_project_id` 로 개명해 쓸이를 피했다) 사용자 축 reconciler 가 생기는 순간 원장이 쓸려 간다. **~~Slice 0(상태 축)~~ 은 2026-09-08 에 닫혔다**(SoT v1.8.45 — `withdrawal_requested_at` · 30일 상수 한 곳 · `>=` 경계 판정 · 전이 멱등/취소). **~~Slice 1(요청·취소 API)~~ 도 2026-09-08 에 닫혔다**(SoT v1.8.46 — `POST`·`DELETE /me/withdrawal`, operation 102→**104**, 검증 H2 도 함께). **~~Slice 2(유예 중 접근 규칙)~~ 도 2026-09-08 에 닫혔다**(SoT v1.8.48 — 별도 `GET /me/withdrawal`, operation 104→**105**, 일반 쓰기 403, 유료 경로는 quota 전에 차단, 취소 뒤 전부 복구). **다음은 Slice 3 파기 데몬**이다. **★ Slice 1 이 남긴 계약 주의**: 두 operation 에는 **403 이 없다**(경로가 대상을 지목하지 않아 남의 계정을 요청할 방법 자체가 없다 — 더하면 화면이 오지 않을 응답을 처리한다) · 재요청은 **200 멱등**이고 취소 없는 취소는 **404 가 아니라 409** 다 · **활동 로그에 안 남는다**(`activity_events` 는 프로젝트 축이라 계정 축을 담을 자리가 없다 — 계획서 체크리스트의 *"활동 로그 기록"* 이 그 계약을 몰랐던 것이고 계약이 정본이다). **★ Slice 0 이 남긴 계약 주의 넷**: ⓐ **탈퇴 상태는 `is_active`·`status` 와 별개인 세 번째 축**이다 — 접으면 D1=C(*유예 중에도 로그인해 취소*)와 D6=A(*비활성화는 단방향*)가 함께 깨진다 ⓑ 유예 산술은 `purge_due_at` **한 곳**이고 판정은 `>=` 다(화면의 *남은 N일* 과 데몬의 *오늘이 그날인가* 가 갈라지지 않게) ⓒ 재요청은 **첫 시각을 지키는 멱등**이고 취소는 **스탬프 제거**다(취소한 계정은 요청한 적 없는 계정과 구별되지 않는다 = D5=A) ⓓ **Mongo 의 naive→UTC 재라벨링은 일관성이 아니라 수정**이다 — 빼면 파기 데몬이 `TypeError` 로 죽고 **fake collection 은 그것을 못 본다**. **★ 정책 문서 §6 승격은 Slice 5 다**(Slice 0 이 §6 을 가리키게 한다고 적혀 있었으나 정책 문서 자신의 §8/§1~7 지위 규칙이 이긴다 — 시행 전에는 안 올린다). **~~D4~~ 는 2026-09-07 에 닫혔다**(SoT v1.8.43 — `target_user_id` 개명 + 멱등 마이그레이션) — **독립 검증 합격 · 차단 0**([`verifications/2026-09-07/account_withdrawal_d4_ledger_axis.md`](docs/verifications/2026-09-07/account_withdrawal_d4_ledger_axis.md); 하드닝 2 는 Slice 3 착수 전에 닫으면 좋다 — 마이그레이션 부분 실패 창·멱등 셀 다리). **★ 배포 전에 `python scripts/migrate_ledger_user_axis.py` 를 돌려야 한다** — 안 돌리면 옛 행이 새 질의에 안 잡혀 **사용량이 0 으로 보인다**(검증이 같은-이름-다른-키 인덱스 거부 code=86 을 실측 — 마이그레이션은 권고가 아니라 기동 필요조건이다). D1~D6는 확정됐고 Slice 3~5가 남았다.
12. **★ 랜딩 페이지 기획(오너 2026-09-07)** — **아직 아무것도 없다.** 화면·문구·푸터 구성이 미착수이며 **푸터에 약관·개인정보처리방침 링크와 `[문의 연락처]` 가 들어간다**(오너 결정). 약관·방침 초안은 이미 있으므로([`docs/legal/`](docs/legal/README.md)) 랜딩이 그것을 **어디에 어떻게 거는지**가 이 슬라이스의 몫이고, 초안의 대괄호 넷 중 `[문의 연락처]` 는 여기서 채워진다. **정본 문구는 오너**지만 **기획·초안은 작업 가능하다** — 위 "열린 것" 표의 같은 항목이 정본이다. 공개 전 법적 요건 축이라 **Phase S-2(nginx 보안 헤더)·AdSense 화면별 제어와 같은 창**에서 보는 편이 싸다(광고가 랜딩에도 뜬다).
13. **~~메모 읽기면 결함 둘~~ 고쳤다(2026-09-07, 오너 관측 당일)** — ① 읽기면이 `body: null`(메모 없음)과 `""`(빈 메모)를 **둘 다 빈 `<p>` 로** 그려 화면이 아무 말도 안 했다(편집면은 이미 갈랐고 **SoT v1.8.11 이 그 구분을 계약으로 박아 둔 자리**라 읽기면만 계약을 안 지킨 것) → 셋(없음/빈 메모/내용)을 각각 다르게 말한다. ② `.note-body` 에 편집 상자와 **같은 면**을 줬다(면·테두리·여백 없이 떠 있어 어디까지가 메모인지 경계가 없었다). **남는 주의**: 이 패널은 편집면과 읽기면이 **같은 화면에 둘 다** 있으므로, 한쪽만 고치면 다시 어긋난다 — 문구든 시각이든 둘을 함께 본다. **미배포**(다음 배포에 실린다).
14. **~~이어쓰기 채택 "아무 동작 안 함"~~ 원인 확정·수정(2026-09-07)** — **버튼은 처음부터 동작하고 있었다.** 오너 콘솔이 답을 줬다: `POST …/writing/accept` → **429**. 계약상 429 는 *한도 초과가 아니라* **"같은 요청이 이미 진행 중"** 이고 `X-Confirm-Duplicate` 재전송으로 풀린다([`api/errors.py`](services/application/app/api/errors.py)). 화면은 그때 확인 대화를 띄우는데 **그 대화는 패널 맨 위에 그려지고 채택 버튼은 맨 아래**라, 아래에서 누른 사용자에게는 **화면 밖에서 열렸다** → *"아무것도 안 된다"*. 고친 것: 대화가 열리면 **스크롤·포커스로 시선을 옮기고**(포커스가 본체, 스크롤은 보조 — jsdom 에 `scrollIntoView` 가 없어 `?.()`), 확인 버튼이 **그 동작의 말**을 쓴다(채택=`그래도 채택하기`. 종전엔 넷 다 `하나 더 만들기` 였다). **★ 남는 교훈**: 세션 37 에서 나는 *죽은 버튼*을 의심했는데 **빗나갔다** — 원인은 로직이 아니라 **피드백의 위치**였다. 세로로 긴 패널에서 **동작은 아래, 피드백은 위**면 그 피드백은 없는 것과 같다. 이 패널에 새 확인·오류 표면을 더할 때 같은 함정을 볼 것. **미배포**. **★★ 2026-09-08 후속 — 이 교훈이 하루 만에 형제 표면에서 재발했다**: 그 수정은 스크롤·포커스를 **확인 대화(`pendingConfirm`)에만** 넣었고 **바로 옆 오류 상자(`setError`)에는 안 넣었다.** 그래서 오너가 다음 날 만난 채택 **400** 이 같은 방식으로 화면 밖에서 떴다(*"바로 안 나오고 슬롯 닫았다 여니까 나오네"*). **패턴 스윕은 같은 파일 안에서 멈추면 안 된다 — 고친 표면의 *형제 표면*까지 센다.** 채택 버튼 자체는 오너 결정으로 제거됐지만(아래 유예 절), **이 패널의 오류 상자는 여전히 위쪽에 있다** — 새 하단 동작을 더할 때 그 동작의 실패는 **그 자리에서** 말할 것(복사 실패 문구가 그 선례다).

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
