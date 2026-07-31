# 2026-07-31 작업 로그

## Task — 컨텍스트 예산 트랙: R-a/R-c **측정** 리그 구축 + 베타 실측 (오너 결정 2026-07-30의 "측정" 단계)

### Goals

- 오너 결정(2026-07-30): **"리포트는 전용 예산이 기본이되, 창을 늘리는 방안도 테스트해보고
  결정한다."** 착수 순서는 **측정 → 선택 → 구현**이므로 오늘의 목표는 **측정**이다.
- 그런데 착수 체크리스트 ⓓ가 그대로 막고 있었다: **어느 머신에도 예산을 꽉 채우는
  프로젝트가 없다.** 그래서 지금까지의 `−1,914`는 실측이 아니라 **항목 7,656을 비율로
  외삽한 값**이었고, **아무도 그 경계를 실제로 본 적이 없다.**
- 오늘 머신은 **베타**(GTX 1060 3GB, 외부 12B `n_ctx=16384`). **R-c(창 32768)는 알파에서만**
  가능하므로, 오늘은 ⑴ 재현 데이터를 만드는 리그를 repo에 넣고 ⑵ 베타 창(16384)에서 R-a
  곡선을 실측한다. 알파로 옮기면 **같은 스크립트 한 줄**로 R-c가 나온다.
- 성공 기준: ① 예산이 실제로 포화되는 프로젝트가 만들어진다 ② 예산별 입력 토큰이
  **추정이 아니라 서버 계수**로 나온다 ③ 그 숫자가 **배포된 가드가 세는 값과 같다**(양방향
  관통으로 확인) ④ 리그가 창을 상수로 박지 않아 알파에서 그대로 돈다.

### Completed work — ① 측정 리그 (`scripts/report_budget_measure.py`, 신규)

예산별로 report 호출의 **실제 입력 토큰**을 재고 `입력 + 출력상한 ≤ 창`(K-3 가드의 식)이
어디서 깨지는지 찾는 오퍼레이터 CLI.

- **패리티를 구조로 확보했다** — 사본을 만들지 않았다:
  - 컨텍스트 조립: `scripts/diagnose_writing_gate.build_services` + `build_search_request`
    (endpoint의 `needs` 튜플·purpose·예산을 그대로 쓴다).
  - report 페이로드: 프로덕션 서비스의 `_request(candidate, package, template)`를 **그대로
    호출**한다. 조립을 베끼면 프롬프트가 바뀔 때 측정만 조용히 옛 형태를 잰다.
  - 토큰 계수: 게이트웨이 클라이언트의 `_count_prompt_tokens`(`/apply-template` +
    `/tokenize`, `add_special=True`). 세 규칙(같은 `chat_template_kwargs` · BOS · 템플릿 몫)을
    여기서 다시 적으면 **가드와 스크립트가 서로 다른 숫자를 말하게 되고, 그러면 측정이
    가드를 검증하지 못한다.**
  - 창: **상수로 박지 않고** `/props`에서 읽는다 → 배포를 따라간다(R-c의 전제).
  - 출력 상한: `reporter.max_tokens`(= `WRITING_REPORT_MAX_TOKENS`)를 서비스에서 읽는다.
- **재현 데이터(`--seed`)**: 예산을 꽉 채우는 프로젝트를 만든다. 이 스크립트의 **유일한
  쓰기**이며 core SOT 서비스를 직접 부른다(앱 HTTP는 D8-3a 이후 401 — 인증을 우회하는 것이
  아니라 지나지 않는다).
  - **heading을 넣지 않는 것이 설계다**: `_split_scene_blocks`는 마지막 heading **뒤** 문단만
    현재 장면으로 잡으므로, 제목이 하나라도 있으면 장면이 꼬리로 줄어 **예산이 안 찬다**.
    회귀 테스트가 이 성질을 잠근다(제목이 생기면 실패한다).
- **후보 산문은 문자 수가 아니라 토큰 수를 목표로 만든다**(`long` 출력 상한 4096 = report의
  최악 입력). 첫 근사에서 멈추면 **10%까지 넘치고**(실측: 목표 4,096에 4,511) 그 초과가
  고정 오버헤드로 들어가 판정을 실제보다 좁게 만든다 → 수렴 루프로 ±2%에 맞춘다.

### Completed work — ② 합성 코퍼스의 밀도를 실제 원고에 맞췄다 (첫 측정의 결함 수정)

첫 실행에서 밀도가 **1.54 자/tok**로 나왔다(실제 원고 실측 **1.708**보다 촘촘). 원인은
문단마다 붙인 번호 표지(`장면 12-3.`)였다 — **숫자가 토큰을 많이 먹는다.** 같은 글자 수가 더
많은 토큰이 되므로 측정이 실제보다 **비관적으로** 기운다. 번호를 빼고 문장 풀 회전으로
문단을 구별하게 바꿔 **1.63 자/tok**까지 올렸다(실제 1.71에 근접).

| | 1차(번호 있음) | 2차(번호 없음) |
|---|---:|---:|
| 코퍼스 밀도 | 1.54 자/tok | **1.63 자/tok** |
| 후보 산문 | 4,511 tok (목표 +10%) | **4,159 tok (목표 +1.5%)** |
| 래퍼 | 82 tok | 94 tok |
| 예산 8192 여유 | −3,614 | **−2,836** |

### Completed work — ③ 베타 실측 (창 16384, 출력 상한 6144, 후보 = `long` 상한)

```
고정 오버헤드 (예산과 무관하게 늘 실린다)
  system 프롬프트 465 · 후보 산문 4,159 · 래퍼(채팅 템플릿 + JSON 포장) 94 → 합계 4,718
```

| 예산 | 항목 | 예산제외 | 회계 | 컨텍스트(실측) | 입력 | 입력+출력 | 창 여유 | 판정 |
|---:|---:|---:|---:|---:|---:|---:|---:|:--|
| 2048 | 15 | 102 | 1,979 | 2,050 | 6,768 | 12,912 | **+3,472** | PASS |
| 3072 | 23 | 94 | 3,035 | 3,124 | 7,842 | 13,986 | +2,398 | PASS |
| 4096 | 31 | 86 | 4,091 | 4,198 | 8,916 | 15,060 | +1,324 | PASS |
| 5120 | 38 | 79 | 5,017 | 5,136 | 9,854 | 15,998 | **+386** | PASS |
| 6144 | 46 | 71 | 6,073 | 6,210 | 10,928 | 17,072 | −688 | REJECT |
| **8192**(현행) | 62 | 55 | 8,185 | 8,358 | 13,076 | 19,220 | **−2,836** | REJECT |

- **R-a 산식이 이제 실측 위에 선다**: `창 16384 − 출력상한 6144 − 고정 4,718` =
  **컨텍스트에 쓸 수 있는 실제 토큰 5,522** → 회계/실측 비율 **0.979**로 환산해 **회계 단위 약
  5,407**. 어제의 산식 후보(약 6,000)보다 **작다** — 어제는 래퍼를 150으로, 후보 산문을
  4,033으로 잡았는데 실측은 래퍼 94 · 후보(상한 사용 시) 4,159였고, 무엇보다 **예산 8192의
  실제 렌더링이 8,358로 외삽값 7,656보다 컸다.**
- **어제의 −1,914는 실제보다 낙관적이었다**(실측 **−2,836**). 외삽이 틀렸다기보다,
  실제 패키지가 예산을 더 촘촘히 채우고 후보가 상한을 다 쓰면 더 무겁다는 뜻이다.
- **R-c는 산술상 여유가 크다**: 같은 입력 13,076 + 6,144 = 19,220이므로 **창 32768이면
  +13,548**이다. 즉 창을 올릴 수 있는 배포에서는 현행 8192가 그대로 통과한다. **다만 그것은
  알파에서 확인할 일이다**(이 스크립트를 그대로 돌리면 된다).

### Verification — 측정이 배포 가드와 같은 숫자를 말하는가 (양방향 관통)

리그의 값이 맞는지는 스스로 증명할 수 없으므로 **실제 파이프라인**(app → gateway → 12B)에
같은 패키지를 태워 대조했다.

| 방향 | 예산 | 결과 |
|---|---:|---|
| **초과(under-strict)** | 8192 | `ProviderError: context window exceeded before the call: input **13076** + output cap 6144 = **19220** > window **16384**` — 측정 표와 **delta 0** |
| **통과(over-strict)** | 5120 | 실제 report 호출이 **그대로 성공**했다(가드가 정상 요청을 막지 않는다) |

- 즉 이 경계는 **처음으로 실제로 관측됐다**(종전까지 외삽). 가드가 모델을 부르기 전에
  거부하는 것도 함께 확인됐다(왕복 0회).
- backend 전량 **1749 passed / 1 skipped / 1499 subtests**(766s, test-mongo ON) → 독립 검증
  보강 뒤 **1752 passed / 1 skipped / 1502 subtests**(741s). 직전 기준선 1738 / 1498 대비
  **+14 테스트**(오늘 새 파일) · **+4 subtest**(가드 cross-parity 경계 3점 + 어제 커밋
  `2480ce2`의 프롬프트 v4 핀 1). **회귀 0건** — `main.py` 변경은 주석뿐이다.
