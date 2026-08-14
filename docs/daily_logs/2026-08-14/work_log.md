# 2026-08-14 작업 로그 (베타)

## Goals

- 어제 마감 메모의 다음 작업은 **Phase 10 끝 육안 확인**이었으나, 오너가 **방향을
  바꿔 D-10.5-d(배포 서버 외부 API 전용) 의 배선 슬라이스를 먼저** 하기로 했다.
- 오너 문언: *"컴포저에 하드코딩이면 env 로 관리할 수 있도록 변경하는 게 좋을 것
  같은데? env 의 유무에 따라 선택 빌드 가능하잖아."*
- 범위는 오너가 **①(배선 env 화 + llama 우선순위)** 로 확정. ②(profiles 로 선택
  기동) · ③(외부 임베딩 어댑터)는 이번 범위 밖.

## Completed work

### Task 1 — 백엔드 3종 + llama base URL 을 env 로 갈아끼울 수 있게 (`b6b1269`)

**착수 전 실측 — 코드는 원래 준비돼 있었다.** 어제 부채가 *"막는 것은 코드가 아니라
compose 하드코딩"* 이라고 적었는데, 그 전제를 다시 확인했다. 세 자리 전부
``if not os.environ.get(...)`` 라 **빈 문자열을 미설정으로 취급**한다:

