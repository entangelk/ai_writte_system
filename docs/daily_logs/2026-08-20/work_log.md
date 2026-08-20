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

### Task 11 — `cd1d82d` 검증 권고 반영 (H1 승격) + 낡은 문구 정정

[`cd1d82d` 독립 검증](../../verifications/2026-08-20/deploy_llama_required_b1_b2.md)은 **합격 ·
Blocking 0** 이고 **미검증 커밋이 0** 이 됐다. 비차단 둘 중 손댈 것은 H1 하나였다.

**H1 — 규칙이 그것을 필요로 하는 사람의 동선 밖에 있었다.** 검증자가 남긴 규칙
*"compose 실측을 기록할 때 `.env` 상태를 함께 적는다"* 는 **이 슬라이스가 아니라 저장소
전체의 절차 규칙**인데, 검증 기록은 감사 산출물이라 **다음에 compose 를 재는 사람이 거기를
열 이유가 없다.** [`guides/verification.md`](../../guides/verification.md) 에
**§"Recording a measurement — state the environment that made it true"** 를 신설하고 HANDOFF
§함정에 한 줄을 걸었다.

**★ 올리면서 같은 병의 얼굴이 셋인 것이 드러났다 — 셋 다 오늘 하루에 나왔다.**

| 실측 | 환경이 바꾼 것 | 어떻게 보였나 |
|---|---|---|
| `rc=1`(주소 없음) | `.env` 가 `LLAMA_BASE_URL` 을 주는가 | 같은 명령이 `rc=0` 이거나 다른 변수부터 걸린다 |
| mypy 전체 에러 수 | 런타임 의존성 설치 여부 | **88 vs 111**(Task 7) |
| 전수 `passed` 수 | test-mongo 예열 여부 | Mongo **11셀 조용히 skip**, 요약줄은 초록 |

- **공통 모양: 숫자는 맞는데 라벨이 불완전하고, 그 차이가 다음 독자에게 안 보인다.** 그래서
  가이드 문장을 *"`.env` 를 적어라"* 가 아니라 **"실측이 환경에 따라 움직이면 환경이 그
  실측의 일부다"** 로 일반화했다. 셋 중 둘은 **내가 오늘 저지른 것**이다.

**부수로 고친 것 둘**

- **HANDOFF 헤더의 낡은 문구**(검증자가 관찰만 하고 남긴 것): 08-20 자가 검수 서술에
  *"`docs/verifications/` 최신이 아직 2026-08-15 다"* 가 있었다. 같은 날 저녁 기준 **08-20 기록이
  3건이고 미검증도 0** 이라 두 번 낡았다. **지우지 않고** *"그 시점엔 …였다"* 로 시제를 박고
  현재 사실을 붙였다 — 그 괄호는 **검수 당시의 서술**이라는 것이 요점이기 때문이다.
- **H2 트리거 선명화**: 종전 문언 *"새 override 를 더하는 사람이 그때 함께 본다"* 는 **무엇을
  보면 여는지를 안 말한다.** 검증자 문언대로 **"새 override 파일이 `LLAMA_BASE_URL` 을 선언하는
  날"** 로 바꾸고, **지금 선언 3곳은 전부 잠겨 있다**(base:202 · llama.yml:76 · external.yml:117 ·
  `test.yml` 미선언)는 사실을 함께 적었다.

**검증 자체를 다시 재본 것 하나**: 커밋된 [재현 스크립트](../../verifications/2026-08-20/repro_deploy_llama_required.sh)를
clean 트리에서 직접 돌렸다 — **config 10종 + 뮤테이션 6종 전부 기록대로**였고(M2' 구 파일 0셀
포함) 매 뮤테이션 뒤 트리가 복원됐다. **`/tmp` 가 아니라 기록 옆에 커밋된 것이 이 확인을
가능하게 했다.**

### Task 12 — 임베딩 어댑터 슬라이스 (축 ①) 착수: 조립 헬퍼 + 전수 가드 (결정 4=A)

**브리프 순서대로 헬퍼가 먼저다** — 새 provider 가 붙을 자리를 하나로 만들지 않으면 조립 6곳에
"어느 provider 인가" 분기가 여섯 벌 생긴다.

**착수 전 실측이 브리프보다 나빴다.** 브리프는 `EMBEDDING_DIMENSIONS` 기본값이 다섯 벌이라
적었는데, 실제로는 **네 값이 자리마다 갈려 있었다**:

| 갈린 것 | 실태 |
|---|---|
| `EMBEDDING_DIMENSIONS` 기본 `"1024"` | **5벌** |
| `EMBEDDING_TIMEOUT_SECONDS` 읽는 법 | `main.py` 는 `_env_float`, 워커 셋은 `float(os.environ.get(…, "30"))` |
| `trust_env` | **`main.py` 만 넘긴다.** 워커 셋은 생성자 기본값에 기대고 있었다 |
| 주소 없음 처리 | fake 로 내려감(4곳) · `ValueError`(live smoke) · CLI 인자(보정) **셋** |

