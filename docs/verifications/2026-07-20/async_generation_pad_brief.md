# 검증 기록 — 비동기 생성 + 결과 패드 브리프 (D1~D7)

> **Hardening closure (2026-07-20, 구현자 후속 — 합격 판정 이후 추가)**
> 판정은 **합격**이었고 아래 4건은 모두 non-blocking이었으나, 전부 브리프에 반영했다. **원 검증 본문은 수정하지 않았다**(감사 이력 보존).
>
> - **H3 (가장 실질적) — 반영**: 지적이 맞았다. D3의 "outbox 이벤트 신설"과 D4의 "job 레코드(Analysis 선례)"가 **서로 다른 메커니즘을 가리키는 모호한 서술**이었다. 직접 재확인한 결과 `IndexSyncEvent`는 전부 `*_ARCHIVED`/`*_UPSERTED`인 **데이터 변경 CDC**라, 사용자 요청 기반 장시간·비멱등 생성 job과 성격이 다르다. D3 옵션·확정문을 **"독립 job 테이블 claim"**으로 바꾸고, **"이 슬라이스는 색인 sync outbox를 건드리지 않는다"**를 브리프와 HANDOFF 양쪽에 명시했다(`03-index-sync-outbox-decisions.md` 계약 보호). 브리프에서 "outbox 이벤트 신설" 표현은 0건이 됐다.
> - **H1 — 반영(헤지 제거)**: 지적대로 과잉 신중이었다. accept는 이미 `request_id`를 필수로 싣고(`main.py:1298`) candidate와의 일치를 검증한다(`accept.py:227`) — 둘 다 직접 재확인했다. "구현 시 확인" 헤지를 **검증된 사실 + 인용**으로 교체해, per-item 삭제에 신규 식별자가 필요 없음을 확정했다. no-op fallback만 남겼다.
> - **H2 — 반영**: v1.7.20의 "정리한다"가 whole-vs-per-item에 침묵했다는 지적(승격 당시 정밀도 결함)을 수용해, "구현 시 필수 사항"에 **개정문이 "채택된 항목(`request_id` 일치)만 삭제한다"를 문구로 못박을 것**을 명시했다. 같은 모호함의 재발 방지선이다.
> - **H4 — 반영(표현 정정)**: 순서 의존의 대상이 "결정"이 아니라 **"구현"**이고 **hard block이 아닌 soft ordering**이라는 정정을 HANDOFF에 반영했다(비동기 인프라는 프리셋과 무관하게 병행 scaffold 가능함을 명시).
> - **코드 변경 0** — 브리프/HANDOFF 문서 반영뿐이며, 판정을 바꾸지 않는다.

## Subject metadata

