# cd1d82d — 배포 override LLM 주소 필수화(B2 시행)와 over-strict 셀(B1 폐쇄) 독립 검증

## Subject metadata

- **날짜**: 2026-08-20 (베타)
- **요청자**: 오너 — *"작업 AI가 작업했던 과거 커밋에 대해 검증이 필요하거든? 검증하고 의심하고 또 의심해줄래? 남은 미검증 1커밋 — cd1d82d (2026-08-16)"* (구현자가 남긴 볼 만한 축 셋을 함께 지목)
- **검증자**: 이 세션 — cd1d82d 구현자가 아니며, 그 세션 컨텍스트를 잇지 않은 새 컨텍스트다(08-20 mypy 검증 세션과도 다르다).
- **대상 커밋**: `cd1d82d` (`.env.example` · `HANDOFF.md` · `docker-compose.external.yml` · `docs/daily_logs/2026-08-15/work_log.md` · `tests/test_compose_backend_env.py` — 5파일, base·`llama.yml` 무변)
- **정본 참조**: 오너 일반 규칙(2026-08-16, [D-2026-08-16-a](../../daily_logs/2026-08-16/work_log.md) §Decisions) *"① env 에 외부 API 가 있으면 그거 사용 ② 없다면 내부 LLM 모델 다운로드 시도 ③ 다운로드가 에러나거나 시도되지 못했다면 당연히 실패"* · [검증 2026-08-15](../2026-08-15/deploy_externalization_axes_1_2.md) B1·B2(이 슬라이스가 닫는다고 주장하는 조건 둘) · [`.env.example`](../../../.env.example) 배포 블록 · [`HANDOFF.md`](../../../HANDOFF.md) 기동 표
- **작업 트리 상태**: 검증은 HEAD `a19574b`에서 시작(대상 5파일은 `cd1d82d..a19574b` 무변 — `git log cd1d82d..HEAD -- <files>` 0건으로 확인). 재현 스크립트 체크포인트 `2d0ba64` 포함. 뮤테이션 사이마다 `git status --short` 공백 확인(clean-tree 분기).

## Scope

1. **★ 축①(오너 지목) — `${LLAMA_BASE_URL:?…}` 가 배포 방식에만 걸리고 base·알파로 안 샜는가.** 구현 diff · 선언 전수 · override 병합 의미론(변수 단위인가) · 자동 포함 벡터 · 가드의 유출 방향.
2. **★ 축②(오너 지목) — over-strict 셀이 B1("잠그는 셀 0건")을 정말 대신하는가.** 양방향 뮤테이션 + **구(舊) 테스트 파일로 "종전 0셀" 재현**. 세 번째 compose 파일 한계를 어떻게 볼 것인가.
3. **★ 축③(오너 지목) — 오너 규칙 ①②③ 서술·HANDOFF 기동 표가 실제 동작과 맞는가.** 세 기동 방식 전부 `docker compose config` 렌더로 실측.
4. **구현자 실측 표 4종의 재현성** — 주장한 rc·문구·주소 그대로 나오는가(환경 통제 방법 재구성 포함).
5. 전수 회귀 기준선.

## Methodology

- **환경 통제가 이 검증의 전제다**: 이 머신 `.env`(기계 로컬, 커밋 금지, 2026-07-27)이 `LLAMA_BASE_URL=http://192.168.1.22:9080` 를 제공하고 compose 는 프로젝트 디렉터리 `.env` 를 자동 로드한다. 그래서 "주소 없음" 계열 실측은 `--env-file /dev/null` 로 `.env` 를 우회하고 셸 env 로만 값을 줬다(구현자 work_log 는 이 통제를 적지 않았다 — Findings 4).
- **config 실측 10종**(P0·P0b·A2~A5·B1a·B1b·B2·B3): `docker compose [-f …] config` 렌더에서 `LLAMA_BASE_URL:` 값·gateway env 병합·`extra_hosts`·`llama` 서비스 존재·`depends_on` 을 직접 읽었다. 전 커맨드는 [repro 스크립트](repro_deploy_llama_required.sh) Part 1.
- **포커스 회귀**: `python3 -m pytest -q tests/test_compose_backend_env.py` → 기준 **12 passed / 48 subtests**.
- **뮤테이션 6종**(Part 2): 아래 diff 리터럴 그대로. clean-tree 분기 — 적용 전 `git status --short` 공백 확인, 복원은 `git checkout -- <path>` + 백업과 `diff -q` byte-identical 증명. "종전 0셀" 실증은 `git checkout cd1d82d~1 -- tests/test_compose_backend_env.py` 로 구 테스트 파일(10셀)을 꺼내 같은 base 대시화를 돌렸다(복원 `git checkout HEAD --`, 인덱스까지 되돌림).
- **전수**: `python3 -m pytest -q`(test-mongo 27020 healthy 상태).