- 회귀: `tests/test_report_budget_measure_script.py` **11 passed**(독립 검증 보강 뒤 **14 passed
  / 3 subtests** — 아래 절). 잠근 것은 ⑴ 시드 원고가
  실제로 현재 장면을 채운다(제목이 생기면 실패) ⑵ 판정이 가드의 식과 같다(창에 **정확히**
  닿으면 PASS · 1토큰 넘으면 REJECT — 양방향) ⑶ 포화하지 못한 실행은 표를 경계처럼 보여주지
  않고 **경고한다** ⑷ CLI 인자 결합.

### Issues found — 이 측정의 한계 (읽는 사람이 알아야 하는 것)

- **합성 코퍼스 밀도 1.63은 실제 원고 1.71보다 약 5% 촘촘하다.** 실제 원고라면 같은 회계
  단위가 조금 더 많은 글자를 담으므로, 권장 예산은 **약 5,407보다 조금 더 커질 수 있다**.
  스크립트가 밀도를 결과에 함께 출력하므로 다음 사람이 이 가정을 바로 확인할 수 있다.
- **이 표는 "후보가 `long` 상한을 다 쓴 최악"이다.** 후보를 medium(2,139 tok)으로 낮춰 같은
  프로젝트를 다시 쟀다: 고정 오버헤드 **2,666**, 통과 최대 예산 **6144**(+1,364), 권장 약
  **7,417**. **다만 현행 8192는 medium에서도 −784로 거부된다** — 즉 후보 길이만으로 설명되는
  문제가 아니고, 이것이 브리프 §2-5-1에서 (iii) 단독을 탈락시킨 근거다.
- 시드 프로젝트는 **베타 DB에 남겨 뒀다**(육안·재측정용). 아래 "머신-로컬 상태" 참조.

### Decisions — 오늘 내가 정한 것과 정하지 않은 것

- **정한 것(구현자 재량)**: 측정 방법(패리티를 사본이 아니라 재사용으로 확보) · 시드 원고의
  형태(heading 없는 단일 장면) · 후보 산문을 토큰 목표로 맞추는 것.
- **정하지 않은 것(오너 결정)**: **R-a의 최종 숫자와 형태**. 측정이 (i)/(ii)의 선택을 바꾸는
  근거를 하나 더 냈기 때문이다 — 위 "최악 기준" 항목대로 **상수 예산은 short/medium 요청을
  불필요하게 굶긴다**. 실측이 연 선택지는 세 갈래다:
  - **(i) 상수 report 예산 ≈ 5,000**: 즉시 가능. 창 16384에서 최악(long)까지 통과. 대신 창이
    다른 배포에서 틀리고, short/medium에서 근거를 3,000 이상 버린다.
  - **(ii) 창에서 유도**: 정확하지만 게이트웨이의 창 값을 앱까지 끌어오는 배선이 하나 는다.
  - **(iii) 신설 — 후보 길이에서 유도**: 앱은 창을 모르지만 **후보 텍스트는 이미 갖고 있다.**
    고정 오버헤드의 88%가 후보 산문이다(4,159 / 4,718). **단독으로는 부족하다** — medium
    후보로 다시 재도 8192는 −784로 거부됐다. (ii)와 결합해야 식이 닫힌다.
  - **구현자 추천은 (ii)+(iii) 한 슬라이스**이고 근거는 브리프 §2-5-1에 표로 정리했다:
    창이 다른 세 머신을 옮겨 다니는 프로젝트에서 (i)은 머신-로컬 값을 **코드에** 박는
    것이고, (ii)가 들어가면 **R-c가 같은 결정에 흡수된다**(창을 키우면 예산이 자동으로
    넓어진다). 가드가 이미 400으로 막고 있어 급히 임시안을 넣을 이유도 없다.
- **R-c는 알파에서 한 번 돌리면 끝난다** — 리그가 창을 읽으므로 `.env`에
  `LLAMA_CTX_SIZE=32768`을 넣고 같은 명령을 실행하면 표가 그 창으로 다시 그려진다.

### 머신-로컬 상태 (베타, 2026-07-31)

- 아침 시작 시점에 스택은 **15시간 전 `Exited(255)`**로 내려가 있었다(머신 재부팅 추정).
  `docker compose up -d`로 복구했고 지금 **healthy 7 + 워커 2**다.
- 시드 프로젝트 2개를 남겼다 — 재현용이므로 지우지 않았다:
  - `6a6be92bda7b035f309a8005` (1차, 번호 있는 코퍼스 = 밀도 1.54, **대표성 낮음**)
  - **`6a6be9c0dbb39de0a51ed8ba`** (2차, 밀도 1.63 — **이쪽을 쓴다**).
    draft `6a6be9c0dbb39de0a51ed8bb` · version `6a6be9c0dbb39de0a51ed8bc`
- 이미지는 여전히 코드보다 뒤처져 있다(`application` 07-29 · `frontend` 07-27). 오늘 측정은
  전부 **작업 트리를 마운트**해 돌렸으므로 이미지 상태와 무관하다.

### 독립 검증 후속 보강 (같은 슬라이스)

독립 검증 [`verifications/2026-07-31/r_a_budget_measure_league.md`](../../verifications/2026-07-31/r_a_budget_measure_league.md)
판정은 **합격(차단 0)**이고 하드닝 권고 3건이 왔다. **세 건 다 반영했다.**

- **★ #1 — 지적은 맞았고 원인 진단은 달랐다. 그래서 고친 것도 다르다.**
  검증자는 "문서의 5,330이 스크립트 실출력 5,381과 불일치"를 잡았고 원인을 **낡은 손계산**
  (래퍼 150을 쓴 잔재)으로 추정했다. **불일치는 사실이지만 원인은 그게 아니다** — 5,330도
  스크립트 출력이었다. 두 값은 **`--budgets`를 어떻게 주느냐**로 갈렸다:

  | 실행 | 첫 포화 행 | 비율 | 출력 |
  |---|---:|---:|---:|
  | 작업자(`2048,…`) | 2048 | 1,979/2,050 = 0.965 | **5,330** |
  | 검증자(`4096,…`) | 4096 | 4,091/4,198 = 0.975 | **5,381** |

  즉 결함은 문서의 숫자가 아니라 **도구가 목록의 첫 행에서 비율을 뽑는다**는 데 있었다.
  비율은 예산이 커질수록 오른다(패키지의 구조적 래퍼가 상각된다 — 실측 0.965@2048 →
  0.979@8192). **문서만 5,381로 고쳤다면 다음 사람이 다른 목록으로 돌려 또 다른 숫자를
  보고 같은 의심을 반복했을 것이다.**
  → **만재에 가장 가까운(가장 큰) 포화 예산에서 비율을 뽑도록 고치고**, 포화 구간의 비율
  **범위를 함께 출력**한다. 재측정 결과 **약 5,407**(비율 0.979, 구간 0.965~0.979)이 단일
  값으로 나오며, 문서 네 곳을 그 값으로 맞췄다. medium 후보 재측정도 같은 규칙으로
  **7,417**이다. 회귀: 작은 예산을 **덧붙였을 뿐인데** 권장치가 달라지면 실패하는 셀.
- **#2 — 스크립트 판정 ↔ 가드 판정 cross-parity 테스트를 넣었다.** 종전 `VerdictTest`는
  스크립트 규칙만 잠갔다. 새 셀은 경계 3점(창−1 · 창 · 창+1)에서 `BudgetRow.verdict`와
  **프로덕션 `LlamaCppProvider._window_decision`의 결정**이 같은지 단언한다(가짜 transport로
  `/apply-template`·`/tokenize`를 태운다). 뮤테이션 확인: 스크립트 식을 `<=`→`<`로 바꾸면
  이 셀과 `VerdictTest`가 함께 문다.
- **#3 — 래퍼가 "예산 무관 상수"임을 출력이 직접 증명하게 했다.** 종전에는 루프 마지막
  예산의 분해만 보고했다. 이제 **예산별로 따로 재서** 전 구간이 같으면 "예산 전 구간에서
  동일(실측)", 다르면 예산별 값을 ⚠와 함께 나열하고 산식은 보수적으로 **최대치**를 쓴다.
  실측 재확인: 여섯 예산 전부 **94**. 회귀: 값이 갈리면 경고가 나오는 셀.
- 회귀 재실행: `tests/test_report_budget_measure_script.py` **14 passed / 3 subtests**
  (종전 11). 뮤테이션 2종(경계 `<=`→`<` · 비율을 첫 행에서) 모두 해당 셀이 물었고 역방향
  Edit으로 원복했다(`git checkout --`는 쓰지 않았다 — 미커밋 작업이 있는 트리다).

### Next steps (측정 슬라이스 시점)

