# 임베딩 어댑터 슬라이스(0bb73ee·c3f75c0·e49d458) — 독립 검증

## Subject metadata

- **날짜**: 2026-08-20 (베타)
- **요청자**: 오너 — *"다음작업 검증해줘. 임베딩 어댑터 슬라이스(축 ①) 완료했습니다. 커밋 4건, 트리 clean."* (구현자 보고와 함께 볼 만한 축 넷을 지목)
- **검증자**: 이 세션 — 임베딩 슬라이스 구현 세션이 아니다(같은 날 `cd1d82d` 검증을 한 세션이다 — 임베딩 구현물과는 이해 관계가 없다).
- **대상 커밋**: `0bb73ee`(조립 헬퍼+가드) · `c3f75c0`(OpenAIEmbeddingProvider) · `e49d458`(README·external override) · 기록 계열 `00a51a2`·`56ba9db`·`c1dfb8a`(감사로 덮음 — 아래 Findings 8)
- **정본 참조**: [`docs/plans/embedding-adapter-slice-decisions.md`](../../plans/embedding-adapter-slice-decisions.md)(Resolved) — 결정 1~4 확정문 · §"구현에서 정해진 것"(env 3종 표) · §산출물
- **작업 트리 상태**: 검증 시작 HEAD `00a51a2`, clean. 재현 스크립트 체크포인트 `f869b72` 포함. 뮤테이션 사이마다 `git status --short` 공백 확인.

## Scope

1. **★ 축①(지목) — AST 가드가 별칭 import 후 호출을 놓치는가.** 이름 재결합 계열 전반(별칭 import · 할당 별칭)과 반대 경계(모듈 속성 호출은 잡는가).
2. **★ 축②(지목) — 헬퍼가 env→provider 만 하는가**(결정 4=A가 그은 선).
3. **★ 축③(지목) — `_strip_version_suffix` 가 경로 안의 `v1` 을 안 건드리는가**(over-strict).
4. **★ 축④(지목) — 기본값 `native` 가 기존 배포에 정말 무영향인가** — 코드 기본값 · 셀 · compose 렌더 세 층.
5. 구현자 뮤테이션 E1~E6 같은 diff 재유도(페어링 대조 포함) · 산출물 4건 · `calibrate` 부트스트랩 실측 · 전수 `2319/1/2544` 재현.

## Methodology

- 포커스: `python3 -m pytest -q tests/test_embedding_assembly.py tests/test_embedding_provider.py` → 기준 **30 passed / 29 subtests**. compose 가드 `tests/test_compose_backend_env.py` → 12 passed(external.yml env 추가 뒤).
- **뮤테이션 9종**(적용 diff 는 [repro 스크립트](repro_embedding_assembly.sh) 그대로): clean-tree 분기, 리터럴 `count==1` 단정, 복원 `git checkout --` + status 공백 확인.
- compose 렌더: `--env-file /dev/null` 로 `.env` 중립화 + 셸 env 명시([`guides/verification.md`](../../guides/verification.md) §"Recording a measurement" — 이 슬라이스 문서화 계열이 올린 규칙을 이 검증도 따른다).
- 전수: `python3 -m pytest -q`(test-mongo 27020 healthy; 구현자가 `hello().isWritablePrimary` 예열 후 재는 절차와 동일 조건).

## Findings

### 1. 축① — 별칭 import 우회는 **실존**한다(→ 조건 B1)

| 뮤테이션 | 가드 반응 |
|---|---|
| **V1** `from …embedding import RemoteEmbeddingProvider as REP` 후 `REP(…)` | **침묵 — 16 passed** |
| **V1c** `P = RemoteEmbeddingProvider` 후 `P(…)`(할당 별칭) | **침묵 — 16 passed** |
| V1b `import …embedding as emb` 후 `emb.RemoteEmbeddingProvider(…)` | **잡음 — NoDirect 셀 실패** |
| E1 직접 회귀(원이름 `RemoteEmbeddingProvider(…)`) | 잡음 — NoDirect 셀 실패 |

