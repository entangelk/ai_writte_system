# 관측 KPI 증분 5 — 집계 API read-out 결정 브리프

상태: `Approved — 2026-07-26 (오너 결정: D1=A · D2=A)` · 구현: SoT v1.7.48
관련: `observability-kpi-decisions.md`(승인 D3=A 범위 · D4=A read API), `observability-site-mapping-decisions.md`(승인, 증분 C), SoT v1.7.47 §"LLM 파이프라인 관측(KPI)"

## Decision needed

증분 5는 `GET /projects/{id}/observability/kpi` 하나를 여는 슬라이스다. endpoint 자체와 KPI 범위는
**이미 승인돼 있다**(D4=A · D3=A). 착수 전 실측에서 그 승인 범위를 그대로 구현하려 할 때 두 가지가
스펙만으로 도출되지 않는다.

1. **D3=A가 나열한 KPI 중 두 항목이 이 read-model 밖에 있다.** D3=A는 "기본 카운트(생성·게이트평가·
   재시도·**승격**) + **루프 미수렴율** + 파생점수"인데, 루프 미수렴율은 `writing_loop_audits`에 있고
   그 영속은 **opt-in이며 기본이 off**다(`main.py:4090`, `WRITING_LOOP_AUDIT_DEFAULT` 기본 False).
   승격은 애초에 LLM 호출이 아니라 memory 도메인 이벤트다.
2. **응답 형태는 공개 계약이다.** 브리프 Follow-up이 "집계 API는 후속 대시보드가 소비할 것을 전제로
   필드를 안정적으로 명명"이라고만 지시하고 형태는 정하지 않았다. `responses=`/`response_model`이
   `openapi.json`·`schema.d.ts`로 흘러가므로 나중에 바꾸면 프론트 생성물이 함께 깨진다.

### 실측 — per-call 레코드만으로 채워지는 항목과 아닌 항목

| D3=A 항목 | `llm_call_audits`만으로 가능? | 근거 |
|---|---|---|
| 호출 카운트(site별·생성·게이트평가) | ✅ | `call_site` 카운트 |
| 성공/실패율 | ✅ | `outcome` 분포 |
| 재시도(repair) 빈도 | ✅ | **site 고정** `correlation_id`당 레코드 수(SoT v1.7.47) |
| 토큰 합계·평균 | ✅ | `success`+`parse_error`만(SoT v1.7.42) |
| 지연 | ✅ | `latency_ms` |
| 게이트 파생점수 | ✅ (커버리지 주의) | loop 내부 gate 레코드에는 없음(SoT v1.7.47 알려진 공백) |
| **루프 미수렴율** | ❌ | `writing_loop_audits`(opt-in, 기본 off) |
| **승격 카운트** | ❌ | memory 도메인. LLM 호출 레코드가 아니다 |

## D1 — 이번 증분의 집계 데이터 소스

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. per-call + loop 미수렴율(분모 동반)** (추천) | `llm_call_audits` 전 항목 + `writing_loop_audits`에서 미수렴율. 단 **`loop_runs_considered`(분모)를 응답에 함께** 실어 0을 "데이터 없음"으로 읽게 한다 | D3=A 승인 범위를 그대로 이행 · loop audit service는 이미 `create_app`에 조립돼 있어 비용이 작다 · **0의 의미를 페이로드가 스스로 설명**한다(extractor `parse_error`=0을 "구조적 사실"로 적은 선례와 같은 패턴) | 기본 배포에서 분모가 0이라 이 지표만 비어 보인다(다만 그 사실이 응답에 드러난다) |
| B. per-call만 | 루프 미수렴율은 후속 증분 | 항상 값이 찍히는 지표만 노출 · 표면 최소 | D3=A 승인 범위를 **말없이 좁힌다**. 오너가 승인한 항목이 사라지는데 그 사실이 어디에도 안 남는다 |
| C. A + 승격 카운트 | memory 승격까지 합산 | D3=A 문구 완전 이행 | 승격은 LLM 호출이 아니라 **이 read-model의 정의를 넘는다**(D1=B "per-LLM-call 감사"). 세 번째 저장소를 이 endpoint에 묶는다 |

## D2 — 응답 형태 (공개 계약)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 요약 + site 배열** (추천) | `{project_id, totals{...}, sites:[{call_site, ...}], gate{...}, loop{...}}` | **`call_site` 리터럴이 늘어도 스키마 무변**(새 멤버는 배열의 새 행이지 새 필드가 아니다) · 대시보드가 site를 순회하면 됨 · 타입 생성물이 안정 | 특정 site를 찍어 읽으려면 클라이언트가 찾아야 함 |
| B. site를 키로 하는 map | `{sites:{writing_gate:{...}, …}}` | 특정 site 접근이 직접적 | 리터럴이 **스키마 키**가 되어 site를 추가할 때마다 생성 타입이 바뀐다 — 증분 C가 리터럴 8종으로 늘린 직후라 정확히 나쁜 방향 |
| C. flat metric 목록 | `{metrics:[{name, value}]}` | 대시보드 범용 | 타입이 사실상 사라진다(모두 `{string, number}`) · 계약이 잠기지 않아 H3 전수 가드의 의미가 옅어짐 |