## Findings

### 1. 축① — `:?` 는 배포 파일 한 곳에만 걸려 있고, 유출도 가드가 막는다

- **선언 전수**(grep): `LLAMA_BASE_URL` 을 선언하는 compose 파일은 정확히 셋 — [`docker-compose.yml:202`](../../../docker-compose.yml) `${LLAMA_BASE_URL:-http://host.docker.internal:9080}` · [`docker-compose.llama.yml:76`](../../../docker-compose.llama.yml) `${LLAMA_BASE_URL:-http://llama:9080}` · [`docker-compose.external.yml:117`](../../../docker-compose.external.yml) `${LLAMA_BASE_URL:?…}`. **`:?` 는 external 한 곳뿐**이고 `docker-compose.test.yml` 은 이 변수를 선언하지 않는다. cd1d82d 의 diff 파일 목록에 base·llama.yml 이 없다("한 줄도 안 건드렸다" 주장과 일치).
- **병합이 변수 단위다**(A3): 배포 구성 렌더에서 gateway env 는 `LLAMA_BASE_URL: https://ext-llm.example` 와 함께 **base 의 나머지 4키**(`LLAMA_DEFAULT_MODEL/THINKING/TIMEOUT_SECONDS/TRUST_ENV`)가 그대로 살아 있고 `extra_hosts: host.docker.internal=host-gateway` 도 생존 — external 의 맵 1키가 base 맵 5키 중 해당 키만 교체했다. "호스트 llama 를 쓰고 싶으면 명시하면 된다(base 의 extra_hosts 가 풀어 준다)" 주장의 전제가 실측으로 확인됐다(A4: `http://host.docker.internal:9080` 이 그대로 통과).
- **자동 포함 벡터 없음**: 저장소에서 `docker-compose.external.yml` 을 참조하는 실행 경로(스크립트·Makefile)는 없고 문서(HANDOFF)뿐 — `-f` 로 명시적으로 얹을 때만 발동하므로 `:?` 가 기본·알파 기동에 끼어들 경로가 없다.
- **가드 방향**(M4): 배포 규칙(`:?`)을 llama.yml 에 유출하는 뮤테이션은 기존 `InStackLlamaOverrideTest.test_an_explicit_base_url_wins_over_the_in_stack_model` 이 물었다. 즉 "안 샜는가"는 상태(diff)와 방향(가드) 둘 다 확인됐다.

### 2. 축② — 양방향 실증, 그리고 B1 "종전 0셀 → 이제 1셀" 의 양단 재현

| 뮤테이션 (적용한 diff 그대로) | file:line | 무는 셀 | 수 |
|---|---|---|---|
| M1 `:?외부 LLM API 주소가 필요하다 (OpenAI 호환 /v1/chat/completions)` → `:-http://host.docker.internal:9080` (필수화 되돌리기 = 원 결함 재현) | external.yml:117 | `ExternalOverrideTest::test_the_llm_address_is_required_because_nothing_can_fall_back` | 1 |
| M2 `:-` → `-` (base 대시화 = B1 시나리오) | docker-compose.yml:202 | `ExternalOverrideTest::test_the_base_file_still_falls_back_so_dev_machines_keep_booting` | 1 |
| M3 `:-http://…9080}` → `:?주소 필요}` (배포 규칙의 base '통일' = 과잉 교정) | docker-compose.yml:202 | 같은 over-strict 셀 | 1 |
| M4 `:-http://llama:9080` → `:?주소 필요}` (규칙 유출) | docker-compose.llama.yml:76 | `InStackLlamaOverrideTest::test_an_explicit_base_url_wins_over_the_in_stack_model` | 1 |
| M4b `:-` → `-` (llama 대시화) | docker-compose.llama.yml:76 | `InStackLlamaOverrideTest` 2셀 모두 | 2 |
| **M2′ 구(舊) 테스트 파일(`cd1d82d~1`, 10셀) × base 대시화** | docker-compose.yml:202 | **없음 — 10 passed** | **0** |

