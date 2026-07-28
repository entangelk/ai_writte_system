# 검증 기록 — 컨텍스트 예산 C-1 (알파 `LLAMA_CTX_SIZE=16384` 기동 확인 슬라이스)

## Subject metadata

- **날짜**: 2026-07-28
- **요청자**: 오너 (작업 AI가 뽑아놓은 C-1 슬라이스 — "코드 변경 0, 실측·기록" — 를 "의심하고 또 의심해" 검증 요청)
- **검증자**: 독립 검증 AI (Claude Code, max effort)
- **검증 대상 슬라이스/산물**: 브리프 [`docs/plans/context-budget-korean-tokens-decisions.md`](../../plans/context-budget-korean-tokens-decisions.md) 의 §1-2·§1-3·§2·§2-1·§4·§7 변경분, [`HANDOFF.md`](../../HANDOFF.md) 변경분, [`docs/daily_logs/2026-07-28/work_log.md`](../../daily_logs/2026-07-28/work_log.md) 의 "C-1" 태스크. **코드 변경 0.**
- **정본 계약 참조**: 본 슬라이스는 정본(SoT)을 건드리지 않음(확정 계약이 아니라 계획). 따라서 정본 레퍼런스는 해당 없음.
- **피검증 작업 출처**: 작업 트리, 미커밋(`git status` — HANDOFF·work_log·브리프 3개 modified, untracked 없음).

> **이 검증의 한계(먼저 읽을 것)**: C-1의 핵심 산출물은 **머신-로컬 실측치**다(VRAM·tok/s·`n_ctx_slot`·`truncated`·`400` 본문·한글 밀도·HF 캐시 `refs/main`). 이 값들은 **알파 머신 접근 없이 독립 재현할 수 없다.** 본 검증이 독립적으로 확보한 것은 (a) 작업 AI가 인용한 **코드 `file:line`의 정확성**, (b) 기록된 수치의 **산술적 내부 일관성**, (c) 결론의 **논리·범위 준수**, (d) **문서 자기일관·정정의 정당성**이다. 머신 측정치 자체는 work_log의 기록치가 브리프 §1의 **베타 머신 관측**과 패턴으로 일치하는지(교차 검증)로만 신뢰를 보강한다.

## Scope

CLAUDE.md의 "boundary matrix / 두 방향 회귀 가드" 률은 **코드·테스트·픽스처 변경이 전무한 실측 슬라이스**라 적용되지 않는다. 대신 이 검증의 축은 아래 네 가지다.

1. **코드 인용 정확성** — 작업 AI가 브리프/work_log에 적은 모든 `file:line`이 소스와 일치하는가.
2. **측정값의 내부 일관성** — §1-2·§2-1 표의 산술이 성립하는가(독립 검산).
3. **결론의 논리·범위 준수** — "A는 뜬다"/"넘는다"/"A만으로 report가 넘친다" 등 결론이 측정값에서 도출되는가; 오너가 정하지 않은 것을 작업 AI가 결정·선점했는가.
4. **문서 자기일관·정당성** — 브리프 내부 모순 여부, §2 "long 노출" 오독 정정이 사실에 근거하는가, HANDOFF 자가 검수·중복 제거가 규칙에 맞는가.

머신 로컬 측정치(VRAM·속도·`n_ctx_slot`·`truncated`·`29d0977` 캐시·1.68 밀도)는 **위 축에서 검증하지 않는다** (재현 불가). 이 항목들은 "재현됐다고 기록됨"일 뿐이며, 패턴 일치 여부만 "Findings"의 별도 표로 남긴다.

## Methodology

repo 작업 디렉터리에서만 재현 가능한 명령들:

```bash
# 인용 정확성
git diff docs/plans/context-budget-korean-tokens-decisions.md
git diff HANDOFF.md
git diff docs/daily_logs/2026-07-28/work_log.md
sed -n '615,650p;1480,1500p' services/application/app/main.py
sed -n '120,160p' services/application/app/writing/report.py
sed -n '105,143p' services/application/app/writing/service.py
sed -n '525,545p' frontend/src/writing/WritingPanel.tsx
sed -n '532,545p' services/application/app/context_search/service.py
sed -n '14,52p' docker-compose.llama.yml
git show --stat --format='%H %ci %s' 4c04a9e
git show HEAD:docs/plans/context-budget-korean-tokens-decisions.md  # §1-1 원본

# 산술 독립 검산 — 전부 손계산(아래 Findings §2에 값 명시)
```

