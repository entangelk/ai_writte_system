# 2026-08-20 작업 로그 (베타)

> **머신은 베타다.** 어제(감마) 로그의 `argon2` 결손 서술은 이 머신의 사실이 아니다 — 아래 Task 1 이
> 그것을 실측으로 뒤집는다.

## Goals

- 오너 질문 둘에 실측으로 답한다: ① 타입체커(그리고 pydantic)로 시그니처 부패를 막을 수 있는가
  ② 감마의 `argon2` 결손이 컨테이너에도 있는가.
- 그 결과로 [`script-rot-guard-decisions.md`](../../plans/script-rot-guard-decisions.md) 를 확정한다.
- **코드는 열지 않는다** — 이 슬라이스의 구현은 확정 다음이다.

## Completed work

### Task 1 — 오너 질문 확인: "도커 내부에서 한 게 아닌가? 결손 의존이 생길 수가 있나?"

- **컨테이너에는 있다.** `docker exec` 로 직접 확인 — `ai_writte_system-worker-1` · `ai_writte_system-admin-1`
  둘 다 `argon2 23.1.0 / python 3.12.13`.
- **그런데 백엔드 테스트는 컨테이너에서 안 돈다.** [`HANDOFF.md:112`](../../../HANDOFF.md#L112) 이
  *"`docker compose -f docker-compose.test.yml up -d` 후 `python3 -m pytest -q`"* 로 적는다 —
  **도커는 test-mongo 만 제공하고 pytest 는 호스트에서 돈다.** 그래서 이미지가 멀쩡해도 호스트에
  `argon2-cffi` 가 없으면 33건이 수집 실패한다. **감마 관측은 진짜였고, 저장소가 아니라 그 머신의
  선행조건 미이행이었다.**
- **베타 실측**: `python3 -m pytest tests/ --collect-only -q` → **2287 collected, errors 0.**
- **그리고 그 선행조건은 이미 문서에 있다** — [`HANDOFF.md:75`](../../../HANDOFF.md#L75) 회귀 기준선
  줄 끝: *"backend 는 `argon2-cffi`, frontend 는 `npm install` 이 선행돼야 한다."*
- **효과**: 결정 2 를 **D(무시)** 로 닫을 근거가 됐다. *"무시해도 된다"* 가 아니라 **애초에 저장소
  결함이 아니었다** 가 근거다.

### Task 2 — 타입체커 실측 (브리프가 "재지 못했다" 고 적은 그 숫자)

mypy 2.3.1 을 **scratchpad venv 에 설치**해서 쟀다 — 시스템 파이썬도 저장소 환경도 안 건드렸다.
`--ignore-missing-imports` 외에는 기본 설정이다.

| 범위 | 에러 | 파일 | 검사한 파일 | 시간 |
|---|---|---|---|---|
| `services` + `scripts` | **88** | 29 | 193 | 8.6초 |
| `tests` | **219** | 55 | 144 | 1.9초 |

- 코드 쪽 88건의 코드 분포: `arg-type` 50 · `operator` 11 · `attr-defined` 10 · `union-attr` 4 ·
  `return-value` 4 · `misc` 4 · `assignment` 3 · `type-var` 1 · **`call-arg` 1**.
- **`call-arg` 1건 = 그 파일 그 줄이다.** 어제 AST 스윕이 낸 *"진짜 적중 1건"* 과 **독립적인 방법으로
  같은 값에 도달했다.** 두 방법이 교차 확인된 셈이다.
- **좁히면 5건이다.** `call-arg` + `misc` 만 켜면 `services`+`scripts` 전체에서 5건 —
  그 버그 1 · 진짜 잠재 결함 2(Task 3) · 노이즈 2.
- **효과**: 브리프가 B 를 유예한 유일한 근거(*"초기 에러 수를 아무도 모른다"*)가 사라졌다.

### Task 3 — mypy 가 찾은 진짜 잠재 결함 둘 (AST 가드로는 원리적으로 안 보이는 것)

| 위치 | 무엇 | 왜 결함인가 |
|---|---|---|
| [`writing/accept.py:134`](../../../services/application/app/writing/accept.py#L134) | `_replay()` 반환이 `tuple[SaveDraftResult, Draft] \| None` 인데 **None 체크 없이 언팩** | **같은 함수 [`:106`](../../../services/application/app/writing/accept.py#L106) 은 `if replay is not None:` 으로 제대로 방어한다.** `DuplicateWritingAcceptReceipt` 를 잡은 뒤 영수증이 아직 안 보이는 레이스에서 fail-closed 대신 `TypeError: cannot unpack non-sequence NoneType` |
| [`quota/lock_mongo.py:99`](../../../services/application/app/quota/lock_mongo.py#L99) | [`:75`](../../../services/application/app/quota/lock_mongo.py#L75) 가 `conflict: DuplicateKeyError \| None = None`, `:99` 가 `raise conflict` | 루프가 `:86` 에 한 번도 안 닿고 빠지면 의도한 fail-closed 대신 `TypeError` |

- **둘 다 "테스트가 부르지 않는 분기" 다** — 어제 그 스크립트와 **정확히 같은 병**이고, 위치 인자
  arity 만 보는 AST 가드(선택지 A)는 둘 다 못 본다.
- **이것이 결정 1 을 A → B 로 넘긴 결정적 근거다.** 브리프는 A 를 *"실증된 유일한 검출기"* 라 적었는데,
  같은 기준을 B 에 적용하니 **B 가 실증한 것이 더 많았다.**
- **고치지 않았다** — 확정만 하기로 한 범위 밖이고, 둘 다 **회귀 셀이 먼저 필요하다**(재현 셀 0건).
  브리프 §유예 항목에 등재했다.

### Task 4 — pydantic 으로 되는가 (오너 질문)

**안 된다. 이유 셋을 실측으로 적었다.**

1. **런타임 검증기다.** 이 결함의 정의가 *"그 줄이 한 번도 실행되지 않았다"* 이므로 원리적으로 침묵한다.
2. **경계에만 있다.** `BaseModel` 98개 중 **94개**가 [`api/models.py`](../../../services/application/app/api/models.py)(73)
   · [`writing/http_models.py`](../../../services/application/app/writing/http_models.py)(21) 로 HTTP 요청/응답
   모델이다. `RemoteEmbeddingProvider` 같은 도메인 클래스는 평범한 클래스라 시야 밖이다.
3. `@validate_call` 을 붙여도 (2)를 (1)로 옮길 뿐이다.

### Task 5 — 브리프 확정 + 인덱스 갱신

- [`docs/plans/script-rot-guard-decisions.md`](../../plans/script-rot-guard-decisions.md) — **Resolved.**
  헤더 확정값 요약 · §"배경 추가 — 2026-08-20 실측" 신설 · 결정 1 ★확정 · **결정 1-b 신설**(확정 과정에서
  드러난 갈래) · 결정 2 ★확정 · 권고 요약 → **확정 요약**(초판 대비 무엇이 달라졌는지 표 포함) ·
  §승인 전 보류 해제 · **§착수 조건 신설**.
- **초판 추천을 지우지 않고 `추천(초판 · 2026-08-19 · 실측으로 뒤집혔다)` 로 라벨만 붙여 남겼다** —
  저장소 관례(지우지 말고 압축)이고, **무엇이 왜 뒤집혔는지가 이 문서의 값이다.**
- [`docs/plans/README.md:224`](../../plans/README.md) 행을 `오너 결정 대기` → `Resolved(2026-08-20)` 로.

## Issues found

**I-1. 브리프가 자기 유예 근거를 재 보지 않고 "미지수" 로 적었다.**

- *문제*: 초판 결정 1 의 ③ 이 B 를 유예하며 *"초기 에러 수를 모르는 채로 여는 문이고, 그것을 재려면
  먼저 설치가 필요하다"* 라 적었다.
- *원인*: **재는 비용 자체를 재지 않았다.** 실제로는 venv 하나에 8.6초짜리 측정이었다.
- *처리*: 브리프에 그 지점을 명시하고, 2026-08-16 이 남긴 *"비용을 과대하게 적으면 오너가 잘못된
  저울로 고른다"* 의 **세 번째 사례**로 등재했다.
- *결과*: **모르는 것을 근거로 유예할 때는 "무엇을 재면 이 유예가 풀리는가" 가 곧 트리거다** —
  [`deferred-items-need-triggers`] 규율의 이 축 적용이다.

**I-2. ★ `--disable-error-code misc` 를 넣으면 표적 결함이 조용해진다.**

- *문제*: 좁힌 설정을 만들다 `services scripts` 전체가 `Success: no issues found` 로 나왔다 —
  같은 파일 단독 실행에서는 나오던 `[call-arg]` 가 사라졌다.
- *원인*: 캐시가 아니었다(`--cache-dir=/dev/null` 로 재현). 에러 코드 8종을 하나씩 끄며 bisect 한
  결과 **`misc` 를 끄는 순간에만** `scripts/calibrate_…:20` 의 `[call-arg]` 가 사라진다(나머지 7종은
  무영향).
- *처리*: 브리프에 **함정으로 박고**, 착수 조건에 *"`misc` off 시 통과해 버리는 것을 잠그는 셀"* 을
  **세 번째 양방향 가드**로 넣었다.
- *결과*: 이걸 못 봤으면 **가드를 세운 그날 표적 결함이 통과하는 설정을 커밋할 뻔했다.**

**I-3. 측정 도구가 저장소를 오염시킬 뻔했다 — venv 로 격리했다.**

- mypy 는 이 저장소에 없는 새 의존성이다. 시스템 파이썬에 넣으면 *"이 머신에서만 참인 상태"* 가
  하나 더 생긴다(HANDOFF §머신-로컬 관측 규율).
- scratchpad venv 에만 설치했고, **`git status --short` 가 측정 전후 모두 비어 있었다.**

## Decisions

**D-2026-08-20-a. 스크립트 부패 가드 브리프 확정 — 1=B · 1-b=가 · 2=D.**

| 결정 | 확정값 | 근거 (한 줄) |
|---|---|---|
| 1. 부패 방지 | **B** — mypy 단독(`call-arg`+`misc` 로 시작) | 좁히면 초기 에러 **5건**(실측) · **A 가 못 보는 잠재 결함 둘을 실제로 찾아냈다** · 오탐 0 |
| 1-b. mypy 배치 | **가** — `requirements-dev.txt` 신설 · 미설치 시 셀 **실패** | CI 가 없어 **pytest 안에 있어야 돈다** · skip 은 M5 침묵 |
| 2. 감마 green | **D** — 무시 | 결손이 아니라 **선행조건 미이행**이었다 · 그 선행조건은 이미 HANDOFF 에 있다 |

- **오너 문언**: *"1은 네 결정대로 가고 의존성이야 뭐 넣으면 되는거니까. 하나정도는 괜찮아.
  2번은 당연히 '가'로 가야지."* · (앞 턴) *"지금은 베타머신이야. 그래서 결정2는 일단 패스 D로."*
- **오너가 처음 제안한 것은 A+B 였다** — *"1을 A 그리고 B까지 얹어서 최대한 정확하게 하는게 맞지
  않을까?"* **분석 결과 그 방향이 오히려 정확도를 떨어뜨린다는 것을 대조로 제시했고**(B 가 A 를
  진부분집합으로 포함 · A 쪽만 오탐 허용목록을 갖는데 그 목록이 브리프 자신이 지목한 M5 침묵 함정),
  오너가 **B 단독**으로 정정했다. **"가드를 하나 더 얹으면 더 안전하다" 가 항상 참이 아니다** —
  침묵 면적이 느는 쪽이면 반대다.
- *A 는 기각이 아니라 불필요*: mypy 를 못 쓰는 환경이 생기면 그때 다시 볼 값이 있다.
- *결정 1-b 는 초판 브리프에 없던 갈래다.* 확정 과정에서 *"mypy 를 어디에 두는가"* 가 드러났고,
  **선택지 표를 만들어 오너에게 낸 뒤 확정**했다 — 브리프에 없던 결정을 구현자가 조용히 고르지
  않는다.

**D-2026-08-20-b. 감마의 33건 서술에 머신-로컬 라벨을 붙인다.**

- 브리프 §"감마에서 green 은 반쪽이다" 가 **저장소 사실처럼 읽힌다.** 결정 2=D 로 그 축을 닫되,
  문단은 지우지 않고 **각주로 라벨을 달았다**(베타에서는 `2287 collected · errors 0`).
- *왜 지우지 않는가*: 감마로 다시 갈 때 **같은 관측이 또 나온다.** 그때 필요한 것은 문단의 부재가
  아니라 **"이건 선행조건 미이행이다" 라는 판정**이다.

## Verification

- `python3 -m pytest tests/test_docs_indexes.py -q` → **13 passed** (아래 실행 기록).
  잠그는 것 둘: ① 브리프가 인덱스에 등재돼 있는가 ② 인덱스·README 의 `.md` 링크가 실제 파일을
  가리키는가.
- **`argon2` 컨테이너 확인**: `docker exec ai_writte_system-worker-1 python -c "import argon2"` ·
  `admin-1` 동일 → 둘 다 `23.1.0 / py 3.12.13`.
- **베타 수집**: `python3 -m pytest tests/ --collect-only -q` → `2287 collected in 41.13s`, errors 0.
- **mypy 측정 재현** (scratchpad venv, mypy 2.3.1):
  - `MYPYPATH=. mypy --ignore-missing-imports services scripts` → `Found 88 errors in 29 files (checked 193 source files)`
  - `mypy --ignore-missing-imports --explicit-package-bases tests` → `Found 219 errors in 55 files (checked 144 source files)`
  - 좁힘(위 둘에서 `arg-type`·`operator`·`attr-defined`·`union-attr`·`return-value`·`assignment`·`type-var` 를 끄고 `call-arg`·`misc` 유지)
    → `Found 5 errors in 5 files (checked 193 source files)`
  - **`misc` 까지 끄면** → `Success: no issues found in 193 source files` (I-2)
- **코드 0줄** — `git diff --stat` 이 브리프 · `docs/plans/README.md` · `HANDOFF.md` · 이 로그뿐임을
  확인했다.

> **★ 위 mypy 수치는 재현 스크립트가 아니라 명령줄이다.** 저장소 관례(검증 재현 스크립트는 커밋한다)에
> 비추면 **약한 형태**다. 다만 이 측정은 슬라이스 착수 시 **가드 셀 자체가 그 자리를 대체**하므로
> 별도 스크립트를 남기지 않았다 — **셀이 생기는 순간 이 명령줄은 셀의 설정으로 굳는다.**

## Next steps

- **다음은 구현이다.** 두 축이 있고 **서로 순서를 다투지 않는다**:
  - **축 ① 임베딩 어댑터 슬라이스** — [브리프](../../plans/embedding-adapter-slice-decisions.md)
    Resolved(08-19). 순서: 조립 헬퍼 + 전수 가드 → `OpenAIEmbeddingProvider` → README env 서술 →
    `docker-compose.external.yml` 문단 수정.
  - **축 ② mypy 가드 슬라이스** — 이 브리프 §착수 조건 5단계.
- **권장 순서는 ② → ①** 이다. ②의 5건 처리에 **①이 닫기로 한 그 스크립트가 포함**되므로, 가드를
  먼저 세우면 ①의 *"닫혔다는 증거는 가드 셀이지 돌려 봤다가 아니다"* 조건이 **이미 충족된 상태로**
  시작한다. 반대 순서면 같은 파일을 두 번 만진다.
- **오너 결정 대기 브리프는 이제 dogfood 착수 하나다.**
- 그 뒤가 리랭커 슬라이스([브리프](../../plans/reranker-slice-decisions.md) Resolved).