- 원인은 정확히 한 줄이다: 가드가 `Call` 의 피호출자를 **원래 이름**(`func.id`/`func.attr`)과만 비교한다([`tests/test_embedding_assembly.py:63-65`](../../../tests/test_embedding_assembly.py)). 별칭으로 부르면 이름이 달라져 `{"RemoteEmbeddingProvider","OpenAIEmbeddingProvider"}` 집합을 그대로 통과한다.
- **왜 조건인가**: 계약 문언이 잠금보다 넓다 — 브리프 §산출물·확정 4=A·셀 docstring 전부 *"생성자를 직접 부르는 자리가 **하나라도** 있으면 실패"* 라고 단정하는데, 별칭 호출은 그 "하나" 이면서 실패하지 않는다. mypy 가드 검증의 M8~M11(초록 가드 + 우회 생존 → **조건부 합격**)과 같은 모양이고, `import X as Y` 는 이 저장소 스크립트에서 실제로 쓰이는 평범한 관행이라 벡터도 현실적이다. **폐쇄 형태 둘**(오너 선택): (i) 가드 강화 — 파일별 `ImportFrom`/`Import` 의 `asname→원래이름` 맵을 만들어 별칭 호출까지 단정(약 10줄; 할당 별칭 V1c는 셀 문언에 "잔여"로 명시). (ii) 문언 축소 — "하나라도"를 "원이름 직접 호출"로 좁히고 브리프·셀 docstring을 그에 맞게 고침. **(i) 을 권장** — B(목록 방식)을 기각한 논리(등재 잊으면 침묵)가 별칭에서도 같이 재발하기 때문이다.
- 가드 스캔 범위는 `services/`+`scripts/` 고정([`:44`](../../../tests/test_embedding_assembly.py)) — 새 최상위 코드 디렉터리는 자동 추적하지 않는다("세 번째 compose 파일"과 같은 계열, H2).

### 2. 축② — 헬퍼는 env→provider 만 한다 ✓

[`build_embedding_provider_from_env`](../../../services/application/app/indexing/embedding.py) 본문 전체를 읽었다: env 읽기(FORMAT/MODEL/KEY/SERVICE_URL/DIMENSIONS/TIMEOUT/TRUST_ENV)와 provider 선택·조립뿐 — 재색인 정책·차원 결정·배치가 없다. `required`·`base_url` 파라미터는 **호출자 정책**을 받는 자리다(live smoke 의 "fake 금지"·보정 스크립트의 CLI 주소)로, 정책을 헬퍼가 정하는 것이 아니다. 브리프가 그은 선 안쪽이다.

### 3. 축③ — 경로 안의 `v1` 은 안 건드린다 ✓

E5(접미 `/v1` 벗기기 제거) 재유도: `https://api.example.com/v1`·`/v1/` 두 서브테스트만 실패하고 **`/v1/proxy` 서브테스트는 통과**(2 failed = 접미 케이스만). 구현자 주장과 정확히 일치 — over-strict 방향 무영향.

### 4. 축④ — 기본값 `native` 무영향, 세 층에서 성립 ✓

- **코드**: 6자리 전부 헬퍼로 이관되면서 기본값이 기존과 동일하다(타임아웃 30.0 · trust_env False — 워커 셋은 생성자 기본값에 기대던 것이 헬퍼의 명시 False 로, 행동 무변 · 차원 1024). 유일한 행동 변화는 live smoke 의 주소 없음 에러가 `KeyError`→`ValueError`(변수명을 말하는)로 **개선**된 것과 `calibrate` 가 돌게 된 것뿐.
- **셀**: `test_the_default_is_our_own_format`(env 무설정 → RemoteEmbeddingProvider).
- **compose 렌더**(환경 통제): 배포 구성에서 새 env 무설정 → `EMBEDDING_API_FORMAT: native` · `MODEL/KEY: ""` 렌더, rc=0. `openai` 명시 → 값 통과, rc=0. 기존 배포는 env 를 하나도 안 건드려도 이전과 같은 경로다.