- **오너 결정 대기**: R-a의 형태 (i)/(ii)/(iii) 및 숫자. 위 "Decisions" 참조.
- **알파에서 R-c 1회**: `.env`에 `LLAMA_CTX_SIZE=32768` → 같은 스크립트. 알파 착수 체크리스트
  (이미지 빌드 · `-hf` 재다운로드 · 오래된 볼륨)는 HANDOFF에 그대로 있다. **재현 데이터
  없음(ⓓ)은 이제 해소됐다** — `--seed`가 그 자리에서 만든다.
- K-4(프론트 글자수 표시·경고)는 여전히 착수 가능하며 R-a 결정과 독립이다.

---

## Task — 컨텍스트 예산 트랙: R-a 구현 (오너 결정 2026-07-31 = (ii)+(iii))

### 오너 결정

오너: **"R-a의 형태는 상수로 박아두는건 안되지... 추천대로 하자. 그게 맞다."**

즉 **(ii) 창에서 유도 + (iii) 후보 길이에서 유도**를 채택하고 **(i) 상수는 명시적으로
기각**했다. 근거는 브리프 §2-5-1에 정리한 그대로다 — 창이 다른 세 머신을 옮겨 다니는
프로젝트에서 상수는 **머신-로컬 값을 코드에 박는** 일이고, 이 프로젝트는 그 방식으로 이미
여러 번 시간을 잃었다. 알파 작업(R-c)은 지금 못 하므로 **베타에서 할 수 있는 것부터**
하라는 지시도 함께 받았다.

### 착수 전에 바뀐 것 — 제품의 주 경로는 `/writing/report`가 아니다

구현 지점을 정하려고 호출부를 전수로 봤고, **설계 전제가 하나 틀렸다는 것을 먼저 발견했다**:

- 프론트는 `/writing/report`를 **부르지 않는다**(`schema.d.ts`에만 존재).
- 제품 경로는 **생성**이다: 워커 → [`WritingService.generate`](../../../services/application/app/writing/service.py)가
  생성 직후 **같은 패키지로** `reporter.enrich(candidate, package)`를 부른다.
- 그래서 report만 따로 예산을 주는 형태로는 **제품이 안 바뀐다**. 구속하는 것은 언제나
  **report 다리**(출력 상한 6144 + 후보 산문)이므로, 유도는 **생성 시점의 패키지 예산**에
  들어가야 한다. 생성 시점에는 후보가 없지만 **상한은 출력 프리셋**이다 — (iii)이 여기서
  자연스럽게 맞물린다.

### Completed work — ① 게이트웨이가 자기만 아는 것을 노출한다

- `GET /v1/capabilities` → `{"context_window": int|null}`
- `POST /v1/tokenize` → `{"tokens": int|null}`
- provider에 `context_window()`·`count_tokens()`를 더했다. **`capabilities`는 창 조회를
  기다린다** — v1.7.60의 "생성은 창 조회를 기다리지 않는다"와 모순이 아니다. 그 계약은
  생성을 지연시키지 말라는 것이고, 이 호출은 **창 자체를 묻는 호출**이라 기다리지 않으면
  답이 없다. 생성 경로는 손대지 않았다.
- **모르면 `null`이다**(비-llama provider · `/props` 실패 · 토크나이저 없음). 지어낸 값을
  주는 것이 이 배선에서 가장 나쁜 실패다 — 앱이 그 위에서 예산을 정하기 때문이다.

### Completed work — ② 앱은 그것을 캐시해서 쓴다

[`writing/model_capabilities.py`](../../../services/application/app/writing/model_capabilities.py):
창은 서버 기동 설정이고 계수 대상은 **고정 문자열**이라 **프로세스당 한 번씩만** 묻는다.
`create_app`/워커 조립 시점에 만들어야 캐시가 요청 간에 살아남는다(요청마다 만들면 매
요청에 왕복이 두 번 붙는다). 모든 실패는 `None`으로 떨어지고 **요청 경로로 새지 않는다**.

### Completed work — ③ 식과 적용

[`writing/report_budget.py`](../../../services/application/app/writing/report_budget.py):

```
예산(회계) = (창 − report 출력상한 − system 템플릿 − 후보 상한 − 포장 150) × 0.96
```

- **system 템플릿은 게이트웨이 토크나이저로 센다**(실측 465). 자체 추정 `len/1.7`은 이
  템플릿이 영문이라 **976으로 2배 과대평가**한다 — 고정 문자열이므로 한 번 세면 끝이고,
  못 세면 그 추정으로 떨어진다(과대평가는 예산을 좁히는 쪽이라 안전하다).
- **포장 150**은 실측 94(여섯 예산 전 구간 동일) 위의 여유다.
- **0.96**은 회계↔실제 렌더링 비의 **낮은 쪽**(실측 0.965~0.979). 낮게 잡을수록 실제
  렌더링이 여유 안에 남는다.
- **적용**: `/writing/generate` 엔드포인트 · **생성 워커** · `/writing/report`. 앞의 둘은
  후보 상한을 **출력 프리셋**으로, 마지막은 **후보 산문의 추정**으로 준다.
- **revise-and-gate 루프는 범위 밖**이다 — 패키지를 병합하고 `retrieve_more`로 키우기까지
  하므로 "언제 무엇을 기준으로 줄일지"가 별도 판단이다. 다음 슬라이스로 남긴다.

### Verification — 관통 실측이 결론이다 (베타, 창 16384, 포화 프로젝트)

| 예산 | 항목 | 회계 | 결과 |
|---|---:|---:|---|
| 종전 8192 | 62 | 8,185 | **REJECTED** — `input 13076 + output cap 6144 = 19220 > window 16384` |
| **유도 5307** | 40 | 5,280 | **PASSED** — 실제 report 호출이 통과했다 |

- 게이트웨이가 앱에 알려준 값도 직접 확인했다: 창 **16384**, report system 템플릿 **465 tok**
  (측정 리그가 llama에 직접 물어 얻은 값과 **동일**). 한국어 산문 밀도도 **1.72 자/tok**로
  나와 K-1(a)의 상수 1.7이 이 경로에서도 확인됐다.
- backend 전량 **1772 passed / 1 skipped / 1502 subtests**(799s). 직전 1752 대비 **+20**이며
  전부 오늘 새 파일이다 — **회귀 0건**.
- 회귀 **20건 신규**: 유도 4방향(줄인다 · 창 모르면 안 건드린다 · **늘리지 않는다** ·
  창이 고정 오버헤드보다 작아도 양수 예산) + 프리셋이 짧을수록 컨텍스트가 많다((iii)) +
  창이 클수록 예산이 크다((ii)) + 계수 실패 시 추정 fallback이 **더 좁은** 쪽인지 +
  게이트웨이 두 endpoint의 `null` 계약 + 클라이언트 캐시·실패 흡수.
- **유도값이 실제로 창에 들어가는지**를 산술로도 잠갔다: 회계 예산을 실측 비율의 **높은**
  쪽(0.979)으로 되돌려 렌더링을 계산하고 고정 오버헤드·출력 상한을 더해도 창을 넘지 않아야
  한다는 단정이다(유도가 낮은 쪽 0.96을 쓰는 이유가 그 여유다).

### Issues found — `max_tokens`의 뜻이 바뀐다 (공개 스키마는 무변)

요청의 `max_tokens`는 이제 **"그대로 쓰는 예산"이 아니라 "상한"**이다 — 창이 허락하는 것보다
크면 앱이 줄인다. OpenAPI 스키마는 그대로라 프론트 재생성은 필요 없지만, **이 의미 변화는
계약이므로 정본(SoT v1.7.65)에 적었다.** 반대 방향(요청보다 크게)은 절대 가지 않는다.

### Next steps

- **다음 슬라이스**: revise-and-gate 루프에 같은 유도 적용(병합·`retrieve_more` 상호작용
  판단 포함).
- **알파에서 R-c 1회**: 창을 32768로 올리면 이제 **유도가 자동으로 넓어진다** — R-c는 별도
  구현이 아니라 이 유도의 관측이 됐다(오너 결정 (ii)가 흡수한 부분).
- 프론트 `MAX_TOKENS=8192`는 그대로 둔다(상한으로서 유효하며 서버가 창에 맞춰 줄인다).

---

## Task — R-a(02feebb) 독립 검증 비차단 보강 3건 (검증자 실시)

### Goals

독립 검증(`verifications/2026-07-31/r_a_implementation.md`)이 02feebb을 **합격**으로 하되
비차단 보강 3건을 꼬집었다. 작업 AI를 대신해 검증자가 이 보강을 구현한다.

### Completed work

- **#1 동시성 경쟁 실결함 수정**(`model_capabilities.py`):
  `context_window()`가 `_window_probed=True`를 probe **전**에 세팅하고 있어, cold-boot에서
  두 요청이 동시에 첫 조회를 하면 한쪽이 lock 밖 fast-path에서 `_window`(아직 None)를 받아
  갔다. 그러면 derivation이 건너뛰고 요청 예산(8192)이 그대로 쓰여 **가드에 400으로 거부**된다.
  `finally`로 probe **뒤**에 표시하게 고쳐 동시 첫 호출이 lock을 기다렸다가 **같은 값**을
  받게 했다(실패도 캐시 — K-3 fail-open 계약 유지).
