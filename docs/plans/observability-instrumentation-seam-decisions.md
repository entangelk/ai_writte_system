# 관측 KPI — 계측 seam 결정 브리프

상태: `Approved — 2026-07-25 (오너 결정: C 채택)` · 구현: SoT v1.7.43(seam + `analysis_extractor`), 잔여 호출부·gate 이행은 후속 증분
관련: `observability-kpi-decisions.md`(승인 D1=B·D2=C·D3=A·D4=A), SoT v1.7.42 §"LLM 파이프라인 관측(KPI)"

## Decision needed

증분 4의 **첫 호출부(`writing_gate`)는 endpoint 레벨에서 계측했는데, 남은 4개 호출부 중 그 방식이 통하는 곳이 하나도 없다.** LLM 호출을 어느 계층에서 포착할지가 남은 4 site 전부와 이미 출하한 gate 계측의 형태를 결정한다. 기존 계약(SoT L359 "모든 LLM 호출부가 공통 한 레코드")과 선례(`writing_loop_audit`은 endpoint 기록)만으로는 도출되지 않는다 — 선례가 다루지 않은 구조(1 요청 = N 호출)가 나왔기 때문이다.

### 착수 전 실측한 구조 (이 브리프가 필요해진 이유)

| site | 실제 호출 구조 | endpoint 레벨 per-call 가능? |
|---|---|---|
| `writing_gate` (완료) | `/writing/gate` → `evaluate_metered` **1회** | ✅ 가능했다 (그래서 v1.7.42가 성립) |
| `analysis_extractor` | `runner.py:137` → `extractor.py:129` 본 호출 + `:158` `_repair_once` → **비-JSON 응답 시 2회** | ❌ 두 호출이 한 endpoint 안에 숨는다 |
| `compare_judge` | `compare.py:147-151` candidate 루프 → `:228` judge → **N candidates = 최대 N회** | ❌ 레코드 1건에 N 호출이 뭉개진다 |
| `query_planner` | `main.py:1888`에서 revise-gate 서비스에 주입 → **loop 내부** 호출 | ❌ endpoint가 호출 시점을 모른다 |
| `writing_generation` | `/writing/generate` → `writing.generate()` 직접. 단 **`generate_metered`가 없고**, `_reporter`가 붙으면 내부에서 enrich LLM **2회째** 호출 | △ 부분적 |

**결정적 사실**: `analysis_extractor`의 repair 재시도는 오너가 dogfood 관찰 항목으로 명시한 지표다(HANDOFF: "`report field must be an array` 실패율 … 잦으면 repair 횟수/프롬프트 축 판단"). endpoint 레벨 계측으로는 **이 지표를 원리적으로 얻을 수 없다** — 실패한 첫 호출과 성공한 repair 호출이 하나의 성공 응답 뒤에 가려진다.

부수 사실: `LLMProvider`는 `generate(request) -> GenerationResult` **단일 메서드 Protocol**(`provider.py:31-38`)이고, provider 인스턴스 생성 지점은 `main.py`의 `_build_*_service`류에 이미 모여 있다. 즉 provider를 감싸는 선택지가 기술적으로 열려 있다.

## Options

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. endpoint/orchestrator 레벨 확장** (현 방식 연장) | 각 endpoint·runner·loop이 자기 호출을 기록. gate에서 한 것을 4번 더 반복 | 이미 출하한 gate 계측 무변 · 도메인 맥락(decision·score)에 자유롭게 접근 · 계층 오염 없음 | **repair 2회·compare N회를 per-call로 못 쪼갠다**(계약 L359 위반 또는 의미 왜곡) · 서로 다른 4곳을 각각 침습적으로 고쳐야 함 · 새 호출부는 계측을 또 잊을 수 있음 |
| **B. 도메인 서비스 내부 주입** | `WritingGateService`·`CandidateExtractor`·`CompareJudge` 등이 audit 서비스를 받아 스스로 기록 | 진짜 per-call(repair·N회 모두 정확) · 도메인 맥락 접근 가능 | **도메인 서비스가 관측 의존성을 갖는다**(계층 오염, 지금까지 이 프로젝트가 피해 온 것) · 서비스마다 격리 로직 재구현 → SoT가 "시행 지점 한 곳"으로 못박은 격리 계약이 흩어짐 · 테스트 하네스 전부 갱신 |
| **C. provider 데코레이터** (추천) | `LLMProvider`를 감싸는 `ObservedProvider`가 모든 `generate()`를 자동 포착. `call_site`는 provider 생성 시점(`main.py`)에 바인딩, `correlation_id`는 `contextvars` | **repair·N회가 자동으로 정확**(호출 1회 = 레코드 1건, 구조적으로 어긋날 수 없음) · **도메인 코드 완전 무변**(§3 수술적) · 새 호출부가 자동 계측 상속(v1.7.38 전역 handler가 값을 한 것과 같은 성질) · 격리가 한 곳 유지 | **`decision`·`gate_quality_score`를 provider가 모른다** — 도메인 산출물이라 별도 보강 필요 · gate 계측을 중복 방지 위해 손봐야 함 · `contextvars` 전파가 async 경계에서 정확한지 확인 필요 |
| **D. C + 도메인 보강 하이브리드** | C로 전 호출을 포착하고, `decision`류는 호출부가 직후에 같은 레코드를 갱신(또는 `contextvars`로 미리 주입) | C의 장점 + 파생점수(D2=C 헤드라인 KPI) 보존 | 레코드가 **append-only가 아니게 되거나**(갱신) 호출부가 여전히 관측을 알아야 함(주입) · 가장 복잡 |

