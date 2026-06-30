# Verification — Phase 2A runner execution decisions brief (commit 54df31e)

## Subject metadata

- 날짜: 2026-06-30
- 요청자: 사용자 ("커밋하고 다음 작업까지 진행했습니다" — 54df31e 검증)
- 검증자: Claude (독립 감사, 문서 작성 미관여)
- 대상: commit `54df31e` "Add Phase 2A runner execution brief" — 신규 문서 `docs/plans/02-analysis-runner-execution-decisions.md`
- 정본 계약 참조:
  - `docs/system-contract-sot.md` v1.6.11 (runner 계약 v1.6.4/v1.6.5, job-state v1.6.9/v1.6.10, HTTP API v1.6.11)
  - `docs/plans/02-analysis-job-state-decisions.md` (브리프가 인용하는 replay 의미)
  - 구현 코드: `services/application/app/analysis/runner.py`
- 검증 대상 소스: commit `54df31e` (working tree clean)

## Scope

이 commit은 구현이 아니라 **결정 브리프**다. 따라서 감사 기준도 다르다: 코드가 계약을 만족하는가가 아니라, (a) 브리프가 현재 상태를 정확히 기술하는가, (b) 승인 대기 상태로 위생적으로 처리됐는가(SoT 미변경/미구현), (c) 추천안이 기존 계약과 모순되지 않는가, (d) 미결정 항목이 사용자 결정으로 명확히 남겨졌는가. **추천안 자체의 승인/기각은 사용자 영역이며 본 검증이 판단하지 않는다.**

1. 브리프 위생: 상태, SoT 비변경, 구현 부재.
2. "현재 확정된 경계" 절의 사실 정확성(코드/SoT 대조).
3. 6개 질문 추천안의 기존 계약 정합성.
4. README/HANDOFF 갱신의 적절성.
5. 승인 필요 항목이 사용자 결정으로 명확히 분리됐는가.

## Methodology

브리프 전문 직독 → 각 "확정 경계" 주장을 코드(`runner.py`)와 SoT(v1.6.4/5/9/10/11)에 대조 → `git show 54df31e`로 README/HANDOFF diff 확인 → runner 실제 signature 검증. worker 주장은 복사하지 않고 primary source에서 재도출.

## Findings

### F1. 브리프 위생 — PASS

- 상태 `Decision Required`(`02-analysis-runner-execution-decisions.md:3`). 승인 대기로 정확히 표기.
- commit이 `docs/system-contract-sot.md`를 건드리지 않는다(`git show 54df31e --stat` 확인). 미승인 브리프가 정본 계약 버전을 올리지 않았다 — 올바르다.
- 구현 코드/테스트 변화 없다. 순수 문서 commit. "사용자 승인 후 다음 순서로 구현한다"(`:96`)로 구현을 승인 뒤로 미뤘다.

### F2. "현재 확정된 경계" 사실 정확성 — 1건 부정확 (I1)

- `:11` "source validation이 구성된 AnalysisService만 받는다" → `runner.py:63-66`이 `source_validation_enabled` 아니면 `AnalysisRunnerConfigurationError`. 정확.
- `:12-14` 새 pending job만 실행/상태무관 replay, failed terminal·새 idempotency_key, all-or-nothing=candidate write 한정 → SoT v1.6.9/v1.6.10과 정합.
- `:15-19` 3개 API, runner/Gateway 미시작 → SoT v1.6.11과 정합.
- `:20-21` Gateway/tool-call 미확정, 외부 queue 전제 안 함 → HANDOFF와 정합.
- **`:10` "Phase 2A runner는 이미 동기 함수형 orchestration으로 구현되어 있다" → 부정확.** `runner.py:71`은 `async def run(...)`이고 테스트는 `await runner.run(...)`(`tests/test_analysis_runner.py:76,124,...`)로 호출한다. runner는 async 코루틴이지 동기 함수가 아니다.

### F3. Q2 추천 근거가 F2의 오기에 의존 — PASS 불가 (I1과 동일 원인)

`:47` Q2 추천 "A. 초기 local MVP와 **현재 runner 계약에 맞춰** 동기 실행으로 시작한다"의 근거 "현재 runner 계약에 맞춰"가 `:10`의 거짓 전제(동기 runner) 위에 있다. 실제 runner는 async라 동기 HTTP 경로에서 직접 호출할 수 없고, `async def` 엔드포인트에서 `await`하거나 `asyncio.run` 브릿지가 필요하다. 승인자가 `:10`을 사실로 받아들이면 Q2를 잘못된 전제 위에서 결정하게 된다.

참고: Q2가 실제로 묻고 싶은 결정 축(요청-블로킹 동기 실행 vs background enqueue) 자체는 유효하다. 문제는 "동기/비동기"라는 단어가 Python sync/async(실제로는 async)와 요청-블로킹/백그라운드(실제 결정) 두 축을 뒤섞고, "현재 runner 계약에 맞춰"가 거짓 전제로 그것을 정당화한다는 점이다.

### F4. 나머지 추천안의 계약 정합성 — PASS

