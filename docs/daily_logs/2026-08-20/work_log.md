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

### Task 6 — mypy 가드 슬라이스 구현 (브리프 §착수 조건 1~5)

**오너 지시**: *"오케이 가보자고. 진행해봐."* — 확정 직후 축 ②를 열었다.

| 단계 | 산출물 | 확인 |
|---|---|---|
| ① 개발 의존성 | [`requirements-dev.txt`](../../../requirements-dev.txt) — mypy 만 | 프로덕션 `requirements.txt` 셋에 mypy 없음을 셀이 단정 |
| ② 설정 | [`mypy.ini`](../../../mypy.ini) — `call-arg`+`misc` 만 켬 | `python3 -m mypy` → 5건 |
| ③ 5건 처리 | 아래 표 | `Success: no issues found in 193 source files` |
| ④ 가드 셀 | [`tests/test_typecheck.py`](../../../tests/test_typecheck.py) — 미설치 시 **실패**(skip 아님) | 7 passed / 3 subtests |
| ⑤ 양방향 3종 | 아래 뮤테이션 표 | 7종 전부 물었다 |

**처리한 5건** — 억제 주석은 **0건**이고, 그것을 잠그는 셀(`test_no_suppression_comment_carries_the_guard`)을 따로 뒀다.

| 파일 | 무엇을 고쳤나 |
|---|---|
| [`calibrate_character_identity_threshold.py:20`](../../../scripts/calibrate_character_identity_threshold.py#L20) | **표적 결함.** 위치 인자 → `base_url=`. **`sys.path` 부트스트랩 결손은 안 건드렸다** — 임베딩 슬라이스 결정 4=A 범위다 |
| [`writing/accept.py:134`](../../../services/application/app/writing/accept.py#L134) | `_replay()` None 검사 추가. 못 읽는 영수증 창에서 `TypeError` 대신 **`DuplicateWritingAcceptReceipt` 로 fail-closed**(호출자가 재시도로 수렴할 수 있다) |
| [`quota/lock_mongo.py:99`](../../../services/application/app/quota/lock_mongo.py#L99) | `CLAIM_ATTEMPTS=0` 이면 `raise None` → `TypeError` 였다. **이유를 말하는 `RuntimeError`** 로 |
| [`observability/kpi.py:219`](../../../services/application/app/observability/kpi.py#L219) | `_headroom_rows` 가 *"판정할 수 있는 행"* 이라는 계약을 타입에 안 적어 호출자가 `None` 을 다시 만났다. **세 값을 튜플로** 내보낸다 |
| [`phase6_gate_finding_live_smoke.py:282`](../../../scripts/phase6_gate_finding_live_smoke.py#L282) | `list[str]` 에 `None` 이 섞일 수 있었다. 문자열만 담는다 |

### Task 7 — ★ 확정 때 쓴 숫자가 틀렸다는 것이 구현 중에 드러났다

- **문제**: 설정을 넣고 처음 돌리자 **5건이 아니라 10건**이 나왔다. 새로 나온 5건이 전부
  `var-annotated`(`client = MongoClient(uri)`).
- **원인**: **오전 측정을 런타임 의존성이 없는 scratchpad venv 에서 했다.** `pymongo` 가 없으니
  `MongoClient` 가 `Any` 로 뭉개져 제네릭 지적이 아예 안 났다. 제대로 준비된 호스트에서는
  **전체가 88 이 아니라 111건/40파일**이다(`arg-type` +15 · `var-annotated` +5 · `return-value` +3).
- **처리**: 브리프에 §정정 소절을 넣고(88 → 111), `var-annotated` 를 disable 목록에 넣었다.
- **★ 그런데 좁힌 집합은 두 환경에서 똑같이 5건이었고 `call-arg` 는 양쪽 다 1건이었다.**
  **`call-arg` 는 우리 코드끼리의 호출이라 서드파티 설치 여부와 무관하게 소스에서 풀리기
  때문**이다. 그래서 **좁힌 집합은 비용 타협이 아니라 이 가드를 재현 가능하게 만드는 조건**이다 —
  넓은 설정은 의존성이 덜 깔린 머신에서 더 조용해지고, **그 침묵이 "깨끗하다" 로 읽힌다.**
  이 브리프가 막으려던 실패 모양 그대로다.
- **결정 1 은 바뀌지 않는다**: B 를 고른 근거는 88 이라는 값이 아니라 ① 좁히면 억제 없이 시작
  가능 ② A 가 못 보는 결함 둘 — 둘 다 111 에서도 그대로다.

### Task 8 — 뮤테이션 검사 (7종 · 어느 뮤테이션이 어느 셀을 물었나)

**★ 뮤테이션 전에 커밋했다**(`0b1c6f3`). 그 뒤 트리가 비어 있음을 확인하고 시작했고, 7종을
끝낸 뒤 `git status --short` 가 다시 비어 있음을 확인했다.

| # | 적용한 변경 | file:line | 재실패한 셀 |
|---|---|---|---|
| M1 | `if replay is None: raise` 제거(버그 재도입) | `accept.py:134` | `test_an_unreadable_receipt_fails_closed_instead_of_type_error` |
| M2 | 같은 자리를 **무조건 `raise`** 로(과잉교정) | `accept.py:134` | `test_a_readable_receipt_still_converges_through_the_same_branch` |
| M3 | `if conflict is None:` 블록 제거 | `lock_mongo.py:99` | `test_zero_attempts_fails_closed_with_a_stated_reason` |
| M4 | **원래 결함 복원**(`base_url=` → 위치 인자) | `calibrate_…:20` | `test_the_configured_scope_typechecks_clean` |
| M5 | `call-arg` 를 disable 목록에 추가 | `mypy.ini` | `test_a_positional_call_to_a_keyword_only_constructor_is_reported` |
| M6 | `misc` 를 disable 목록에 추가 | `mypy.ini` | 위 셀 + `test_disabling_misc_would_hide_the_target_defect` |
| M7 | `# type: ignore[call-arg]` 로 우회 | `calibrate_…:20` | `test_no_suppression_comment_carries_the_guard` |

- **M4 가 이 슬라이스의 핵심 증거다** — 한 달 넘게 아무 층도 못 잡던 그 결함을 **이제 저장소가
  스스로 잡는다.**
- **M5 가 잡는 구멍이 따로 있다**: `call-arg` 를 끄면 저장소는 **여전히 초록**이고 가드만 조용히
  사라진다. 저장소 초록 셀 하나로는 그 길이 안 막힌다.
- **M7 도 같은 종류다**: 억제 주석 한 줄이면 mypy 자체는 통과한다(실제로 통과했다). 잡은 것은
  억제 금지 셀이다.

### Task 9 — 독립 검증 조건 폐쇄 (B1·H1)

[검증 기록](../../verifications/2026-08-20/mypy_guard_slice.md) 판정은 **조건부 합격**이었다.
보고 7종(M1~M7)·전수·정정 둘·미설치 거동은 **전부 독립 재현**됐고, 조건은 **검증자 자체
공격 4종이 전부 뚫린 것**이었다.

| 벡터 | 무엇을 했나 | 왜 뚫렸나 |
|---|---|---|
| M8 | `#type:ignore[call-arg]`(**공백 없음**) | 셀이 문자열 `"type: ignore"` 를 찾았다 |
| M9 | 파일 1행 `# mypy: ignore-errors` | 같은 사각 |
| M10 | `mypy.ini` 에 퍼모듈 `ignore_errors = True` | **설정 단위 억제**를 보는 셀이 없었다 |
| M11 | `files = services, scripts` → `files = services` | **범위 축소**를 보는 셀이 없었다 |

**★ 지적의 핵심은 벡터 넷이 아니라 문언이었다** — *"억제 주석 0건이며 그것을 잠그는 셀이
따로 있다"* 가 **실제 잠금 범위보다 넓었다.** 검증자는 폐쇄안 둘을 줬다: ① 검사를 넓힌다
② **문언을 실제 범위로 좁혀 기록한다.**

- **①을 골랐다.** ②는 계약을 **약해진 채로 합의**시키는 길이고, 이 슬라이스가 막으려는
  것이 정확히 그 모양(*"green 이 말하지 않은 것"*)이다. 문언이 검사보다 넓으면 다음
  사람이 문언을 믿는다.
- **벡터를 하나씩 막지 않았다.** 넷은 같은 병의 네 얼굴이고 다섯째가 있을 것이 뻔하다
  (`exclude` · `follow_imports = skip`). **허용된 것만 남기는** 형태로 바꿨다 — 섹션은
  `[mypy]` 하나 · 키는 넷 · `files` 는 정확히 두 디렉터리.

**★ 그리고 disable 목록은 부분집합만 단정한다.** 코드를 **더하면(약화) 실패**하지만
**빼면(강화) 통과**한다. 고정 일치로 잠갔으면 **이 셀이 브리프 §후속 고려의 확장 트리거를
막았을 것**이다 — 가드를 조이다가 **개선 경로를 잠그는 것**이 새 실패 모양이다.

**재검 6종** (`5182cad` 커밋 후 트리 clean 분기, 매 회 `git status --short` 공백 확인)

| # | 뮤테이션 | 재실패한 셀 |
|---|---|---|
| M8 | 위치 인자 + `#type:ignore[call-arg]` | `test_no_suppression_comment_carries_the_guard` |
| M9 | 위치 인자 + 1행 `# mypy: ignore-errors` | 〃 |
| M10 | 위치 인자 + 퍼모듈 `ignore_errors = True` | `test_the_config_cannot_be_quietly_weakened`(신규) |
| M11 | 위치 인자 + `files = services` | 〃 |
| **M12** | `arg-type` 를 disable 목록에서 **제거**(강화) | **설정 셀 통과** · 저장소 초록 셀만 실패 = 의도대로 |
| **M13** | 억제가 아닌 평범한 주석(`# mypy 가 … type ignore 는 쓰지 않는다`) | **8 passed** — 오탐 0 |

- **M12·M13 은 검증자 목록에 없던 과잉교정 점검이다.** 억제 검사를 넓히면 **정상적인
  강화와 평범한 주석을 무는 것**이 새 실패 모양이 되므로, 좁히는 방향만 재면 반쪽이다.
- **셀은 7 → 8개**가 됐다. 주석 축과 설정 축을 한 셀에 묶지 않은 이유는 **무엇이 깨졌는지
  가 안 보이기 때문**이다.

### Task 10 — 재검 권고 반영 (H4·H5)

[조건 폐쇄 재검](../../verifications/2026-08-20/mypy_guard_closure.md)은 **합격**이었고(원 기록도
`조건부 합격` → `합격` 승격), Blocking 0 · 비차단 권고 둘이 남았다. **둘 다 적용했다**(`6268519`).
**문언만 바뀌고 단정식은 한 자도 안 바뀌어** 뮤테이션을 다시 돌리지 않았다(`8 passed` 무변).

**H4 — 비차단이지만 그냥 둘 수 없는 종류였다.** 설정 셀의 실패 메시지가
*"이 키들 밖은 전부 조용해지는 길이다"* 였는데, **거짓 보편문**이다:
`warn_unused_ignores`(가드를 **강화**한다) · `python_version` · `plugins` ·
`explicit_package_bases` 는 조용해지는 길이 아니다.

- **★ 이것은 결정 1-b②(*"실패가 원인을 안 말하면 다음 사람이 셀을 지운다"*)의 더 나쁜 형태다.**
  원인을 **안** 말하는 실패는 사람을 **멈춰 세우지만**, **틀리게** 말하는 실패는 **엉뚱한 방향으로
  멀리 보낸다.** `warn_unused_ignores` 를 넣으려던 사람이 그 메시지를 읽으면 **가드를 강화하려다
  포기한다** — 재검이 O1 로 실증한 것이 정확히 그 시나리오다.
- *바꾼 요지*: **이 검사는 트립와이어이지 억제 키 목록이 아니다.** 허용 목록 밖이면 무해한
  키도 실패하며, 요구하는 것은 *"조용해지지 말 것"* 이 아니라 **"의식적으로 추가할 것"** 이다.
  `_ALLOWED_KEYS` 주석에 **정당한 키의 예 넷과 추가가 정상 경로라는 것**을 명시했다.

**H5** — `files` 등가 단정이 **확대도 거부한다**는 사실과, 확대가 정당해지는 날(`tests/` 편입
트리거) 이 줄을 함께 고친다는 것을 메시지에 넣었다.

**★ 세 번째로 같은 병이었다.** ① 정본 산출물 문언이 잠금보다 넓었다(첫 검증 B1) ② 셀 메시지가
잠금의 성격을 틀리게 말했다(재검 H4) — **둘 다 "검사가 무엇을 보는지" 를 실제보다 넓게
주장한 것**이고, 이 슬라이스의 주제(*"green 이 말하지 않은 것"*)와 같은 축이다. I-6 의 규칙을
한 단계 넓힌다: **"X 를 막았다" 라고 쓰기 전에 X 의 표기가 몇 가지인지 세고, 그 문장을
실패 메시지에도 그대로 쓸 수 있는지 본다.**

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

**I-4. ★ 측정 환경이 측정값을 바꾼다 — 그런데 표적 클래스는 안 바뀐다.**

- *문제*: 오전에 잰 88건이 오후 호스트에서 111건이었다(Task 7).
- *원인*: 서드파티가 설치돼 있어야 그 제네릭이 풀린다. venv 에는 런타임 의존성이 없었다.
- *처리*: 브리프에 정정 소절 + `var-annotated` disable.
- *결과*: **이 저장소가 이미 아는 병의 새 얼굴이다** — [`verify-head-before-labeling-measurements`]
  · [`live-smoke-runs-working-tree-no-rebuild`] 와 같은 축. **실측 라벨에는 "어느 환경에서"
  가 붙어야 한다.** 그리고 이번엔 **좁힌 집합이 그 변동을 자동으로 흡수**했다는 것이 값이다.

**I-5. 억제 한 줄이면 mypy 는 통과한다 — 그래서 셀을 하나 더 뒀다.**

- *문제*: 뮤테이션 M7 에서 `# type: ignore[call-arg]` 를 넣자 **mypy 자체는 통과**했다.
- *원인*: 저장소 초록 셀은 "mypy 가 조용하다" 만 단정한다. 조용하게 만드는 방법이 둘이다.
- *처리*: `test_no_suppression_comment_carries_the_guard` 가 `services/`·`scripts/` 전수에서
  `type: ignore` 를 0건으로 잠근다. 같은 이유로 `test_a_positional_call_…` 이 **설정 자체**를
  잠근다(M5 에서 `call-arg` 를 꺼도 저장소는 초록이었다).
- *결과*: **"초록이다" 를 단정하는 셀과 "무엇을 보고 있다" 를 단정하는 셀은 다른 셀이다.**

**I-6. ★ 계약 문언이 검사보다 넓으면, 그 차이가 곧 다음 사람의 오해다.**

- *문제*: 산출물 문언 *"억제 주석 0건이며 그것을 잠그는 셀이 따로 있다"* 가 참인 범위는
  **정준형 `# type: ignore` 하나**뿐이었다. 독립 검증이 네 벡터로 반박했다.
- *원인*: 셀을 쓸 때 **mypy 가 억제로 받아들이는 표기를 세어 보지 않았다.** 하나를 막고
  "억제를 막았다" 라고 적었다.
- *처리*: 검사를 문언에 맞춰 넓혔다(문언을 좁히지 않았다). 브리프 §산출물도 **무엇이
  잠겼는지 표로** 다시 썼다.
- *결과*: **이 슬라이스가 저지른 실패가 이 슬라이스의 주제와 같은 모양이다** — *"green 이
  말하지 않은 것"* 을 막겠다면서 **"셀이 말하지 않은 것"** 을 만들었다. 규칙:
  **"X 를 막았다" 라고 쓰기 전에 X 의 표기가 몇 가지인지 센다.**

**I-7. 커밋 해시를 커밋하기 전에 기록에 적었다 — 그리고 틀렸다.**

- *문제*: 조건 폐쇄 커밋을 `4bd1a3d` 로 적어 문서 4곳에 넣었는데, 실제 해시는 **`5182cad`** 였다.
- *원인*: **커밋 전에 기록을 먼저 썼다.** 해시는 커밋 시점에 정해지는데 미리 적었다.
- *처리*: 커밋 직후 `git log` 와 대조해 4파일 7곳을 전수 치환했다.
- *결과*: **기록의 해시는 커밋 뒤에 적거나, 적었으면 커밋 직후 `git log` 로 대조한다.**
  잘못된 해시는 조용하다 — `git show 4bd1a3d` 가 실패할 뿐 어떤 가드도 안 문다.
  이 저장소 규율([`verification-repro-scripts-must-be-committed`] 계열)과 같은 축이다.

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

**D-2026-08-20-c. 축 ② 를 먼저 열었다 (오너 승인).**

- 확정 직후 오너 문언: *"오케이 가보자고. 진행해봐."* — 제시한 권장 순서(②→①) 그대로 열었다.
- *경계를 지킨 곳*: `calibrate_character_identity_threshold.py` 의 **`sys.path` 부트스트랩
  결손은 손대지 않았다.** 그것은 임베딩 슬라이스 결정 4=A(조립 헬퍼 이관)의 범위이고, 여기서
  같이 고치면 **①이 그 파일을 다시 만질 때 충돌한다.** 이 슬라이스는 **가드가 무는 것만** 고쳤다.
- *부수 효과*: ①의 조건(*"닫혔다는 증거는 가드 셀이지 돌려 봤다가 아니다"*)이 **이미 충족된
  상태**가 됐다 — 뮤테이션 M4 가 그 증거다.

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

### 전수 회귀 (베타, 2026-08-20)

**`2296 passed · 1 skipped · 2519 subtests` (1145초).** 남은 skip 1건은 호스트에서 구조적으로
항상 skip 되는 live Chroma 셀([`test_chroma_adapter.py:490`](../../../tests/test_chroma_adapter.py#L490))이다.

- **셀 증감이 정확히 맞는다**: 오늘 오전 착수 전 이 머신 실측이 **2287 collected** 였고,
  이 슬라이스가 더한 것이 **10셀**(typecheck 7 · accept 2 · lock 1)이라 **2297**(= 2296+1)이다.
- **subtest +3** 은 `test_typecheck.py` 의 프로덕션 requirements 3종 전수뿐이다.
- **HANDOFF 의 종전 기준선 `2284/1/2515` 는 알파·2026-08-15 값**이라 그대로 빼면 안 된다
  (그 사이 08-18·08-19 문서 작업이 있었고 이 슬라이스가 측정하지 않았다). **비교는 오늘
  이 머신의 착수 전 값(2287)과 한다.**

**★ 그리고 1회차 실행은 `12 skipped` 였다 — 그것이 이 슬라이스의 주제를 한 번 더 증명했다.**

| 회차 | 명령 | 결과 |
|---|---|---|
| 1 | `up -d` **직후** `python3 -m pytest -q` | 2285 passed · **12 skipped** |
| 2 | 같은 트리, `-rs` | skip **1건**(live Chroma)뿐 |
| 3 | 같은 트리, mongo 예열 후 | **2296 passed · 1 skipped** |

- *원인*: `docker compose -f docker-compose.test.yml up -d` 직후에는 **복제셋이 아직 준비 전**이라
  Mongo 셀 11개가 **skip 으로 빠진다**. 저장소 관례상 미기동은 실패가 아니라 skip 이다.
- *왜 위험한가*: **요약줄이 여전히 초록이다.** *"2285 passed"* 를 그대로 받아 적으면 **Mongo
  어댑터 11셀을 안 돌린 초록**이 회귀 기준선이 된다. **어제 감마의 `argon2` 33건과 정확히 같은
  모양**이고, 이 브리프가 막으려던 *"green 이 말하지 않은 것"* 그 자체다.
- *처리*: HANDOFF 함정으로 등재했다. **판정은 passed 수가 아니라 skip 수를 먼저 본다.**

> **★ 위 mypy 수치는 재현 스크립트가 아니라 명령줄이다.** 저장소 관례(검증 재현 스크립트는 커밋한다)에
> 비추면 **약한 형태**다. 다만 이 측정은 슬라이스 착수 시 **가드 셀 자체가 그 자리를 대체**하므로
> 별도 스크립트를 남기지 않았다 — **셀이 생기는 순간 이 명령줄은 셀의 설정으로 굳는다.**

## Next steps

- **다음 전수 기대값 `2297 / 1 / 2521`** — 재검 실측이 `2297/1/2520` 이었고, **재검 기록 등재가 `test_docs_indexes` 판정 열 전수 셀을 subtest +1**(코드 무관 자리).
- **다음은 임베딩 어댑터 슬라이스(축 ①) 하나다** — 축 ②는 오늘 닫혔다.
  [브리프](../../plans/embedding-adapter-slice-decisions.md) 순서: 조립 헬퍼 + 전수 가드 →
  `OpenAIEmbeddingProvider` → README env 서술 → `docker-compose.external.yml` 문단 수정.
- **①을 여는 사람이 알아야 할 것 둘**: ① `calibrate_character_identity_threshold.py` 의
  **시그니처는 이미 고쳐졌고 부트스트랩(`sys.path`)만 남았다** — 그것이 결정 4=A 헬퍼 이관의
  범위다(일부러 안 건드렸다). ② ①의 조건 *"닫혔다는 증거는 가드 셀"* 은 **이미 충족된 상태로
  시작한다**(뮤테이션 M4).
- **오너 결정 대기 브리프는 dogfood 착수 하나뿐이다.**
- 그 뒤가 리랭커 슬라이스([브리프](../../plans/reranker-slice-decisions.md) Resolved).
- **미검증 = 1커밋**(`cd1d82d`, 2026-08-16). `5182cad`·`0741a45`·`d3cc557` 은 [조건 폐쇄 재검](../../verifications/2026-08-20/mypy_guard_closure.md)이 덮었고 **첫 기록의 판정도 `합격` 으로 승격**됐다. **`6268519`(H4·H5 문언)는 단정식 무변이라 별도 검증 대상이 아니다.**
  필요한 키를 나중에 못 넣게 되는 방향의 과잉교정).