- **헬퍼 계약**: `build_embedding_provider_from_env(*, base_url=None, required=False)`.
  `base_url` 은 보정 스크립트가 주소를 CLI 로 받기 때문이고, `required` 는 live smoke 가
  **fake 로 조용히 내려가면 안 되는 도구**이기 때문이다. **env → provider 만 한다** — 재색인
  정책·차원 결정·배치를 넣으면 그것이 두 번째 조립 지점이 된다(브리프 경고).
- **가드는 AST 다.** *"생성자를 직접 부르는 자리가 하나라도 있으면 실패"* — 등재 목록(선택지 B)을
  기각한 이유가 M5 침묵이라 목록을 만들지 않았다. **문자열이 아니라 AST 인 것은 오늘 mypy
  가드에서 배운 것**이다(표기 하나만 보면 나머지를 놓친다 — I-6).

**★ 6번 자리는 시그니처만이 아니라 부트스트랩까지 닫았다.** 브리프가 *"그 이관은 '부트스트랩도
넣는다' 를 포함해야 한다 — 그렇지 않으면 헬퍼만 옮기고 여전히 안 돈다"* 고 명시한 부분이다.
실측: 이관 전 `python3 scripts/calibrate_character_identity_threshold.py --help` 는
`ModuleNotFoundError: No module named 'services'`, 이관 후 **rc=0**.

### Task 13 — `OpenAIEmbeddingProvider` (결정 1=A)

경로·요청 키·응답 구조·인증 **넷이 달라서** `wire_format` 분기가 아니라 두 번째 클래스다.
**Protocol 세 곳 무변 · 새 컨테이너 0 · 배치 없음**(결정 2=A — 형식이 배열을 받으므로
*"어차피 받으니 지금"* 충동이 드는 자리이고, 브리프가 그것을 미리 막아 뒀다).

**차원 가드는 두 provider 가 같은 함수를 쓴다**(`_vector_from_numbers`). 결정 3=A 의 **전 기제가
그 가드**라 둘 사이에서 갈리면 그 결정이 반쪽이 된다.

### Task 14 — 브리프가 구현에 위임한 env 결정 (§후속 고려)

브리프는 *"변수를 하나 더 둘지 형식을 별도 env 로 뺄지는 구현에서 정할 문제"* 로 남겼다.
**정한 값과 근거는 [브리프 §구현에서 정해진 것](../../plans/embedding-adapter-slice-decisions.md)에
표로 적었다.** 핵심 셋:

- **형식은 `EMBEDDING_API_FORMAT` 로 명시하고 키 유무로 추론하지 않는다.** 추론이 더 짧지만
  **키를 잠깐 지우면 형식이 조용히 바뀌고**, 그 실패는 `404` 로 **원인에서 가장 먼 자리**에
  떨어진다. 기본이 `native` 라 기존 배포는 env 를 안 건드려도 그대로 돈다.
- **`EMBEDDING_MODEL_NAME` 을 재사용하지 않았다.** 그건 우리 컨테이너가 받는 **HF 모델 id** 이고
  새 변수는 **벤더 모델 이름**이다. 같은 이름을 쓰면 HF id 가 외부 API 로 나간다.
- **base 는 호스트 루트, 접미 `/v1` 하나는 벗긴다.** 벤더 문서가 `…/v1` 로 인쇄하므로 그대로
  복사해도 404 가 아니어야 한다. 경로 **안**의 `v1`(`…/v1/proxy`)은 안 건드린다(over-strict 셀).

### Task 15 — README 절(③)과 external override 문단(④)

- **README** — 어제 신설한 재색인 절 **바로 뒤**에 붙였다. 독자는 오너 조건대로 *"내부 구조를
  모르는 사람"* 이라 env 표 + **붙여넣을 수 있는 예시** + 주소가 호스트 루트라는 것 + 형식을
  명시해야 하는 이유를 적었다. **★ 외부 API 로 바꾸는 것도 "모델이 바뀌는 것" 이라는 연결이
  이 절의 값이다** — 오히려 모델이 확실히 바뀌는 경우다. 비용 주의(재색인 = 건당 1회 호출)도
  결정 2 트리거와 함께 적었다.
- **external override** — *"임베딩은 아직 진짜 외부 API 에 못 붙는다"* 문단이 이 슬라이스로
  **거짓이 됐다.** 지우지 않고 **[해소됨]** 로 표시하고 무엇이 바뀌었는지 적었다. 새 env 3종을
  세 서비스에 배선하고 `:?` 메시지도 갱신했다.