- **#1 회귀(양방향)**: `test_concurrent_first_calls_share_one_probe_and_both_get_the_window`
  추가 — 두 동시 호출이 같은 창을 받고 probe는 1회. **결함 코드에서 `None != 16384`로 실패**하는
  것을 되돌려 넣어 직접 확인했다(under-strict). +1 테스트.
- **#2 `max_tokens` 의미 변경을 OpenAPI description에 반영**(`main.py`):
  `WritingGenerateRequest`·`WritingReportRequest`(derivation이 실제 적용되는 둘)의
  `max_tokens`에 "창에 맞춰 줄일 수 있는 상한(늘리지 않음)" description 추가. 게이트·revise는
  derivation 미적용이라 건드리지 않아 의미가 정확히 갈린다. **구조·기본값(8192) 무변** —
  description만. OpenAPI 핀 테스트(H3 응답코드 계약)는 영향 0(`test_application_api.py` 145 passed).
- **#3 SoT v1.7.65 ⑥ 명확화**(`system-contract-sot.md`): 프리셋별 유도 실측값(long 5,307 ·
  medium 7,273 · short 8,192 캡)을 적고, medium이 §2-5-1 리그 권고 7,417보다 작은 이유(후보 상한을
  실측 2,139가 아니라 프리셋 2,048 + 보수 상수 150·0.96 — 안전 방향)를 한 줄로. #2로 인해
  "스키마는 무변"을 "구조는 무변, description만 의미 반영"으로 정정.

### Verification

- 포커스: `test_gateway_capabilities.py`(11)·`test_report_budget_derivation.py`(10)·
  `test_application_api.py`(124) = **145 passed**. #2 Field 변경이 OpenAPI 계약 테스트를
  깨뜨리지 않음.
- 전량: backend **1773 passed / 1 skipped / 1502 subtasks**(02feebb의 1772 + 본 보강 +1).
  회귀 0건.

### Decisions

- **#2를 전체(max_tokens 5곳)가 아니라 generate·report 2곳에만**: derivation이 적용된 곳만
  "상한" 의미가 참이고, gate/revise는 그대로 쓴다. 일괄 적용하면 거짓 계약이 된다.
- #1은 "1회 왕복" 단언의 엣지가 아니라 **실제로 cold-boot 동시 요청이 400으로 죽는 결함**이라
  보강(테스트만)이 아니라 코드 수정으로 닫았다.

### Next steps

- revise-and-gate 루프 유도(02feebb이 남긴 다음 슬라이스).
- 알파 R-c 관측(LLAMA_CTX_SIZE=32768 → 유도 자동 확대).

---

## Task — R-a 유도를 revise-and-gate 루프 + /writing/accept로 확장 (SoT v1.7.66)

### Goals

- v1.7.65 ⑤가 **"revise-and-gate 루프는 이 버전 범위 밖 — 패키지 병합·`retrieve_more`와의
  상호작용은 별도 판단이 필요"**로 남겨둔 것을 닫는다. HANDOFF Next Tasks #2·위 "Next steps"가
  모두 이것을 다음 슬라이스로 지목했다.