### 5. 구현자 뮤테이션 E1~E6 재유도 — 전부 일치

| # | 재유도 결과 | 구현자 주장 |
|---|---|---|
| E1 | NoDirect 셀 실패(내 diff 는 import 문을 남겨 **1셀** — 구현자는 import 까지 지운 diff 로 **2셀**. 셀 주장과 모순 없음: 남은 import 가 reaches-the-helper 셀을 계속 만족시킨 것) | 2셀 ✓ |
| E2b(결합: 두 생성자 동시 제거) | **13 failed** 에 `test_the_helper_itself_is_allowed_to_construct` 포함 ✓ | over-strict 셀 ✓ |
| E3(키 유무 추론) | 6 failed — `test_the_key_alone_does_not_switch_the_format` 포함 ✓ | ✓ |
| E4(모델 조용히 기본값) | `test_openai_format_without_a_model_fails_fast` 1셀 ✓ | ✓ |
| E5(접미 벗기기 제거) | 접미 2 서브테스트만, `/v1/proxy` 통과 ✓ | ✓ |
| E6(openai 쪽 차원 가드 탈락) | `test_the_dimension_guard_reaches_the_openai_provider_too` 1셀 ✓ | ✓ |

### 6. 산출물 4건

- **① 헬퍼+가드**: `tests/test_embedding_assembly.py` 16셀(NoDirect 3 · HelperBehaviour 6 · WireFormat 7) — 셀 수 주장 일치.
- **② Provider**: wire 테스트가 브리프 대조표의 **차이 넷**(경로 `/v1/embeddings` · 요청 `{"input","model"}` · 응답 `data[0].embedding` · `Authorization: Bearer`)을 각각 단정. **Protocol 세 곳 무변** — 이 슬라이스의 services diff 는 `embedding.py`·`main.py` 뿐(`semantic_matcher`·`memory_index`·`service` 미수정). 새 컨테이너 0.
- **③ README 절**: "외부 임베딩 API에 붙이기"가 재색인 절(132행) **바로 뒤**(176행) — 형식 명시·"외부 API 전환=모델 변경→재색인" 연결·비용 주의(건당 1호출)·차원 변경 경로 미검증 고지까지 브리프 의무 충족.
- **④ external override**: §"아직 안 되는 것" 임베딩 문단이 **[해소됨]** 으로 재작성(낡은 제약 서술 잔존 없음 — grep 확인), env 3종 배선 표기가 §"구현에서 정해진 것" 표와 정확히 일치(FORMAT 콜론 `${…:-native}` · MODEL/KEY 대시 `${…-}`, 서비스 셋 동일).
- **부트스트랩**: `python3 scripts/calibrate_character_identity_threshold.py --help` → **rc=0**(종전 `ModuleNotFoundError`). 브리프 조건("부트스트랩도 넣는다") 이행.

### 7. 전수 회귀

- **`2319 passed · 1 skipped · 2545 subtests`**(1183초, 이 기록 등재 후 트리에서 실측). **passed 2319 · skip 1 은 구현자 예고와 정확히 일치**하고, subtest 는 2545 = 구현자 실측 2544 + **이 기록의 인덱스 등재분 1**(판정 열 전수 셀 — 코드 무관 자리). 착수 전 `2297/1/2522` 대비 **셀 +22 · subtest +22** 도 일치(조립 16 + provider 6 신규 셀). skip 1 = live Chroma.

### 8. 기록 계열 감사(56ba9db·c1dfb8a·00a51a2)

