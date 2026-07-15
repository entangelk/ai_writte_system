# B2b per-stage ceiling — live 12B 측정 (2026-07-15)

측정 도구: `scripts/measure_writing_stages.py` (SoT v1.6.87, M-i). raw 데이터: `writing_loop_per_stage_ceiling_q4.json`.

## Provenance

- **모델**: `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0` (외부 llama.cpp `192.168.1.22:9080`, gateway 경유).
- **스택**: 이 프로젝트 compose 풀스택(application/gateway/mongo[rs0]/embedding[BGE-m3-ko]/chroma/ES[nori]), gateway `LLAMA_BASE_URL=http://192.168.1.22:9080`, host 포트 override `MONGO_PORT=27019`/`GATEWAY_PORT=8011`. gateway `/health/ready=ready`.
- **정책**: 기본 `WritingLoopPolicy(2/1/3)` (revision 2·retrieval 1·gate 3). 최악경로 stage 카운트 = revise 2·report 2·gate 3·retrieve_plan 1·context_search 1.
- **repeats**: 3 (stage별 보수적 MAX). `complete=true`, `incomplete_stages=[]`.
- **project**: `6a573f8e6d46c52c517d02e7` (benchmark 전용, idempotent context seed).

## per-stage 측정 (보수적 MAX over 3 passes)

| stage | tokens (max) | wall-clock ms (max) | 비고 |
|---|---|---|---|
| revise | 323 | 1018 | |
| report | 766 | 5578 | 최대 token 기여 stage |
| gate | 815 | 3368 | |
| retrieve_plan | 368 | 1435 | |
| context_search | (token 제외) | 27024 | **콜드스타트 아티팩트** — 아래 참조 |

## raw ceiling (도구 출력)

- **`max_total_tokens = 4991`** = 2·323 + 2·766 + 3·815 + 1·368. (token은 콜드스타트 영향 없음 — 안정적.)
- **`max_wall_clock_ms = 51755`** = 2·1018 + 2·5578 + 3·3368 + 1·1435 + **1·27024(context_search)**.

## ⚠️ context_search 콜드스타트 caveat (wall-clock에만 영향)

context_search wall-clock이 pass별로 **27024ms(pass1) → 3924ms(pass2) → 4093ms(pass3)**. pass1의 27s는 측정 하네스의 **1회성 컨테이너 콜드스타트**(Chroma 클라이언트 초기화 + embedding 모델 첫 호출)다. **프로덕션 loop는 상시 실행 application에서 돌므로 context_search는 warm**이고, 27s는 재현되지 않는다(하네스 아티팩트).

따라서 wall-clock ceiling 해석 2가지:

- **A. 도구 raw(보수적, 콜드 포함)**: `51755 ms` (~51.8s).
- **B. steady-state(warm context_search max=4093ms 대입)**: 2036 + 11156 + 10104 + 1435 + **4093** = **`28824 ms`** (~28.8s). — 프로덕션 상시 app 기준 대표값.

token ceiling `4991`은 두 해석 모두 동일(콜드 무관).

## 다음 (오너, B4)

raw ceiling에 **B4 여유율**을 얹어 `WRITING_LOOP_MAX_TOTAL_TOKENS`/`WRITING_LOOP_MAX_WALL_CLOCK_MS` production 기본값(default-on 여부 포함)을 오너가 확정한다. wall-clock은 A(51.8s 콜드 포함) vs B(28.8s steady-state) 중 기준 선택 필요.
