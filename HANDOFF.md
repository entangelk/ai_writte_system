# HANDOFF

> **다음 작업자가 지금 일을 시작하는 데 필요한 것만.** 이력이 아니다.
> 완료 서술은 여기 쓰지 않는다 — `docs/daily_logs/`(상세) · `docs/system-contract-sot.md` 변경이력 · `CHANGELOG.md`(마일스톤) · `docs/verifications/`(독립 검증)에 이미 있다.
> 편집 규칙은 `CLAUDE.md`·`AGENTS.md`의 "HANDOFF.md" 절에 있다. **길이 상한은 없다** — 대신 **~200줄을 넘으면 자가 검수**하고(그 뒤로는 ~100줄마다) 결과를 아래 한 줄로 남긴다. 길어야 할 이유가 있으면 길어도 된다. 안 보는 것이 문제다.
>
> 마지막 자가 검수: 2026-08-02 · 236줄 (D8-6 검증 대기와 낡은 알파 상태를 제거하고 합격 상태·알파 종료 관측·베타 첫 체크·Phase 8 착수만 남겼다. 다음 검수 트리거는 300줄)

## 머신 구성 (알파 · 베타 · 감마)

이 프로젝트는 성격이 다른 세 머신을 옮겨 다닌다. **HANDOFF·문서가 "환경과 안 맞는다"고 느껴지면 먼저 지금 어느 머신인지부터 본다.** 아래는 각 머신이 *무엇을 띄울 수 있는지*(항구적 성질)이지, *지금 무엇이 떠 있는지*(머신-로컬 관측치)가 아니다 — 후자는 각 절에서 날짜를 달아 따로 적는다.

| 머신 | 역할 | LLM | 띄울 수 있는 것 |
|---|---|---|---|
| **알파(Alpha)** | 서비스 배포용 | **in-stack llama**(GPU **RTX 3060 12GB** — `nvidia-smi` 실측, `docker-compose.llama.yml`) | 전체 스택 + 자체 GPU LLM |
| **베타(Beta)** | 테스트·개발용 (**다음 작업 예정 — 상태 재확인 필수**) | **외부 LLM**(gemma-4-12B, LAN) — 주소·context는 `.env`와 `/props`로 다시 잰다. 이 머신 GPU는 **GTX 1060 3GB**라 12B를 못 올린다 | 전체 스택. gateway는 `.env`의 `LLAMA_BASE_URL`로 외부 서버를 가리킨다 |
| **감마(Gamma)** | 사이드 개발용 (노트북) | **없음** — LLM을 못 띄운다 | CPU 기반 컨테이너·DB 정도(mongo/test-mongo·ES·chroma). LLM 관통 작업은 불가 |

- **어느 머신에서든 `docker compose up`만으로 같은 포트로 뜬다**(포트는 repo에 고정, 아래 "기동·실행법"). 머신별로 달라지는 것은 **LLM을 어디서 얻느냐**뿐이다:
  - 알파: `docker compose -f docker-compose.yml -f docker-compose.llama.yml up`(in-stack llama 9080).
  - 베타: `.env`에 `LLAMA_BASE_URL=http://192.168.1.22:9080`(커밋 금지 — gateway 기본값 `host.docker.internal:9080`을 외부 서버로 덮는다).
  - 감마: LLM 관통이 필요 없는 작업(회귀·저장소·색인)만. 필요하면 알파/베타로 옮긴다.