머신 의존 측정(VRAM 등)은 work_log ①의 리그가 "스크래치패드에 있고 repo에 넣지 않았다(일회성 리그)"므로 재현 스크립트가 repo에 없다 — 이것도 한계로 기록한다.

## Findings

### 1. 코드 인용 정확성 — 전부 일치 (CONFIRMED)

| 작업 AI 인용 | 실제 소스 | 일치 |
|---|---|---|
| `main.py:630` "6144 leaves 2048 tokens of prompt headroom" | `main.py:630-632` 주석이 8192 창·6144/2048 headroom 명시 (그대로) | ✅ |
| `main.py:634` self-report 6144 | `WRITING_REPORT_DEFAULT_MAX_TOKENS = 6144` | ✅ |
| `main.py:1489` short/medium/long = 1024/2048/4096 | `_writing_output_length_tokens()` 기본 1024/2048/4096 | ✅ |
| `report.py:138-144` report 입력 = system + candidate_text + context_package | `_request()` payload가 정확히 그 구성, `include_pointers=True` | ✅ |
| `service.py:126` report = 모든 생성 후 실행 | `if self._reporter is not None: return await self._reporter.enrich(...)` | ✅ |
| `WritingPanel.tsx:540-542` short·medium·long 셋 노출 | 3개 `<option>` 전부 존재 | ✅ |
| `context_search/service.py:540` 추정식 `len/4` | `estimate_tokens = max(1, (len(text)+3)//4)` | ✅ |
| `-hf …:Q4_0` 리비전 미고정 | `docker-compose.llama.yml:24` `-hf "${LLAMA_HF_REPO:-google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0}"` — 콜론 뒤는 파일명이지 리비전(sha) 아님 | ✅ |
| `--ctx-size` 기본 8192 | `:29` `${LLAMA_CTX_SIZE:-8192}` | ✅ |

**의도적 대조 검사(over-strict 방향)**: "-hf가 사실 리비전을 고정하고 있어 작업 AI 주장이 틀린 거 아닌가"를 확인했다 — 고정 안 함이 확인됐으므로 작업 AI 주장이 참. "프론트는 long도 숨겨놓고 옵션이 2개인 거 아닌가"도 확인했다 — 3개가 소스에 있으므로 §2 정정이 참.

### 2. 측정값 산술 — 독립 검산으로 전부 일관 (CONFIRMED)

작업 AI가 기록한 측정치 자체는 재현 불가지만, **테이블 내부 산술**은 손계산으로 검증했다.

**§1-2 바닥값** (system 473 + 후보 산문, 컨텍스트 0):

| 프리셋 | 473+산문(계산) | 작업 AI 기록 | 차이(JSON/payload 오버헤드로 설명 가능) |
|---|---|---|---|
| short (981) | 1,454 | 1,486 | +32 |
| medium (1,962) | 2,435 | 2,485 | +50 |
| long (4,033) | 4,506 | 4,594 | +88 |

오버헤드가 산문 길이에 비례해 커지는 패턴(`json.dumps({"candidate_text":…,"context_package":…})` + 컨텍스트 포맷 고정부)과 일관. 어색한 값 없음.

- 2048 헤드룸 판정: short 1,486 ≤ 2,048(이내) · medium 2,485 > 2,048(초과) · long 4,594 > 2,048(초과) — 작업 AI 표와 정확 일치.
- 출력 여유(8192−바닥값): 6,706 / 5,707 / 3,598 — 정확 일치. 6144 clamp 판정(✓/✗/✗)도 정확.

**§2-1 만재 시나리오** (컨텍스트 입력 예산 `4096 × len/4` = 16,384자 → 작업 AI 실측 10,094 tok):