| 자리 | 코드 | env 없을 때 |
|---|---|---|
| [main.py:1123](../../../services/application/app/main.py#L1123) | `if not base_url:` | `DeterministicFakeEmbeddingProvider()` |
| [main.py:1025](../../../services/application/app/main.py#L1025) | `if not host or not ...` | 벡터 검색기 `None` |
| [main.py:1047](../../../services/application/app/main.py#L1047) | `if not url:` | Mongo 직조회 |

즉 필요한 것은 **compose 한 파일**이고 프로덕션 코드는 0줄이다.

**★ 콜론 하나가 기능을 죽인다 — 이것이 이 슬라이스의 핵심이다.** 이 파일의 다른
40여 항목은 전부 `${VAR:-default}` 라 그쪽이 저장소 관례처럼 보인다. 그런데 여기서
그 표기를 쓰면 **끄기가 불가능해진다**:

| 문법 | 빈 값(`VAR=`) | 미설정 |
|---|---|---|
| `${VAR:-default}` | **default 로 되돌림** — 끌 수가 없다 | default |
| `${VAR-default}` | **빈 값 유지** — 코드의 fallback 에 도달 | default |

겉보기로는 올바른 수정과 구별되지 않아 **배포 서버에서야 발견된다.** 그래서 이 축을
사람 눈이 아니라 셀이 본다.

**★ `CHROMA_PORT` 는 일부러 남겼다 — 이름 충돌.** 같은 이름이 host publish
(`127.0.0.1:${CHROMA_PORT:-8523}:8000`)에서는 **호스트 포트**를 뜻하고 environment
에서는 **컨테이너 내부 포트**를 뜻한다. 그리고 [`.env.example:35`](../../../.env.example)
가 `CHROMA_PORT=8523` 을 문서화하고 있다 — 즉 **문서를 그대로 따른 사람이** 앱을
아무도 안 듣는 포트로 돌리게 된다. env 화하면 안 되는 자리이고, 외부 Chroma 는
override 파일로 붙인다.

| 파일 | 변경 |
|---|---|
| [`docker-compose.yml`](../../../docker-compose.yml) | application·worker·generation_worker 세 자리 × 3변수 = 9곳을 dash form 으로. `CHROMA_PORT` 는 사유 주석과 함께 유지 |
| [`docker-compose.llama.yml`](../../../docker-compose.llama.yml) | gateway `LLAMA_BASE_URL` env 화 |
| [`tests/test_compose_backend_env.py`](../../../tests/test_compose_backend_env.py) | 신규 가드 |

**실측(전후 지문).**

- `docker compose config` **IDENTICAL** — 기본 동작 무변
- llama override 는 **한 줄만** 변경: `http://llama:9080` → `.env` 의
  `http://192.168.1.22:9080`. 이 머신에 `.env` 가 있어 **기능이 바로 관측된다**
- 끄기: `EMBEDDING_SERVICE_URL= CHROMA_HOST= ELASTICSEARCH_URL=` → 셋 다 `""` 유지
- 외부: 주소가 세 서비스 전부에 전파(각 3건)

### Task 2 — llama 는 콜론 형태여야 한다 (`3ff94a3`)

**Task 1 이 llama 에도 dash 형태를 썼는데 그 자리에서는 틀렸다.** 기록을 갱신하며
gateway 의 읽기를 확인하다 잡았다:

```python
# services/llm_gateway/app/main.py:56, 116
base_url = os.environ.get("LLAMA_BASE_URL", DEFAULT_LLAMA_BASE_URL)
```

**기본값 *인자*라 빈 문자열이 미설정으로 취급되지 않는다** — dash 형태면
`LLAMA_BASE_URL=` 이 빈 base URL 로 그대로 전달돼 모든 호출이 실패한다. 콜론
형태라야 빈 값이 in-stack llama 로 돌아가고, 그것이 *"외부 API 가 설정되지 않음"*
의 온당한 해석이다.

**실측**: `.env` 의 외부 API 가 여전히 이김(`192.168.1.22:9080`) · `LLAMA_BASE_URL=`
→ in-stack 복귀(`http://llama:9080`).

## Issues found

**문제**: 같은 슬라이스 안에서 표기를 **통일하려는 충동**이 정확히 결함을 만든다.
`${}` 표기를 한 파일 안에서 맞추는 것은 리팩터링으로서 자연스러워 보이는데, 두
변수가 코드에서 **다르게 읽히면** 그 통일이 곧 회귀다.

**원인**: compose 표기와 코드의 읽기 방식이 **짝**인데 그 짝이 어디에도 안 적혀
있었다. Task 1 은 세 백엔드의 읽기(`if not`)만 확인하고 llama 를 같은 것으로
가정했다.

**해소**: 두 방향 다 셀로 잠갔다 — 백엔드 3종은 콜론 형태를 거부하고, llama 는
dash 형태를 거부한다. 그리고 두 클래스의 docstring 이 *왜* 반대인지를 적는다.

**남는 일반 규칙**: **compose 의 `${}` 표기는 취향이 아니라 코드가 그 변수를 읽는
방식을 따라간다.** `os.environ.get(name, default)` 면 콜론, `if not
os.environ.get(name)` 이면 dash. 두 방향 다 배포에서만 드러난다.

## Mutation testing

커밋 후 뮤테이션(§6 순서: 커밋 → 뮤테이션 → 복원 → tree 확인). **뮤테이션 사이마다
`git status --short` 를 찍었고 6회 전부 clean** 이었다(어제 배운 것).

| # | 적용한 diff | 자리 | 재실패한 셀 |
|---|---|---|---|
| M1 | `${EMBEDDING_SERVICE_URL-…}` → `"http://embedding:8002"` (하드코딩 복귀) | `docker-compose.yml:106` | `test_every_service_declaring_a_backend_takes_it_from_env` · `test_the_default_is_still_the_in_stack_service` |
| M2 | `${EMBEDDING_SERVICE_URL-…}` → `${EMBEDDING_SERVICE_URL:-…}` (콜론 회귀) | `docker-compose.yml:106`(+워커 2자리) | `test_every_service_declaring_a_backend_takes_it_from_env` · `test_the_colon_form_is_rejected_because_it_cannot_express_off` |
| M3 | `${ELASTICSEARCH_URL-http://elasticsearch:9200}` → `${ELASTICSEARCH_URL-}` (default 소실) | `docker-compose.yml:118` | `test_every_service_declaring_a_backend_takes_it_from_env` · `test_the_default_is_still_the_in_stack_service` |
| M4 | `${LLAMA_BASE_URL:-…}` → `"http://llama:9080"` (하드코딩 복귀) | `docker-compose.llama.yml:69` | `test_an_explicit_base_url_wins_over_the_in_stack_model` |
| M5 | `CHROMA_PORT: "8000"` → `${CHROMA_PORT-8000}` (이름 충돌 도입) | `docker-compose.yml:114` | `test_chroma_port_stays_hardcoded_because_the_name_is_taken` |
| M6 | `${LLAMA_BASE_URL:-…}` → `${LLAMA_BASE_URL-…}` (표기 '통일') | `docker-compose.llama.yml:69` | `test_an_empty_value_falls_back_to_the_in_stack_model` · `test_an_explicit_base_url_wins_over_the_in_stack_model` |

M1·M4 는 **원래 결함의 재현**(어제까지의 상태가 정확히 그것이다). M2·M6 은 **같은
실수의 두 방향**이고, M3·M5 는 over-strict 방향이다.

## Decisions

**D-10.5-e. 배포 서버 외부화는 세 축으로 쪼개고, 이번엔 ①만 한다.**

- *결정*: 오너가 범위 **①(배선 env 화 + llama 우선순위)** 선택.
- *근거*: 오너 제안(*"env 로 관리… env 유무에 따라 선택 빌드"*)을 실측해 보니 **축이
  셋**이었다 — ① env 로 갈아끼우기(배선) ≠ ② 안 띄우고 기동(profiles) ≠ ③ 외부
  API 로 물리기(어댑터). ①은 코드 0줄이고 **API 없이 지금 가능**하다.
- *트레이드오프*: ① 만으로는 **"선택 빌드"가 안 된다.** `depends_on: condition:
  service_healthy` 가 embedding·chroma·elasticsearch 를 강제로 기다리므로
  ([:130-135](../../../docker-compose.yml#L130) · 워커 둘도 동일), env 를 비워도
  컨테이너가 안 뜬다. 그리고 이 저장소에 `profiles:` 는 **현재 0건**이다.
- *열어 둔 문*: ②는 profiles 도입 + `depends_on` 조건부화. ③은 임베딩 계약이
  OpenAI 형식이 아니라 자체 `POST /embed` 라 어댑터가 필요하고, 트리거는 여전히
  **오너가 외부 API 를 준다**.

**D-10.5-f. 트리거 정정 — ①②는 API 없이 지금 할 수 있다.**

- *결정*: 어제 부채 전체를 *"API 받은 뒤 착수"* 로 유예했는데, **API 가 실제로
  필요한 것은 ③뿐**이다.
- *근거*: ①은 오늘 실제로 끝냈다(코드 0줄·API 0회 호출). ②도 compose 작업이다.
- *따라서*: HANDOFF 부채 항목의 트리거를 축별로 쪼개 다시 적었다.

## Next steps

- **오너 결정 대기**: ② profiles 로 선택 기동을 이어서 할지. 하면 배포 서버에서
  torch 를 끌고 오는 embedding 이미지를 빌드·기동하지 않을 수 있다.
- **여전히 대기**: Phase 10 끝 육안 확인(부채 ③ T1 · ④ `:disabled` 농도의 판단
  자리) · dogfood 착수(GATE-1) · H2(API 문서 제품명, 착수 전 오너 설명 필수).
- **전수 회귀는 안 돌렸다** — 프로덕션 코드 0줄이고 compose 를 읽는 가드
  (`test_compose_exposure` · `test_admin_surface_separation` · `test_app_import_paths`
  · `test_docs_indexes`) 35 passed / 350 subtests 로 대신했다. 새 기준선은
  **셀 +6 · subtest +30** 이 될 것이다(신규 파일 하나뿐, 예상값).
