# 배포 외부화 축 ①② — env 배선 · 외부 전용 override 독립 검증

## Subject metadata

- **날짜**: 2026-08-15 (알파)
- **요청자**: 오너 (*"핸드오프랑 데일리로그 확인해서 코드쪽이나 뭐 이런걸로 내 개입없이 작업할 수 있는게 있는지 확인해봐"* → 미검증 구간 검증을 선택)
- **검증자**: 이 세션(구현 세션과 별개 — 2026-08-14 커밋을 만들지 않았다)
- **대상 슬라이스**: 배포 서버용 "모델 다운로드 0 · 외부 API 전용" **축 ①(env 배선) · ②(선택 기동 override)**
- **대상 커밋**: `b6b1269` · `3ff94a3` · `8e57369`(코드/compose) + `86e193b` · `6a51bbb` · `e13a482` · `9e2f1ef`(기록·문서)
- **정본 참조**: [`docs/daily_logs/2026-08-14/work_log.md`](../../daily_logs/2026-08-14/work_log.md) §Decisions D-10.5-e/f/g · [`HANDOFF.md`](../../../HANDOFF.md) "추적 부채" 배포 외부화 항목 · [`.env.example`](../../../.env.example) §"배포 서버: 모델 다운로드 0"
- **작업 트리 상태**: HEAD `9e2f1ef`, clean (검증 시작·종료 시점 `git status --short` 공백)

## Scope

1. **축 ① dash/콜론 짝** — compose 표기가 각 변수를 읽는 코드와 실제로 짝인지. HANDOFF가 지정한 첫 축이며 **구현자가 한 번 틀렸다고 기록한 자리**다.
2. **축 ② `CHROMA_PORT` 예외** — env 화하지 않고 남긴 판단의 근거와 그 근거가 셀에 잠겼는지.
3. **축 ③ override 방식** — `docker-compose.external.yml` 이 base 를 건드리지 않고 ①②를 함께 닫는지.
4. **경계 행렬** — 계약이 요구하는 "그래야 한다"/"그러면 안 된다" 분기가 전부 셀에 매핑되는지.
5. **문서 ↔ 동작** — `.env.example` 의 배포 안내가 실제 compose 동작과 일치하는지.

## Methodology