- **표기 규칙대로 갈랐다** — `EMBEDDING_API_FORMAT` 은 `get(name, DEFAULT)` 라 **콜론**,
  `API_MODEL`·`API_KEY` 는 `get(name)` + falsy 검사라 **대시**(빈 값이 빈 채로 넘어가야 코드의
  "없음" 분기에 닿는다).
- **compose 실측** — `.env` 는 `--env-file /dev/null` 로 중립화했다(**오늘 올린
  [`guides/verification.md`](../../guides/verification.md) §Recording a measurement 규칙의 첫 적용**):
  주소 없음 → `rc=1` · openai 4종 지정 → 그대로 렌더.

### Task 16 — 뮤테이션 (임베딩 축 6종)

**커밋 후 clean 트리 분기**, 매 회 `git status --short` 공백 확인.

| # | 뮤테이션 | 재실패한 셀 |
|---|---|---|
| E1 | 한 자리가 생성자 직접 호출로 되돌아감(원 결함 형태) | `test_no_site_builds_an_embedding_provider_by_hand` + `test_every_assembly_site_reaches_the_helper` subtest |
| E2b | 헬퍼 파일이 provider 를 아예 안 만듦(over-strict 축) | `test_the_helper_itself_is_allowed_to_construct` 외 4 |
| E3 | **형식을 키 유무로 추론**하게 바꿈 | `test_the_key_alone_does_not_switch_the_format` 외 |
| E4 | openai 인데 모델 없으면 조용히 기본값 | `test_openai_format_without_a_model_fails_fast` |
| E5 | 접미 `/v1` 벗기기 제거 | `test_a_pasted_vendor_base_url_…` subtest 2(**`/v1/proxy` subtest 는 통과 = over-strict 무영향**) |
| E6 | 차원 가드를 **openai 쪽만** 빼먹음 | `test_the_dimension_guard_reaches_the_openai_provider_too` |

**E3 가 이 슬라이스에서 가장 값진 뮤테이션이다** — 추론 설계는 **더 짧고 더 편해서** 다음 사람이
실제로 그렇게 고칠 만한 방향이고, 그때 깨지는 것은 코드가 아니라 **진단 가능성**이다.

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

### 전수 회귀 — 임베딩 슬라이스 뒤 (베타, 2026-08-20)

**`2319 passed · 1 skipped · 2544 subtests` (1068초).** skip 1 = live Chroma(구조적).

- **셀 +22 · subtest +22 가 전부 이 슬라이스의 신규 가드다** — 조립 16셀(신규 파일) ·
  provider +6셀.
- **검산**: 착수 전 `2297 / 1 / 2522`. 그 2522 는 재검 실측 2520 에 **검증 기록 둘**(폐쇄 재검 ·
  `cd1d82d`)이 판정 열 전수 셀을 **subtest +2** 한 값이다. `2297+22 = 2319` · `2522+22 = 2544`
  로 **양쪽 다 맞는다.**
- **★ mongo 를 `hello().isWritablePrimary` 로 예열한 뒤 돌렸다** — 오늘 오전 등재한 함정
  (`up -d` 직후면 Mongo 11셀이 조용히 skip 되고 요약줄은 초록)의 첫 적용이다. **포트가
  27020 이라 기본 포트로 물으면 `ECONNREFUSED` 다** — 예열 명령에 `--port 27020` 이 필요하다.

> **★ 위 mypy 수치는 재현 스크립트가 아니라 명령줄이다.** 저장소 관례(검증 재현 스크립트는 커밋한다)에
> 비추면 **약한 형태**다. 다만 이 측정은 슬라이스 착수 시 **가드 셀 자체가 그 자리를 대체**하므로
> 별도 스크립트를 남기지 않았다 — **셀이 생기는 순간 이 명령줄은 셀의 설정으로 굳는다.**

### 독립 검증 — cd1d82d (배포 override LLM 주소 필수화 · B1·B2 폐쇄) — 합격

(다른 세션 — 구현자가 아님. 기록 [`verifications/2026-08-20/deploy_llama_required_b1_b2.md`](../../verifications/2026-08-20/deploy_llama_required_b1_b2.md) · 재현 [`repro_deploy_llama_required.sh`](../../verifications/2026-08-20/repro_deploy_llama_required.sh) 커밋)