## Recommendation + reason

**추천: C**(파생점수는 아래 방식으로 보존하여 D의 복잡도를 피한다).

근거는 프로젝트 현 단계에 묶여 있다:

1. **오너가 원한 지표가 A로는 불가능하다.** repair 횟수는 dogfood 관찰 항목으로 이미 명시됐다. A를 고르면 그 지표는 이 페이즈에서 영원히 못 얻고, 나중에 결국 C로 오게 된다 — 그때는 5개 site를 다시 고쳐야 한다.
2. **계약이 "per-LLM-call"이다**(SoT L359, 브리프 D1=B). A는 compare에서 N개 호출을 1레코드로 뭉개므로 계약을 지키지 못하거나, 지키려면 결국 서비스 내부로 들어간다(= B/C).
3. **도메인 코드를 안 건드린다**(§3). B는 도메인 서비스 5개 + 그 테스트 하네스 전부를 바꾸는데, C는 `main.py`의 provider 조립 지점만 바꾼다.
4. **격리 계약이 한 곳에 유지된다.** SoT v1.7.42가 "`_record_llm_call` 한 곳에서만 격리"를 못박았는데, B는 그걸 서비스 수만큼 흩뜨린다.

**파생점수(`gate_quality_score`) 처리 — C의 유일한 약점에 대한 해법**: gate는 **이미 endpoint 레벨 계측이 출하돼 있다**(v1.7.42). C를 도입하면서 gate만 현행 유지하고 데코레이터에서 제외하면, "decision류가 필요한 site는 도메인 레벨, 나머지는 provider 레벨"이라는 **두 계층 혼재**가 남는다. 이걸 피하는 방법은 데코레이터가 `contextvars`로 받은 `call_site`에 더해, 호출부가 원하면 **호출 직후 같은 correlation 안에서 파생 필드만 얹는 얇은 훅**을 두는 것이다. 이 선택은 D의 축소판이며, 결정 시 함께 확정해야 한다 — 그래서 아래 Follow-up에 명시한다.

**A를 택할 만한 반론도 실재한다**: 지금 필요한 KPI가 "호출 수·성공률·게이트 판단 정도"뿐이라면(D3=A 범위 그대로) repair·N회의 정밀도는 과잉일 수 있고, A는 이미 검증된 패턴을 4번 반복하는 것이라 슬라이스당 위험이 가장 낮다. 오너가 "지금은 거친 카운트로 충분하다"고 보면 A가 합리적이며, 그 경우 **repair 횟수는 이 페이즈의 비목표로 명시**하는 편이 정직하다.

## Follow-up considerations

- C 채택 시 **gate 계측(v1.7.42)을 어떻게 이행할지**를 같은 슬라이스에서 정해야 한다 — 중복 레코드가 나지 않도록 endpoint 기록을 제거하고 파생 필드만 훅으로 얹는 형태가 유력.
- `contextvars`가 이 코드베이스의 async 호출 경계(FastAPI → 서비스 → provider)를 넘어 정확히 전파되는지 **착수 첫 단계에서 실측**한다. 안 되면 C는 `call_site` 바인딩만 생성 시점에 하고 `correlation_id`는 request 인자로 실어야 한다.
- `outcome` 분류 위치: provider 레벨에서는 `provider_error`만 보이고 `parse_error`는 도메인 판정이다. C에서 parse 실패를 어떻게 표시할지(후속 갱신 vs 도메인 훅) 결정 필요.
- SoT v1.7.42가 명문화한 "레코드 조건 = provider가 실제로 호출된 경우"는 C에서 **자동으로 참**이 된다(데코레이터가 곧 그 경계). 계약 문장은 유지하되 근거를 갱신한다.

## Deferred / out of scope

- 대시보드(오너가 후속 페이즈로 분리 확정).
- D2-B(게이트가 직접 방출하는 품질 점수) — 이 결정과 독립.
- 증분 5 집계 API — seam 결정 이후에 착수해야 집계 대상 레코드의 밀도가 확정된다.
- embedding 호출(`indexing/`)의 계측 — `call_site` enum에 없고 LLM이 아니다. 필요하면 별도 결정.