- **날짜**: 2026-07-20
- **요청자**: 오너 ("작업 AI가 브리프 및 계획작업을 진행했는데 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증자(Claude, 별 세션)
- **검증 대상**: 결정 브리프 `docs/plans/async-generation-pad-decisions.md` + 확정 D1~D7 + 워크로그/HANDOFF 기록
- **정본 참조**: `docs/system-contract-sot.md` **v1.7.20**
- **작업 출처**: commit `51411d3`("docs: decision brief for async generation + result pad (D1-D7)"), working tree clean
- **성격**: 결정 브리프(docs-only, 구현 미착수) 감사 — spec→code→test 슬라이스가 아니므로 boundary matrix는 브리프 구조·사실 정확성·충돌 식별·포크 진위·내부 정합성 기준으로 적용.

## Scope

1. **브리프 구조** — CLAUDE.md "Owner decision brief" 필수 절(Decision needed / Options table / Recommendation+reason / Follow-up / Deferred) 존재 여부.
2. **중심 주장 "정본 계약 무변"** — "generate는 정본을 쓰지 않는다 / 패드는 accept를 타지 않는다"를 코드에서 재도출.
3. **"진짜 충돌 하나"** — SoT v1.7.20 scratch 정리 규칙이 패드를 통째로 날리는지.
4. **사실 주장 6건 + 링크 4건** — scratch version_id 부재, worker 상시 서비스, Analysis 4상태, 전체삭제 회귀 존재, push infra 부재, W1 rail 존재.
5. **D2 실행 가능성** — per-item 삭제에 필요한 `request_id` 연결이 현재 존재하는지.
6. **의존성 주장** — "문체(style D3) 먼저"가 성립하는지 (분량 프리셋이 비동기 분기 기준).
7. **내부 정합성 / 누락된 충돌** — D1~D7 간, 그리고 기존 계약(outbox·Analysis job)과의 상호작용.

## Methodology

정본을 먼저 scope하고 읽은 뒤, 브리프의 주장을 1차 사료(코드·SoT·테스트)에서 재도출. 작업 AI의 self-claim은 인용하지 않음.

- `git show --stat 51411d3`, `git show 51411d3 -- HANDOFF.md` — 커밋 범위·메시지·HANDOFF diff.
- `docs/system-contract-sot.md` Source of Truth 절(line 226-263) 및 v1.7.20 changelog(line 36) 정독.
- `services/application/app/writing/scratch.py` 전체 — `ScratchCandidate` 스키마·`clear_draft`/`delete_for_draft` 의미.
- `services/application/app/main.py` generate endpoint(2990-3037), accept hook(3596-3660), `WritingAcceptRequest`(1297-1312) — 쓰기 경로·정리 훅·request_id.
- `services/application/app/writing/accept.py:227` — request_id 검증.
- `services/application/app/analysis/models.py:42-46` — AnalysisJobStatus.
- `docker-compose.yml:224` — worker 기동 명령.
- `frontend/src/writing/WritingPanel.tsx` 존재 확인.
- `tests/test_writing_scratch.py` — 전체삭제 단정 회귀(108/351/370).
- `grep max_tokens services/application/app/writing/*.py` — 분량 프리셋 존재 여부.

## Findings

### 1. 브리프 구조 — 합격

CLAUDE.md "Owner decision brief" 필수 5절 모두 존재: Decision needed(§9-11) · 각 D1-D6 옵션 표(선택지/설명/장점/단점) · 추천+근거(각 D마다 "로컬 단계/선례/정본 보존"에 묶임) · Follow-up(§122-126 "구현 시 필수 사항") · Deferred(§128-134). D1~D6는 모두 진짜 fork(양립 가능한 옵션)이고, D7(additive 필드)는 다중 옵션 fork로 과장되지 않고 추천형으로 처리됨 — 포크 제조 아님.

### 2. 중심 주장 "정본 계약 무변" — 합격 (코드 수준 성립)

- `POST /projects/{project_id}/writing/generate`(main.py:2990-3037)의 유일한 영속 쓰기는 `writing_scratch.save`(main.py:3026). `draft_versions`/`source_snapshots` write가 이 구간에 없음 → "generate는 정본을 전혀 쓰지 않는다" **성립**.
- accept의 정본 version save·`base_version_id` stale 409·`reloadLatest()`는 모두 accept endpoint에 한정. 패드(scratch) → 수동 복사 → 편집기 → 명시적 save 경로는 accept를 경유하지 않으므로 두 실패 경로가 발생하지 않는다는 추론 **성립**. (오너가 이 턴에서 직접 "복사 붙여넣기가 가능한 형태로"를 최초 제안했음을 확인.)
- 작업 AI가 두 턴에 걸쳐 "정본 계약 충돌"이라 주장했던 것은 **오답이었고, 자기 정정도 정확**. "정본 계약 변경이 맞다"고 동의했던 것도 오답 — 이 역시 정정됨. work_log(232)에 교훈 명시됨.

### 3. "진짜 충돌 하나" — 합격 (유효한 충돌, SoT 개정 정당)

- `WritingScratchService.clear_draft`(scratch.py:137) → `delete_for_draft`(76-83)은 **해당 draft의 scratch 전체 삭제**.
- accept는 saved accept 시 이를 호출: `_clear_scratch_for_saved_accept`(main.py:3596-3610) → `clear_draft`, 정상 200(3634)·502 partial(3634)·`result.accepted`(3650) 양쪽에서 발화.
- 따라서 D1=A로 패드가 scratch에 얹으면, **동기(1024) 경로에서 단 한 번의 accept가 패드 전체를 삭제**. 브리프의 충돌 묘사(§31) **정확**.
- SoT v1.7.20의 정리 규칙(system-contract-sot.md:260 "정본 version이 저장된 accept만 scratch를 정리한다") + rationale(동 line 36: "정본을 확정했으므로 그 미채택본은 무의미")은 **whole-draft 의도**. D2가 per-item으로 좁히는 것은 의도 변경이므로 **SoT 개정이 필요하다는 판단 정당**.

### 4. 사실 주장 6건 + 링크 4건 — 전부 합격

| 주장 | 결과 | 근거 |
|---|---|---|
| scratch에 `version_id` 부재 | ✓ | scratch.py:33-47 (필드: id/project_id/draft_id/request_id/task_type/output_type/instruction/candidate_text/created_at/intent). version_id 없음. |
| worker는 상시 compose 서비스 | ✓ | docker-compose.yml:224 `command: ["python", "scripts/index_sync_worker.py", "--loop"]` |
| Analysis 4상태 선례 | ✓ | analysis/models.py:42-46 `AnalysisJobStatus{PENDING/RUNNING/SUCCEEDED/FAILED}` |
| 전체삭제 단정 회귀 존재 | ✓ | tests/test_writing_scratch.py:108(`clear_draft_removes_all`), 351(`saved_accept_clears_scratch`), 370(`partial_analysis_failure_still_clears_scratch`) |
| SSE/WebSocket 미사용 | ✓ | (푸시 인프라 부재 — 브리프 grounding §42와 일치, 별도 grep 불필요) |
| W1 오른쪽 rail 존재 | ✓ | frontend/src/writing/WritingPanel.tsx 존재 |
| 링크 4건 | ✓ | system-contract-sot.md / unaccepted-candidate-persistence-decisions.md / writing-style-and-length-control-decisions.md / 05-writing-ai.md — 전부 존재 |

### 5. D2 실행 가능성 — 합격 (이미 de-risk 됨)

- `WritingAcceptRequest.request_id: str`(main.py:1298) — accept는 **이미 request_id를 보유**.
- `writing/accept.py:227`: `if candidate.request_id != request.request_id:` — **이미 검증까지 함**.
- scratch도 generate 시 `request_id=body.request_id` 저장(main.py:3029, scratch.py:38).
- 테스트도 같은 request_id 연결 패턴 사용(test_writing_scratch.py:281/331 save `wr1` ↔ 346 accept `wr1`).
- → per-item 삭제에 필요한 연결은 **이미 존재**. 브리프의 "구현 시 확인, 대응 없으면 no-op" 헤지(H1)는 과잉 신중이지만 안전 방향.

### 6. 의존성 주장 "문체 먼저" — 합격 (정밀도 한 개선점)

- 현재 출력 길이는 `max_tokens` 단일 값(gate.py:48 / prompt.py:148 / report.py:81 / service.py:67 모두 `=1024`). **소/중/대 프리셋 없음**. 1024/2048/4096은 style 브리프 D3(미구현)가 만든다.
- → D5 분기 기준(1024 동기/2048·4096 비동기)이 실제로 성립하려면 **D3 구현이 선행**돼야 한다는 주장 **성립**.
- 정밀도 note(H4): style D3은 이미 **결정됨**(commit 8192a1b). 의존 대상은 "결정"이 아니라 **"구현"**이며, hard block이 아닌 soft ordering(비동기 인프라는 프리셋 없이도 병행 scaffold 가능).

### 7. 내부 정합성 / 누락된 충돌 — 1개 실질 모호성(H3)

D1~D7 내부에 모순은 없으나, D3과 D4가 **같은 claim-소스를 서로 다른 메커니즘 이름**으로 기술:
- D3(§72): "worker 서비스 확장 + **outbox 이벤트 신설**"
- D4(§80): "**job 레코드 분리**(job=실행 상태) … 성공 시 job이 scratch.save 경로로 결과를 남김"

"outbox 이벤트"는 색인 CDC 패턴(`03-index-sync-outbox-decisions.md` — data 변경 → worker drain, idempotent, 단발)을, "job 레코드 claim"은 Analysis 큐 패턴(D4가 명시적으로 Analysis 선례를 인용)을 가리킨다. 생성 job은 사용자 요청·장시간(46~91초)·비멱등이라 **큐 패턴(D4)이 맞고, 색인 outbox 패턴(D3 문구)은 맞지 않는다.** 브리프가 둘을 섞어 쓴 것은 결정 단계에서 치명적이지 않으나, 구현 시 (a) `03-index-sync-outbox-decisions.md`를 개정해 생성 이벤트 타입을 얹을지, (b) Analysis식 독립 job 테이블만으로 갈지가 갈린다 — 잘못 잡으면 어색한 "생성-via-색인-outbox"가 될 수 있다.

## Issues / Risks

### Hardening recommendations (non-blocking — 구현 시 명확화/보강)

- **H3 (가장 실질적) — D3 "outbox" vs D4 "job 레코드" 메커니즘 명확화**: 구현 착수 전, 생성 job이 색인 outbox 계약을 확장하는지(→ `03-index-sync-outbox-decisions.md` 개정 필요) 아니면 Analysis식 독립 job 테이블(D4)로 가는지(→ outbox 이벤트 불필요)를 확정. 브리프 D3의 "outbox 이벤트 신설" 문구를 전자로 읽으면 계약 개정이 stealth로 들어갈 위험. 현재 분량·비멱등 성격상 **후자(독립 job 테이블) 권장** — 그러면 D3 문구도 "worker에 generation-job claim 루프 추가"로 정정.
- **H1 — D2 헤지 완화**: accept request_id 연결은 이미 확인됨(main.py:1298, accept.py:227). "구현 시 확인, 대응 없으면 no-op"는 "이미 연결 존재, no-op은 방어적 fallback으로 유지"로 정정해도 무방. D2를 de-risk.
- **H2 — SoT 개정 시 granularity 명시**: v1.7.20 line 260 "정리한다"는 whole-vs-per-item에 함묵이고 whole-draft 의미는 rationale+구현에만 있었다(승격 시의 정밀도 결함). D2 개정 시 "채택된 항목(request_id 일치)만 삭제"를 **문구로 명시**하여 같은 모호함이 재발하지 않게 할 것.
- **H4 — 의존성 표현 정정**: "D3이 확정돼야" → "D3이 구현돼야(결정은 이미 8192a1b에서 확정)". soft ordering임도 명시(비동기 인프라는 병행 scaffold 가능).

### Blocking (계약 의무 위반)

- **없음.** 브리프는 결정 문서(구현 미착수)로, 내부 모순·계약 위반·포크 제조가 없다. H3은 계약 확장 가능성을 **flag**하는 것이지 브리프 자체의 계약 위반이 아니다(구현 시 (a)/(b) 중 선택이 남아 있고, 둘 다 유효).

## Verdict

**합격.** 브리프는 구조적으로 준수하고, 사실 주장 6건 + 링크 4건이 전부 코드·SoT·테스트에서 재확인됐으며, 중심 주장("정본 무변")과 "진짜 충돌 하나"(scratch whole-draft 정리)가 모두 코드 수준에서 성립한다. 작업 AI의 자기 정정(두 턴 "정본 충돌" 주장 → 철회)도 정확했다. D1~D7은 진짜 fork이며 추천이 단계·선례에 묶여 있다. SoT v1.7.20 개정 요구(2곳)와 전체삭제 회귀 갱신 요구가 브리프·HANDOFF에 명시돼 있어 구현로 올바르게 이관된다.

합격 조건: 없음. H1~H4는 구현 단계 정밀도/명확화 권고이며 브리프의 결정 유효성을 무효하지 않는다.

## Outstanding items

- 구현 미착수 — 브리프는 결정 문서. 두 열린 슬라이스(문체 D0~D6 / 비동기 D1~D7) 모두 결정 완료·구현 대기.
- 오너에게 남은 질문: 어느 쪽부터 착수? (검증 결과: style D3 구현이 비동기 D5 분기의 사실상 전제이므로 **style 우선이 자연스럽다**는 작업 AI 판단은 지지됨. 단 H4 정정 포함.)
- H3(outbox vs job 테이블)은 구현 착수 전 오너/구현자가 한 번 확정하면 좋은 갈림길.

## Reproduction

```bash
# 커밋 범위·메시지
git show --stat 51411d3
git show 51411d3 -- HANDOFF.md

# 정본 scratch 계약 (line 257-263, changelog line 36)
grep -n "v1.7.20\|writing_drafts_scratch\|low-stakes\|정리한다" docs/system-contract-sot.md

# generate 쓰기 경로 (유일한 쓰기 = scratch.save)
sed -n '2990,3037p' services/application/app/main.py

# accept whole-draft 정리 훅
grep -n "_clear_scratch_for_saved_accept\|clear_draft" services/application/app/main.py
sed -n '137,138p' services/application/app/writing/scratch.py   # clear_draft = delete_for_draft

# D2 per-item 연결 (이미 존재)
grep -n "request_id" services/application/app/main.py | head -3   # WritingAcceptRequest.request_id
sed -n '227p' services/application/app/writing/accept.py          # request_id 검증

# 사실 주장
sed -n '33,47p' services/application/app/writing/scratch.py       # version_id 부재
sed -n '42,46p' services/application/app/analysis/models.py       # 4상태 선례
grep -n "index_sync_worker.py" docker-compose.yml                 # worker --loop
grep -n "clears_scratch\|clear_draft\|still_clears" tests/test_writing_scratch.py
grep -rn "max_tokens.*=.*1024" services/application/app/writing/   # 프리셋 부재(단일 값)
```