권장 A의 구체 형태(필드명은 대시보드가 소비할 안정 이름):

```json
{
  "project_id": "project-1",
  "totals": {"calls": 42, "success": 39, "provider_error": 2, "parse_error": 1,
             "total_tokens": 8123, "tokens_counted_from": 40},
  "sites": [{"call_site": "writing_gate", "calls": 12, "success": 11,
             "provider_error": 1, "parse_error": 0, "total_tokens": 2400,
             "tokens_counted_from": 11, "avg_latency_ms": 830,
             "repair_correlations": 1, "correlations": 10}],
  "gate": {"scored_calls": 10, "avg_quality_score": 0.72},
  "loop": {"runs_considered": 0, "non_convergence_rate": null}
}
```

- `tokens_counted_from` = 토큰 집계의 **분모**(`success`+`parse_error` 행 수). SoT가 `provider_error`를
  분모에서 빼라고 못박았으므로 그 사실이 응답에서 보여야 오독이 없다.
- `repair_correlations` / `correlations` = "레코드가 2건 이상인 `correlation_id` 수 / 전체" —
  SoT의 **site 고정** 규칙을 형태로 강제한다(site 행 안에만 존재).
  > **정정(2026-07-26, 구현 중)**: 이 필드는 **`multi_call_correlations`로 출하됐다.** 착수 후
  > 확인한 사실 — writing loop은 gate를 **설계상 최대 3회** 부르므로(`WRITING_LOOP_MAX_GATE_EVALUATIONS`
  > 기본 3) loop site에서 "레코드 2건 이상 = repair"는 거짓이다. 값·규칙은 위 설명 그대로이고
  > **이름만** 잰 사실을 말하도록 바꿨다. 위 예시 JSON은 오너가 무엇을 보고 D2=A를 골랐는지의
  > 기록이라 소급 수정하지 않는다(과거 결정 기록 불변 원칙). canonical은 SoT 본문이다.
- `gate.scored_calls` = 파생점수가 실제로 있는 호출 수. loop 내부 gate 호출은 여기서 빠지므로
  (SoT 알려진 공백) 평균의 분모를 함께 낸다.
- `loop.non_convergence_rate`는 분모 0일 때 **`null`**(0.0이 아니다) — "미수렴이 없었다"와
  "잰 적이 없다"는 다른 사실이다.

## Recommendation + reason

**D1=A · D2=A.** 근거는 이 프로젝트가 이미 비싸게 배운 두 가지다:

1. **0의 의미를 페이로드가 스스로 설명해야 한다.** v1.7.46이 extractor의 `parse_error`=0을 "구조적
   사실이지 데이터 부족이 아니다"라고 본문에 적어야 했던 이유가 그대로 적용된다. 분모를 함께 내면
   다음 소비자(대시보드·오너)가 계약 두 조항을 연결하지 않아도 값을 옳게 읽는다.
2. **리터럴을 스키마 키로 쓰지 않는다.** 증분 C가 `call_site`를 5→8로 늘렸고 앞으로도 는다
   (Phase 7). map 형태를 고르면 site 추가가 매번 프론트 타입 변경이 된다.

## Follow-up considerations

- 이 응답은 후속 대시보드 페이즈의 입력이다. 필드 추가는 additive로 가능하지만 **이름 변경은 아니므로**
  지금 이름을 신중히 고른다.
- 캘리브레이션(D3-C, accept/edit 대조)이 붙으면 `gate` 블록에 additive로 들어갈 자리가 있다.
- `loop` 블록은 `WRITING_LOOP_AUDIT_DEFAULT`를 켜면 즉시 채워진다 — 코드 변경 없이 데이터만 생긴다.

## Deferred / out of scope

- **시간 창·페이지네이션**: 선례(`GET …/writing/loop-audits`)가 프로젝트 전량을 반환하므로 같은 형태로
  간다(§2). 로컬 1인 단계에서 project_id 인덱스 스캔은 안전하다. `?since=`류는 필요가 관측된 뒤 additive로.
- **대시보드/시각화** — 오너가 다음 페이즈로 이미 분리.
- **승격 카운트**(D1-C) · **게이트 캘리브레이션**(D3-C) · **명시 quality_score**(D2-B).
- **Mongo aggregation pipeline으로의 이행** — 지금은 Python 집계. 데이터량이 문제로 관측되면.