- 생성 입력 10,382 역분해: 10,094(만재 컨텍스트) + 215(생성 system, §1-2에 기록) + ~73(instruction/payload 오버헤드) ≈ 10,382. 합리적(작업 AI가 이 분해를 명시하진 않았지만 산술이 닫힘 — 아래 hardening 3).
- 생성 +출력: short 11,406 · medium 12,430 · long 14,478 — 전부 ≤ 16,384(이내). 작업 AI 표와 일치.
- report 입력 역분해(473 + 후보 산문 + 만재 컨텍스트): short 11,765→컨텍스트 10,311 · medium 12,764→10,329 · long 14,873→10,367. 만재 10,094와 가깝고 report 포맷팅으로 약간 큰 것은 일관. 입력 증분이 후보 산문 증분과 거의 일치(999 vs 981, 2,109 vs 2,071).
- report +출력 6,144: 17,909 / 18,908 / 21,017 — 전부 > 16,384(초과). 작업 AI 표와 일치.
- C-2 후 추정치: 473+8,192+4,096+오버헤드 ≈ 12,800 + 6,144 ≈ 18,944 > 16,384 — 작업 AI "~18,900"과 일치.

**결론 산술이 깨지는 행은 없다.** 다만 역산 밀도에 대한 메모는 아래 Issues를 볼 것.

### 3. 결론 논리·범위 준수 (CONFIRMED)

- **"A는 뜬다"** — 근거: `n_ctx_slot=16384` 기동 + 동작(같은 12,971 tok 프롬프트가 창 16384에서 200·전량 생성, 창 8192에서 400). "선언만 보지 않고 동작으로 확인"했다는 점은 검증 방법론상 타당. (머신 측정치 자체는 한계 항목.)
- **"넘는다"**(§1-1 답) — §1-1은 "현재 배포의 실제 프롬프트가 2048을 넘는지"를 물었다. 작업 AI는 운영 데이터 대신 **구조적 하한(바닥값)**으로 답했다: medium·long 바닥값이 2,485/4,594 > 2,048이면, 컨텍스트 유무와 무관하게 실제 프롬프트 ≥ 바닥값 > 2,048. **더 강한 답**이며 논리 건전. 작업 AI도 "운영 데이터 없이 확정된다"고 명시.
- **"A만으로 report가 넘친다"** — §2-1 표에서 report 3종 전부 16,384 초과. 단 이 결론은 **컨텍스트 만재(16,384자 ≈ 10,094 tok) 전제 하**임(아래 Issues — 이 전제의 가시성).
- **범위/선점 검사(적대)**: 작업 AI가 `-hf`를 `-m`으로 repo에서 바꿨는가? → 아니요(추적 부채로만). `LLAMA_CTX_SIZE` 기본값을 16384로 올렸는가? → 아니요(브리프가 C-3에 배치했고, C-1은 확인 슬라이스로 닫음). §2-1에서 report 해법을 결정했는가? → (a)(b) 대안과 구현자 추천만 냈고 "결정은 오너 몫" 명시. **오너가 정하지 않은 것을 임의로 고르지 않았다.**

### 4. 문서 자기일관·정정 정당성 (CONFIRMED)

- **§2 "long 노출" 정정**: 원본이 "프론트가 실제로 제공하는 것은 short·medium 둘뿐"이었는데, `WritingPanel.tsx:540-542`(3개 옵션) + `git show 4c04a9e`(2026-07-21, `frontend/src/writing/WritingPanel.tsx` +28, long 포함)로 **정정이 사실임**을 확인. 작업 AI가 "최신화 누락이 아니라 조사 시점 오독"으로 진단한 것도 합리적(브리프 작성보다 일주일 앞선 커밋). 표를 보존하고 각주로 정정한 선택은 "결정 이력 보존" 규칙에 부합.
- **브리프 내부 모순**: 발견 안 됨. §1-1→§1-2(답), §2→§2-1(파생), §4 C-3↔§2-1(연결 "착수 전 §2-1 필독")이 모두 서로 가리킨다.
- **HANDOFF 자가 검수(187→194줄)**: pymongo naive 날짜·쿠키 `Secure` 항목이 실제로 통째로 중복돼 있었음을 diff로 확인 — 하나로 통합한 것은 스택 금지 규칙에 부합. 베타 관측치의 nginx 완료 서술(이미 `docker-compose.yml`·git에 있는 수정 내역)을 걷어낸 것도 "완료 서술 금지" 규칙에 부합. 머신 표 `3060 Ti`→`RTX 3060`(3060 Ti는 8GB 표준이라 12GB와 불일치) 정정도 타당. **다음 검수 트리거를 300줄로 올린 것**은 CLAUDE.md "~100줄마다" 규칙에 부합.