- 구현 세션이 **이 검증자의 `cd1d82d` 기록**에 §"권고 반영"을 추가했다 — **출처("검증자가 아니라 구현 세션이 나중에 추가")를 명시하고 원 Findings·Verdict 는 그대로** 뒀다 ✓. 가이드 §"Recording a measurement" 는 H1(`.env`)·mypy 88/111·mongo 예열 세 얼굴로 일반화돼 있고 과대 없음 ✓. HANDOFF 헤더의 낡은 문구는 지우지 않고 시제로 보존 + 현재 사실 부기(이 검증자가 관찰만 남긴 것을 올바르게 닫음) ✓. 커밋된 재현 스크립트를 clean 트리에서 재실행해 "기록대로"임을 확인했다는 서술도 있다 ✓.

## Issues / Risks

### Blocking (조건)

- ~~**B1 — AST 가드의 별칭 import 우회**~~ **[닫힘 2026-08-20 `a9bca6d`]**(Findings 1). 계약 문언 *"하나라도"* 가 잠금보다 넓고, 벡터(`import … as …`)는 평범한 관행이다. 폐쇄까지 판정을 **조건부**로 둔다. 권장 처방은 가드 강화(i) — `asname` 맵으로 별칭 호출까지 단정, 할당 별칭(V1c)은 셀 문언에 잔여로 명시. 폐쇄 확인은 [repro 스크립트](repro_embedding_assembly.sh) V1 블록이 **16 passed → 가드 실패로 뒤집히는 것**으로 재현된다.

### Hardening recommendations (비차단)

- ~~**H1 — external.yml 새 env 3종의 표기를 잠그는 셀이 없다.**~~ **[닫힘]** `EMBEDDING_API_FORMAT` 의 콜론 형태는 빈 값 처리가 갈리는 자리(콜론=빈 값→native, 대시=빈 값→코드 ValueError)라 `llama.yml`·`CHROMA_PORT` 선례와 같은 형태-셀의 value 가 있다. MODEL/KEY 는 빈 기본값이라 대시/콜론이 행동 중립(선택은 표기 규칙 준수).
- ~~**H2 — 가드 스캔 범위가 경로 하드코딩**~~ **[닫힘 — 분류 강요로]**(`services`+`scripts`). 새 최상위 코드 디렉터리는 자동으로 안 따라온다 — "세 번째 compose 파일"과 같은 계열. 트리거: 새 디렉터리 추가 시 `_sources()` 함께 고친다.
- (관측) [`tests/test_embedding_assembly.py:162`](../../../tests/test_embedding_assembly.py) 의 `if __name__` 블록이 `WireFormatSelectionTest` **앞에** 있어 직접 실행(`python -m`) 시 그 클래스가 수집되지 않는다 — pytest 로 돌 때는 무영향.

## Verdict

**조건부 합격** — B1(AST 가드가 별칭 import 후 호출을 못 본다 — "하나라도" 단정과 잠금 사이의 간극 폐쇄)를 닫을 것. **[→ 승격 2026-08-20 · 판정 합격]** 폐쇄 커밋 `a9bca6d`(구현 세션)를 검증자가 독립 재검했다 — 재현 스크립트 전체 재실행으로 V1 이 가드 실패로 뒤집힘·V1b 유지·V1c 는 문언 명시 잔여 확인. 근거: [`reranker_slice.md`](reranker_slice.md) Findings 7. 나머지 전 축은 실증적으로 성립했다: 헬퍼는 env→provider 만 하고(축②), `/v1/proxy` 무영향(축③), 기본값 native 의 무영향이 코드·셀·렌더 세 층에서 확인됐으며(축④), E1~E6 전부 같은 diff 로 재현되고 산출물 4건·전수 `2319/1/2544` 예고치까지 일치한다.

## 조건 폐쇄 — **B1 닫힘 · H1·H2·관측도 함께 (2026-08-20, 구현 세션 `a9bca6d`)**

> 이 절은 **검증자가 아니라 구현 세션이 나중에 추가한 것**이다. 위 Findings·Verdict 는
> 검증 시점 그대로 두었다.