- **★ 2026-08-03: 알파→베타 전환이 끝났고 베타에서 재측정했다**(아래 "지금 상태"의 베타 관측치). repo 동기화도 확인됐다(`c2ca946`과 마감 커밋 존재, HEAD `05286a6` clean). 다음에 또 머신을 옮기면 같은 절차를 반복한다 — `git status --short`·`git log -1 --oneline`·`docker compose ps`·이미지 날짜·외부 LLM `/props`.
- **함정**: HANDOFF가 "스택이 내려가 있다/떠 있다"고 적었으면 그건 **그 시점 그 머신의 관측치**다. 다른 머신에서 그대로 믿지 말고 `docker compose ps`로 직접 확인한다(memory 규칙 "verify-machine-state-before-claiming-blocked").
- **★ 알파로 옮길 때 반드시 먼저 할 것 — `LLAMA_CTX_SIZE=16384`(2026-07-29).** 알파의 in-stack llama는 [`docker-compose.llama.yml:29`](docker-compose.llama.yml#L29)에서 **기본 8192**이고 `.env.example`에 항목이 없다. 그런데 **2026-07-29 회계 수정 후에도 report 프롬프트는 약 11,000~11,900 tok**이라, 창 8192에서는 **프롬프트만으로 창을 넘어 HTTP 400(`exceed_context_size_error`) → `provider_error` → generation job 실패**가 된다 — **오늘 아침 베타에서 4/4 실패했던 그 증상 그대로**다. 베타는 오너가 외부 서버를 16384로 올려 뒀지만 **그것은 그 서버의 설정이고 repo가 옮겨 주지 않는다.** 그러므로 알파에서 `long`을 돌리기 전 `.env`에 `LLAMA_CTX_SIZE=16384`를 넣는다(C-1 실측: 기동 성공, VRAM 9,481/12,288, 속도 무변). **안 넣고 실패를 보면 "오늘 수정이 안 먹었나"로 오독하기 쉽다 — 수정은 먹었고 창이 작은 것이다.** 근본 해결은 R-e(포인터 제거)이며 그 뒤에는 8192에서도 여유가 생긴다.

## 지금 상태

- 정본은 `docs/system-contract-sot.md` **v1.7.82**(Approved). 미확정 항목은 추측 구현하지 않는다.
- **진행 중 페이즈 = 다중 사용자 인증(D8).** 오너 지시로 **슬라이스를 잘게 쪼개 진행 중**이다(한 번에 큰 덩어리 금지). 진행표:

  | 슬라이스 | 상태 | 내용 |
  |---|---|---|
  | 1a·1b·1c | **완료** | User 저장(Argon2id) · 서버 세션 · `/auth/login`·`/auth/logout`·`/auth/me` (operation 62→**65**), 실 스택 관통 검증 |
  | **2a** | **완료** | `Project.owner_id: str \| None` 필드 + Mongo 왕복. `create_project(name, owner_id=None)`. **공개 API 무변** |
  | **2b** | **완료** | `POST /projects`가 세션이 있으면 생성자를 owner로 **기록**. 세션 없으면 unowned로 **여전히 200** |
  | 2c(선택) | 미착수 | `owner_id`를 공개 payload에 노출할지 — **프론트가 읽을 이유가 생길 때** 하면 된다(schema.d.ts 변경이므로 공짜 아님) |
  | **D8-4 선행** | **완료·검증 합격** | 프론트 로그인·세션 만료·route guard |
  | **3-a** | **완료** | 인증 dependency + 61 operation 401 선언 + 두 겹 전수 가드 |
  | **3-b** | **완료** | project-scoped 59 operation 소유권(403) + `GET /projects` 저장소 필터. `owner_id=None` 항상 deny |
  | **3-c** | **완료** | 401·403 결합 boundary matrix 감사. **D8-3 시행 종료** |
  | **5-a** | **완료** | `require_admin_user` + 관리자 tier 전수 가드 + `/admin/users` 목록·생성·비활성화 |
  | **5-c** | **완료** | 전역 관측 KPI `GET /admin/observability/kpi` — 감사 저장소 전역 조회 + 집계 재사용 |
  | **5-e** | **완료** | **승격(access grant)** — C-1~C-5 확정(TTL **1시간**·읽기 전용·사유 필수·append-only). `POST /admin/projects/{id}/access-grants`(201, operation **72**) + `require_project_owner` 인지 |
  | **5-f** | **완료** | **C-3 operation 단위 감사 + C-4 사후 조회**. 승격 아래 요청마다 `access_grant_uses` 한 행(사유 denormalize) + `GET /projects/{id}/access-log`(operation **73**). **기록은 fail-closed** |
  | **5-b** | **완료** | `GET /admin/projects` — 전 프로젝트 **메타데이터**(id·name·archived·owner_id, operation **74**). **내용은 안 준다**(승격 우회 방지) · 목록 조회는 감사 미기록 |
  | **C-6** | **완료** | 관리자가 정한 비밀번호는 **1회용** — 첫 로그인에 교체(409 → `new_password`). 정책 **최소 12자** |
  | **5-d** | **완료·검증 합격·hardening 폐쇄** | `/admin` guard/lazy 화면 · 강제 교체 UI · 전 프로젝트 목록 · 사용자 관리 · 전역 KPI · 승격 발급 · 소유자/관리자 접근 이력 |
  | **6 (D8-6)** | **완료·독립 검증 합격(`c2ca946`)** | archive-only purge UI+감사. Blocking/Hardening 0, 7축 mutation 전부 작동, 실제 Mongo에서 reconciler가 `target_project_id` tombstone을 보존함을 실증했다. **D4=A는 현행 core-first+reconciler**, **D4-D operation journal/saga는 원격 저장소·다중 worker 또는 수동 reconciler 부담이 생길 때 확장**한다. operation 75(ADMIN 8). 기준선 backend 1911/4/1625, frontend 236/17, build 698 modules. 검증 `docs/verifications/2026-08-02/d8_6_purge_ui.md`. |
  | **7 (D8-7)** | **절반 완료 — G1=C 시행(A), 나머지는 배포 시점** | **인프라 노출면.** 오너가 **G1=C**를 확정했다(2026-08-02) — 위험을 자격증명이 아니라 **노출면 축소로 없앤다**. 저장소·내부 5종(`mongo`·`chroma`·`elasticsearch`·`gateway`·`embedding`)과 `test-mongo`가 **`127.0.0.1:` 바인드**다. **코드 0줄**(compose 3파일뿐). **"외부 노출 금지"의 해제 조건이 *인증*에서 *노출 없음*으로 개정됐다**(SoT v1.7.75). **G2~G6(자격증명 SCRAM·keyfile·basic auth)은 각하가 아니라 유예** — 원격/다중 호스트 배포가 계기이며 브리프가 그대로 실행 계획이다 |

- **D8-3 E1~E4 = 전부 A로 확정** — `plans/auth-d8-3-enforcement-decisions.md`(Resolved). `owner_id=None`은 탈퇴·삭제 누락 같은 미래 비정상 잔존도 **항상 deny**. project 경로는 소유권, 그 외는 인증이며 `GET /projects`는 저장소 조회에서 본인 소유만 반환한다.
- **HTTP 인증·프로젝트 인가는 섰고 결합 감사까지 닫혔다.** 세션 없는 요청은 `/health`와 공개 `/auth` 두 곳을 빼고 401, project-scoped **59 operation**은 타인 소유·`owner_id=None`에 403이다. `GET /projects`는 Mongo `owner_id` 쿼리 경계에서 본인 소유만 반환한다. **저장소 계층은 D8-7 G1=C로 닫혔다** — 인증한 것이 아니라 **노출을 없앴다**(아래 항목).
- **★ 저장소는 이제 LAN에서 보이지 않는다(D8-7 G1=C, 2026-08-02) — 그러나 인증된 것은 아니다.** `mongo`·`chroma`·`elasticsearch`·`gateway`·`embedding`과 `test-mongo`가 compose에서 **`127.0.0.1:` 바인드**로 게시된다. 종전에는 이 셋이 0.0.0.0이라 **LAN의 누구나 무인증으로 붙을 수 있었고**, 그것이 "외부 노출 금지"의 실체였다. 오너 결정으로 그 위험을 **자격증명이 아니라 노출면 축소로** 없앴다(SoT v1.7.75가 해제 조건 문구를 *인증*→*노출 없음*으로 개정). **알아야 하는 것 넷**: ① **저장소 자체는 여전히 무인증**이라 포트를 다시 0.0.0.0으로 열면 원래 위험이 그대로 돌아온다 — 바인드가 유일한 방어다. ② **컨테이너 간 통신은 무영향**(compose 네트워크 이름 `mongo:27017`·`gateway:8001`)이고 **호스트 툴링도 무영향**(localhost로 붙는다 — mongosh·`migrate_ordered_units.py`·호스트 pytest·runbook curl 전부 그대로). 앱 코드는 **0줄** 바뀌었다. ③ **일부러 공개인 것은 셋뿐**이다 — `application`·`frontend`(제품 표면, 세션 뒤) · **`llama`(9080)**(GPU 머신이 12B를 못 올리는 머신에 모델을 주는 유일한 크로스머신 의존. 여기를 loopback으로 묶으면 베타가 스택을 못 돌린다 — 회귀가 "LAN에서 보여야 한다"로 잠근다). ④ `.env`로는 **번호만** 바뀌고 바인드 주소는 못 바꾼다. 가드는 `tests/test_compose_exposure.py`이며 **새 서비스가 포트를 게시하면 분류를 강제**한다(미분류면 실패 — 멀티라인·인라인·따옴표 유무 전 표기). **★ 다만 이것은 파일 수준의 시행이다** — **이미 만들어진 컨테이너는 옛 매핑을 그대로 들고 있으므로 재생성 전까지 런타임은 안 닫힌다**(아래 함정 절 참조). 독립 검증(`verifications/2026-08-02/`)이 잡은 항목이며 **재생성은 오너 결정 대기**다.
- **관리자 경계(D8-5·D8-6)**: `/admin/*` **8개 operation**이 `require_admin_user` 뒤에 있다. 비관리자는 403이고, 관리자는 project 내용에 자동 접근하지 않는다. 내용 조회는 사유 필수·1시간·읽기 전용 승격만 가능하며 `owner_id=None`은 승격으로도 열리지 않는다. 승격 사용 감사(`access_grant_uses`)는 fail-closed이고 TTL이 없다. purge는 내용 열람이 아닌 별도 ADMIN 예외이며, archive·사유·삭제 tombstone 계약을 따른다. 첫 관리자는 `create_user.py`로 부트스트랩한다.
- **마지막 활성 관리자는 비활성화되지 않는다**(F2=A, 409). 불변식은 호출자가 아니라 **활성 관리자 population**에 대한 것이다. 비활성화는 **단방향**이다 — 재활성화 API는 D6=A 범위 밖이라 만들지 않았고, 되살리려면 컨테이너에서 직접 고쳐야 한다.
- **인증 경계를 건드릴 사람이 알아야 하는 것**: 가드는 `tests/test_auth_api.py`의 `AuthenticationBoundaryTest`·`ProjectAuthorizationTest`·`CombinedBoundaryMatrixTest` 세 겹이며, 현재 **75개 operation 중 ADMIN 8개**다. 새 endpoint는 세 클래스가 모두 본다. `POST /projects`·`GET /projects`는 인증 전용이고, 403 생산자는 소유권·관리자 정확히 둘이다. 도메인 스위트는 dependency 해석만 override하므로 경계 테스트는 override 없는 앱으로 쓴다. 숫자의 권위는 코드의 tier 단정이다.
- **함정 — 인증은 두 겹이라 한 겹이 빠져도 아무 테스트도 실패하지 않는다**(2026-07-28 뮤테이션 실측): project route가 `_REQUIRE_PROJECT_OWNER`에서 인증 dependency를 먼저 선언하고 `require_project_owner`도 같은 dependency를 하위로 갖는다. 어느 한 겹을 지워도 **관측 상태코드가 전혀 변하지 않아** 요청 구동 테스트로는 원리적으로 볼 수 없다(둘 다 지워야 401이 403으로 샌다). 안쪽 겹은 **바깥 겹을 뺀 일회용 앱에 `require_project_owner`만 마운트해** 격리 구동하는 셀로 잠갔다(`CombinedBoundaryMatrixTest.test_the_ownership_dependency_cannot_run_without_authentication`). 인증을 유지한 합성·래퍼 dependency 리팩터링은 이 셀을 깨지 않지만(실측), **인증을 실제로 잃는 리팩터링은 깬다** — 여기서만 그것이 보인다.
- **첫 계정 만드는 법**(`POST /admin/users`가 생겼지만 그것을 쓰려면 이미 관리자여야 하므로 **부트스트랩은 여전히 스크립트**다. **★ C-6 이후 그 비밀번호는 1회용이다** — 첫 로그인에 `new_password`(12자 이상)를 함께 보내야 세션이 나온다): `docker exec -e PYTHONPATH=/app -e AUTH_BOOTSTRAP_PASSWORD='…' ai_writte_system-application-1 python scripts/create_user.py <username> --admin`. **`PYTHONPATH=/app`이 필수다** — 이미지에 PYTHONPATH가 없고 `python scripts/x.py`는 CWD를 sys.path에 넣지 않는다.
- **관측 KPI 페이즈의 결과물**(다음 작업이 이 위에서 돈다): LLM을 부르는 **호출부 8곳 전부**가 seam C(provider 데코레이터)로 계측되고 — **★ "8"의 기준은 `LlmCallSite` enum 리터럴 수(= LLM 어댑터 수)이며 `ObservedProvider(` 감싸기 지점 수와 일치한다(둘 다 8, 2026-08-02 실측). scope 진입 10·endpoint 9·TASK_TYPE 5는 *다른 것*의 개수라 일치할 이유가 없다 — 이 혼동이 실제로 독립 검증에서 "기준 불명" 지적을 낳았다. 그리고 "전부"는 호출부 단위이지 "모든 LLM 호출"이 아니다**(요청 경로 + 생성 워커는 기록, script·diagnostic은 계약상 미기록) — `analysis_extractor`·`writing_gate`·`compare_judge`·`query_planner`·`writing_retrieval_planner`·`writing_generation`·`writing_revision`·`writing_report` — `GET /projects/{id}/observability/kpi`가 집계를 내고, `/projects/:id/observability` 화면이 그것을 그린다. QUAL-1(제품 품질·수기·dogfood)과 별개 트랙이며 운영기획 포트폴리오는 `docs/observability-kpi-rationale.md`.
- **새 호출부를 계측하는 법**(Phase 7 등): ① `main.py` 조립 지점에서 provider를 `ObservedProvider(inner, call_site=…)`로 감싼다(도메인 코드는 건드리지 않는다). ② 그 호출이 일어나는 요청 경로에서 `llm_call_scope(...)`를 연다 — **감싸기와 scope 개방은 항상 함께 간다. 빠뜨리면 레코드가 조용히 0건인데 스위트는 green이다**(scope 유닛 테스트로는 안 물리므로 배선 회귀를 함께 넣는다). ③ **조립 가드도 함께 넣는다** — 하네스는 `ObservedProvider`를 직접 만들기 때문에 `_default_*`가 감싸기를 빠뜨려도 green이고 **배포에서만** 계측이 사라진다(실측: gate 조립에서 wrapper를 벗겨도 56 passed). 가드는 **리터럴까지 단정한다** — 잘못된 site로 감싸는 것은 안 감싸는 것과 똑같이 틀렸다. ④ 도메인만 아는 판정(gate decision·파생점수)은 `scope.annotate_last(...)`, 최종 도메인 거부는 **`scope.reclassify_last_as_parse_error(...)`**(마지막 레코드가 `success`일 때만 동작 — `provider_error` taxonomy를 덮지 않기 위한 가드)로 flush 전에 얹는다. `ContextSearchFailed` 계열은 같은 모듈의 `reclassify_planner_parse_error(scope, exc)`가 `llm_error` 계보만 걸러 준다 — **endpoint와 worker가 같은 정의를 쓴다**(복제하면 두 정책이 조용히 갈라진다).
- **계측에서 지켜야 하는 계약**(SoT §"LLM 파이프라인 관측(KPI)"): ① 레코드는 **provider가 실제로 호출된 경우에만** — seam C에서는 구조적으로 참이다. ② **실패한 호출도 센다**(성공만 세면 성공률이 영구히 100%). ③ **scope 밖 호출(worker·script)은 기록하지 않는다** — 추측 `project_id`는 오염이다. ④ 격리(`_flush`)를 **좁히지 않는다** — 좁히면 감사 저장소의 pymongo 예외가 전역 handler(v1.7.38)에 도달해 **정상 200이 503으로 뒤집히고**, flush가 `finally`에 있어 요청의 원래 예외까지 덮어쓴다.
- **`parse_error` 재분류는 호출부가 명시할 때만 일어난다**(데코레이터는 도메인 거부를 모른다). v1.7.47부터 **`analysis_extractor`만 재분류하지 않고 나머지 7 site는 재분류한다** — 재분류가 마지막 호출 1건만 건드리므로 repair로 회수된 첫 호출은 `success`로 남고 repair 빈도 신호가 손상되지 않기 때문이다. 따라서 **extractor의 `parse_error`=0은 구조적 사실이지 데이터 부족이 아니다**(`outcome`이 `success`·`provider_error` 둘뿐). **같은 repair 구조인데 정책이 갈리는 상태**이며, 정렬 여부는 아래 오너 결정 대기 항목이다.
- **집계 API를 읽을 때의 함정 3가지**(v1.7.48, 전부 응답이 분모를 함께 실어 방어한다): ① `total_tokens`는 `success`+`parse_error` 행만 — 분모는 `tokens_counted_from`. ② **표본이 0이면 비율은 `null`이지 `0.0`이 아니다**(`gate.avg_quality_score`·`loop.non_convergence_rate`) — loop 감사는 opt-in(기본 off)이라 기본 배포에서 `loop.runs_considered`=0이 정상이다. ③ **`multi_call_correlations`는 repair 수가 아니다** — site 고정 후 레코드 2건 이상인 correlation 수이며, repair 구조 site(extractor·compare·planner)에서만 repair를 뜻하고 writing loop에서는 **설계된 라운드**다(gate 최대 3회).
- **집계를 손볼 때 지켜야 하는 것**(v1.7.57): per-project(`GET /projects/{id}/observability/kpi`)와 전역(`GET /admin/observability/kpi`)이 **`kpi.py`의 `_fold` 한 곳을 공유한다** — 위 함정 3종이 전역에서도 성립하는 이유가 그 공유다. 규칙을 한쪽에만 고치는 형태로 갈라 놓으면 두 화면이 다른 사실을 말하게 된다. 그리고 **`multi_call_correlations`의 버킷 키는 `(project_id, correlation_id)`다** — `correlation_id`는 호출자가 준 `request_id`라 project가 다르면 같은 문자열이 나올 수 있고, project를 키에서 빼면 per-project는 멀쩡한데 **전역만 조용히** 일어나지 않은 repair를 센다.
- **loop 내부 gate 레코드에는 `decision`·`gate_quality_score`가 없다**(v1.7.47 알려진 공백): 파생점수는 endpoint가 `annotate_last`로 얹는데 revise loop이 round별 판정을 결과에 노출하지 않는다(`WritingLoopStage`는 stage/ordinal/status만). 그 필드는 **독립 `POST …/writing/gate` 호출에만** 채워지므로 집계가 전수 커버리지를 가정하면 안 된다.
- 공개 API 계약(H3)은 닫혀 있다: **전체 75개 operation**이 realistic 에러 상태를 OpenAPI에 선언하고 미매핑 500 부채는 0건이다. 새 endpoint는 `responses=`와 dependency를 함께 붙이고, `tests/test_auth_api.py`의 tier 전수 가드에 등재한다. 저장소 예외를 광의 `except Exception`보다 먼저 503으로 보존한다.
- 회귀 기준선: backend **test-mongo ON 1988 passed / 1 skipped / 1719 subtests**(베타 2026-08-03, Slice 8.2 + 검증 보강까지. 직전 알파 기준선은 1911/4/1625였고 차이는 전부 설명된다 — Slice 8.0 신규 가드 8+75, 검증 보강 4+15, 그리고 알파에서 skip되던 3건이 베타에서는 실행됐다. 남은 skip 1건은 호스트에서 구조적으로 항상 skip되는 live Chroma 셀), frontend **236 passed / 17 files**, build **698 modules · 진입 410.29 kB · AdminConsole lazy 8.39 kB · 관측 lazy 386.70 kB**. skip 수는 머신·인프라 기동 여부마다 달라 같은 환경에서 비교한다. backend는 `argon2-cffi`, frontend는 `npm install`이 선행돼야 한다.
- **스택 health를 읽는 법**(머신 무관, 구조적 사실): 정상 상태는 **healthy 7**(`application`·`gateway`·`mongo`·`elasticsearch`·`embedding`·`chroma`·`frontend`) + **healthcheck 없는 2**(`worker`·`generation_worker` — async 배경 워커라 by design, "Up"이지 "healthy" 아님). **"전부 healthy"라고 쓰지 않는다.**
- **[★ 최신 베타 관측, 2026-08-03 — 지금 작업 중인 머신]** `nvidia-smi` **GTX 1060 3GB**로 베타 확정. HEAD `05286a6` clean. `docker compose ps`에는 **`frontend`(healthy)·`worker`·`generation_worker`만** 있고 application·mongo·gateway·embedding·chroma·ES와 test-mongo는 **떠 있지 않다**(Slice 8.0 브리프는 스택이 필요 없어 올리지 않았다). 이미지는 코드보다 뒤처져 있다 — gateway 07-31, **application/generation_worker 07-29**(= D8-5~D8-7 인증·관리자 작업 이전), frontend·worker 07-27. **화면 확인이나 라이브 관통을 하려면 `docker compose build application frontend && docker compose up -d --no-deps application frontend`가 선행돼야 하고, 스택을 올렸으면 `curl :8520/projects`가 401인지 먼저 본다**(아래 ★★ 이미지 부채 — 낡은 application은 죽지 않고 인증 없는 제품으로 뜬다). 외부 12B(`192.168.1.22:9080`)는 살아 있고 `/props` 실측 **`n_ctx=16384`·`total_slots=1`**이며, 모델 스냅샷은 **`29d0977…`**(알파 `-hf` 리비전 부채가 가리키던 새 리비전을 외부 서버는 이미 쓴다).
- **[베타 머신 관측치, 2026-07-31 작업 종료 시점 — DB·계정·시드는 여전히 참고용]** 스택은 아침에 **15시간 전 `Exited(255)`**로 내려가 있었고(머신 재부팅 추정) `docker compose up -d`로 복구했다 — 지금 **healthy 7 + 워커 2**다. **첫 `docker` 명령이 30초 넘게 응답하지 않을 수 있다**(데몬 워밍업 — 죽은 것으로 오독하지 말 것). **★ 이미지가 코드보다 뒤처져 있다 — 화면으로 확인하기 전에 반드시 본다**: `gateway`는 07-30 14:52 빌드로 **K-3 가드까지 들어 있고**, `application`은 **07-29 15:48 빌드**라 **K-3 앱 절반(400 매핑·job 사유)·KPI 경고·K-1(환산·예산 8192)이 이미지에 없다**, `frontend`는 **07-27 빌드**라 **KPI 경고 타일과 `MAX_TOKENS=8192`가 없다**. 즉 브라우저로 보는 것은 **그 시점의 제품**이다. 확인하려면 `docker compose build application frontend && docker compose up -d --no-deps application frontend`. 라이브 검증은 전부 **작업 트리를 마운트**해 돌린다(`docker compose run --rm --no-deps -v "$PWD/services:/app/services" …`) — 재빌드 없이 실 파이프라인을 관통하는 그 방법이 표준이다. 외부 12B(`.env`의 `192.168.1.22:9080`)는 `/props` 실측 **`n_ctx=16384` · `total_slots=1`**. GPU는 **GTX 1060 3GB**. DB에는 프로브가 만든 project와 `llm_call_audits`가 있다(일부러 남겼다 — 육안 확인용). 계정 `probe`(admin). Mongo `prompt_templates`는 **`analysis_extract` v1~v4 4행뿐**이다(report·gate·생성 템플릿은 in-memory seed). **예산 포화 프로젝트(2026-07-31 시드, 재측정용)**: `6a6be9c0dbb39de0a51ed8ba` / draft `6a6be9c0dbb39de0a51ed8bb` / version `6a6be9c0dbb39de0a51ed8bc` — 밀도 1.63으로 만든 쪽이며 **이것을 쓴다**. `6a6be92bda7b035f309a8005`는 1차 시드(밀도 1.54, 대표성 낮음).
- **[베타, 2026-07-27 — 여전히 유효한 함정]** 이 머신 DB는 그때 비웠다. 구 `analysis_extract_v3` 본문(sha `fb4e272…`)이 현재 canonical(sha `4376310…`)과 달라 `PromptTemplateConflict`로 app이 죽었고, **오너 판단으로 데이터 볼륨(mongo·es·chroma)을 비워**(embedding 모델 캐시는 보존) 해소했다. 코드 회귀가 아니라 **오래된 볼륨과 현행 프롬프트 핀의 충돌**이며, 오래된 볼륨을 가진 다른 머신에서도 같은 일이 난다(위 "출시된 프롬프트 본문은 immutable" 함정과 같은 뿌리).
- **[★ 최신 알파 종료 관측, 2026-08-02]** `nvidia-smi`는 **RTX 3060 12GB**로 알파임을 재확인했다. `docker compose ps`에는 frontend(healthy)·worker·generation_worker와 **test-mongo(healthy, `127.0.0.1:27020`)만** 보였고 application/mongo/gateway/embedding/chroma/elasticsearch는 떠 있지 않았다. test-mongo는 D8-6 실제 Mongo 검증 뒤 **의도적으로 그대로 두었다**; 필요 없으면 알파에서 `docker compose -f docker-compose.test.yml down`으로 내린다. 베타 2026-07-31 관측은 과거 참고이고 이 줄이 알파의 최신 관측이다.
- 인증 백엔드 변경은 application, 로그인 UI 변경은 frontend 이미지 rebuild가 필요하다.

## 기동 · 실행법

**포트는 전용 대역으로 repo에 고정돼 있다.** env 없이 `docker compose up`만으로 어느 머신에서든 같은 포트로 뜬다. 값과 근거는 [`.env.example`](.env.example)에 있고, 머신별로 바꿔야 하면 `.env`로 복사한다(커밋 금지). **2026-08-02부터 아래 표의 포트는 종류가 둘이다** — `application`·`frontend`(+ 별도 파일의 `llama` 9080)만 전 인터페이스이고, **나머지는 `127.0.0.1` 전용**이라 다른 기기에서는 보이지 않는다(D8-7 G1=C, 위 "지금 상태" ★ 항목).

| 서비스 | 포트 | 서비스 | 포트 |
|---|---|---|---|
| application | 8520 | chroma | 8523 |
| gateway | 8521 | elasticsearch | 9520 |
| embedding | 8522 | frontend | 5520 |
| mongo | 27520 | test-mongo | 27020 |

표준 포트(27017·8000~8003·9200·5173)를 쓰지 않는 이유는 `.env.example` 상단에 있다 — 여러 머신을 옮겨 다니는 프로젝트라 충돌하고, 임시 env 회피는 repo에 안 남아 문서에 머신-로컬 관측치가 사실처럼 적히게 된다.

**백엔드 테스트** — `docker compose -f docker-compose.test.yml up -d` 후 `python3 -m pytest -q`. env 불필요(기본 URI가 27020 replica set `rs-test`). 미기동이면 Mongo 테스트가 **skip**(실패 아님). 끝나면 `... down`.

> **함정 — `up -d` 직후 곧바로 돌리지 말 것(2026-07-29 실측).** healthcheck는 `rs.initiate` 후 **writable PRIMARY**가 될 때까지 healthy를 보고하지 않으므로 기동에 수십 초가 걸린다. 고정 `sleep`을 주고 시작하면 **초반 모듈만 skip되고 나머지는 붙어**, 전량 실패가 아니라 **부분적으로 잘못된 기준선**이 나온다(실측: `1698 passed / 9 skipped` — 정상은 `/ 1`). 증상이 조용해서 "내 변경이 8건을 깨뜨렸나"로 오독하기 쉽다. **healthy를 기다린 뒤 시작한다**: `until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done`. 숫자가 안 맞으면 `-rs`로 skip 사유부터 본다.

**live Chroma 테스트**(호스트 `pytest`에서는 항상 skip되는 1건) — 호스트를 오염시키지 않고 이미 `chromadb`가 있는 application 이미지에서 돌린다:

```bash
docker compose up -d --no-deps chroma
docker compose run --rm --no-deps -v "$PWD/tests:/app/tests" \
  -e CHROMA_TEST_URL=chroma:8000 \
  application python -m unittest tests.test_chroma_adapter.ChromaAdapterLiveTest -v
```

**창 가드 라이브 확인**(K-3) — 배포된 게이트웨이 컨테이너에 붙어 `창 ± 1` 경계를 **자기 교정**으로 본다(창을 응답에서 읽으므로 배포 창이 8192든 16384든 그 배포의 경계를 본다):

```bash
docker compose run --rm --no-deps -v "$PWD/scripts:/app/scripts" -e PYTHONPATH=/app \
  application python scripts/gateway_generate_live_smoke.py --gateway-base-url http://gateway:8001
```

`context_window_guard.exercised: false`는 실패가 아니라 **창을 아직 몰라 판정 대상이 아니었다**는 뜻이다(프로세스 첫 호출·`/props` 실패). 게이트웨이 코드를 고친 뒤라면 `docker compose build gateway && docker compose up -d --no-deps gateway`가 선행돼야 한다.

**프론트** — `cd frontend && npm run gen:api && npx tsc --noEmit && npm run build && npx vitest run`.

## 함정 (모르면 시간을 잃는 것들)

- **출시된 프롬프트 본문은 immutable이다.** `tests/test_prompt_templates.py`가 `analysis_extract` **v1~v4 전부**의 본문 sha256을 핀한다(**현행 v4가 빠져 있던 것을 2026-07-30에 발견해 채웠다** — 옛 버전은 아무도 고칠 이유가 없지만 **현행 본문은 고칠 이유가 늘 있어서** 핀이 가장 필요한 자리가 그쪽이다. 핀 목록이 출시 버전 전부를 덮는지도 같은 셀이 단정한다). 본문을 고치면 테스트가 깨지는데 **해시를 갱신하면 안 되고 새 버전을 만들어야 한다.** 어긴 결과: 기존 Mongo를 가진 배포가 `PromptTemplateConflict`로 전부 죽어 스택이 3일간 안 떴다. Mongo에 영속되는 프롬프트는 `analysis_extract` 하나뿐이라, 다른 프롬프트를 영속으로 옮기면 sha256 핀도 함께 확장해야 한다.
- **compose의 `ulimits.nofile`은 튜닝이 아니라 필수다.** Docker 기본 1024면 WiredTiger가 `Too many open files`로 mongod를 죽이는데, **test-mongo에서는 증상이 skip이 아니라 failure라 코드 회귀처럼 보인다.** 배포 `mongo`(64000)·`elasticsearch`(65535)에도 같은 이유로 들어가 있다 — 값이 다른 것은 각 데몬이 요구하는 최소치를 그대로 쓴 것이다.
- **뮤테이션 테스트 원복에 `git checkout -- <file>`을 쓰면 미커밋 작업이 사라진다.** 이 프로젝트는 "변형을 넣고 테스트가 무는지 본 뒤 원복"을 표준 절차로 쓰는데, **슬라이스 자체가 아직 커밋되지 않은 상태가 흔하다** — 그때 `git checkout --`은 변형만 지우는 게 아니라 **HEAD로 되돌려 그 슬라이스를 통째로 날린다**. 실제 사고(2026-07-30 독립 검증): `git checkout -- writing/report.py`가 미커밋 R-e(v2)를 v1으로 되돌렸고, 검증자가 처음 읽은 내용으로 복구해 무사했다. **원복은 역방향 Edit이나 사전 `cp` 백업으로 한다.** 그리고 남이 복구했다고 하면 **백업과 `diff`로 직접 대조한다** — `git diff --stat`이 같아도 내용이 같다는 보장은 아니다.
- **★ compose의 포트 매핑 변경은 이미 만들어진 컨테이너에 적용되지 않는다 — `up -d`로도 안 된다**(2026-08-02 독립 검증이 잡았다). 포트 매핑은 **컨테이너 생성 시점에 고정**되므로, D8-7 G1=C의 loopback 바인드는 **파일 수준에서만 참**이고 기존 컨테이너는 `docker ps -a`에 여전히 `0.0.0.0:27520->27017` 같은 **옛 매핑을 들고 있다**. 지금은 그 컨테이너들이 Exited라 실제 노출은 없지만, **옛 컨테이너를 그대로 다시 살리면 LAN 노출이 그대로 복귀한다.** 반영하려면 **재생성**이 필요하다(`docker compose down` 후 `up -d`, 또는 `up -d --force-recreate`). 볼륨은 named라 `down`으로 지워지지 않는다(`down -v`는 지운다 — 쓰지 말 것). **확인법은 파일이 아니라 `docker port <container>`다** — compose 파일을 읽고 "닫혔다"고 결론내면 안 된다. 같은 성질이 env·command 변경 전반에 적용된다.
- **백엔드는 `pytest`가 아니라 `python -m pytest`로 실행한다.**
- **★ 계약에 "…는 잠기지 않는다 / …해도 안 깨진다" 류의 *방어적 단언*을 쓰면, 그 단언을 지나는 셀이 있는지 그 자리에서 확인한다.** 2026-08-02 하루에 두 번 걸렸다 — D8-5e의 `owner_id=None`(**Blocking**: 무소유 project가 승격으로 열렸다)과 C-6의 pre-C-6 Mongo 행(`.get(..., False)`를 하드 서브스크립트로 바꿔도 **1898 전부 통과**). **둘 다 결함을 *넣는* 뮤테이션으로는 원리적으로 안 보인다** — 없는 셀은 무엇을 깨뜨려도 실패하지 않기 때문이다. 잡은 것은 **방어를 없애 보거나 고칠 것을 미리 넣어 보는** 뮤테이션이다. 후자는 특히 fake가 늘 새 필드를 갖는 저장소 계층에서 위험하다(아래 naive-datetime 함정과 같은 형태 — 스위트는 green, 배포만 죽는다).
- **pymongo는 BSON 날짜를 naive로 돌려준다**(client가 `tz_aware=True`가 아닌 한). 그것을 aware `datetime.now(UTC)`와 비교하면 `TypeError`다. **fake-collection 테스트는 이걸 재현하지 못한다** — aware를 넣으면 aware가 나오므로 **스위트는 green인데 배포만 깨진다**. 실측(2026-07-27): 세션 `expires_at` 비교가 실 Mongo에서 `GET /auth/me`를 전량 500으로 만들었는데 유닛 46건은 전부 통과했다. 규칙: **Mongo 날짜를 파이썬으로 끌어와 비교하면 `_entry` 경계에서 UTC를 재부착**하고(`auth/sessions_mongo.py`의 `_aware`), fake collection이 **드라이버처럼 naive를 돌려주는** 회귀를 함께 넣는다. 기존 코드가 무사한 이유는 같은 판정을 **쿼리 서버측**(`{"$lte": …}`)에서 하기 때문이다(`generation_job_mongo.py:85`·`indexing/mongo_repository.py:130-136`) — 그 방식을 따르면 이 함정 자체가 없다.
- **쿠키 인증 테스트는 `TestClient(app, base_url="https://testserver")`로 만든다.** 세션 쿠키는 `Secure`가 기본 on이라 http 클라이언트는 쿠키를 **조용히 버린다** — 세션 테스트가 엉뚱한 이유로 실패한다(실제로 처음 4건이 그렇게 실패했다).
- **in-stack llama(`-hf`)가 캐시가 멀쩡한데도 모델을 다시 받는 이유가 잡혔다**(2026-07-28 알파 실측): `-hf …:Q4_0`은 리비전을 고정하지 않고 `main`을 따라가는데, HF 캐시의 `refs/main`이 `29d0977…`로 이동한 반면 디스크 snapshot은 `f6e7774…`·`2b318d6…`뿐이다. 즉 **"정체"가 아니라 새 리비전을 받는 중**이며, 기다리면 언젠가 뜨지만 6.5 GB를 다시 받는다. 회피는 캐시 snapshot을 `-m`으로 직접 지정하는 것: `-m /models/models--google--gemma-4-12B-it-qat-q4_0-gguf/snapshots/2b318d6ebebf093f50ca4376e858325f10703358/gemma-4-12b-it-qat-q4_0.gguf`. 볼륨에 stale `.downloadInProgress` 약 4.9 GB가 남아 있다(11.8 GB 중). **repo는 아직 안 고쳤다** — 리비전 고정 여부는 추적 부채.
- live 작업 시 외부 llama(`192.168.1.22:9080`)가 죽어 있으면 in-stack llama로 돌린다.
- **[프론트 회귀 플레이크, 2026-07-31 관측]** `DraftEditor.test.tsx` 전체 스위트가 희귀하게(~9회 중 1회)
  "1 failed | 40 passed"로 떨어진다 — 독립 검증 중 관측, 희귀해 테스트명 못 잡았다. 유력 원인 (a) 기존 타이밍
  의존 테스트의 사전 플레이크, 차선 (b) K-4(b) `useWritingBudget` mount-fetch가 DraftEditor 렌더 경로에 새로
  들어간 비동기-온-마운트와의 레이스. **핵심은 프론트 변경 후 이 플레이크가 떨어지면 내 변경 탓이 아닐 수 있다는
  것** — 재현 시 특성화하고 (b)가 의심되면 `useWritingBudget` mount-fetch부터 본다. 상세는
  `docs/verifications/2026-07-31/k4_front_counter_budget.md`.

## Active Decisions (앞으로의 작업을 구속하는 것)

완료 이력이 아니라 **표준 제약**만. 근거는 각 `docs/plans/*-decisions.md`.

- **개발 단계(2026-07-20 오너)**: "Gate 우선" 단계는 끝났다. 지금은 **Gate ↔ UI/UX 왕복**이 주축이다.
- 아이디에이션·계획이 충돌하면 임의 구현 없이 오너 결정을 받는다. 나중 요청이 기록된 결정과 충돌하면 어느 쪽이 canonical인지 먼저 묻는다.
- monorepo + 독립 LLM Gateway/Worker, Application = FastAPI. 경계는 `project_id`이며 **모든 저장·검색·Gate·tool handler가 강제한다**.
- **개발 단계(2026-07-26 오너)**: MVP 단일 사용자 유예가 만료돼 **다중 사용자로 확장 중**이다(정본 **v1.7.49** = D0=A 단계 전환 — 2026-08-02 독립 검증이 정정. 종전 이 줄이 적던 v1.7.57은 전역 관측 KPI(D8-5c)라 무관하다). 사용자·세션·프론트 로그인과 HTTP 소유권 격리·결합 감사는 섰다. **저장소 계층은 D8-7 G1=C(노출면 축소)로 닫혔다 — 조건은 "인증"이 아니라 "노출 없음"이다**(v1.7.75). 소유권은 `project_id` 강제를 대체하지 않고 그 위에 얹힌다.
- frontend = React + TS + Vite, 서빙은 별도 compose 서비스(nginx). OpenAPI→TS 타입 생성 + 얇은 `fetch` 래퍼.
- **Core SOT**: offset = raw Unicode code point, `content_hash` = raw UTF-8 SHA-256. `source_ref` span은 단일 `source_block` 안에 든다. persistence는 Mongo transaction 기본이고 non-transaction fallback은 **single-writer local/test 전용**. project/draft는 archive(soft delete)하고 snapshot/version/source_ref는 보존한다(archive = 읽기 허용, 본문 쓰기·rename 409).
- **memory는 append-only**. AI가 직접 덮어쓰지 않고 검색·대조·Gate·검토·versioned upsert를 거친다. canonical만 `memory_vectors`에 색인하며 트리거는 async outbox→worker다. semantic 매칭은 **off 기본**.
- **재색인 enqueue는 무조건 choke point다**(v1.7.37): canonical을 만드는 모든 경로가 `MemoryService._enqueue_reindex`를 지나고 **idempotent replay도 재enqueue한다**. outbox가 PENDING/RUNNING 항목에만 dedup하므로 pending 중 replay는 no-op이고, drain된 뒤의 replay만 재색인을 한 번 더 돌린다(upsert라 오염 아님). **`promoted[]` 보고 의미론은 불변** — replay는 여전히 제외되며 바뀐 것은 색인 side-effect뿐이다.
- taxonomy 3종(`character_observation`/`event_observation`/`open_question_observation`), provenance `source_observed`/`ai_inferred`.
- **agent loop 계약층은 더 진행하지 않는다**(tool-call parsing·wire format 미계약). sub-agent spawn 없이 bounded flat loop만.
- **에러 계약(H3)**: 본문은 균일 `{"detail": <string>}`. 상태코드=기계용, `detail`=사람용이라 **`detail` 문자열로 분기하면 안 된다**. 503은 **세 얼굴** — 협력자 **미구성**(배포 구성) · 데이터 **무결성**(`scripts/migrate_ordered_units.py`) · **정본 저장소 장애**(v1.7.35, 복구 후 재시도가 유효한 유일한 얼굴). **상류가 없는 게 아니라 있는데 실패한 것은 502**이고, **정본 저장소는 상류가 아니라 503**이다. 저장소 face는 `create_app`의 **전역 exception handler**가 매핑하므로 새 endpoint가 자동 상속한다 — 다만 **`responses=`에 503을 붙이는 것은 여전히 수동**이고 전수 가드가 빠뜨림을 잡는다(`/health`만 제외).
- **균일 본문의 유일한 예외 = partial envelope**, 허용 지점 **정확히 6곳**(revise-and-gate 4 · accept 1 · auto-promote 1). 되돌릴 수 없는 성공 부분이 이미 영속된 실패 경로만 해당하며, 새 Union은 정본 목록을 함께 넓히는 명시 결정으로만 들어온다(트랙별 over-strict 가드가 drift를 막는다).

## 추적 부채

- **[확장 방향 확정·착수 조건 대기] D8-6 D4-D purge operation journal/saga.** 현재는 오너 결정 A대로 core SOT 선삭제 + `purge_reconciler.py` 수습이며, 503 후 UI 재시도는 금지한다. **원격 저장소·다중 worker를 도입하거나 수동 reconciler가 실제 운영 부담이 되는 시점**에 durable operation id와 단계별 상태·재개 worker를 가진 D안으로 확장한다. 그 전에는 core-first 순서나 never-existed 404 의미를 임의로 바꾸지 않는다. 정본 v1.7.82 · 결정 브리프 `docs/plans/auth-d8-6-purge-ui-decisions.md` D4.
- **[미구현이나 구현 결정됨, 포트폴리오 정확성 주의] cross-encoder(뉴럴) 리랭커는 아직 없다.** 현재 RAG 리랭킹은 **RRF(Reciprocal Rank Fusion) 융합만**이다 — 벡터(Chroma/BGE-m3-ko) + lexical(ES/nori) 두 랭킹을 `1/(k+rank)`(k=60)로 합쳐 재정렬([`context_search/service.py:279`](services/application/app/context_search/service.py#L279)·[`:495`](services/application/app/context_search/service.py#L495), env `vector/lexical/hybrid`). query-document 쌍을 신경망으로 재채점하는 cross-encoder 리랭커는 2026-07-05에 유예됐다가([`plans/04-real-vector-backend-decisions.md:11`](docs/plans/04-real-vector-backend-decisions.md#L11)) **2026-07-27 구현하기로 결정**됐다(`plans/external-api-expansion-decisions.md` D5): 로컬은 self-host **`dragonkue/bge-reranker-v2-m3-ko`**(임베딩 서비스와 같은 패턴), 외부 리랭커 API도 붙일 수 있게 `RerankProvider` seam을 함께 뚫는다. **별도 슬라이스**(인증·외부 API LLM/임베딩 슬라이스 뒤). **삽입 자리**: RRF 융합 결과 뒤, `retrieve()` seam 다음. **포트폴리오/README 표기**: 현재 상태는 "RRF 하이브리드 융합 리랭킹 있음, 뉴럴 cross-encoder 리랭커는 미구현(구현 예정)"이 정확 — 코드가 붙기 전까지 "있음"으로 쓰면 거짓이다.
- **[미래 확장, 지금 범위 아님] 공유·협업 글쓰기.** 오너(2026-07-27)가 "생각 안 해봤다 — 나중에 한 번 생각해보자"며 유예. 다중 사용자 소유권은 **D3=A(`Project.owner_id` 한 필드 = 격리, 1 project 1 owner)**로 가되, 공유/협업(권한 등급·workspace·`members[]`)은 미래 확장이다. D3=A가 그 문을 **닫지 않게** 설계돼 있다(`owner_id`는 나중에 `members[]` 첫 원소나 workspace 소유로 승격 가능 — `plans/multi-user-auth-cms-decisions.md` D3). 착수 시점 아님.
- **[해소됨 2026-08-01] 앱 route를 치는 스크립트 9종에 세션 로그인이 붙었다.** 공용 코드는 [`scripts/script_auth.py`](scripts/script_auth.py) 한 곳이고 종류가 둘이다 — **운영자용 8종**은 `--username <계정>` + **`APPLICATION_PASSWORD` env**(비밀번호 argv 금지 — `create_user.py` 선례, shell history·`ps` 노출), **자기 스택을 소유하는 in-process smoke 1종**(`phase2a_provider_live_smoke`)은 **일회용 계정을 스스로 발급**해 로그인한다(빌릴 운영자 계정도, 실행 뒤 남는 것도 없다). **자격증명을 안 주면 종전대로 익명 진행.**
  - **★ 세션을 실을 때 지켜야 하는 것**: 로그인 응답의 쿠키를 **httpx jar의 자동 왕복에 맡기면 안 된다** — 세션 쿠키는 `Secure`라 plain http(`application:8000`·ASGI `application-smoke`)에서 조용히 안 실린다(뮤테이션 실측 `cookie: None`). 지금 구현은 **명시 `Cookie` 헤더**지만 **헤더가 유일한 정답은 아니다** — `client.cookies.set(...)`도 동작한다(손으로 넣은 쿠키엔 Secure가 없다, 실측). 회귀는 그래서 *행동*만 잠근다. **헤더 전용으로 조이지 말 것**(정상 구현을 깨는 과잉 교정).
  - **가드는 두 겹이다**(`tests/test_script_login.py::ScriptLoginWiringCoverageTest`): ① 레지스터의 9종이 실제로 로그인하는가 ② **`scripts/*.py`를 읽어 앱 route 마커(`"/projects`·`\bseed_context\b`)가 있는데 레지스터에 없는 스크립트가 있는가**. ②가 없던 첫 판에서 **`phase2a_provider_live_smoke`를 놓친 채 "8종 전부"라고 보고했다**(스윕이 `application:8000` 문자열만 봤고 그 스크립트는 ASGI 가상 호스트를 쓴다). **새 스크립트는 레지스터에 넣는다 — 안 넣으면 ②가 실패한다**(이제 규칙이 아니라 강제다).
  - 진단 2종(`diagnose_writing_report`·`diagnose_writing_gate`)은 **`--current-position`을 주면 시드를 건너뛰므로 로그인도 필요 없다**(로그인이 필요한 것은 시드 write뿐).
  - 라이브 확인: 실 앱 관통으로 무자격 401 → 로그인 후 통과(phase3a exit 0, phase2a 인증 write 6건 200), in-process smoke는 죽은 llama를 가리켜 인증 통과 후 `final_job=failed`. **워커는 여전히 무관**(HTTP를 안 쓰고 Mongo 직접 — D8-7).
  - **첫 관리자 계정만** 부트스트랩 스크립트로 만든다. 그 뒤 계정 생성·확인은 `/admin` 화면에서 한다.
- **[해소됨 2026-08-02] 기획 축 "제품 한 장 요약" = [`docs/product-overview.md`](docs/product-overview.md).** 제품 컨셉·MVP 범위·핵심 위험이 `abstract.md`(48KB) 안에만 있던 공백을 닫았다. **원본 요약이 아니라 코드 실측 기준으로 다시 썼고**, 초안(2026-06)에서 달라진 5건을 §5에 따로 모았다 — ① 단일 사용자 → 다중 사용자 ② 추출 5종 → **관찰 3종**(장소·관계 미착수, 떡밥은 `open_question_observation`) ③ Gate 4종 분리 → **Writing Gate 하나**(지적 4유형·판정 5종, `style`은 판정을 안 바꾼다) ④ 문체는 학습이 아니라 **선언**(프로젝트 브리프 4필드) ⑤ 관측이 제품 기능으로 추가. **★ 이 다섯이 "초안만 읽으면 틀리는 지점"이다** — 포트폴리오·설명 자료를 쓸 때 abstract를 그대로 인용하면 거짓이 된다. MVP 4는 **승인 UI만 섰다**(Review Inbox 병합/분할까지 배선, 인물카드·타임라인·관계 그래프 화면은 0건). README 기획 축의 시작점이 이 문서로 바뀌었다(abstract는 "원본"으로 유지).
- **★ [권위 소스의 낡은 단언, 3건 미정정] 위 문서를 쓰며 패턴 스윕으로 찾았고, 고칠 권한이 없거나 결정 사안이라 남겼다.** (a) **정본 `system-contract-sot.md` §"현재 구현 상태"(L696~710)가 자기 자신과 모순된다** — L696이 "Review Inbox v1.6.67 구현"·L709가 "Writing 작업공간 구현 완료"라고 적으면서 **L710이 `Phase 2~6 UI | 미구현`이라 단언**한다. **(2026-08-02 독립 검증이 정밀화한 지점: 종전 이 줄은 L710을 그냥 "거짓"이라 적었으나 과했다** — Phase 2/3/4 UI 중 **인물카드·타임라인·관계 그래프는 실제로 미구현**이라 그 행은 *부분적으로 성립*한다. 진짜 결함은 거짓이 아니라 **같은 표 안의 모순**이다.) v1.6.x 이후 갱신이 끊긴 표이며 **현재 상태의 실제 권위 소스는 변경이력과 코드**다. 정정은 버전 개정 사안(v1.7.77): ⓐ 갱신 ⓑ **"이력 표이며 현재 상태는 변경이력을 본다"로 성격 명시(추천 — 갱신하면 같은 부채가 세 번째로 쌓인다)** ⓒ 걷어내기. (b) `observability-kpi-rationale.md` §6 로드맵 4항목 중 **2항목이 이미 완료**(호출부 계측 확대·집계/대시보드) — 기획 톤 문서라 표현 손질이 논조 변경이고 포트폴리오 정문이라 오너 취향 사안. (c) `plans/00-foundations.md` "전역 착수 전 결정사항" 체크박스 미갱신(에러 envelope=H3·삭제 정책=D5=A·monorepo 경계는 확정됨) — 거짓 단언이 아니라 미갱신이라 급하지 않다. **정정된 5건은 그날 work_log 표에 있다**(그중 `plans/README.md`가 가리키던 `tests/test_plans_index.py`는 **존재하지 않는 파일**이었다 — 인덱스 가드는 `.md` 링크만 보므로 코드 파일명 참조는 안 잡힌다).
- **[문서 부채 — 도달 가능성은 해소됨 2026-08-02, 디렉터리 재편은 여전히 미결정] `docs/plans/`가 크다(89개 문서, 그중 73개가 `*-decisions.md` 브리프).** **가장 아프던 증상은 닫혔다**: 종전 [`plans/README.md`](docs/plans/README.md)는 평평한 번호 목록이라 **90개 중 51개가 미등재**였고 그래서 오너가 자기 결정 브리프를 못 찾았다. 이제 **89개 전부가 트랙별 표로 등재**돼 있고, [`tests/test_docs_indexes.py`](tests/test_docs_indexes.py)가 **미등재 문서**와 **깨진 링크**를 양방향으로 막는다 — 새 브리프를 인덱스에 안 넣으면 실패한다(규칙이 아니라 강제). 같은 가드가 **검증 기록**과 **최상위 `README.md` 링크**도 덮고, 2026-08-02부터 **"검증 기록 N건"이라는 숫자 주장 네 곳과 판정 분포 합계까지** 디스크 실측에 묶는다(`VerificationCountClaimsTest`) — 세 문서가 각자 세던 탓에 하루 세 번 갈라졌고 **매번 최상위 README 만 뒤처졌다**. 링크는 강제였는데 숫자는 아니었던 자리다. 접두 체계가 무너져 있어(`00`~`07` 계열 + 접두 없는 최근 것들) 인덱스는 **접두가 아니라 트랙**으로 묶었다.
  - **★ 남은 미결정 = 디렉터리 재편이고, 2026-08-02에 실측해 보니 "지금 하지 않는다"가 근거 있는 판단이다.** 브리프 경로 인용이 **1,083건 / 253개 파일**이며 그중 **183개가 `docs/verifications/`의 과거 검증 기록**이다 — 즉 파일을 옮기면 **지나간 검증 기록 본문을 대량으로 고쳐 쓰는 일**이 되고, 그 작업이 평가자·작업자 어느 쪽에도 주는 가치는 사실상 0이다(브리프가 `plans/`에 있든 `plans/decisions/`에 있든 달라지는 것이 없다). **아프던 증상(도달 불가)은 인덱스로 이미 닫혔으므로 재편의 남은 동기는 미학뿐이다.** 열려는 사람은 이 비용을 알고 열 것.
  - **주의: 브리프는 오너 결정의 근거 기록이라 삭제·병합하면 "왜 그렇게 정했는가"가 사라진다** — 이동·인덱싱은 되지만 통폐합은 결정 이력 손실이므로 별도 판단이다.
- **[수리됨 2026-07-30] `long` report의 창 초과는 R-e로 없어지고, 남는 초과는 가드가 400으로 거부한다.** 2026-07-29에는 `writing_report`가 4/4 `provider_error`(400 하드 거부)로 죽었고 원인은 항목마다 붙는 포인터 JSON이었다(report 컨텍스트의 79%). **R-e**(SoT v1.7.61)가 프롬프트를 11,841 → 3,216 tok으로 줄여 헤드룸을 −1,665 → +7,024로 바꿨고, **K-3 가드**(v1.7.62)가 그래도 넘는 요청을 **모델을 부르기 전에** 400으로 거부한다(왕복 0회). 창 8192에서 `3,216 + 6,144 = 9,360 > 8,192`인 경우가 그 자리다 — 종전에는 이것이 400이 아니라 **조용한 잘림**이었다. 알파에서 `LLAMA_CTX_SIZE=16384`를 넣는 이유는 이제 "안 죽게 하려고"가 아니라 **거부당하지 않으려고**다(위 ★ 함정 유지).
- **[프론트 UX 부채, 미수리] 결정적 `provider_error`에도 프론트가 "다시 시도"를 준다.** 문구는 "생성 모델 호출에 실패했습니다."([`GenerationPad.tsx:20`](frontend/src/writing/GenerationPad.tsx#L20))다. 게이트웨이는 4xx를 `retryable=False`로 분류하지만 **그 정보가 화면까지 오지 않아** 재시도가 반드시 같은 실패로 끝나는 경우에도 버튼이 그대로 있다. 종전에 이 항목을 눈에 띄게 만든 원인(`long` report 400)은 R-e로 사라졌지만 **UX 부채 자체는 남는다**(창을 넘기는 다른 입력·모델 4xx 전반).
- **[관측·분류의 잔존 한계, 2026-08-03 독립 검증 H1] "provider를 부르는 route는 반드시 분류된다"는 강제되지 않는다 — 강제되는 것은 *scope를 여는* route까지다.** [`ObservedProvider.generate`](services/application/app/observability/llm_call_scope.py#L209)는 scope가 없으면 호출을 **미기록 통과**시킨다(worker 진입점·script를 위해 계약이 그렇게 정했다 — 추측 `project_id`로 오염시키지 않으려는 것). 따라서 미래에 **provider를 부르되 `llm_call_scope`를 안 여는 route**가 열리면 ① 관측에 안 남고 ② `llm_call_scope(` 문자열이 없어 Slice 8.0 분류 가드에도 안 잡혀 **무료로 조용히 빠진다**. **지금은 안전하다** — 유료 9경로 전부가 per-endpoint 관측 셀(요청을 구동해 레코드가 남는 것을 단정)에 묶여 있고 그 대응표 자체를 `BillableActionObservabilityCoverageTest`가 잠근다(새 유료 동작을 관측 셀 없이 추가하면 실패). **새 LLM 호출부를 만들 사람이 알아야 하는 것**: 감싸기(`ObservedProvider`)와 scope 개방은 늘 함께 가고, Phase 8 이후로는 **분류표 등재까지 셋이 함께 간다**. 닫으려면 route 본문에서 scope 블록 밖의 provider 호출을 정적 탐지하거나 scope-None 경로를 진단 메트릭으로 노출해야 하는데, 둘 다 별도 판단이라 하지 않았다.
- **[관측 공백] `llm_call_audits`로는 "출력이 잘렸다"를 직접 볼 수 없다.** v1.7.59가 `prompt_tokens`·`completion_tokens`·`context_window`·`max_output_tokens`를 추가해 헤드룸은 계산할 수 있지만 **`finish_reason`·`truncated`는 여전히 없다**. 따라서 상한 기준 초과는 보이되 실제 잘림 여부는 `parse_error`로만 간접 관측된다.
- **[알파 작업을 막는 것, 미결정] `docker-compose.llama.yml`의 `-hf`가 리비전을 고정하지 않는다.** `-hf …:Q4_0`은 `main`을 따라가는데 업스트림 `refs/main`이 `29d0977…`로 이동해, 캐시에 온전한 6.5 GB 모델이 있어도 **새 리비전을 다시 받는다**(위 함정 절에 회피법). 고정하려면 `-hf`에 리비전을 붙이거나 `-m`으로 캐시 경로를 직접 쓰면 되지만, **모델 리비전을 최신으로 올릴지 현행을 고정할지가 먼저 정해져야 한다** — 새 리비전이 프롬프트 sha 핀·gate 동작에 어떤 영향을 주는지 미측정이다. 볼륨의 stale `.downloadInProgress` 약 4.9 GB 정리도 함께 판단할 사안.
- **[★★ 알파 이미지 부채 — 증상 정정 2026-08-02, 종전 서술이 위험을 과소평가했다] 오래된 `application` 이미지는 죽지 않는다. 조용히 *인증 없는 제품*으로 뜬다.** 종전 이 항목은 "임포트 체인이 `ModuleNotFoundError`로 **죽는다**"고 적었으나 **실측은 반대였다**(2026-08-02, 스택 재생성 후): 이미지가 **2026-07-22 빌드**(= auth 슬라이스 D8-1~6 전체보다 앞선다)라 그 코드에는 `argon2` import 자체가 없고, 그래서 **앱은 정상 기동해 healthy를 보고한다**. 대신 **`/auth/login`이 404이고 `GET /projects`가 세션 없이 200**이다 — 즉 **HTTP 인증 시행이 통째로 없는 제품**이 뜬다. `docker exec … python -c "import argon2"`는 여전히 `ModuleNotFoundError`이므로 **"argon2가 없다"는 관측은 맞았고 그로부터 추론한 증상이 틀렸다**. **왜 위험한가**: 죽으면 즉시 알지만 이건 healthy라 안 보이고, 하필 `application`·`frontend`는 **일부러 LAN에 공개**하는 두 표면이다(D8-7 G1=C가 "세션 뒤에 있다"를 근거로 공개를 유지한다) — **오래된 이미지에서는 그 근거가 성립하지 않는다.** **규칙: 스택을 올린 뒤 `curl :8520/projects`가 401인지 확인한다. 200이면 이미지가 낡은 것이고 즉시 재빌드한다**(`docker compose build application frontend && docker compose up -d --no-deps application frontend`). **트리 마운트는 코드만 덮고 파이썬 패키지는 이미지 것**이라 마운트로는 안 고쳐진다.
- **[프론트 스타일 부채, 오너 관측 2026-07-29] 이어쓰기 예비 원고가 줄바꿈되지 않아 탭이 좌우로 길어진다.** 원인은 정확히 하나다 — [`ScratchRecovery.tsx:83`](frontend/src/writing/ScratchRecovery.tsx#L83)이 `<pre className="scratch-recovery-text">`로 그리는데 **`styles.css` 1,693줄에 그 클래스 규칙이 0건**이라 `<pre>`가 브라우저 기본 `white-space: pre`로 떨어진다(= 줄바꿈 없음). **바로 옆 후보 산문 블록은 이미 `white-space: pre-wrap`을 쓰고 있어**([`styles.css:1117`](frontend/src/styles.css#L1117)) 이 클래스만 빠진 형태다. **증상 자체는 한 줄 수정**이지만, 오너 판단은 **이것을 계기로 프론트 스타일을 제대로 한 번 잡자**는 쪽이다 — 그래서 단발 수정으로 닫지 않고 부채로 둔다. 스타일 슬라이스를 열 때 **최소한 함께 볼 것**: 긴 본문을 그리는 다른 지점의 줄바꿈·넘침 정책, 좁은 화면에서 표가 넘치는 문제(관측 화면), 그리고 실패 UX(위 `provider_error` 항목의 "다시 시도" 문구).
- **관리자 제품 표면(v1.7.82)**: 첫 관리자만 부트스트랩 스크립트로 만든다. `/admin`에서 사용자·전 project 메타데이터·전역 KPI·승격/접근 이력과 **archive project 영구 삭제·최근 삭제 감사**를 다룬다. 최초 비밀번호는 같은 로그인 화면에서 12자 이상으로 교체한다. `owner_id=None`은 승격으로도 안 열린다. purge는 정확한 이름+사유가 필수이고 503 뒤 재시도하지 않는다. 첫 관리자 없이 자기 가입하는 표면은 없다.
- **[해소됨 2026-07-30, 대신 알아야 하는 것] 컨텍스트 항목 렌더링은 이제 한 정의다.** [`context_search/item_render.py::render_context_item`](services/application/app/context_search/item_render.py)을 프롬프트(`writing/prompt.py`)와 예산 회계(`estimate_rendered_item_tokens`)가 **함께** 쓴다(사본을 두게 했던 순환 import가 R-e로 사라졌다). **항목 렌더링을 바꿀 때 예산이 자동으로 따라오지만 정확히 한 곳에 여유가 있다**: 회계는 항목 생성 시점에 그 항목의 인용 번호를 모르므로 `_BUDGET_CITATION_NUMBER=999`로 센다 — 항목당 최대 1토큰 과대평가이며 세 회계 셀이 `0 ≤ 여유 ≤ 항목수`로 단정한다. **여유를 넓히려면 그 단정을 함께 고친다**(밴드 뒤에 숨기면 항목을 두 번 세는 과잉 교정이 통과한다).
- **[오너 결정 대기, K-3 가드의 의도된 공백] 창을 모르는 호출은 가드 밖이다.** 게이트웨이 프로세스의 **첫 생성 1회**와 **`/props` 조회가 실패한 프로세스 전체**가 그렇다(1b가 실패를 재시도하지 않기로 정했으므로 후자는 계속 꺼져 있다). 닫으려면 가드가 창을 짧은 예산 안에서 **기다려야** 하는데, 실측해 보니 **v1.7.60이 계약으로 못박은 "생성과 동시에 시작하고 결과를 기다리지 않는다"를 어기고** B1 회귀 셀([`test_llama_provider_client.py`](tests/test_llama_provider_client.py)의 `test_a_slow_probe_does_not_delay_or_fail_the_generate`)이 그 예산만큼 매달린다. **성능 문제가 아니라 계약 개정 문제**이며 임의로 뒤집지 않았다. 선택지: ⓐ 그대로 둔다(첫 호출만 노출) ⓑ 가드 경로에 한해 짧은 대기를 허용하도록 v1.7.60을 개정한다 ⓒ `/props` 실패를 1회 재시도하게 바꾼다(1b 결정도 함께 개정).
- **[기존 불일치, 미정렬] `/writing/generate`만 provider TIMEOUT을 502로 낸다.** gate·revise·report·compare는 504다([`main.py`](services/application/app/main.py)의 `_provider_error_status`가 504로 정한다). generate는 자기 `except ProviderError`에서 502를 내고 그 502를 [`test_writing.py`](tests/test_writing.py)의 셀이 잠그고 있다. **2026-07-30 K-3 슬라이스가 만든 것이 아니다** — 창 가드 분기만 더하고 정렬은 손대지 않았다. 정렬하려면 선언 surface(504 declared 여부)와 잠긴 셀을 함께 바꿔야 하므로 별도 판단이다.
- **[누수 아님, 의존성 주의] `context_search/service.py:199`·`:406`의 `embed()`**: 자체적으로 `EmbeddingProviderError`를 안 잡지만 호출자(step runner `:752`·`:835`)의 광의 `except Exception` → `BACKEND_ERROR` → 502가 이미 보호한다. **그 catch를 좁히면 그 순간 500 누수가 된다.**

## Owner Decisions Needed

- **★ dogfood 착수(GATE-1)** — 실 12B 풀스택 관통은 끝났고 기술적 선행 조건은 없다. 착수하면 `OPS-1` Ready 승격. **인증 HTTP 시행이 닫히면서 "인가 없이 dogfood하면 데이터가 섞인다"는 종전 걸림돌은 사라졌다** — 이제 남은 것은 D8-5~7 구현과의 순서 판단이며 오너 결정 사항이다.

**결정 완료 — 오너 결정 대기 아님, 구현만 남음:**

- **Phase 8 Slice 8.2b = G1=C·G2~G6=A 확정, 구현 대기**(오너 2026-08-03, 브리프 [`plans/08-2b-duplicate-request-lock-decisions.md`](docs/plans/08-2b-duplicate-request-lock-decisions.md)). 잠금은 **"5초 타이머"가 아니라 진행 중 보호 + 최소 냉각 창**이다(G1=C) — 동기 생성이 **약 23초**라 고정 5초 창으로는 "결과가 나오기 전 재클릭"을 못 막기 때문이다. 문서는 `_id="{user}:{action}:{project}"`(키가 곧 id라 **추가 인덱스 불필요**) + `claimed_at`·`expires_at`(**판정의 유일한 축**)·`released_at`(`None`이면 진행 중). 연산 셋: 차지(`now + lease`) · 해제(`max(now, claimed_at + 최소 창)`) · **강제 재차지**(확인 — UX이자 **크래시 복구 경로**). **막힌 이유는 `released_at`에서 파생**된다. **★ 두 상수를 합치지 말 것**: 최소 창 5초는 제품 정책, lease(잠정 180초)는 기술 한계(gateway timeout 120초보다 커야 한다). **★ TTL은 청소용이고 판정은 `expires_at` 비교다** — 존재 여부로 판정하면 Mongo TTL 주기(~60초) 때문에 5초가 최대 1분이 되고, **fake에는 TTL 주기가 없어 테스트로는 안 보인다**. 실패 응답은 **`429`**(앱 전체 미사용이라 충돌 없음) + `detail` 문구이며 **H3 균일 본문 개정은 하지 않는다** — 429 선언·전수 가드 등재는 8.3이 한다. **알려진 한계**: lease 만료 시점에 원래 요청이 살아 있으면 중복이 샌다(`WRITING_LOOP_MAX_WALL_CLOCK_MS`가 기본 무제한이라 동기 상한을 증명할 수 없다) — **최선 노력 통제이지 절대 보장이 아니다**.
- **Phase 8 Slice 8.2 = L1=B·L2~L5=A 확정·구현·독립 검증 합격**(오너 2026-08-03, SoT v1.7.85, 검증 `afc9df0` PASS·Blocking 0 + H1·H2 보강 완료, 브리프 [`plans/08-2-usage-ledger-decisions.md`](docs/plans/08-2-usage-ledger-decisions.md)). 원장은 **`(user_id, action, target_project_id, 창 키 2개, at, dedupe_key)`** 행이고 관리자 조정은 **같은 컬렉션의 다른 종류**(`kind`, 필드 구성이 겹치지 않는다)다. 집계 정본은 **행 count**(카운터 캐시 없음), **TTL 없음**. **★ 필드명은 반드시 `target_project_id`다** — `project_id`로 적으면 purge reconciler가 그 필드를 가진 컬렉션을 DB에서 발견해 **과금 기록을 지운다**. 오너 결정이 "프로젝트가 삭제돼도 사용 기록은 남는다"이므로 이름 하나가 결정의 성패를 가른다. **삭제된 프로젝트는 id 수준으로만 답해진다** — purge가 이름을 안 남기므로 원장도 이름을 스냅샷하지 않는다(그러면 삭제 계약을 우회한다). **중복 방지 키에 `action`이 들어간다** — 프론트가 한 흐름에서 uuid를 공유하므로 그것 없이는 유료 동작 4개가 1개로 접힌다. **5초 오·중복 가드**(프로젝트별·확인 필수·locking)는 오너 요구다. **★ 주의 — 초판 브리프가 "유니크 인덱스가 곧 locking"이라 적은 것은 오류이며 정정됐다**: 그 인덱스는 dedupe 키가 같을 때만 물고 프론트는 **클릭마다 새 uuid**를 만들므로 실수 중복은 그대로 통과한다. **별도 잠금이 필요하다**(L7). 그리고 오너가 **프로젝트 이름·제목을 히스토리로 보존**하기로 해(삭제 요청이 지우지 않는다) **L6**이 신설됐다 — 이것은 **D8-6 삭제 계약 개정**과 **purge UI 문구 수정**을 부른다(현재 "전체가 삭제되며 복구할 수 없습니다"가 부분적으로 거짓이 된다). **범위는 나(분리)로 확정됐다** — **8.2**(L1~L5, 원장만·백엔드) → **8.2b**(L7 잠금·백엔드, 8.3이 곧바로 소비) → **8.2c**(L6 이름 이력 + D8-6 계약 개정 + purge UI 문구, 백엔드+프론트+정본). 오너 근거는 중간 독립 검증 단위를 작게 유지하는 것이고, 개발 중이라 중간 상태를 감수한다는 판단이다. **구현자가 반대 논거로 들었던 "거짓 UI 문구 구간"은 나에서는 생기지 않는다** — L6을 통째로 미루므로 이름 이력·계약 개정·UI 문구가 8.2c 안에서 함께 들어간다. **구현 결과**: `request_usage_ledger`에 `kind`로 갈린 두 종류(사용/조정)가 살고 **필드 구성이 겹치지 않는다**. 창 사용량 = 사용 행 수 + 조정 합이며 **음수가 될 수 있다**(환급 초과 — 깎지 않는다, 잔여 해석은 8.3). **★ 유니크 인덱스는 부분 인덱스여야 한다** — 조정 행에 `action`·`dedupe_key`가 없고 Mongo가 없는 필드를 `null`로 색인해, 전체 인덱스면 **두 번째 조정 행이 거부된다**(구현이 드러낸 함정). 인덱스는 부분 유니크 `(user_id, action, dedupe_key)` + 집계 `(user_id, daily_key)`·`(user_id, weekly_key)` **셋**이다(최근성 인덱스는 8.2b의 잠금 문서가 대체하므로 안 만들었다). **아직 아무도 조립하지 않는다** — 소비자는 8.3이다. L6·L7의 세부는 8.2c·8.2b 착수 시 결정한다. **검증 보강 2건**: 원장 경계에서도 **naive 입력을 거부**한다(8.1에서 전이적으로 오던 보호를 여기서 잠갔다), 그리고 **저장 문서의 키 집합 자체를 고정**했다 — 파기 reconciler의 컬렉션 발견은 `find_one`이라 **표본 한 건**이므로, 원장 문서 **하나**에만 `project_id`가 섞여도 컬렉션 전체가 sweep 대상이 된다. 새 필드를 더하려면 그 셀을 함께 고쳐야 한다.
- **Phase 8 Slice 8.1 = P1~P8 확정·구현·독립 검증 합격**(오너 2026-08-03, SoT v1.7.84, 검증 `756bf2e` PASS·Blocking 0 + H1~H3 보강 완료, 브리프 [`plans/08-1-request-quota-policy-decisions.md`](docs/plans/08-1-request-quota-policy-decisions.md)). **사용량 초기화 주기와 구독 이용기간은 다른 축이다**(오너 지적으로 초판 P2를 재구성했다). 사용량 창은 **일(KST 자정마다) + 주(가입일로부터 7일, 회원별)** 이중 창이고 요청은 **두 창을 모두** 통과해야 한다. **경계는 KST이고 [`quota/policy.py`](services/application/app/quota/policy.py)가 이 저장소의 유일한 지역 시간대 지점이다** — 창 키 계산을 다른 곳에서 또 하면 화면과 시행이 다른 "오늘"을 말한다. **창은 파생이라 리셋 작업이 없다**(스케줄러 없는 스택에 새 인프라를 안 들인다). 한도는 창별 `daily_limit`·`weekly_limit`(`None`=무제한) + `status`이며 **`limit=0`(0회)과 정지는 다른 상태**다. **행이 없으면 코드 기본값**(env override) — 기본값 `일 20 / 주 100`은 **잠정**이고 호출부는 상수가 아니라 해석 함수를 지난다. **정책 변경은 필드별로 유리하면 즉시·불리하면 현재 주기 끝에** 발효한다 — **정지도 유예 대상이다**(오너: 최대 1주 지연을 사용감 우선으로 수용). **즉시 차단이 필요하면 계정 비활성화를 쓴다** — 세션 해석이 매 요청 `is_active`를 보므로 기존 세션까지 즉시 끊긴다(실측). 저장은 `request_quota_policies`(`_id`=`users._id`, 추가 인덱스 없음). **아직 아무도 조립하지 않는다** — 소비자는 8.3이다. 차감·차단·원장·관리자 API는 8.2~8.5. **검증 보강 2건**: 창 함수가 **naive 입력을 거부한다**(`_require_aware` — `astimezone`이 naive를 시스템 로컬로 읽어 비-UTC 호스트에서 경계가 조용히 어긋나던 가정을 계약으로 올렸다. 저장소 경계의 `_aware`와 방향이 반대인 것은 의도적이다), 그리고 **`policy.limits`는 유효 한도가 아니다** — 발효한 예약이 문서에 남을 수 있으므로 읽기는 항상 `effective_limits`/`limits_for`를 지난다(8.5 관리자 조회 주의).
- **Phase 8 Slice 8.0 = B1~B6 전부 A로 확정·시행·독립 검증 합격**(오너 2026-08-03, SoT v1.7.83, 검증 `3b7afc8` PASS·Blocking 0, 브리프 [`plans/08-0-billable-request-boundary-decisions.md`](docs/plans/08-0-billable-request-boundary-decisions.md)). **회원 사용량 1회 = 유료 endpoint 요청 1건**이고 provider 호출 수가 아니다. **원가 차이는 요금 단위로 옮기지 않고 내부 BM에서 흡수한다** — 그래서 가중치는 회원에게 보이는 단위로는 채택하지 않는다(유예가 아니라 채택 안 함). 유료 경로 **9개**이며 판정 기준은 **`llm_call_scope`를 여는가**다. 내부 repair·루프 라운드는 그 1회에 포함하되 **관측에서는 전부 보여야 한다**(오너 단서 — 새 계측 없이 기존 seam C로 충족, 근거는 브리프 §3.1). `analysis_compare`는 후보 수 비례 fan-out이지만 역시 1회다. 비동기 워커 실행과 실패 job 재시도는 같은 논리 요청이라 **재차감하지 않는다**. **분류 정본은 코드다** — [`quota/billable_actions.py`](services/application/app/quota/billable_actions.py), 강제는 `tests/test_billable_actions.py`(양방향, 뮤테이션 7종 확인). **시행은 아직 없다** — 차감 시점·기간·한도·원장·면제는 8.1~8.4다. 검증 비차단 지적 4건은 그날 닫았다: 표현 정정(H1 — 아래 추적 부채)·워커 상관키 셀(H2)·"N일치"와 `docs/plans/` 문서 수 주장을 가드로(H3)·README 기준선 갱신(H4).
- **Phase 8 회원별 요청 제한 = 상위 방향 확정, 슬라이스별 결정·구현 대기**(오너 2026-08-02). 회원 quota/BM 기준은 **토큰량이 아니라 서비스 요청 횟수**다. 토큰은 각 요청의 생성 상한에서 통제하며 회원 quota로 누적하지 않는다. 부모 계획은 [`plans/08-member-request-quota.md`](docs/plans/08-member-request-quota.md). **세부 정책을 지금 일괄 결정하지 않는다** — 8.0 사용 동작 인벤토리부터 8.6 결제 entitlement seam까지 각 슬라이스 착수 시 별도 owner decision brief를 만들고 승인 뒤 구현한다. 실제 결제·환불·정산과 CMS 프론트는 범위 밖. **D8-6 독립 검증 종료 뒤 8.0**이 다음 구현이며, 외부 API 확장은 새 quota seam을 소비하게 한다.

- **다중 사용자 인증 D0~D8 + E1~E4 = 결정·제품 시행·독립 검증 완료**. HTTP 인증·소유권·관리자 API/화면·archive-only 영구 삭제 UI·최소 삭제 감사·인프라 노출면 축소가 섰다. D8-6 최종 검증은 `c2ca946` PASS이고, D8-7 저장소 자격증명(G2~G6)은 원격 배포 시점으로 유예됐다.
- **외부 API 확장 D1~D6 = 전부 결정됨**(2026-07-27). `plans/external-api-expansion-decisions.md` §2: 세 축 전부 확장하되 **슬라이스 분리**(LLM → 임베딩 → 리랭커)·D2=A(generic OpenAI 호환)·D3=A(env 키, 인증 시크릿 재사용)·D4=A(전역 기본)·D5=리랭커 포함(self-host `bge-reranker-v2-m3-ko` + 외부 seam). 코드 실측 공백 = 인증 헤더 주입 지점·provider 선택 config. **착수는 인증 다음**.
- **`analysis_extractor`를 D4로 정렬할지**(v1.7.47): 지금 이 site만 최종 도메인 거부를 `parse_error`로 재분류하지 않아 같은 repair 구조인 `compare_judge`와 정책이 갈린다. 정렬하면 두 site가 같은 규칙을 따르고, 두면 v1.7.46 결정이 유지된다. 어느 쪽이든 이행 무손실 증명이 필요한 별도 증분.
- **loop의 round별 gate decision 노출 여부**(v1.7.47 공백): 노출하면 loop 내부 gate 레코드에도 파생점수를 얹을 수 있다. 도메인 계약(`WritingLoopStage`) 변경이라 D2-B(파생점수 정교화)와 함께 볼 사안.

## Next Tasks

**1번이 현재 진행 중인 트랙이다.** 나머지는 그와 무관하게 남아 있는 것들.

1. **Phase 8 Slice 8.2b 구현**(G1=C·G2~G6=A 확정, 위 결정 완료 항목에 잠금 문서 모양까지 있다). ① 계약을 **양방향 회귀로 먼저** 잠근다 — **동시 두 요청 중 하나만 차지** · **만료된 잠금은 TTL 주기와 무관하게 다시 차지된다** · **진행 중/냉각 두 구간을 각각**(경계 직전·직후) · **다른 `action`·다른 프로젝트는 서로를 막지 않는다** · **강제 재차지 뒤 곧바로 온 요청은 다시 막힌다** · **lease > 최소 창** · **막힌 이유가 `released_at`에서 파생된다** ② 도메인 + Mongo 어댑터(청소용 TTL, fake는 TTL을 흉내 내지 않는다 — 그것이 판정에 안 쓰인다는 증거다) ③ `mongo_collections.md` §43E ④ 8.3 시행 브리프(429 선언·전수 가드 등재 포함).
2. **베타 상태 확인 뒤 화면 육안 확인 2건**(둘 다 로직은 회귀로 잠겨 있고 렌더만 미검증). 2026-07-31에는 계정 `probe`와 감사 데이터가 있었지만 현재 존재를 다시 확인한다:
   (a) 관측 화면 `/projects/:id/observability` — 차트 라벨 충돌·막대 배치·좁은 화면 표 넘침. **`heavy long report probe` project를 보면 `provider_error`가 섞인 분포**를, `long report probe`를 보면 성공 분포를 볼 수 있다.
   (b) 비동기 패드 — 렌더 · 이어쓰기 탭 완료 배지 · 5초 폴링 · "다시 시도" 버튼 · 탭 전환 후 폴링 생존. **failed job이 4개 남아 있어 실패 UX를 바로 볼 수 있다** — 위 추적 부채대로 "다시 시도"가 결정적으로 재실패하는 것도 여기서 확인된다.
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