### 5. 머신 로컬 측정치 — 패턴 일치(PLAUSIBLE), 독립 재현 불가

재현 불가이므로 **신뢰도를 패턴 일치로만 평가**한다:

- BOS +1(400 본문 `12972` vs tokenize `12971`): §1 원본 베타 관측(`9782` vs `9781`)과 **같은 패턴**. 모델/머신이 달라도 재현. 신뢰 ↑.
- `truncated: true` 조용히 잘림(프롬프트+n_predict 초과): §1 원본 측정 ②(7,653+2,048→538 tok)과 **같은 메커니즘**. 신뢰 ↑.
- 한글 밀도 1.68자/token(234자/139 tok): §1 평균 1.70(1.62~1.79) 범위 내. 단일 샘플이므로 "평균 1.70의 재현"이라기보다 "같은 범위에서 관측"이 정확한 표현.
- VRAM +155 MiB(창 2배): 작업 AI가 "왜 싼지 단정하지 않는다"고 명시 — 추정(SWA 등)을 사실로 적지 않은 것은 정직. 다만 이 값은 검증자가 확인할 수단이 없음.
- `29d0977` refs/main / snapshot `f6e7774`·`2b318d6`: repo에서 `-hf` 리비전 미고정은 CONFIRMED(위 §1). 캐시 상태 자체는 머신 로컬이라 미검증 — 작업 AI가 "추적 부채로만" 명시한 한계와 일치.

## Issues / Risks

### Blocking (계약 위반)

**없다.** 본 슬라이스는 코드 0이고 계약(정본/스키마)을 건드리지 않았으므로, CLAUDE.md의 "boundary matrix 공백 = blocking" 률이 적용될 계약 obligation 자체가 없다. 인용 정확성·산술·논리·범위·문서 자기일관 전부 통과했다.

### Hardening recommendations (non-blocking — 브리프 정밀도 향상)

1. **§2-1 "report 초과"의 만재 전제 가시화**. 현재 표는 "현행 입력 예산이 허용하는 **최대치**"로 계산한다고 명시하지만, 본문 "K-3 가드가 report에서 **상시로 발동**한다"는 표현이 "컨텍스트가 만재(16,384자)일 때"라는 전제를 함축하지 않고 읽힐 여지가 있다. 컨텍스트가 적으면 report 바닥값(long 4,594 + 6,144 = 10,738 < 16,384)은 16,384 창에서 넘지 **않**는다. 즉 "초과"는 만재 시나리오에서만. 운영에서 만재가 얼마나 자주 일어나는지는 **미측정**(작업 AI도 §1-2·work_log에서 "실제 report 실패를 관측한 것은 아니다"라고 명시). C-3 오너 결정 시 이 빈도가 미측정임을 한 줄로 못박으면, "창만 키우면 해결" vs "report 전용 예산이 필요" 판단이 더 정확해진다.

2. **§2-1 구현자 추천을 선택지 표의 명시적 행으로**. 작업 AI는 본문에 "report에 별도 더 작은 컨텍스트 예산"을 추천했지만, §2의 (a)/(b) 선택지 **표 밖**에 있다. 오너가 표만 훑으면 (a) report 출력 6,144 인하 / (b) 창 32,768확장 두 가지만 보게 된다. 추천안(별도 report 컨텍스트 예산)을 표의 세 번째 행(예: (c))으로 올리면 owner decision brief의 "선택지 표에 모든 현실적 옵션을 행으로" 규칙에 더 가깝고, 오너 판단이 (a)/(b)/(c) 위에서 명확해진다.

3. **생성 입력 10,382의 분해를 한 줄로**. §2-1 표에서 생성 입력 10,382가 어디서 왔는지(만재 컨텍스트 10,094 + 생성 system 215 + payload 오버헤드)가 명시돼 있지 않아, 다음 작업자가 값을 재현하려면 역추론해야 한다. 한 줄 분해를 적으면 재현성이 보강된다(결론에는 영향 없음).