- 표기 전수 대조: `grep -cE '\$\{[A-Z_]+-' docker-compose.yml` = **10**, `grep -cE '\$\{[A-Z_]+:-' docker-compose.yml` = **42**. 콜론 42곳의 변수를 전부 뽑아 `services/`·`scripts/` 에서 읽는 코드를 찾아 대조했다.
- 코드 읽기 직접 확인: [`main.py:1123`](../../../services/application/app/main.py#L1123) · [`main.py:1025`](../../../services/application/app/main.py#L1025) · [`main.py:1047`](../../../services/application/app/main.py#L1047) · [`llm_gateway/main.py:58`](../../../services/llm_gateway/app/main.py#L58) · `_env_bool`/`_env_float`([`llm_gateway/main.py:43-55`](../../../services/llm_gateway/app/main.py#L43)).
- 실측 재현: `docker compose -f docker-compose.yml -f docker-compose.external.yml config`(주소 유무 두 갈래) · `config --services` 를 base 와 대조.
- 뮤테이션 4종(아래 표). 트리가 clean 이므로 `git checkout -- <path>` 분기를 썼고, **뮤테이션 사이마다 `git status --short` 를 찍어 4회 전부 공백**을 확인했다.
- 기준선: `python3 -m pytest tests/test_compose_backend_env.py tests/test_compose_exposure.py -q` = **17 passed / 55 subtests**.

## Findings

### 1. 축 ① dash/콜론 짝 — 짝 규칙 자체는 참이고, 추가 위반은 0건

세 백엔드는 전부 빈 값을 미설정으로 취급한다 — `if not base_url:`([main.py:1047](../../../services/application/app/main.py#L1047)) · `if not host or not os.environ.get("EMBEDDING_SERVICE_URL"):`([main.py:1025](../../../services/application/app/main.py#L1025)) · `if not url:`([main.py:1123](../../../services/application/app/main.py#L1123)). **dash 형태가 맞다.** gateway 는 `os.environ.get("LLAMA_BASE_URL", DEFAULT_LLAMA_BASE_URL)`([llm_gateway/main.py:58](../../../services/llm_gateway/app/main.py#L58)) 로 기본값 *인자* 라 **콜론 형태가 맞다.** work_log Task 2 의 정정은 옳다.

**콜론 42곳을 전수로 훑어 `if not` 으로 읽는 변수를 추가로 찾으려 했으나 0건이다.** 전부 `os.environ.get(name, default)` 또는 `_env_bool`/`_env_float`/`_env_int` 형태였다. 이 중 `_env_bool` 은 `raw is None` 만 보므로 **빈 문자열을 `True` 로 읽고**(`"".lower() not in {"0","false","no"}`), `_env_float` 는 `float("")` 로 죽는다 — 즉 이 변수들이 dash 형태였다면 결함이 됐을 자리이며, 콜론이라서 도달 불가능한 것이지 안전해서가 아니다. 짝 규칙의 근거를 오히려 강화한다.

### 2. 축 ② `CHROMA_PORT` — 판단 타당, 그리고 셀이 *전제까지* 잠갔다

같은 이름이 host publish([docker-compose.yml:272](../../../docker-compose.yml#L272))에서는 호스트 포트, environment 에서는 컨테이너 내부 포트다. 코드는 `int(os.environ.get("CHROMA_PORT", "8000"))` 로 읽으므로 env 화하면 `.env.example:35` 의 `CHROMA_PORT=8523` 을 그대로 따른 사람이 앱을 아무도 안 듣는 포트로 돌리게 된다. 판단은 옳다.

**특기할 것**: `test_chroma_port_stays_hardcoded_because_the_name_is_taken`([tests/test_compose_backend_env.py:164](../../../tests/test_compose_backend_env.py#L164))이 하드코딩 유지뿐 아니라 **그 예외의 전제**(host publish 가 여전히 `${CHROMA_PORT:-8523}` 를 쓴다)까지 단정한다. 전제가 사라지면 셀이 실패해 예외를 다시 보게 만든다 — 예외를 영구화하지 않는 드문 설계다.

### 3. 축 ③ override — base 무변·profiles·`!override` 전부 재현됨

- `8e57369` 의 diff 는 `.env.example`·`docker-compose.external.yml`·테스트 2개뿐이고 **`docker-compose.yml` 을 한 줄도 건드리지 않았다** — "base 지문 IDENTICAL" 주장은 diff 만으로 증명된다.
- 주소 없이 `config` → **rc=1**, `required variable ELASTICSEARCH_URL is missing a value: 외부 Elasticsearch 주소가 필요하다`. 재현됨.
- `config --services` 대조: base **10개** → external **7개**(`chroma`·`elasticsearch`·`embedding` 제외). 재현됨.
- 전수 셀 `test_every_service_declaring_a_backend_takes_it_from_env` 는 선언 서비스를 **파일에서 유도**하고 수를 단정하지 않는다([:102-112](../../../tests/test_compose_backend_env.py#L102)) — 네 번째 서비스가 생겨도 강제된다. `admin` 이 백엔드 3종을 안 받는 것은 Slice 2 설계이고 사유가 [docker-compose.yml:166-173](../../../docker-compose.yml#L166) 주석에 있다(Mongo 전용 표면). 이번 슬라이스의 편차가 아니다.

### 4. 뮤테이션

| # | 적용한 diff | 자리 | 결과 |
|---|---|---|---|
| **M-A** | `${LLAMA_BASE_URL:-…}` → `${LLAMA_BASE_URL-…}` | [`docker-compose.yml:202`](../../../docker-compose.yml#L202) (base gateway) | **0셀.** compose 를 읽는 가드 전부(`test_compose_backend_env` + `test_compose_exposure` + `test_admin_surface_separation`) = **27 passed / 135 subtests 전원 green** |
| **M-B** | **문자 그대로 같은 diff** | [`docker-compose.llama.yml:76`](../../../docker-compose.llama.yml#L76) (override gateway) | **2셀 재실패** — `test_an_empty_value_falls_back_to_the_in_stack_model` · `test_an_explicit_base_url_wins_over_the_in_stack_model` |
| **M-C** | `${ELASTICSEARCH_URL:?…}` → `${ELASTICSEARCH_URL:-http://elasticsearch:9200}` (3자리) | `docker-compose.external.yml` | **1셀 / 3 SUBFAILED** — `test_external_addresses_are_required_not_defaulted`(application·worker·generation_worker) |
| **M-D** | (M-C 복원 후 기준선 재측정) | — | 17 passed / 55 subtests 복귀 |

**M-A ↔ M-B 의 대비가 이 검증의 핵심이다** — 같은 변수, 같은 서비스(`gateway`), 같은 코드 읽기, 문자 그대로 같은 diff 인데 한 파일에서는 2셀이 물고 다른 파일에서는 0셀이 문다.

M-C 는 가이드가 경고한 `grep FAILED` 사각지대를 실제로 재현했다 — `pytest-subtests` 가 `SUBFAILED` 로 찍으므로 `^FAILED` 필터였으면 "안 물었다"로 오독했을 자리다. 요약 줄(`3 failed`)로 읽었다.

## Issues / Risks

### Blocking

**B1. base `docker-compose.yml:202` 의 `LLAMA_BASE_URL` 표기를 잠그는 셀이 0건이다.**

`InStackLlamaOverrideTest` 는 `docker-compose.llama.yml` 만 읽고([:206-208](../../../tests/test_compose_backend_env.py#L206)), `ExternalBackendEnvTest` 는 base 를 읽지만 `_EXTERNALIZABLE`(백엔드 3종)만 순회한다([:44-48](../../../tests/test_compose_backend_env.py#L44)). `LLAMA_BASE_URL` 은 어느 목록에도 없다.

- work_log §Issues found 는 해소를 *"두 방향 다 셀로 잠갔다 — 백엔드 3종은 콜론 형태를 거부하고, llama 는 dash 형태를 거부한다"* 고 적었다. **그 주장은 llama override 한 자리에서만 참이다.**
- 위험이 큰 쪽이 안 잠긴 쪽이다. work_log 가 경고한 *"이 파일의 다른 40여 항목이 전부 콜론이라 표기 통일이 자연스러워 보인다"* 의 **그 파일이 base** 이고(콜론 42곳이 여기 있다), base gateway 는 **override 없이도 늘 뜨는 기본 기동 경로**다. 베타는 실제로 base + `.env` 의 `LLAMA_BASE_URL` 로 외부 LLM 을 가리킨다(HANDOFF 머신 구성).
- 이 슬라이스가 결함을 *만든* 것은 아니다 — base:202 의 콜론 형태는 `60553c4` 부터 올바른 값이었다. 다만 이 슬라이스가 **세운 계약**("표기는 코드가 그 변수를 읽는 방식을 따라간다")이 같은 변수의 두 자리 중 한 자리에서만 강제된다.
- **닫는 법(제안, 구현은 구현자 몫)**: `LLAMA_BASE_URL` 의 콜론 형태를 base·llama override **두 파일에서 함께** 단정하는 셀 하나. `_EXTERNALIZABLE` 의 반대 방향 목록(`_COLON_REQUIRED = {"LLAMA_BASE_URL": …}`)으로 두면 세 번째 파일이 생겨도 같은 규칙이 따라간다.

**B2. `.env.example` 의 "값이 없으면 기동을 거부한다" 가 `LLAMA_BASE_URL` 에는 참이 아니다.**

[`.env.example:96-109`](../../../.env.example) 는 배포 서버 절에서 *"**값이 없으면 기동을 거부한다** — 조용히 in-stack 기본값으로 떨어지면 뜨지도 않는 서비스를 가리키기 때문이다"* 를 적은 뒤 주소 다섯을 나란히 나열한다. 그중 `EXTERNAL_CHROMA_PORT` 는 같은 줄에서 *"생략하면 8000"* 이라고 **자기 예외를 밝힌다.** `LLAMA_BASE_URL` 은 예외를 밝히지 않았는데 **실제로도 거부하지 않는다** — external override 는 gateway 를 건드리지 않고([`docker-compose.external.yml:24-26`](../../../docker-compose.external.yml#L24) *"gateway 는 끄지 않는다 … 주소는 base 의 `LLAMA_BASE_URL` 로 정한다"*), base 는 콜론 형태라 미설정 시 `host.docker.internal:9080` 으로 조용히 떨어진다.

즉 배포 서버 운영자가 이 안내를 그대로 따르다 `LLAMA_BASE_URL` 을 빠뜨리면, **파일 자신이 배격한 바로 그 실패 형태**(뜨지도 않는 자리를 가리키고 연결 실패로만 드러남)가 된다. 같은 문단이 세운 fail-fast 원칙이 네 번째 주소에만 적용되지 않는 **계약 내부 비대칭**이다.

- **어느 쪽으로 닫을지는 결정 사안이라 검증자가 고르지 않는다**: (a) external override 에서 gateway `LLAMA_BASE_URL` 을 `:?` 로 필수화해 문서와 맞춘다 — 배포 서버가 호스트 llama 를 쓰는 선택지를 배제한다. (b) `.env.example` 이 `EXTERNAL_CHROMA_PORT` 처럼 예외를 명시한다 — 문서가 실제를 반영하되 fail-fast 는 셋에만 남는다.

### Hardening recommendations (비차단)

- **H1. `_env_bool` 의 빈 문자열 해석**(`""` → `True`, [llm_gateway/main.py:43](../../../services/llm_gateway/app/main.py#L43)). 지금은 콜론 형태가 막고 있어 compose 경유로 도달 불가능하지만, 이 값을 dash 로 바꾸는 사람에게는 `LLAMA_TRUST_ENV=` 가 **`True`** 가 된다. 코드 쪽에서 `if not raw:` 로 바꾸면 표기와 무관해진다.
- **H2. 새 override 파일의 사각지대.** `test_compose_exposure` 의 포트 셀과 `ExternalOverrideTest` 는 파일을 **이름으로** 읽는다. 세 번째 override 가 생기면 아무 셀도 그것을 보지 않는다 — work_log 가 M11 노트로 같은 한계를 이미 적었으므로 여기서는 재확인만 한다.

## Verdict

**조건부 합격** — B1(base `docker-compose.yml:202` 의 `LLAMA_BASE_URL` 표기를 잠그는 셀 0건)과 B2(`.env.example` 의 "기동 거부" 약속이 `LLAMA_BASE_URL` 에는 거짓)를 닫을 것.

근거가 되는 사실들:

- 축 ①의 **판단 자체는 옳다.** 코드 5자리를 직접 읽어 확인했고, 콜론 42곳 전수 대조에서 추가 위반은 **0건**이다. 구현자가 Task 2 에서 자기 실수를 잡은 것도 재현으로 확인했다(M-B 가 2셀을 문다).
- 축 ②·③의 실측 주장은 **전부 재현됐다** — rc=1 과 한국어 사유, 서비스 10 → 7, base diff 무변, `:?` 셀의 3 SUBFAILED.
- 그럼에도 **계약이 요구하는 lock 하나가 비어 있다.** 슬라이스가 명문화한 규칙("표기는 코드 읽기를 따른다")의 적용 대상은 파일이 아니라 변수이며, 같은 변수의 실제 기본 기동 경로가 안 잠겼다. 가드 공백은 "미래 위험"이 아니라 지금 비어 있는 셀이므로 `합격` 으로 넘기지 않는다.
- B2 는 문서와 동작이 갈리는 자리이고, 해소 방향이 둘 다 타당해 **오너/구현자 결정을 요한다.**

## Outstanding items

- 검증 중 뮤테이션 4회를 적용·복원했고 **작업 트리는 검증 종료 시점에 clean 이다**(`git status --short` 공백, 기준선 17 passed / 55 subtests 복귀 확인).
- 이 기록은 커밋되면 [`tests/test_docs_indexes.py`](../../../tests/test_docs_indexes.py) 의 판정 열 전수 셀을 **242 → 243 건**으로 1 올린다(subtest +1, 코드와 무관한 자리).
- backend 전수 회귀는 이 검증 범위 밖이며 별도로 진행한다. 2026-08-14 work_log 가 적어 둔 예상값 *"셀 +6 · subtest +30"* 은 **`8e57369` 이전에 쓴 값**이라 그대로 쓰면 안 된다.

## Reproduction

```bash
git status --short                    # 공백이어야 시작한다
python3 -m pytest tests/test_compose_backend_env.py tests/test_compose_exposure.py -q
#   → 17 passed / 55 subtests

# 축 ① 짝 규칙 전수 대조
grep -cE '\$\{[A-Z_]+-'  docker-compose.yml     # 10 (백엔드 3종 × 3서비스 + 주석 예시)
grep -cE '\$\{[A-Z_]+:-' docker-compose.yml     # 42

# 축 ③ 실측
docker compose -f docker-compose.yml -f docker-compose.external.yml config >/dev/null
#   → rc=1, "required variable ELASTICSEARCH_URL ... 외부 Elasticsearch 주소가 필요하다"
EMBEDDING_SERVICE_URL=http://x:1 CHROMA_HOST=x ELASTICSEARCH_URL=http://x:2 \
  docker compose -f docker-compose.yml -f docker-compose.external.yml config --services | sort
#   → admin application frontend gateway generation_worker mongo worker  (10 → 7)

# B1 실증 — 같은 diff 를 두 파일에 넣고 비교한다
sed -i 's|${LLAMA_BASE_URL:-http://host.docker.internal:9080}|${LLAMA_BASE_URL-http://host.docker.internal:9080}|' docker-compose.yml
python3 -m pytest tests/test_compose_backend_env.py tests/test_compose_exposure.py \
                 tests/test_admin_surface_separation.py -q     # → 27 passed, 0셀
git checkout -- docker-compose.yml && git status --short       # 복원 확인

sed -i 's|${LLAMA_BASE_URL:-http://llama:9080}|${LLAMA_BASE_URL-http://llama:9080}|' docker-compose.llama.yml
python3 -m pytest tests/test_compose_backend_env.py -q         # → 2 failed
git checkout -- docker-compose.llama.yml && git status --short # 복원 확인
```