- M2(1셀)와 M2′(0셀)가 같은 base 대시화 diff 로 양단을 만들었다: **B1 이 지적한 "그 자리를 잠그는 셀 0건"이 커밋 직전 상태에서 재현됐고, 커밋 후에는 정확히 1셀(신규 over-strict 셀)이 문다.** "B1 도 함께 닫혔다" 주장은 실증으로 참.
- M4b 는 08-15 검증의 *"같은 diff 를 두 파일에 넣으면 llama.yml 에서는 2셀이 물고 base 에서는 0셀"* 전제의 전반부도 재현했다(llama 2셀).
- **세 번째 compose 파일 한계 평가**: 현재 변수 선언 3곳은 전부 잠겼다(external 1 · base 1 · llama 2 — 위 표). 한계는 셀이 **파일 경로를 하드코딩**한다는 데서 온다([`tests/test_compose_backend_env.py:246`](../../../tests/test_compose_backend_env.py) `PATH` · `:314` base 경로 · `:207` llama 경로) — 네 번째 파일이 생기면 자동 따라가지 않는다. `docker-compose.test.yml` 은 미선언이라 현재 공백이 없고, 열린 항목에 트리거("새 override 를 더하는 사람이 그때 함께 본다")가 붙어 있다. **별도 슬라이스 없이 열린 항목 유지가 정당하다고 판단한다** — 지금 일반화(`_COLON_REQUIRED`)를 미리 두면 셀 수만 늘고, 실제 파일이 생기는 순간의 계약(그 파일의 ② 가능 여부)을 아는 사람이 정의하는 것이 맞다.

### 3. 축③ — 오너 규칙 ①②③ · 기동 표가 실측과 정확히 맞는다

| 기동 표(HANDOFF) 서술 | 실측 | 일치 |
|---|---|---|
| 기본: 안 주면 `host.docker.internal:9080` — 내 호스트 llama 로 폴백 | B1a(`--env-file /dev/null`, env 무변) → rc=0, 렌더 값 그대로 | ✓ |
| 기본: 모델은 "외부 LLM(`.env` 의 `LLAMA_BASE_URL`)" | B1b(.env 활성) → `http://192.168.1.22:9080` 승리(① env 우선) | ✓ |
| 알파: 안 주면 `llama:9080` — 스택 안 llama 로 폴백 | B2 → rc=0, `http://llama:9080`, `llama` 서비스 존재, gateway `depends_on: llama: service_healthy` 머지 확인 | ✓ |
| 알파: "모델이 있어도 API 가 있으면 API 로"(①) | B3(LLAMA_BASE_URL 셸 지정) → env 값 승리 | ✓ |
| 배포: 안 주면 **기동 거부**(`:?`) — 주소 넷 다 `.env` 필수 | A2(넷 중 LLAMA 만 제외) → **rc=1**, 사유 전문 `required variable LLAMA_BASE_URL is missing a value: 외부 LLM API 주소가 필요하다 (OpenAI 호환 /v1/chat/completions)` | ✓ |
| 배포: 호스트 llama 도 명시하면 쓸 수 있다 | A4 → rc=0, 값 통과(감사 F2 정정의 재실측) | ✓ |
| (보강) 빈 값도 거부 | A5(`LLAMA_BASE_URL=`) → rc=1 — `:?` 는 미설정·빈 값 모두 거부 | ✓ |

- **③의 사슬**(알파: 모델 못 받으면 gateway 도 안 뜬다): `llama` healthcheck([`docker-compose.llama.yml:50-57`](../../../docker-compose.llama.yml), retries 60) + gateway `depends_on: llama: service_healthy`(B2 머지 렌더 확인) — **config·선언 수준에서 확인**했다. 라이브로 모델 다운로드를 실패시켜 gateway 미기동을 관통하지는 않았다(compose 조건부 기동 의미론 + 선언로 충분하다고 판단; 모델 7GB 다운로드를 강제로 깨는 실측은 비용 대비 정보가 없다).
- **"빌드가 아니라 기동에서 실패한다"**(오너 원문 "빌드 실패"의 정밀화): `llama` 는 pull 이미지(`ghcr.io/ggml-org/llama.cpp:server-cuda`, llama.yml:17)고 GGUF 를 `-hf` 인자로 **컨테이너 기동 시** 받는다(llama.yml:23-24) — 서술과 파일이 일치한다.
- **fail-fast 셋→넷 정합**: `.env.example` 배포 블록의 주소 다섯 중 넷(`EMBEDDING_SERVICE_URL`·`CHROMA_HOST`·`ELASTICSEARCH_URL`·`LLAMA_BASE_URL`)이 `:?`, `EXTERNAL_CHROMA_PORT` 만 `:-8000` 으로 예외 명시 — "종전에는 '기동을 거부한다'가 이 하나(LLAMA)에만 거짓이었다"와 표의 "주소 넷 다 .env 필수"가 모두 실제와 맞다.