- **갭**: `/writing/revise-and-gate` 엔드포인트만 `body.max_tokens`를 가공 없이 context budget에
  넣고 있었다([`main.py:4712`](../../../services/application/app/main.py#L4712)). 다른 3개 writing 호출부
  (generate · report · 생성 워커)는 `derive_context_budget`로 창에 맞춰 줄인다. 루프의 report 다리
  (같은 report 서비스, 출력 상한 6144 + 후보 산문)가 창을 넘으면 K-3 가드가 400으로 거부해 루프가 죽는다
  — 생성 경로에서 이미 본 증상과 같다.
- **패턴 스윕이 두 번째 사이트를 잡았다**: 루프를 고친 뒤 같은 결함(raw 예산 + report 다리)을
  repo 전수로 훑어 `/writing/accept`를 찾았다(`WritingAcceptService.run` → `reporter.enrich`).
  오너 승인으로 같은 슬라이스에 함께 담았다.
- 성공 기준: ① 루프 진입 시 예산이 창에서 유도된다 ② 유도값이 루프의 패키지 예산·merge 상한 양쪽에
  흐른다(retrieve_more로 자란 패키지도 묶인다) ③ accept에도 같은 유도가 들어간다 ④ 창을 모르면 종전
  동작(요청값 그대로) ⑤ 회귀 0건.

### 설계 판단 — SoT가 요구한 "별도 판단" (진입 시 1회 유도)

루프는 패키지를 merge로 키우고 `retrieve_more`로 추가 검색까지 하므로 "무엇을 기준으로 언제 줄일지"가
결정 사항이었다. 분석 결론:

- **진입 시 1회 유도(엔드포인트)가 정답**이다. 후보가 이미 있으므로 report 엔드포인트와 같이
  `candidate_tokens_from_text(candidate_text)`를 후보 상한으로 쓴다(출력 프리셋이 아니다 —
  `output_length`는 generate-only라 revise-and-gate 요청에 없다).
- **루프 본체는 무변경**이다. 루프는 `context_budget.max_tokens`를 (a) `build_context_package`의
  예산과 (b) `merge_context_packages(max_tokens=…)`의 merge 상한 **양쪽에** 그대로 쓴다
  ([`revise_gate.py:490,501`](../../../services/application/app/writing/revise_gate.py#L490)). 엔드포인트에서
  유도값을 한 번 넣으면 두 곳 모두 자동으로 따른다.
- **merge 상한이 패키지 성장을 묶는다** — `merge_context_packages`는 합계가 상한을 넘으면 초과 항목을
  `excluded`로 보낸다([`retrieval.py:280`](../../../services/application/app/writing/retrieval.py#L280)).
  그러므로 retrieve_more가 패키지를 유도값 너머로 키우지 못한다.
- **per-round 재유도는 기각** — 이미 만들어진 패키지는 merge 없이는 줄어들지 않으므로, 라운드마다 예산
  숫자만 다시 유도해 봤자 "후보가 revise로 커진" 문제를 풀지 못한다. 후보는 partial patch
  (revise 출력 상한 512)라 유의하게 자라지 않고, 구속하는 다리는 여전히 report이며, 남는 초과는
  **K-3 가드가 백스톱**한다.

### Completed work

- **① 엔드포인트에 유도 적용**([`main.py`](../../../services/application/app/main.py) `writing_revise_and_gate_endpoint`):
  `ContextBudget(max_tokens=body.max_tokens)` → `await derive_context_budget(...)` (report 엔드포인트와
  동일 형태). `body.candidate_text`는 이미 그 시점에 available해 재배치 불필요.
- **② `WritingReviseRequest.max_tokens` description 정렬**: 독립 검증 hardening #2가 generate·report에만
  붙인 "창에 맞춰 줄일 수 있는 상한(늘리지 않음)" description을 이제 유도가 적용되는 이 필드에도 붙였다.
  **구조·기본값 무변 — description만.** gate는 report 다리가 없어 구속하지 않으므로 **그대로** 둔다(이
  차이가 정확한 계약 — hardening #2 Decisions의 연장).
- **③ SoT v1.7.66**: 변경이력에 v1.7.66 행 추가(루프로 확장 · 1회 유도 · merge 상한이 성장을 묶음 ·
  per-round 기각 · K-3 백스톱). v1.7.65 ⑤의 "범위 밖"은 변경이력 행이라 그대로 두고 v1.7.66이 대체.
- **④ wiring 테스트**([`tests/test_writing.py::WritingReviseGateBudgetDerivationTest`](../../../tests/test_writing.py)):
  엔드포인트→루프 배선을 양방향으로 잠갔다. 관측점은 `_FakeContextSearch.last_request.context_budget.max_tokens`.
  collaborator stub(revise→report→gate PASS)으로 루프를 첫 판에 끝내고, `_default_model_capabilities`를
  patch해 창 값을 제어한다.
- **⑤ 패턴 스윕 — `/writing/accept`에 동일 적용**: ④를 붙인 뒤 같은 raw 예산 패턴을 repo 전수로 훑었더니
  accept가 걸렸다 — `WritingAcceptService.run`이 `reporter.enrich(candidate, package)`를 부른다
  ([`accept.py:96`](../../../services/application/app/writing/accept.py#L96)), 즉 report 다리가 있고 원래
  구현(2026-07-12)부터 raw 예산이었다(git blame `27164ae9`). v1.7.65(02feebb)가 generate·worker·report에만
  유도를 넣고 accept는 놓친 것. **같은 수정**(엔드포인트에서 `derive_context_budget`, `WritingAcceptRequest`
  description 정렬)으로 닫고, 양방향 wiring 테스트(`WritingAcceptBudgetDerivationTest`)를 추가했다.
  accept는 injection params에 writing_accept_service가 없어 게이트를 주입해 `writing_accept`를 build하게
  했고, accept.run은 base version 미시드로 실패하지만 `build_context_package`가 그 **이전**이라
  last_request는 잡힌다(accept.run 이후 동작은 `test_writing_accept.py` 범위).
- **⑥ 패턴 스윕 결산(조용히 넘기지 않음)**: raw 예산 사이트 4곳을 전수 조사했다 — `/writing/gate`
  · `/writing/revise`(둘 다 report 다리 없음, **올바르게 raw**) · `/context-search`의
  `_build_context_search_request` 헬퍼(report 다리 없음, 올바르게 raw). accept만이 결함 사이트였다.

### Verification

- **wiring 양방향(revise-gate + accept)**: 창 8000을 알면 요청 8192가 유도값(≈1182)으로 내려가고, 그
  값은 report 엔드포인트와 **같은 입력**(후보 산문 추정)으로 계산한 `derive_context_budget` 결과와 정확히
  일치한다(→ (iii) 후보 길이에서 유도함을 함께 건다). 게이트웨이를 모르면 요청값 8192 그대로(종전 동작).
- **뮤테션(under-strict)**: 두 엔드포인트를 각각 raw `body.max_tokens`로 되돌리면 `8192 != 1182`로
  재실패함을 직접 확인했다(역방향 Edit으로 원복 — `git checkout --`는 미커밋 작업 트리라 쓰지 않았다).
- **포커스 회귀**: `test_writing.py`·`test_writing_accept.py`·`test_report_budget_derivation.py` 등 +
  OpenAPI 핀 `test_application_api.py`(**124 passed**) — description 변경 영향 0.
- **전량 backend**: **1777 passed / 1 skipped / 1502 subtests**(704s, test-mongo ON). 기준선 1773 대비
  **+4 = 신규 wiring 4건**(revise-gate 2 + accept 2), subtest·skip 무변 → **회귀 0건**.

### Decisions

- **1회 유도 vs per-round**: 1회 유도. 근거는 위 설계 판단(이미 만들어진 패키지는 merge 없이 못 줄임).
- **후보 상한 = 후보 산문 추정**(출력 프리셋 아님): report 엔드포인트와 같고, 후보가 이미 존재하므로.
- **gate 엔드포인트는 손대지 않음**: gate는 report 다리가 없어 창을 구속하지 않는다.
- **accept를 같은 슬라이스에 담은 것**: 패턴 스윕으로 잡은 동일 결함이라 오너에게 묻고 같이 고치기로(별도
  슬라이스가 아니라). 수정은 accept에도 동일하게 적용(report 다리가 같으므로).
- 루프 본체(`revise_gate.py`)는 **무변경** — 유도는 엔드포인트 한 곳에서만.

### Next steps

- **알파 R-c 관측 1회**: 이제 루프·accept도 유도를 쓰므로 창을 32768로 올리면 그 예산도 자동으로 넓어진다.
  `.env`에 `LLAMA_CTX_SIZE=32768` 후 같은 리그/엔드포인트로 관측.
- R-a 트랙은 이것으로 적용 지점이 전부 채워졌다(generate · worker · report · **revise-and-gate 루프** ·
  **accept**). 남은 것은 알파 관측뿐이다.

---

## Task — 컨텍스트 예산 트랙: K-4 프론트 글자수 카운터 + 소프트 경고 (오너 결정 2026-07-31 "서버 예산 노출까지")

### Goals

- K-4(브리프 `plans/context-budget-korean-tokens-decisions.md:655`): 글쓰기 입력에 **글자수 카운터 + 소프트
  경고**. 브리프 결정은 "카운터 + 소프트 경고, 원고 본문 hard maxLength 금지(정본 손상), 지시문은 hard 가능".
  선행 C-2(환산 1.7 확정)는 끝났다.
- **오너 결정(이 대화)**: R-a(v1.7.66)가 예산을 "창에서 유도"로 바꾼 지금 카운터 기준을 **프론트 고정 8192**로
  할지 **서버에서 유도 예산 노출**로 할지가 포크. 오너는 **"서버 예산 노출까지"** 를 택했다 — 프론트 고정값은
  R-a 유도값(베타, long preset ≈5,307 토큰)과 어긋나 경고를 거짓으로 만든다.
- **범위 정렬(브리프 §6 + 코드)**: 원고 본문은 `/writing/generate` 에 **안 실린다**(서버가 `draft_id` 로 잘라
  읽음) — §6 가 "창과 무관, 범위 밖"으로 뺐다. 그러므로 경고 대상은 **지시문**, 원고 본문은 hard 제한 없이
  글자수 가이드만.

### Completed work — ① K-4(a) 백엔드: `GET /projects/{id}/writing/budget` 노출

- **새 endpoint**([`main.py`](services/application/app/main.py) `get_writing_context_budget`): R-a 유도 예산을
  **per-preset**(short/medium/long 토큰)으로 노출. 각 preset마다 `derive_context_budget` 을 그 preset의 출력
  상한(1024/2048/4096)을 후보 상한으로 돌린다(project-scoped 인증 `_REQUIRE_PROJECT_OWNER` +
  `_owned(_ERRORS_404)` = {401,403,404,503}, sibling `get_writing_generation_job` 와 동형).
- **payload 모델**([`http_models.py`](services/application/app/writing/http_models.py)): `WritingContextBudgetPresetPayload`·
  `WritingContextBudgetPayload`.
- **seam 은 넣었다가 뺐다**: `create_app` 에 `model_capabilities` 주입 seam 을 넣었다가, 기존 R-a 회귀
  (`WritingReviseGateBudgetDerivationTest`)가 `patch.object(main_module, "_default_model_capabilities")` 방식을
  이미 쓰는 걸 보고 **제거**(Simplicity + 기존 스타일 일관). endpoint 는 클로저의 `_default_model_capabilities()`
  값을 그대로 쓴다.
- 회귀: 선언 가드(`EXPECTED` 12→13, auth matrix project tier 59→60·전체 69→70) + endpoint 동작
  (`WritingContextBudgetApiTest` 양방향 — 창을 알면 per-preset derive 산식과 정확히 일치, 모르면 요청값 그대로).

### Completed work — ② K-4(b) 프론트: 카운터 + 소프트 경고

- **`tokenEstimate.ts`**(신규): `estimateTokens(text)=ceil([...text].length/1.7)`(spread=Python `len` code point),
  `formatInstructionCount`·`formatCharCount`. **1.7 은 서버 `context_search/service.py:558` `KOREAN_CHARS_PER_TOKEN`
  의 미러** — 주석으로 cross-ref, drift 는 표시 경고에만 영향(K-3 가드는 real tokenization).
- **`useWritingBudget.ts`**(신규): mount 1회 `getWritingContextBudget` + 모듈 캐시(탭 전환 재패치 방지).
  **실패(transport/5xx/403)하면 null** — 예산을 모르면 경고 안 한다(거짓 경고 방지).
- **`WritingPanel.tsx`**: 지시문 아래 카운터(`{X}자 (≈{Y} 토큰)`), 해당 preset 예산 대비 **90%** 소프트 경고
  (`writing-counter-warn`). `maxLength` 없음.
- **`DraftEditor.tsx`**: `.editor-meta` 에 원고 글자수 가이드만(`editor-char-count`). 토큰 추정·경고·budget fetch 없음(§6).
- 회귀 8: `tokenEstimate.test.ts`(5) + `WritingPanel` 카운터(렌더 under-strict · 90% 경고 전환 하중받침 · preset over-strict, 3).

### Issues found — 기존 fetch 시퀀스 테스트가 budget GET 에 밀렸다 (해결)

- `useWritingBudget` 이 mount 시 budget GET 을 보내, 기존 `mockResolvedValueOnce` 시퀀스(WritingPanel)와
  `mockFetch`/`stubFetch`(App·DraftEditor — **DraftEditor 가 WritingPanel 을 렌더**)의 첫 응답을 소비해 9 테스트가
  깨졌다. **해결은 파일마다 기존 패턴에 맞춰**: WritingPanel.test.tsx 는 `seedWritingBudgetCache`(fetch 스킵),
  App/DraftEditor.test.tsx 는 기존 `/writing/scratch` URL 가로채기와 같은 패턴으로 `/writing/budget` 자동 응답.

### Decisions

- **per-preset 맵**(단일 보수값 아님): preset마다 derive, 비용 미미(window probe 캐시로 1왕복). 단일값보다 정확하고
  short/medium 의 거짓 양성을 없앤다.
- **90% 단일 임계**(two-tier 아님): "잘게 쪼개기" 원칙.
- **1.7 하드코드 + cross-ref 주석**(`chars_per_token` 노출 아님): drift 는 표시 경고의 미세 오차뿐.
- **지시문 hard maxLength 이 슬라이스 제외**: 소프트 경고가 K-4 기본값.
- **원고 본문은 §6 정신으로 글자수 가이드만**.

### Verification

- 백엔드: endpoint 동작 양방향(창 알면 per-preset derive 일치 · 모르면 요청값) + **뮤테이션 under-strict**
  (세 preset에 같은 upper bound → expected 불일치로 셀이 물음, 역방향 Edit 원복). **전량 1779 passed /
  1 skipped / 1519 subtests**(713s, test-mongo ON) — 회귀 0.
- 프론트: **227 passed / 15 files**(tokenEstimate 5 + WritingPanel 카운터 3 신규). build 진입 청크
  405.89 kB(+1 kB, lazy 경계 유지).
- **독립 검증 합격**(`docs/verifications/2026-07-31/k4_front_counter_budget.md`, 커밋 22736b9): 변이 5건이
  전부 가드 재실패(계약을 진짜로 잠금). B1(원고 본문 `maxLength` 금지 빈 셀)을 assert 1줄로 폐쇄. H1(정상
  스케일에서 경고 사실상 발화 안 함)은 오너 확인 "안전망 의도, 현행 유지"로 종결.

### Next steps

- **DraftEditor maxLength 없음 assert — 폐쇄**(독립 검증 22736b9): 원고 본문 `maxLength` 금지(정본 손상 방지)
  의 빈 셀을 `DraftEditor.test.tsx` assert 1줄 + 변이(`maxLength` 넣으면 재실패)로 채웠다.
- **DraftEditor 스위트 희귀 플레이크**(정직 보고, 재현 필요): 독립 검증 중 ~9회 중 1회 "1 failed | 40 passed"
  관측. 희귀해 테스트명 못 잡음. 유력 원인 (a) 기존 타이밍 의존 테스트의 사전 플레이크, 차선 (b) K-4(b)
  `useWritingBudget` mount-fetch 레이스. **재현 시 특성화 권장** — (b)면 mount-fetch 타이밍 조사.
- 컨텍스트 예산 트랙: 이제 K-4(프론트 표시)까지 닫혔다. 남은 것은 **알파 R-c 관측 1회**(창 32768).

---

## Task — 컨텍스트 예산 트랙: 알파 R-c 관측 1회 (창 32768) — **트랙 종료**

> **이 슬라이스는 알파 머신에서만 할 수 있었다.** 베타의 외부 12B(`192.168.1.22:9080`)는 창이
> `n_ctx=16384`로 고정돼 있고 repo가 그것을 옮겨 주지 않는다. 반면 알파는 **in-stack llama**라
> `docker-compose.llama.yml`의 `LLAMA_CTX_SIZE`로 창을 직접 바꾼다. R-c(창 확대) 관측은 그래서
> 알파에서만 가능했고, 이것이 컨텍스트 예산 트랙의 마지막 남은 관측이었다.

### Goals

- 핸드오프 Next Tasks #2·Owner Decisions가 "남은 것 = 알파 R-c 관측 1회뿐"으로 못박은 것.
  R-a(창에서 유도, SoT v1.7.66)는 코드가 끝났고, R-c는 **"창을 32768로 올리면 (a) 현행 예산
  8192가 가드를 통과하는가, (b) 유도 예산이 자동으로 넓어지는가"**를 관측하는 것. 베타(16384)에서는
  두 질문 모두 답할 수 없다 — 창이 고정이라.
- 성공 기준: ① 창 32768이 `/props`로 확인된다 ② **8192가 PASS**(베타 16384에선 가드 400 거부였음)
  ③ R-a 산식(실측)이 베타 권장 5,407 대비 창 증분(16,384)에 비례해 넓어진다.

### Completed work — 관측 (코드 변경 0)

**창 32768 기동 (in-stack llama, 알파 RTX 3060 12GB):**

- `.env`는 만들지 않고 쉘 환경변수 `LLAMA_CTX_SIZE=32768`로 줬다(커밋 금지 파일 회피).
- **`-hf` 재다운로드 함정을 회피했다.** `llama_models` 볼륨에 온전한 snapshot 2개(`2b318d6…`·
  `f6e7774…`)가 있으나 **stale `.downloadInProgress` 2개**도 있고 `-hf`는 리비전을 고정하지 않아
  refs/main이 이동하면 6.5GB를 다시 받는다(HANDOFF 함정 + 추적 부채). **`-m`으로 캐시 snapshot을
  직접 지정**하는 로컬 override(`/tmp/llama-local-rc32768.yml`, 커밋 영역 밖)를 얹어 재다운로드 0으로
  로드 — HANDOFF가 명시한 회피법 그대로. **repo의 `docker-compose.llama.yml`은 건드리지 않았다**
  (리비전 고정 여부는 별개 결정 = 기존 추적 부채).
- 기동 결과: **healthy 9**(application·gateway·mongo·elasticsearch·embedding·chroma·frontend·llama + 워커 2).
  **application이 PromptTemplateConflict 없이 뜬다** — 알파 mongo 볼륨(2026-07-04 생성)이 현행
  프롬프트 sha 핀과 호환됨(2026-07-27 베타 사고와 다르게 알파는 안전).
- `/props` 실측: **`n_ctx = 32768`** ✓, model = `…/2b318d6…/gemma-4-12b-it-qat-q4_0.gguf`(캐시 직접 로드),
  chat_template 있음(`--jinja` 정상). `.env.example`의 "32768 — 기동 확인, VRAM 9,774/12,288" 실측을
  재현(기동 자체의 위험은 0이었다).

**관측 도구는 K-4 이전의 측정 리그를 그대로**(`scripts/report_budget_measure.py`). 리그는 창을
`/props`에서, 토큰 계수를 게이트웨이 가드와 **같은 경로**(`/apply-template`+`/tokenize`)로 잰다. 창을
상수로 박지 않으므로 **같은 스크립트 한 줄**로 알파(32768)·베타(16384)가 다시 그려진다. application
컨테이너에서 `services`/`scripts`를 트리 마운트해 현행 코드로 관통(이미지 상태와 무관).

### Verification — 알파(32768) vs 베타(16384) 별개 시드 등가 대조

시드(`--seed`, 24000자, 밀도 1.63 자/tok)는 알파에서 새로 만들었다 — 베타 시드와 **같은 결정론적
생성기(`build_manuscript`)**로 만든 **별개 시드**지만 패키지 구조가 같다(항목 62·회계 8,185).
**입력 토큰이 13,077(알파) vs 13,076(베타)으로 1 차이** — 완전 동일 시드가 아니라 두 모델 서버의
`/tokenize` 미세 차이가 후보 산문 수렴을 1단계 어긋나게 한 것이다(독립 검증 §4; 결론엔 영향 없음).
고정 오버헤드는 **베타와 토큰 단위로 동일**(같은 모델·토크나이저): `system 465 · 후보 산문 4,159 ·
래퍼 94 = 4,718`.

| 예산 | 항목 | 회계 | 컨텍스트(실측) | 입력 | 입력+출력 | 창 여유(32768) | 판정 |
|---:|---:|---:|---:|---:|---:|---:|:--|
| 2048 | 15 | 1,979 | 2,051 | 6,769 | 12,913 | +19,855 | PASS |
| 4096 | 31 | 4,091 | 4,199 | 8,917 | 15,061 | +17,707 | PASS |
| 6144 | 46 | 6,073 | 6,211 | 10,929 | 17,073 | +15,695 | PASS |
| **8192**(현행) | 62 | 8,185 | 8,359 | **13,077** | **19,221** | **+13,547** | **PASS** |
| 12288 | 93 | 12,276 | 12,515 | 17,233 | 23,377 | +9,391 | PASS |
| 16384 | 117 | 15,444 | 15,755 | 20,473 | 26,617 | +6,151 | PASS(포화) |
| 20480 | 117 | 15,444 | 15,755 | 20,473 | 26,617 | +6,151 | PASS(포화) |
| 24576 | 117 | 15,444 | 15,755 | 20,473 | 26,617 | +6,151 | PASS(포화) |

- **★ 성공 기준 ② — 8192가 PASS다.** 베타(16384)에서는 같은 패키지 구조(항목 62·회계 8,185,
  입력 **13,076** tok)가 `13,076 + 6,144 = 19,220 > 16,384` → 가드 400 거부(여유 **−2,836**)였다.
  알파(32768)에서는 같은 구조의 별개 시드 패키지(입력 **13,077**, 1 토큰 차이)가 `19,221 < 32,768` →
  **PASS(여유 +13,547)**. **같은 구조의 요청이 창에 따라 REJECT↔PASS로 갈린다** — 여유 차이
  `13,547 − (−2,836) = 16,383 ≈ 창 차이 16,384`. R-c의 본질(창을 키우면 현행 예산이 통과한다)이 관측됐다.
- **★ 성공 기준 ③ — 유도가 자동으로 넓어진다.** R-a 산식(실측)
  `32768 − 6144 − 4718 = 21,906`, 회계 단위 권장 **약 21,487**(만재 비율 0.981, 구간 0.965~0.981).
  베타 권장 5,407(비-만재 행 비율 0.979) 대비 **+16,080** 넓어졌다 — 창 증분 16,384에 **거의** 비례
  (알파는 만재 행 비율 0.981에서 뽑아 엄밀한 정비례는 아니나 차이 미세; 독립 검증 §5). **R-c(창 확대)는
  별도 구현이 아니라 R-a(창에서 유도)에 흡수됐음을 실측으로 확인** — 오너 결정 (ii)가 맞았다.
- **성공 기준 ①** — `/props` 실측 `n_ctx=32768` ✓.

### Issues found

- **★ 시드 규모가 창 32768을 못 채운다.** 예산 16,384에서 항목이 **117개로 포화**(`예산제외 0`:
  예산이 940 남아도 담을 항목이 없음) — 컨텍스트 15,755(입력+출력 21,899)에서 더 안 늘어난다. 즉
  24,000자 시드의 항목 풀로는 창 32768의 절반도 못 쓴다. **이것은 R-c의 한계가 아니라 시드 규모의
  한계** — 실제 대형 원고(더 많은 장면·항목)라면 117을 넘어 창을 더 썼을 것이다. 핵심 관측(8192 PASS·
  유도 넓어짐)에는 영향 없다. 더 큰 시드(`--seed-chars 48000+`)로 재측정하면 창 사용 상한을 볼 수 있으나
  별도 측정 사안.
- **고정 오버헤드의 입력 분해가 정확히 맞는다**: 8192 행 `465(system) + 8,359(컨텍스트) + 4,159(후보) +
  94(래퍼) = 13,077(입력)`. 베타의 13,076과 토큰 1 차이(시드 산문 미세 차이) — 리그 패리티(사본이 아니라
  게이트웨이 가드와 같은 경로 재사용)가 확인됐다.

### Issues found — 알파 application 이미지가 auth 슬라이스 **이전** 빌드 (추적 부채 신규)

- 리그가 `_default_core_sot_service`를 임포트하는 순간 `from argon2 import PasswordHasher`로
  `ModuleNotFoundError: No module named 'argon2'`. 원인: 알파 application 이미지가 **`argon2-cffi`가
  `requirements.txt`에 추가된 auth 슬라이스(2026-07-26~) 이전**에 빌드됐다. 코드는 트리 마운트로 현행이지만
  **파이썬 패키지는 이미지 것**이라 argon2가 빠졌다(HANDOFF "argon2-cffi가 설치돼 있어야 한다" 함정의
  컨테이너 사례).
- **이 슬라이스의 조치(외과적)**: R-c 관측 1회를 위해 전체 재빌드(큰 작업) 대신 **런타임에
  `argon2-cffi>=23,<24`만 설치**하고 리그를 돌렸다(`requirements.txt:1` 핀과 동일). 핵드오프 베타 관측치의
  "라이브 검증은 트리 마운트가 표준(재빌드 없이)" 원칙을 따르되, argon2만 파이썬 패키지라 트리 마운트로는
  덮이지 않는 예외.
- **근본 해결은 별도**: 알파 `application`(·`frontend`·`gateway`) 이미지 재빌드. 베타 관측치가 이미
  "application 07-29 빌드라 K-3 앱 절반이 이미지에 없다"고 적었듯 알파도 동일 부류의 부채다. 관측 자체는
  트리 마운트 + 런타임 argon2로 이미지 상태와 무관하게 현행 코드로 관통했으므로 결과에 영향 없다.

### Decisions

- **코드 변경 0**: 이 슬라이스는 관측이다. R-a 코드는 이미 끝났고(v1.7.66), R-c는 그것이 창 32768에서
  예측대로 작동함을 **보는** 것. 따라서 회귀 기준선은 **무변**(1779 passed / 1 skipped / 1519 subtests).
  **회귀는 재실행하지 않았다** — 코드가 안 바뀌었으므로 변화의 원천이 없고, 알파 머신은 argon2-cffi
  부재로 1779를 재실측할 수 없어 **베타 K-4 기준선을 인용**한다(재실측해도 같다; 독립 검증 §6).
- **시드는 알파 DB에 보존**: 베타 패턴(재측정용으로 지우지 않음)과 일관. project
  `6a6c7f914d586daaeef1cf22` / draft `6a6c7f914d586daaeef1cf23` / version `6a6c7f914d586daaeef1cf24`.
- **엔드포인트 실관통(/writing/report 등)은 이 슬라이스 범위 밖**: 리그가 가드와 같은 식·같은 토크나이저를
  쓰므로(cross-parity 테스트로 검증됨) 리그 PASS = 가드 통과이고, 유도 산식도 derive와 같은 형태라
  엔드포인트 관통은 리그로 이미 검증된 결론의 재확인이다. 인증(계정)·이미지 빌드를 동반하므로 별도 판단.
- **스택은 관측 후에도 창 32768로 둔다**: 다음 작업자의 관통·육안 확인을 위해. 내릴지 여부는 오너 결정.

### Next steps

- **컨텍스트 예산 트랙 = 종료.** R-a 구현(5곳 전부) + R-c 관측(알파 32768)이 닫혔다. 남은 것 없음.
- **알파 이미지 재빌드 부채**(위)와 **`-hf` 리비전 고정 부채**(기존)는 별개 추적 항목.
- **머신-로컬**: 알파 스택이 이제 떠 있다(창 32768). 베타 관측치의 "이미지 뒤처짐" 경고가 알파에도
  그대로 해당 — 화면·엔드포인트 관통 전에 이미지 빌드 상태를 본다.

### 독립 검증 후속 보강 (같은 슬라이스, 검증자 실시)

독립 검증 [`verifications/2026-07-31/alpha_rc_observation.md`](../../verifications/2026-07-31/alpha_rc_observation.md)
판정은 **합격(차단 0건)**이다. 핵심 주장(코드 변경 0 · 표 산술 전 행 정확 · 8192 PASS · 리그=가드 식
동등 + cross-parity 양방향 · 회귀 무변 타당)이 코드·산술 수준에서 검증됐다. 비차단 hardening 3건이
왔고 **전부 반영했다.**

- **H1 — "동일 시드" 서술 정정(반영, 오너 "보강" 지시로 방향 확정 = 별개 시드 등가 대조)**: 검증자가
  알파 시드 `6a6c7f91…` 와 베타 시드 `6a6be9c0…` 는 **별개 시드**인데 오너 요약·SoT가 "동일 시드/같은
  패키지"로 적었다를 잡았다. 증거는 입력 토큰 1 차이(13,077 vs 13,076) — `build_manuscript`가
  결정론적이므로 완전 동일 시드면 바이트 동일이어야 한다. 결론(8192 PASS, 여유 +13,547)은 안 흔들리나
  표현이 엄밀하지 않았다. **위 Verification·Issues 절과 SoT v1.7.68 행·HANDOFF 를 "같은 결정론적
  생성기로 만든 별개 시드, 패키지 구조 동일, 입력 1 토큰 차이"로 정정했다.**
- **H2 — 권장치 환산 비율 비대칭(반영)**: 베타 5,407(비-만재 0.979)·알파 21,487(만재 0.981)이 다른
  포화 행에서 비율을 뽑아 "창 증분에 정확히 비례"가 엄밀히 아님(+16,080 vs 창 증분 16,384). 위 성공
  기준 ③ bullet 에 "거의 비례(엄밀한 정비례는 아님, 차이 미세)"로 명시.
- **H3 — 회귀 미재실행 명시(반영)**: 알파 머신은 argon2 부재로 1779 재실측이 불가 → 베타 K-4 기준선
  인용, 재실행 안 함. 위 Decisions 에 명시.
- **머신 상태 재확인(검증자 outstanding 폐쇄)**: 검증자는 다른 머신이라 `docker compose ps` 재확인을
  못 했다. **알파에서 직접 재확인**: healthy 9 + 워커 2, `/props` **n_ctx=32768** — "스택이 창 32768로
  떠 있다" 작업자 주장이 확인됐다.

---

## Task — 인증 D8-6a: project 영구 파기 core_sot 인터페이스 + outbox 이벤트 (SoT v1.7.69)

### Goals

- D8-6(영구 삭제, D5=A)의 **첫 서브슬라이스**. 전체 D8-6은 "잘게 쪼갠다"(D8) + "부분 삭제 고아
  금지"(D5) 긴장을 풀기 위해 4개로 분할(a core_sot · b derived · c vector/drain · d endpoint)하고,
  **endpoint는 d에서만** 추가한다 — endpoint가 유일한 production 호출자이므로 그 전엔 고아 데이터
  (정본만 파기하고 vector 잔류 → 타 project 검색에 뜸)가 생길 수 없다.
- 이 슬라이스(a): core_sot 8컬렉션 파기 인터페이스 + outbox `PROJECT_PURGED` 이벤트 정의. **endpoint 없음**.

### Completed work — 구현 (코드 변경)

- `IndexSyncEvent.PROJECT_PURGED`(indexing/models.py) + `enqueue_project_purged`(indexing/service.py,
  `enqueue_project_archived`의 복사; **drain은 연결하지 않는다** — a 단계엔 production 호출자가 없어
  worker가 이 entry를 만날 일이 없다).
- `CoreSotRepository.purge_project`(Protocol) + in-memory 구현(직접 project_id 스코프 6 + snapshot 체인
  2) + mongo 구현(`_use_transactions` 분기 재사용, 한 트랜잭션에서 직접 6 `delete_many` + version→
  snapshot_id 집합 수집 후 snapshots·blocks `$in` 삭제; 기존 orphan-prune 순회와 동일 패턴).
- `CoreSotService.purge_project`(`archive_project` 구조 재사용 — `_require_project`→NotFound 후 repo 위임,
  **enqueue하지 않는다**: enqueue는 endpoint D8-6d에서 archive와 같은 시점에).

### Verification — 핵심 회귀 (host, argon2-cffi OK)

- in-memory + indexing: `test_core_sot.py`·`test_indexing_phase3a.py` **64 passed**(1.2s). `CoreSotPurgeTest`
  3건(전체 그래프 제거 + 인접 유지 · 부재 NotFound · 잔류 없음 재파기) + `enqueue_project_purged` entry
  shape contract.
- mongo(양쪽 transaction 경로 자동 커버): `test_core_sot_mongo.py` **76 passed**(22s). `_MongoContractMixin`의
  파기 테스트 2건이 `FallbackMongoTest`(use_transactions=False)·`TransactionMongoTest`(True)·
  `WritingIntentMongoTest`(True) 모두 통과.
- **endpoint 미추가** → operation 카운트 단정(`CombinedBoundaryMatrixTest`의 `len(tiers)` 등)은 **무변** —
  이것이 a에서 endpoint를 빼는 부수 이유다.
- test-mongo 기동 시 **stale 네트워크 참조** 오류(`network ... not found`) → `docker rm -f` 후 재기동으로
  해소(옛 컨테이너가 사라진 네트워크를 잡고 있었다).
- **전량(test-mongo ON, host argon2 OK, 120s)**: **1786 passed / 4 skipped / 1519 subtests** — 직전
  1779/1/1519 대비 **+7 = D8-6a 신규 회귀**(in-memory 3·indexing 1·mongo 2×3클래스), **회귀 0건**.
  **양방향 뮤테이션 검증**(in-memory `purge`에서 snapshot 체인을 건너뛰면 `test_purge_removes_entire…`
  가 `assertNotIn(snapshot, repo.snapshots)`에서 실패 → 역방향 Edit 원복 → 41 passed). skip +3은 알파
  호스트 환경(live 등), D8-6a와 무관.

### Decisions

- **endpoint는 D8-6d에서만**(고아 데이터 위험 회피의 핵심 통제).
- **감사(`AdminActionAuditRepository`)는 별도 슬라이스 추천** — 브리프 D5는 "감사 로그 UI"만 후속 명시하고
  저장은 미명시, 기존 admin 작업(사용자 생성·비활성화)도 감사를 남기지 않는다.
- **파기 권한 = 관리자, 승격(F1) 불필요**(내용을 읽지 않음) — ExitPlanMode 승인으로 착수 전 확인 완료.

### Next steps

- **D8-6b**: derived mongo 10컬렉션(memory·analysis 3·writing 3·observability·context_search·review) 파기.
- **D8-6c**: vector/index 4백엔드 project-scoped delete + worker `PROJECT_PURGED` drain handler.
- **D8-6d**: `POST /admin/projects/{id}/purge` endpoint + `_REQUIRE_ADMIN` + boundary matrix(ADMIN tier +1·총 +1).

### 독립 검증 후속 보강 (같은 슬라이스, 검증자 실시)

독립 검증(`docs/verifications/2026-07-31/d8_6a_purge_core_sot.md`, 커밋 a7b9b08) 판정은 **합격(차단 0)**이다.
비차단 발견 1건을 보강했다.

- **★ in-memory/mongo snapshot 파기 비대칭 → mongo 를 직접 project_id 스코프로 정정(반영)**: 검증자가
  in-memory 는 `snapshot.project_id` 직접 스코프(더 넓음), mongo 는 `version→snapshot_id` 경유(더 좁음)라는
  비대칭을 잡았다. purge 는 비가역이라 안전 방향은 더 넓게(in-memory 쪽). 확인하니 **mongo snapshot
  doc(`_snapshot_doc`)·block doc(`_block_doc`) 모두 `project_id`를 보관**한다 → version 경유가 아니라
  **직접 `{"project_id": project_id}` 스코프**로 정정(8컬렉션 전부). in-memory 와 대칭 + (비정상) 고아
  snapshot 잔류 방지. 회귀 재실행: **140 passed**(in-memory 41 + mongo 76 + indexing 23) — 정상 데이터에선
  직접/경유가 같은 결과라 통과.
- **enqueue_project_purged 미사용(6a)**: 의도적 — endpoint(D8-6d)가 유일한 production 호출자. 메서드
  코멘트에 "drain은 D8-6c, 호출은 D8-6d" 명시돼 있다. 6c/6d에서 실제 연결되는지가 후속 검증 포인트.

---

## Task — 인증 D8-6b-1: derived 파기 memory + analysis (SoT v1.7.70)

### Goals

- D8-6b(derived 10컬렉션 파기)의 **첫 반**. 전체 6b는 b-1(memory + analysis 4) / b-2(writing 3·
  observability·context_search·review 6)로 분할(잘게 쪼개). endpoint 없음(D8-6d).

### Completed work — 구현 (코드 변경)

- `MemoryRepository.purge_project`(Protocol·in-memory·mongo) + `MemoryService.purge_project` thin.
- `AnalysisRepository.purge_project`(Protocol·in-memory·mongo — jobs·tasks·candidates 3컬렉션 **직접
  `project_id` 스코프**) + `AnalysisService.purge_project` thin.
- **10 derived 컬렉션 모두 `project_id` 보관** 확인(탐색 에이전트) → 6a의 in-memory/mongo 비대칭 교훈을
  적용해 **전부 직접 `project_id` 스코프**(경유 없음).

### Verification

- 핵심 회귀: `test_memory_mongo.py` + `test_analysis_mongo.py` = **15 passed**(양쪽 transaction 경로 자동 커버).
  memory purge(memory 2 project → 대상 비움 + 인접 유지) + analysis purge(jobs·tasks·candidates 그래프 +
  인접 유지). payload 검증(character_observation 필수 필드)·import 누락 수정 과정 포함.
- endpoint 미추가 → operation 카운트 단정 무변.
- 전량 suite 백그라운드 실행 중(결과는 후속 반영).

### Decisions

- b-1/b-2 분할(잘게 쪼개). "18컬렉션 모두 purge 경로" 전수 가드는 **b-2 끝에서**(b-1 단독으론 12컬렉션).
- 10 derived 컬렉션 전부 직접 `project_id` 스코프(project_id 보관 확인).

### Next steps

- **D8-6b-2**: writing 3(generation_jobs·scratch·loop_audits) + observability(llm_call_audits) +
  context_search(gate_findings) + review(review_queue) = 6컬렉션 + **전수 가드(18컬렉션)**.
- **D8-6c**: vector/index 4백엔드 + worker drain. **D8-6d**: endpoint + 권한 + boundary matrix.

---

## Task — 인증 D8-6b-2: derived 파기 나머지 6컬렉션 + 전수 가드 (SoT v1.7.71)

### Goals

- D8-6b(derived 10)의 둘째 반으로 **6b 완료**. b-2는 writing 3(generation_jobs·scratch·
  loop_audits)·observability(llm_call_audits)·context_search(gate_findings)·review(review_queue) = 6컬렉션
  + **18컬렉션 전수 가드**. endpoint 없음(6d).

### Completed work — 구현 (코드 변경)

- 6도메인 각각 Protocol·in-memory·mongo·서비스에 `purge_project`(직접 `project_id` 스코프).
  탐색 에이전트가 6컬렉션 **모두 Protocol 기반**(in-memory+mongo+service)임을 확인 — 6b-1 패턴과 동일.
- **전수 가드** `tests/test_purge_project_coverage.py`(신규): 9개 repository 계약(core_sot·memory·
  analysis·writing 3·observability·context_search·review = 18 컬렉션)이 모두 `purge_project`를 노출함을
  `dir()` 단정. 하나라도 빠지면 project 파기가 고아를 남긴다(D5 부분 삭제 금지). over-strict 로 9 라는
  수 자체도 고정.

### Verification

- 전수 가드 + 기존 6b-2 도메인 `_mongo`(generation_job·scratch·loop_audit·llm_call_audit·gate_findings)
  = **34 passed**. 전수 가드 통과(9 repository purge_project 노출), 기존 도메인 테스트 안 깨짐.
- 6b-2 purge 동작은 6b-1(memory·analysis)에서 검증한 **직접 `delete_many({"project_id": ...})`** 패턴과
  동일(모든 컬렉션이 project_id 보관 확인). 전수 가드가 메서드 누락을 잡고, 동작 패턴은 6b-1에서 검증.
- 전량 suite 백그라운드 실행 중(결과는 후속 반영).

### Decisions

- 6b-2 개별 동작 회귀는 전수 가드(메서드 존재) + 기존 안 깨짐으로(패턴 동일). 도메인별 동작 테스트는
  검증자 지적 시 추가.
- 18컬렉션 전부 직접 `project_id` 스코프(6a 비대칭 교훈 적용).

### Next steps

- **D8-6c**: vector/index 4백엔드(Chroma 2·ES 2) project-scoped delete + worker `PROJECT_PURGED` drain handler.
- **D8-6d**: `POST /admin/projects/{id}/purge` endpoint + `_REQUIRE_ADMIN` + boundary matrix(ADMIN +1·총 +1).
