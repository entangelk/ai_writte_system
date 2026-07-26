# 독립 검증 — 관측 KPI 대시보드 첫 화면

## Subject metadata

- **날짜**: 2026-07-26
- **요청자**: 오너 ("다음작업 검증해줘. 관측 KPI 대시보드 첫 화면 완료 — 커밋 c1c5ddd")
- **검증자**: 독립 검증자 (Claude, 별개 세션)
- **대상 슬라이스**: `/projects/:id/observability` 신설 — 증분 5의 집계 API를 소비하는 첫 화면. 프론트 전용, **SoT bump 없음**.
- **정본 계약 참조**: SoT v1.7.48 §"LLM 파이프라인 관측(KPI)" read-out 조항 (392–398줄) — **이번 슬라이스는 계약을 안 건드리므로 SoT 무변**. 결정 브리프 `docs/plans/observability-dashboard-decisions.md` (D1=C·D2=A·D3=A, Approved 2026-07-26).
- **작업 소스**: 커밋 `c1c5ddd` (HEAD). 작업 트리 clean. 파일: `frontend/src/observability/ObservabilityDashboard.tsx`(신규 290)·`.test.tsx`(신규 219)·`api/client.ts`(+10)·`App.tsx`(+20)·`styles.css`(+69)·`package.json`(+recharts)·브리프(신규 97)·HANDOFF·work_log·CHANGELOG.

## Scope

이 슬라이스의 성공 기준은 이중이다 — ① **백엔드·계약 무변**(순수 소비), ② **화면이 오독을 막는 것**. 둘 다 검증 대상.

1. **백엔드·공개 계약 무변** — `services/`·`tests/`·`system-contract-sot.md`·`schema.d.ts`가 c1c5ddd에서 변경 0인지, `gen:api` 재실행 후 no-drift인지.
2. **오독 방어 3종** (SoT v1.7.48) — `gate.avg_quality_score=null`·`loop.non_convergence_rate=null`·`multi_call_correlations`의 화면 처리.
3. **서버 순서·반올림 보존** — 화면이 재정렬·재반올림하지 않는지.
4. **색 접근성** — 팔레트 `#1a6d99`·`#9d2f2f`·`#a8742a`의 CVD 분리·명도대·채도·표면 대비.
5. **번들 분할** — `React.lazy` 경계, 진입 vs 차트 청크.
6. **회귀** — vitest(신규 10건)·백엔드(무변).
7. **mutation** — 오독 방어 3종 + 서버 순서의 양방향 가드.

## Methodology

스코프된 계약 읽기(SoT v1.7.48 read-out 조항은 이미 확정됨) → boundary matrix → 실행·mutation으로 셀 채우기. 색은 작업 AI 보고를 **독립 재계산**으로 실증.

**정확한 명령**:

- 백엔드 무변: `git show --stat c1c5ddd`로 `services/`·`tests/`·`SoT`·`schema.d.ts` 부재 확인 + `git diff 2374538 HEAD -- src/api/schema.d.ts`(빈) + `npm run gen:api` 후 `git status --short src/api/schema.d.ts`(clean).
- 백엔드 회귀(백그라운드): `python3 -m pytest tests/ -q -p no:cacheprovider`.
- 프론트: `npm run build`(`tsc --noEmit && vite build`) + `npm test`(vitest) 백그라운드.
- 색 CVD 독립 재계산: Python으로 sRGB→Lab(D65) → 정상 ΔE76(3쌍)·명도대 ΔL*·채도·WCAG contrast(vs `#f4f0e7`)·CVD 시뮬(Viénot/Brettel 근사 protanopia/deuteranopia/tritanopia) 후 ΔE76.
- **mutation 4종 (cp 백업 → Edit → `npx vitest run` → `diff -q` 복원)**:
  - **M1**: `score(null)` → `"0.00"` → null gate 방어.
  - **M2**: loop null → `"0%"` → loop 방어.
  - **M3**: multi-call 컬럼 헤더 → `"재시도"` → 중립 라벨 방어.
  - **M4**: 테이블 tbody `[...kpi.sites].sort(...)` 추가 → 서버 순서 보존.
  - 복원 후 Dashboard 10건 재실행으로 무결성 확인.

## Findings

### 1. 백엔드·공개 계약 무변 (성공 기준 ①)

- `git show --stat c1c5ddd`: 변경 파일 전부 `frontend/`·`docs/`·`HANDOFF`·`CHANGELOG`·`package*.json`. **`services/`·`tests/`·`system-contract-sot.md` 부재** → 백엔드·SoT 무변 ✓.
- `git diff 2374538 HEAD -- frontend/src/api/schema.d.ts`: **빈 출력** → schema.d.ts가 증분 5(2374538) 이후 무변 ✓.
- `npm run gen:api` 재실행 후 `git status --short src/api/schema.d.ts`: **clean** → no-drift ✓. "순수 소비" 성공 기준 충족.