4. **"한글 밀도 1.68"과 만재 역산 밀도(1.62)의 관계 짚기**. 작업 AI는 §1-3/③에서 밀도를 1.68(234자/139 tok)로 보고하면서, §2-1 만재(16,384자→10,094 tok)는 역산 1.62 자/tok로 계산에 썼다. 둘 다 §1의 1.62~1.79 범위 내라 모순은 아니지만, "밀도 1.68"을 대표값으로 말하는 문맥과 "만재는 1.62로 잡았다"가 동시에 있어 미세 긴장. 만재 계산이 **보수적 방향**(토큰 과다 추정 → 창 초과 더 잘 발생)이라 결론은 강화되지만, 한 줄로 "만재 샘플은 하한 밀도를 썼다(보수적)"고 적으면 다음 작업자가 재산정 시 헷갈리지 않는다.

> 위 4개는 어느 것도 합격을 가로지르지 않는다. 브리프가 이미 **정직하게 한계를 명시**하고 있어(미측정·보수적·추천은 결정 아님) owner가 잘못된 전제 위에서 결정할 위험은 낮다. 정밀도 보강 후보로만 남긴다.

## Verdict

**합격 (pass).**

하중 이유:
1. 본 목적(알파에서 A=16384가 뜨는지)을 선언 + 동작의 양방향으로 답했고, 후퇴선(KV 양자화→레이어 하향→B)이 불필요했음을 근거와 함께 기록.
2. 코드 인용 9건 전부 정확, 산술 전부 내부 일관(독립 검산), 결론이 측정에서 도출, 오너 결정을 선점하지 않음.
3. 파생 발견(§2-1 report 초과, §7 `-hf` 재다운로드 원인, §2 long 노출 정정)을 owner decision brief 구조로 정직하게 회람 — 결정은 오너에게, 구현자 추천만 제시.
4. 문서 자기일관·정정의 정당성·HANDOFF 자가 검수 모두 규칙에 부합.

**한계(conditional이 아닌 pass인 이유)**: 머신 로컬 측정치는 본 검증이 재현할 수 없다. 그러나 (a) 그 측정치가 지지하는 **결론**은 코드 인용 + 산술로 독립 확보됐고, (b) 측정치 자체는 §1 원본(베타) 관측과 패턴으로 교차 검증돼 "재현됐다고 기록됨"의 신뢰가 충분하다. conditional이 되려면 "코드 인용 오류 / 산술 불일치 / 오너 결정 선점 / 문서 모순" 중 하나가 있어야 하는데, 어느 것도 없었다. 따라서 머신 측정치의 재현 불가는 합격을 가로지르는 blocking이 아니라 **outstanding**(다음 작업자가 알파에서 재실행해 완전 확정)으로 분류한다.

## Outstanding items

- **커밋 미수행**: 작업 AI가 커밋 안 함(오너 승인 대기). 검증자는 커밋 여부에 대해 의견을 내놓지 않는다 — 오너 판단.
- **머신 측정치의 독립 확정 미완료**: VRAM·속도·`n_ctx_slot` 동작·`29d0977` 캐시·1.68 밀도는 알파 접근 시 재실행해야 완전히 확정. 본 검증은 repo에서 재현 가능한 면(인용·산술·논리·문서)만 확정했다.
- **C-2 착수 가능**: 작업 AI 주장대로 C-2(토큰 계측 보정)는 알파 불필요·어느 머신이나 가능. 단 C-2가 추정식을 정확화해도 §2-1의 report 초과는 해소되지 않으므로(검증 §2에서 산술 확인), C-3 착수 전 §2-1·위 Hardening 1~2를 오너가 먼저 읽어야 함.

## Reproduction

```bash
# 인용 정확성 (전부 repo에서)
sed -n '630,634p;1489,1500p' services/application/app/main.py
sed -n '138,144p' services/application/app/writing/report.py
sed -n '126,128p' services/application/app/writing/service.py
sed -n '540,542p' frontend/src/writing/WritingPanel.tsx
sed -n '540,541p' services/application/app/context_search/service.py
sed -n '23,29p' docker-compose.llama.yml
git show --stat 4c04a9e
git show HEAD:docs/plans/context-budget-korean-tokens-decisions.md | sed -n '40,75p'  # §1-1 원본

# 산술 독립 검산 — 위 Findings §2의 값들을 손계산으로 대조

# 머신 측정치(알파 필요, 재현 스크립트는 repo에 없음 — 일회성 리그)
docker compose -f docker-compose.yml -f docker-compose.llama.yml run --rm \
  llama-server --ctx-size 16384 ...   # work_log ①의 리그; repo 미수록
```