### 4. 실측 표의 재현성 — 절차 미기록(→ H1)

- 구현자 실측 표의 네 결과(주소 없음 rc=1 한국어 사유 · 넷 지정 rc=0 · 호스트 llama 통과 · base/llama rc=0 무변)는 **값·문구까지 전부 재현됐다**. 다만 "주소 없음 → rc=1" 은 **환경 통제 없이는 이 머신에서 재현되지 않는다**: `.env` 가 LLAMA 를 제공하므로 P0(셸 3개 + `.env` 활성)은 rc=0(LLAMA 는 `.env` 가 채움), P0b(아무것도 안 줌)도 LLAMA 아닌 다른 필수부터 rc=1 — 어느 서비스가 먼저 걸리는지는 실행마다 달랐다(수동 실측 `application.EMBEDDING_SERVICE_URL` · 스크립트 재실행 `generation_worker.ELASTICSEARCH_URL`, compose 의 보간 순서가 고정이 아니다). `--env-file /dev/null` 로 우회해야만 LLAMA 의 `:?` 가 드러난다(A2). 구현자가 어떻게 통제했는지 work_log 에 없다 — 주장은 참이지만 절차가 없어 제3자가 "그대로" 돌리면 다른 결과를 본다. 이 기록의 Methodology 와 repro 스크립트가 그 절차를 채운다.

### 5. 문서·링크 정합

- HANDOFF 가 시행 근거로 가리키는 [2026-08-16 work_log](../../daily_logs/2026-08-16/work_log.md) `D-2026-08-16-a` 가 그 자리에 있다(커밋 당시에는 08-15 로그에 적혔고 이후 이동 — 08-15 쪽 [`work_log.md:212`](../../daily_logs/2026-08-15/work_log.md) 가 포인터로 남아 있다. 현재 링크는 유효).
- 패턴 스윕: `docs/plans/`·README·가이드에 "배포에서 LLM 주소는 선택"류의 낡은 서술 없음(plans 두 건은 일반 메커니즘·다른 게이트웨이 서술로 무관).

### 6. 전수 회귀

- **최종 트리(이 기록·인덱스 등재 완료 상태)에서 `2297 passed · 1 skipped · 2522 subtests`**(1173초). skip 1건은 구조적으로 항상 skip 되는 live Chroma 셀. passed 2297 은 직전 재검(mypy 폐쇄) 실측과 같고, subtest 2520 → 2522 는 이 기록의 인덱스 등재분이다.
- **1회차는 검증자 편집에 오염돼 5건 실패** — suite 실행 중에 카운트(246→247)를 인덱스 행보다 먼저 고치는 동안 docs-index 계열(행 없는 기록 파일 · 분포 불일치)이 걸린 것. 행과 누락 2곳([`docs/README.md`](../../README.md) 카운트 · [`README.md`](../../../README.md) 분포 문장)을 채운 뒤 재실행한 것이 위 수치다. **카운트 가드가 검증자의 등재 절차까지 검사한다는 뜻이지, 대상 슬라이스의 회귀가 아니다.**

## Issues / Risks

### Blocking — 0건

### Hardening recommendations (비차단)