### 2. 오독 방어 3종 (성공 기준 ②) — `ObservabilityDashboard.tsx`

SoT v1.7.48 read-out 조항(392–398)이 정한 3가지를 화면이 물려받았다:

- **D1 gate 점수 null** (159–164줄): `score(null)` → `"—"`, `kpi-note`에 `"측정된 호출 없음"`. 분모 `scored_calls` 동반.
- **D2 loop 미수렴율 null** (169–180): null → `"—"`, `kpi-note`에 `"루프 감사가 꺼져 있어 측정되지 않음"`. **load-bearing case**(loop 감사 opt-in, 기본 배포 정상 상태).
- **D3 multi_call_correlations** (259·279–283): 컬럼 헤더 `"여러 번 호출된 워크플로"`, 주석에 "재시도 횟수가 아님…작성 루프는 게이트·수정·보고를 설계상 여러 번 부른다".
- 토큰 분모 동반(153–155): `"${tokens_counted_from}건 기준 (응답 없는 호출 제외)"`.

### 3. 서버 순서·반올림 보존

- `chartRows`(`kpi.py`의 `sorted()` 결과를 그대로 map, 82–90)·테이블 tbody(`kpi.sites.map`, 263) 모두 **재정렬 없음**.
- `percent()`(65–68)는 표시용 변환(비율→% 문자열)이지 데이터값 반올림이 아님.
- 회귀 `test_keeps_the_server_s_site_order`(156–173)가 입력 순서 `[writing_gate, compare_judge]`를 보존함을 단정. M4로 검증.

### 4. 색 접근성 — 독립 재계산 (성공 기준 ④)

Python(sRGB→Lab D65→WCAG/CVD)으로 작업 AI 보고를 재계산. 결과(ΔE76, 단정 기준은 추세 비교):

| 항목 | 값 | 판정 |
|---|---|---|
| Lab L* | success 43.4 / providerError 36.8 / parseError 52.9 | 명도 분산 양호 |
| 정상 ΔE76 (3쌍) | 78.2 / 81.2 / 41.3 | 전부 큼 |
| 명도대 ΔL* (pro↔par) | **16.2** (적갈↔호박은 명도로 가장 잘 분리) | CVD 주 단서 충분 |
| WCAG contrast vs `#f4f0e7` | 5.00 / 6.41 / **3.55** | 전부 ≥3:1 PASS (parseError 여유 가장 작음) |
| CVD 시뮬 후 최소 ΔE76 | **26.7** (tritanopia pro↔par) | 작업 AI 보고 "초록↔호박 ΔE 2.4 붕괴" 대비 11배 — 추세 일치 |

- **색만으로 식별하게 두지 않음**: 범례(`<Legend/>`) + 상세 표가 같은 값을 반복 → WCAG 1.4.1 충족. 이것이 ΔE 수치와 무관한 핵심 방어.
- 주: 작업 AI의 "ΔE 2.4"는 검증기의 단위(ΔE2000 추정)와 본 검증자의 ΔE76이 달라 절대 스케일은 다르지만, "최종 팔레트가 초록↔호박보다 훨씬 잘 분리"라는 **추세는 일치**.

### 5. 번들 분할 (성공 기준 ⑤)

- `npm run build` 출력: 진입 `index-*.js` **401.19 kB** + 관측 화면 청크 `ObservabilityDashboard-*.js` **385.67 kB** (별도 청크).
- 작업 AI 보고(401.19 / 385.67)와 정확히 일치. `React.lazy` + `Suspense`(`App.tsx`)가 차트 라이브러리(recharts/d3)를 진입에서 분리 — 관측 화면을 열 때만 로드.
- 693 modules transformed (recharts/d3 포함). 진입은 이전 399.03에서 +2.16(401.19).

### 6. 회귀

- **vitest**: `204 passed (204) / 14 files`. 신규 `ObservabilityDashboard.test.tsx (10 tests)`. 작업 AI 보고와 정확히 일치.
- **백엔드 회귀(백그라운드)**: `1480 passed / 80 skipped / 612 subtests, 실패·에러 0`.
  - subtests **612 = 작업 AI 보고 612와 정확히 일치**.
  - 이전 증분 5 검증(610) 대비 +2 = 9c98a8a 커밋(증분 5 검증 hardening 반영)의 결과 — c1c5ddd는 백엔드 무변이므로 9c98a8a 상태 보존.
  - passed 차이 76(1556−1480) = 동일한 WSL2 skip 정책(80 vs 4). "그대로" 유효.