**폐쇄안 (i) 가드 강화를 골랐다.** (ii) 문언 축소는 *"하나라도"* 를 *"원이름 직접 호출"* 로
좁혀 기록을 참으로 만드는 길인데, 그것은 **계약을 약해진 채 합의**시킨다. 오늘 이 저장소가
같은 실수를 이미 두 번 했다(mypy 슬라이스의 정본 산출물 문언 B1 · 재검의 셀 실패 메시지 H4).
**세 번째로 같은 선택지가 나왔고 세 번 다 "검사를 넓힌다" 를 골랐다.**

**구현**: 파일마다 `ImportFrom` 의 `asname` 을 모아 원이름 집합에 더한다. **별칭은 파일
스코프**라 한 파일의 `as REP` 가 다른 파일의 `REP` 를 뜻하지 않으므로 맵을 파일마다 다시 만든다.

**★ 잔여를 문언에 명시했다 — 검증자 권고 그대로.** 할당 별칭(`P = RemoteEmbeddingProvider`
뒤의 `P(…)`, V1c)은 **안 잡는다.** 이름 재결합 추적은 타입체커의 일이고, **여기서 멈추는 것이
이 셀의 계약**이다. 셀 docstring 이 *"잡는 형태 셋 + 잔여 하나"* 로 다시 쓰였다 — **"하나라도"
라는 문언이 사라진 것이 이 폐쇄의 절반**이다.

**재검(구현 세션, 검증자 스크립트 그대로 — `bash docs/verifications/2026-08-20/repro_embedding_assembly.sh`)**

| 블록 | 검증 시점 | 폐쇄 후 |
|---|---|---|
| **V1** 별칭 import 후 호출 | 16 passed(침묵) | ✅ **가드 실패** — 예고된 뒤집힘 그대로 |
| **V1c** 할당 별칭 | 침묵 | 침묵(**문언에 잔여로 명시**) |
| **V1b** 모듈 속성 | 잡음 | 잡음(경계 보존) |

**비차단도 함께 닫았다**

| | 처방 | 무는 것 확인 |
|---|---|---|
| **H1** | external.yml 새 env 3종의 표기 셀([`test_compose_backend_env.py`](../../../tests/test_compose_backend_env.py) `ExternalOverrideTest`) | V4(FORMAT→대시) · V5(MODEL→콜론) 각각 subtest 재실패 |
| **H2** | 스캔 범위 하드코딩 → **분류 강요**(`_SCANNED` 또는 `_OUT_OF_SCOPE` 에 이유와 함께) | V2(새 최상위 디렉터리) 재실패 |
| H2 반대쪽 | 목록만 남고 디렉터리가 사라지면 스캔이 0파일이 되어 조용히 통과 — 그것도 잠갔다 | V3(`_SCANNED` 에 없는 이름) subtest 재실패 |
| 관측 | `if __name__` 블록을 파일 끝으로 | `PYTHONPATH=. python3 tests/test_embedding_assembly.py` → **11 → 18 tests** |

**★ 관측 항목이 가장 조용한 결함이었다.** `if __name__` 블록 뒤에 정의된 `WireFormatSelectionTest`
**7셀**이 직접 실행에서 아예 수집되지 않았다. pytest 로는 돌기 때문에 **CI 도 전수도 아무 말을
안 한다** — 이 저장소가 오늘 세 번 만난 *"green 이 말하지 않은 것"* 의 네 번째 얼굴이다.

## Outstanding items

- **조건 B1 폐쇄 대기(오너 결정: 가드 강화 (i) 권장 / 문언 축소 (ii))** — 폐쇄 커밋 뒤 재현 스크립트 V1 블록으로 재검한다(그 스크립트가 이미 그 검사를 하고 있다).
- 외부 키가 필요한 것(실호출·재색인 지연/호출 수 실측)은 브리프 트리거와 함께 유예 유지 — 이 검증의 범위 밖(구현자 서술과 동일).

## Reproduction

```bash
bash docs/verifications/2026-08-20/repro_embedding_assembly.sh   # 기준·렌더·V1/V1b/V1c·E1~E6 전량
python3 -m pytest -q tests/test_embedding_assembly.py tests/test_embedding_provider.py
```