- **축① `:?` 국소성** — `LLAMA_BASE_URL` 선언 3곳 전수에서 `:?` 는 `docker-compose.external.yml:117` 뿐(base:202·llama:76 은 콜론 폴백, test.yml 미선언). 병합도 변수 단위로 확인(배포 렌더에 base env 4키·`extra_hosts` 생존). 알파 유출 뮤테이션(M4)은 기존 InStack 셀이 물었다.
- **축② B1 대체** — 뮤테이션 페어링(적용 diff 그대로):

  | 뮤테이션 | file:line | 무는 셀 | 수 |
  |---|---|---|---|
  | M1 `:?외부 LLM API 주소가…` → `:-http://host.docker.internal:9080` | external.yml:117 | `ExternalOverrideTest::test_the_llm_address_is_required_because_nothing_can_fall_back` | 1 |
  | M2 `:-` → `-`(base 대시화 = B1 시나리오) | docker-compose.yml:202 | `ExternalOverrideTest::test_the_base_file_still_falls_back_so_dev_machines_keep_booting` | 1 |
  | M3 `:-` → `:?`(배포 규칙 base '통일') | docker-compose.yml:202 | 같은 over-strict 셀 | 1 |
  | M4 `:-` → `:?`(알파 유출) | docker-compose.llama.yml:76 | `InStackLlamaOverrideTest::test_an_explicit_base_url_wins_over_the_in_stack_model` | 1 |
  | M4b `:-` → `-`(llama 대시화) | docker-compose.llama.yml:76 | InStack 2셀 모두 | 2 |
  | **M2′ 구(舊) 테스트 파일(`cd1d82d~1`) × M2** | docker-compose.yml:202 | **없음(10 passed)** | **0** |

  M2(1셀)·M2′(0셀)이 같은 diff 로 **B1 "종전 0셀 → 이제 1셀"** 을 양단 실증했다.
- **전수(최종 트리)** — `2297 passed · 1 skipped · 2522 subtests`(1173초). passed 는 직전 재검과 동일, subtest +2 는 이 기록의 인덱스 등재분.
- **축③** — 기동 표 3행·오너 규칙 ①②③ ↔ `docker compose config` 10종 전부 일치(rc=1 한국어 사유 전문 · 호스트 llama 명시 통과 · **빈 값도 거부** · 세 방식 폴백 주소 · `depends_on` 머지).
- **H1(비차단)** — 구현자 실측 표의 "주소 없음 rc=1" 은 **`.env` 중립화 없이 재현 불가**하다(이 머신 `.env` 가 LLAMA 를 제공 — 무통제면 LLAMA 아닌 다른 필수부터 rc=1, 어느 것이 먼저 걸리는지는 실행마다 다르다). 재현 스크립트가 표준 절차(`--env-file /dev/null` + 셸 3개)로 고정했다. **남기는 규칙: compose 실측을 기록할 때 `.env` 상태를 함께 적는다.**
- **H2(비차단, 기존 열린 항목 유지)** — 네 번째 compose 파일은 가드가 자동 추적하지 않는다(셀이 파일 경로를 하드코딩). 트리거: 새 override 의 `LLAMA_BASE_URL` 선언.
- **★ 전수 1회차가 내 편집을 잡았다** — 1회차(등재 완료 전 트리) `2294/5failed/1/2520` 의 실패 5건이 전부 docs-index 계열이었다: 카운트(246→247)를 인덱스 행보다 먼저 고치는 동안 **행 없는 기록 파일·분포 불일치**가 그대로 걸린 것. 행+누락 2곳(docs/README.md 카운트·README 분포 문장)을 채우니 `test_docs_indexes` 13 passed/257 subtests. **카운트 가드가 검증자의 등재 절차까지 검사한다.**

## Next steps

- **다음은 리랭커 슬라이스다.** [브리프](../../plans/reranker-slice-decisions.md) Resolved(08-18)이고
  **1=A(임베딩 어댑터 먼저)의 선행 조건이 오늘 충족됐다.** 확정값: 2=A(seam+외부 먼저 · 로컬
  기본 no-op) · 3=A(데코레이터+조립 가드) · 4=A+C **단 평가 하네스 선작성**.
  **★ 그 하네스의 첫 고객이 임베딩일 수 있다**(임베딩 브리프 §후속 고려).
- **임베딩 축에서 열린 채 남은 것 둘 — 둘 다 트리거가 붙어 있다.**
  ① **배치(`embed_many`)** — 트리거는 **재색인 지연·호출 수 실측**이고 그 실측은 **외부 키가
  있어야** 가능하다. ② **차원까지 바뀔 때의 컬렉션 재생성 절차** — 트리거는 **실제로 차원이
  다른 모델을 조달할 때**.
- **오너 결정 대기 브리프는 dogfood 하나뿐이다.**
- **미검증 = 3커밋**(`0bb73ee`·`c3f75c0`·`e49d458`). 볼 만한 축 넷: ① 조립 가드가 **AST 라서**
  놓치는 형태(별칭 import 후 호출 등) ② 헬퍼가 **env → provider 만** 하는가 ③
  `_strip_version_suffix` 가 **경로 안의 `v1`** 을 안 건드리는가 ④ `EMBEDDING_API_FORMAT` 기본이
  `native` 라 **기존 배포가 정말 무영향**인가. **외부 키가 필요한 것은 실호출과 재색인 실측뿐**이다.