- Q1(별도 `POST .../run`, `:35`): 기존 3-엔드포인트 계약(v1.6.11)을 변경하지 않는 additive 경로. 단 구현 시 "surface가 runner를 시작한다"로 v1.6.11 의미가 바뀌므로 SoT minor bump가 필요함을 브리프가 옵션 A 설명에서 인지하고 있다(`:31`). 올바른 인식.
- Q3(replay 의미, `:51-58`): pending→실행, terminal/nonterminal→재실행 않고 반환, missing/cross-project→404. `02-analysis-job-state-decisions.md`의 "상태무관 replay, failed 재실행은 새 idempotency_key"와 정합하며 브리프가 이를 명시 인용(`:58`).
- Q4(runner factory 주입, `:70`): `create_app(..., analysis_runner=...)` — 기존 `analysis_service` 주입 패턴과 일관. "기본 factory는 fake/no-op로 두지 말고 실제 wiring 계약이 생길 때 추가"는 추측 구현 회피와 정합.
- Q5(envelope `{job, candidates, idempotent_replay}`, `:76-86`): 기존 read API payload literal 재사용. 실패 HTTP status 매핑은 미결정으로 명시(`:88`) — 사용자 결정 항목에 정확히 남김.
- Q6(source_ref 자동 생성 안 함, `:92`): v1.6.1(source_anchors 요구·기존 SourceRef 대조)과 정합.

### F5. README/HANDOFF 갱신 — PASS

- `docs/plans/README.md`: 신규 브리프를 항목 11로 등록(`:11`). 함께 `02-analysis-job-state-decisions.md`를 항목 10으로 보강 등록했는데, 이 문서는 기존에 README 목록에서 빠져 있었다(stated task 범위 밖이지만 색인 누락 수정이라 양성적).
- `HANDOFF.md`: Current Status에 브리프 라인 추가, Next Tasks #2가 "사용자 승인 필요"로 5개 항목(run endpoint, 동기 실행, replay 의미, runner 주입, 실패 envelope)을 명시, 프로젝트 구조 트리에 신규 문서 추가. 구현 완료로 오독될 문구 없음.

## Issues / Risks

- **I1 (blocking for brief accuracy)** — `:10` "runner는 이미 동기 orchestration"이 `runner.py:71` `async def run`과 모순. 이 거짓 전제가 Q2 추천 근거("현재 runner 계약에 맞춰 동기 실행", `:47`)를 지탱한다. 승인자가 Q2(동기/비동기)를 잘못된 사실 위에서 결정할 위험이 있다. → 조건: `:10`을 "runner는 async 코루틴으로 구현돼 있으며 호출 시 await/브릿지가 필요하다"로 정정하고, Q2의 "동기/비동기" 단어가 (a) Python sync/async와 (b) 요청-블로킹/백그라운드를 구분하도록 재구성할 것. 이 정정 후에야 브리프가 정확한 전제 위에서 승인 가능.
- **I2 (non-blocking, 권고)** — Q3의 "running 상태 job에 run 호출 시 재실행 않고 반환"(`:55`)은 신규 의미(기존 job-state 계약은 runner 내부 replay만 다룸). 브리프가 추천으로 명시하긴 했으나, 사용자 승인 시 이 케이스(run-on-running)의 HTTP 응답 의미가 `idempotent_replay=true`로 확정됨을 명시하면 더 완전하다.
- **I3 (informational)** — Q1 옵션 A 설명이 v1.6.11 "상태/결과 노출 surface" 의미 변경을 인지하긴 하나, B 추천을 채택해도 결국 "Application API가 runner를 시작한다"는 의미에서 v1.6.11은 갱신돼야 한다. 구현 slice 시 SoT minor bump 필요 — 브리프가 명시하지 않았으나 slice 2 검증 기준으로 자연스럽게 도출되므로 차단 아님.

## Verdict

**조건부 합격 (conditional pass).**

사유(load-bearing):
- 브리프 위생은 모범적이다 — `Decision Required` 상태, SoT 미변경, 구현 부재, 미결정 항목(특히 실패 HTTP envelope)을 사용자 결정으로 명확히 분리(F1, F5).
- 6개 질문 중 Q1/Q3/Q4/Q5/Q6 추천안은 기존 계약과 정합(F4).
- **그러나** `:10`의 "runner 동기 orchestration" 주장이 코드와 모순되고(F2), 이 거짓 전제가 Q2 추천의 근거가 된다(F3). 결정 브리프가 현재 상태를 정확히 기술하지 않으면 승인자가 잘못된 전제 위에서 결정하므로, 이것은 브리프 적합성의 닫기 조건이다.

합격으로 승격 조건: I1 한 건(`:10` async/sync 사실 정정 + Q2 재구성). I2/I3은 권고/informational.

**한계 명시:** 본 검증은 브리프의 *정확성과 위생*을 감사했을 뿐, run endpoint 도입·동기 실행·replay 의미·runner 주입·실패 envelope라는 5개 설계 결정의 승인/기각은 판단하지 않는다. 그것은 사용자 결정 영역이다.

## Outstanding items

- I1 정정 전까지 사용자는 브리프를 있는 그대로 승인하면 안 된다(특히 Q2).
- 정정 후 사용자가 5개 항목을 승인하면 SoT minor bump(v1.6.12 예상)와 함께 구현 slice 진입. 구현 시 run-on-running HTTP 응답 의미(I2)와 SoT 의미 변경(I3) 반영 권고.
- 작업 트리 clean, 양 commit 모두 committed.

## Reproduction

```bash
cd "/mnt/d/devel/에베베/ai_writte_system"
# 1. 브리프 전문 확인
sed -n '1,117p' docs/plans/02-analysis-runner-execution-decisions.md
# 2. 핵심 모순 확인 — :10 "동기" vs runner.py:71 "async def"
grep -nE "동기.*orchestration|이미 동기" docs/plans/02-analysis-runner-execution-decisions.md
grep -nE "async def run" services/application/app/analysis/runner.py
grep -nE "await runner.run" tests/test_analysis_runner.py | head -1
# 3. SoT 미변경 확인 (미승인 브리프)
git --no-pager show 54df31e --stat | grep system-contract-sot || echo "SoT untouched (correct)"
# 4. README/HANDOFF 갱신 확인
git --no-pager show 54df31e -- docs/plans/README.md HANDOFF.md
```