### 7. mutation 4종 (각각 해당 회귀만)

- **M1** `score(null)→"0.00"`: `test_labels_a_null_gate_score_as_unmeasured` 실패 — `queryByText("0.00").not`가 dd의 "0.00"을 잡음(양방향: "측정된 호출 없음" positive + "0.00" negative).
- **M2** loop null→"0%": `test_says_the_loop_audit_is_off` 실패 — `queryByText("0%").not`가 잡음. load-bearing case 보호.
- **M3** 컬럼 헤더→"재시도": `test_does_not_call_the_extra_call_column_a_retry_count` 실패 — `findByText("여러 번 호출된 워크플로")` 부재 + `queryByText("재시도").not` 발견(양방향).
- **M4** 테이블 sort 추가: `test_keeps_the_server_s_site_order` 실패 — sort로 `rows[0]`가 "비교 판정"(≠"작성 게이트"). 서버 순서 보존 가드.
- 각 mutation은 정확히 의도한 회귀만 포착, 나머지 9건 통과. 복원 후 Dashboard 10건 재통과로 무결성 확인.

### 8. 작업 AI 자기 보고 교차 검증

- **D1=C 추천과 다른 선택**: 브리프가 추천 문단(D1=A)을 소급 수정하지 않고 결정 절(D1=C)을 덧붙임 — 과거 결정 기록 불변 원칙 준수.
- **번들 실측 투명**: "399.03 → 786.13 kB로 뛰어(Vite 경고)… React.lazy로 401.19+385.67 지역화". 본 검증자 build 출력과 정확히 일치. "+100~200 kB 추정 틀렸다"를 솔직히 기록.
- **색 검증기 사용**: "눈이 아니라 검증기로 골랐다… ΔE 2.4 붕괴 → 탈락". 본 검증자 독립 재계산이 추세 일치를 확인.
- **미검증 명시**: "브라우저 렌더를 보지 못했다… 차트 라벨 충돌·좁은 화면 표 넘침은 dogfood 확인 항목". HANDOFF Next Tasks 1번으로 승격 — 투명.
- HANDOFF 회귀 기준선 갱신(204/14, 진입 401.19+청크 385.67)·Project Structure(observability/ 추가) 일치.

## Issues / Risks

### Blocking (계약 의무)

**없음.** 백엔드·공개 계약 무변(성공 기준 ①)을 실측했고, 오독 방어 3종 + 서버 순서가 회귀 10건으로 잠겼으며 mutation 4종이 양방향 생존을 실증. 색 접근성(contrast 전 PASS + CVD 분리 + 색만 의존 아님)을 독립 재계산으로 확인.

### Hardening recommendations (non-blocking)

**H-1 — 루프 미수렴율을 역산해 표시.** `ObservabilityDashboard.tsx:171-174`가 `percent(rate * runs_considered, runs_considered)`로 백엔드가 준 `non_convergence_rate`를 다시 `rate·runs/runs`로 역산해 `%`로 변환한다. 작업 AI 명제("정렬·반올림은 API가 보장, 화면이 다시 하지 않는다")와 미묘한 긴장.

- **blocking이 아닌 이유**: 수학적으로 `rate = non_converged/runs`이므로 `rate·runs/runs`는 `rate`와 동일(표시용 변환). 동작은 맞고 회귀가 통과.
- **권장 이유**: 부동소수점에서 `rate·runs`가 정확히 정수가 안 될 수 있어(예: rate=1/3, runs=3 → 0.999…), 미세한 반올림 차이가 생길 수 있다. `${(rate*100).toFixed(1)}%` 직접 변환이 역산보다 의도가 명확. 또는 백엔드가 `non_converged` 카운트도 제공.

**H-2 — 빈 상태에서 요약 카드와 빈 메시지가 동시 표시.** `kpi.sites.length === 0`일 때 `kpi-summary`(모두 0/—)와 `"아직 기록된 LLM 호출이 없습니다."` empty-state가 형제로 동시 렌더(137–187줄).

- **blocking이 아닌 이유**: 둘 다 참인 정보(0 호출). 틀리지 않음. 회귀 `test_shows_an_empty_state`(186–208)는 empty-state + table 부재를 검사하지만 summary 동시 표시는 검사 안 함.
- **권장 이유**: UX상 "아직 기록 없음"일 때 요약 카드(0/—)를 함께 보여주면 정보가 중복. `sites.length===0`이면 summary도 숨기는 한 줄 가드가 깔끔. 동작 영향 없음.