- ~~**H1 — 실측 표에 환경 통제 절차가 없다**~~ **[정본 가이드로 승격 — 위 §권고 반영]**(Findings 4). 기계-로컬 `.env` 유무에 따라 같은 명령의 rc 가 뒤집히는 자리에서 "어떻게 통제했는가"가 재현성의 전부다. 원 work_log 를 고치지는 않는다(사실 오류가 아니라 절차 누락) — 이 기록 §Methodology 와 [repro 스크립트](repro_deploy_llama_required.sh)가 표준 절차로 대신한다. **교훈으로 남기는 규칙: compose 실측을 기록할 때 `.env` 상태를 함께 적는다.**
- **H2 — 네 번째 compose 파일은 자동 추적 안 됨**(이미 열린 항목, Findings 2). 트리거가 있으므로 유지. 일반화가 필요해지는 순간은 "새 override 파일이 `LLAMA_BASE_URL` 을 선언하는" 날이다.
- (관측, 조치 불요) over-strict 셀은 인용부호까지 포함한 리터럴을 단정하므로 base 를 홑따옴표로 재포맷하는 무해한 변경에도 실패한다 — fail-noisy 방향이며 이 저장소 가드 관례와 일치한다.

## Verdict

**합격** — 오너 규칙 ①②③의 배포 축(② 불가능 → ③ 강제)이 문서·compose·셀 세 층에서 일치하고, B2 시행(under-strict)과 B1 폐쇄(over-strict, 종전 0셀→1셀 양단 실증)의 가드 주장이 전부 뮤테이션으로 확인됐으며, `:?` 의 국소성(축①)도 상태와 가드 방향 모두에서 성립했다. 남는 것은 비차단 둘(H1 절차 기록 — 이 기록으로 폐쇄, H2 기존 열린 항목 유지).

## Outstanding items

- **미검증 커밋 0** — 이 기록으로 `cd1d82d` 가 닫혔다(지금까지 미검증 없음).
- H2(`_COLON_REQUIRED` 일반화)는 기존 열린 항목 그대로 — 트리거: 새 override 파일의 `LLAMA_BASE_URL` 선언.

## 권고 반영 — **H1 규칙을 정본 가이드로 올림 (2026-08-20, 구현 세션 `<이 커밋>`)**

> 이 절은 **검증자가 아니라 구현 세션이 나중에 추가한 것**이다. 위 Findings·Verdict 는
> 검증 시점 그대로 두었다.

**H1 이 남긴 규칙이 이 기록 안에만 있었다.** *"compose 실측을 기록할 때 `.env` 상태를 함께
적는다"* 는 **이 슬라이스가 아니라 저장소 전체의 절차 규칙**인데, 검증 기록은 감사 산출물이라
다음에 compose 를 재는 사람이 여기를 열 이유가 없다. **규칙이 그것을 필요로 하는 사람의
동선 밖에 있으면 없는 것과 같다.**

그래서 [`guides/verification.md`](../../guides/verification.md) 에 **§"Recording a measurement —
state the environment that made it true"** 를 신설하고, HANDOFF §함정에 한 줄을 걸었다.

**★ 올리면서 같은 병의 얼굴이 셋인 것이 드러났다** — 셋 다 2026-08-20 하루에 나왔다.

| 실측 | 환경이 바꾼 것 | 어떻게 보였나 |
|---|---|---|
| `rc=1`(주소 없음) | `.env` 가 `LLAMA_BASE_URL` 을 주는가 | 같은 명령이 `rc=0` 이거나 **다른 변수부터** 걸린다 |
| mypy 전체 에러 수 | 런타임 의존성이 설치돼 있는가 | **88 vs 111** — 서드파티 제네릭이 풀려야 난다 |
| 전수 `passed` 수 | test-mongo 가 예열됐는가 | Mongo **11셀이 조용히 skip** 되고 요약줄은 초록 |

**공통 모양: 숫자는 맞는데 라벨이 불완전하고, 그 차이가 다음 독자에게 안 보인다.** 그래서
가이드의 문장을 *"`.env` 를 적어라"* 가 아니라 **"실측이 환경에 따라 움직이면 환경이 그
실측의 일부다"** 로 일반화했다.

**부수 확인**: 커밋된 [재현 스크립트](repro_deploy_llama_required.sh)를 구현 세션이 clean 트리에서
직접 돌렸다 — **config 10종 + 뮤테이션 6종 전부 기록대로 재현**됐고(M2' 구 파일 0셀 포함),
매 뮤테이션 뒤 트리가 복원됐다. **`/tmp` 가 아니라 기록 옆에 커밋된 것이 이 확인을 가능하게
했다.**

## Reproduction

```bash
bash docs/verifications/2026-08-20/repro_deploy_llama_required.sh   # config 10종 + 뮤테이션 6종 전량
python3 -m pytest -q tests/test_compose_backend_env.py              # 12 passed / 48 subtests
```