**H-3 — `parseError`(`#a8742a`)의 표면 대비 여유가 가장 작음.** 독립 재계산에서 contrast 3.55로 세 색 중 가장 낮음(success 5.00, providerError 6.41). 3:1 기준은 넘지만 여유가 작아, 좁은 화면·저급 모니터·강제 색상 모드에서 더 떨어질 수 있다.

- **blocking이 아닌 이유**: 3:1을 넘으므로 WCAG 그래픽 기준 충족. 색만 의존하지 않으므로(범례+표) 식별은 보장.
- **권장 이유**: 호박을 좀 더 어둡게(예: `#8f6020`) 해 contrast 여유를 늘리면, CVD 분리를 유지하면서 대비 안전마진 확보. 단, CVD 재검증 필요.

## Verdict

**합격 (pass).**

이유(유효 하중):

1. **백엔드·공개 계약 무변**(성공 기준 ①)을 실측: c1c5ddd stat에 `services/`·`tests/`·SoT 부재, `schema.d.ts` no-diff + `gen:api` no-drift. "순수 소비" 충족.
2. 오독 방어 3종(gate null·loop null·multi_call 라벨)이 화면에 정확히 구현됐고, mutation 4종(M1–M4)이 각 방어의 **양방향 생존**(positive 텍스트 + negative "0"/"0.00"/"0%"/"재시도" 부정)을 실증. 특히 M2(loop null→"0%")는 **load-bearing case**(기본 배포 정상 상태) 보호.
3. **서버 순서 보존**을 M4가 잡고, 색 접근성을 **독립 Python 재계산**으로 실증(contrast 전 PASS·CVD 최소 ΔE76 26.7·명도대로 pro↔par 분리·WCAG 1.4.1 색만 의존 아님).
4. 번들 분할(진입 401.19 + 청크 385.67)·vitest 204/14·tsc 0·백엔드 612 subtests 전부 작업 AI 보고와 정확히 일치.
5. 작업 AI 자기 보고(D1=C 추천 상이·번들 실측 투명·색 검증기 사용·미검증 명시)가 코드·HANDOFF와 투명하게 일치.

Hardening 3건(H-1 rate 역산, H-2 빈 상태 동시 표시, H-3 parseError contrast 여유)은 동작이 이미 맞는 경로의 정리·안전마진 제안이며, 오독 방어 잠금이 빠진 것이 아니다.

## Outstanding items

- **브라우저 렌더 미검증**: 이 머신 스택이 내려가 있어 작업 AI·검증자 모두 브라우저 렌더를 못 봄. 차트 라벨 충돌·좁은 화면 표 넘침·막대 배치는 **dogfood 첫 세션의 육안 확인 항목**(HANDOFF Next Tasks 1번). 로직·오독 방어는 회귀 10건으로 잠겨 있음.
- **커밋 완료**: `c1c5ddd` HEAD, 작업 트리 clean. 검증자 mutation 전부 복원 후 `diff -q`로 원본 일치 확인.
- **다음**: ① 관측 화면 육안 확인(스택 기동), ② 대시보드 확장은 API 시간 창(`?since=`) 뒤(지금은 누적 스냅샷이라 추세 없음) + `React.lazy` 경계 유지, ③ ★ dogfood 착수(GATE-1) — 이제 관측까지 자동 계측+화면으로 보임.
- **오너 결정 대기 2건 이월**: `analysis_extractor` D4 정렬 · loop round별 gate decision 노출.

## Reproduction

```bash
# 1. 백엔드 무변 + 공개 계약 no-drift
git show --stat c1c5ddd | grep -E "services/|tests/|system-contract|schema.d.ts"  # 빈 출력
cd frontend && npm run gen:api && git status --short src/api/schema.d.ts          # clean

# 2. 프론트 회귀/빌드
cd frontend && npm run build   # 진입 401.19 + 청크 385.67, tsc 0
cd frontend && npm test        # 204 / 14

# 3. 백엔드 회귀 (무변)
python3 -m pytest tests/ -q -p no:cacheprovider   # 1480/80 skip/612 (검증자 환경)

# 4. 색 CVD 독립 재계산 (Python sRGB→Lab→WCAG/CVD)
#    contrast: 5.00 / 6.41 / 3.55 | CVD 최소 ΔE76 = 26.7

# 5. mutation (cp 백업 → Edit → vitest → 복원). 예: M2
cp frontend/src/observability/ObservabilityDashboard.tsx /tmp/d.bak
# Edit: loop null ? "—" → "0%"
cd frontend && npx vitest run src/observability/ObservabilityDashboard.test.tsx  # → 1 failed
cp /tmp/d.bak frontend/src/observability/ObservabilityDashboard.tsx && diff -q ...
```
