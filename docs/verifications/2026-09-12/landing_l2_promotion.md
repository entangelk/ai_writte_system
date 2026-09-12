# 랜딩 축 ② (약관·방침 페이지 + 공개 푸터) — 조건 폐쇄 승격 재검

**합격** — 세션 59 검증의 조건 하나(LB1)가 세션 60(`7be433e`, SoT v1.8.57)에서 닫혔고(하드닝 H3 동반 · H2 는 `d5c63fb`·`9ca0e8b`), 이 재검이 변이 재적용으로 그 폐쇄를 확증했다. 선행 기록 [`landing_l2_terms_privacy.md`](../2026-09-11/landing_l2_terms_privacy.md) 의 판정 **조건부 합격을 합격으로 승격**한다(발행 시점 판정은 인용으로 아래 보존 — Slice 4 선례).

- **일시**: 2026-09-12 · **검증자**: 세션 67 — 구현(58)·검증(59)·폐쇄(60) 어느 쪽도 아니다
- **대상**: 폐쇄 커밋 `7be433e`(LB1 셀 + H3 범위 교정 — 프로덕션 변경은 렌더러 한 군데) — 검증 트리 HEAD `3ccf880`(트리 clean)
- **방법**: 프리플라이트 `git status --short` 무출력 게이트 → 변이 → 초점(`src/legal` + `src/App.test.tsx`, 45셀 · 파일 캡처) → `git -C <절대경로> checkout -- <절대경로>` → 무출력 확인. 기준 초록 45/45 확인 후 6종 재적용. **초점은 반드시 `frontend/` 안에서** — MO-8 첫 측정은 셸 cwd 가 저장소 루트로 옮겨진 채 돌아 `--reporter=basic` 로드 실패(Startup Error)로 무효가 됐다(프런트 전수 함정과 같은 발생형태) — 재측으로 바로잡았다.

## 변이 재적용 — 6종 전부 세션 60 기록과 일치

| 변이 | diff | 세션 60 기록 | 실측 |
|---|---|---|---|
| MO-6a (under) | `AuthStatus`(세션 확인·오류 얼굴)의 `<LegalFooter />` 한 줄 제거 | 1실패 | **1실패** `hangs the footer off every public face of the front door, not just the form` — 세션 59 실측은 legal 14 + App 29 **전건 초록**이던 자리 |
| MO-6b (under) | 가입 접수 얼굴의 `<LegalFooter />` 한 줄 제거 | 1실패 | **1실패**(같은 LB1 셀) — 종전 43/43 초록이던 자리 |
| ML-3b (under) | 로그인 폼 얼굴의 `<LegalFooter />` 한 줄 제거 | 2실패 | **2실패** `hangs the legal links off the front door…`·`walks an anonymous visitor…` — 기존 두 셀이 그 얼굴을 계속 지킨다 |
| MH-3a (under) | `markdown.tsx` 머리말 스코프를 문서 전체로 되돌림(`7be433e` diff 의 역방향 — 전체 filter + 메타 조건의 `headLines` 제거) | 1실패 | **1실패** `strips the editorial head line without eating a body line that starts the same way` |
| MH-3b (over) | `근거:` 걷기 제거(머리말 filter 삭제 — 편집 메타가 공개면에 뜬다) | 2실패 | **2실패**(위 H3 셀 + `links the two documents…` 링크 셀) |
| MO-8 (등가) | 머리말 경계를 `---` 없이 첫 `## ` 로만 구한다 | 초록이어야 한다 | **45/45 초록** — 경계 유도 방식을 과잉 고정하지 않는다 |

변이↔셀 짝: MO-6a·MO-6b 가 같은 신규 LB1 셀을 물고 ML-3b 가 **기존** 둘을 물어 세 얼굴이 셋의 소유로 **분할 점유**됐다 — *"열거가 셋이면 셀도 셋을 본다"* 의 실증이 그대로 재현됐다.

## 폐쇄 ↔ 처방 대조

- **LB1**: 처방("세션 확인/오류 얼굴과 가입 접수 얼굴에서 각각 `법적 고지` nav 존재 단정 — 두 얼굴을 한 셀의 subTest 로도 돌 수 있다") 그대로 — 세 얼굴을 **한 셀**에 담고 `unmount()` 로 사이를 끊었다. 얼굴을 셋으로 쪼개지 않은 선택(하나가 빠지면 다시 조용해진다)도 검증 제안 형태 그대로다.
- **H3**: 관찰로 끝날 뻔했던 축을 기계로 옮겼다(머리말 경계 유도) — MH-3a·MH-3b 양방향 재실패와 MO-8 등가 초록이 그 교합을 다시 확인한다.

## 기준선 — 이 세션이 전수로 확인했다(선행 유도 정정)

백엔드 전수 **3026 passed / 1 skipped / 4156 subtests · EXIT=0**(373초, test-mongo PRIMARY 확인 후 시작). 선행 유도값 **4154 보다 subtest +2** — 귀속: 유도 시점 이후 Phase W 가 새 문서 둘(`docs/plans/frontend-writing-studio-phase.md` `dede62b` · `docs/daily_logs/2026-09-12/work_log.md` `bc78ed6`)을 만들었고 `test_repo_hygiene` 는 문서당 1 subtest 를 낸다(`git log --diff-filter=A --name-only 33b67e2..HEAD -- 'docs/**' '*.md'` 실측 — 둘뿐). 교차 확인: 문서 가드 7종 **59 passed / 1138 subtests** = 세션 60 실측 58/1114 + 정책 가드 +1셀/+22 subtests(`d5c63fb`·`9ca0e8b`) + 문서 둘 +2. **회귀가 아니라 유도값이 낡은 것**이며 기준선은 4156 이다(핸드오프 회귀 줄 갱신). ★ **이 기록 자체가 그 직후 +2를 다시 만든다**(검증 기록 파일 +1 · 인덱스 행 +1 — 기록 추가 뒤 문서 가드 7종 실측 **59/1140**, 추가 전 1138) — 그래서 인계되는 기준선은 **4158**(전수 4156 + 2 유도)이고, 이것이 위 "유도값은 시점의 함수" 교훈의 당장 적용이다. 프런트는 이번 재검에서 소스 무변이므로 세션 66 실측 **478/41 · EXIT=0** 이 그대로 유효하다(재실측 불요 — 유도 정당 조건의 프런트 판).

## Verdict

**합격** — 조건 LB1 폐쇄가 변이 재적용으로 재현됐고 하드닝 H3 의 교합도 양방향으로 확인됐다. 선행 기록 발행 시점 판정 원문:

> **조건부 합격** — LB1(세 얼굴 중 두 얼굴의 푸터 장착 셀)을 닫아야 합격이다.

## Outstanding items

- 랜딩 ③(본문)·④(가입 동의 게이트)는 이 판정과 무관하게 열려 있다 — 구현 세션이 다음에 집는 축.
- H1/H4 시계 플레이크는 등재 상태 그대로 — 이 재검의 초점 45셀은 시각을 재지 않으므로 그 축을 늘리지 않았고 재검 중 관측도 없었다.
- H2(ML-10 계열) 폐쇄의 자체 검증은 세션 60 이 변이 셋(ML-10 1실패 · MO-9 over 2 SUBFAILED · MO-10 over 초록)으로 마쳤다 — 판정 조건이 아니므로 이 재검의 지정 6종에 포함되지 않는다.

## Reproduction

```bash
cd <repo> && git status --short                        # 무출력(프리플라이트)
cd frontend && npx vitest run src/legal src/App.test.tsx   # 45 passed(기준 초록)
# MO-6a: src/auth/AuthGate.tsx 의 AuthStatus 안 <LegalFooter /> 한 줄 제거
npx vitest run src/legal src/App.test.tsx   # → 1 failed(LB1 셀)
git checkout -- <절대경로>/frontend/src/auth/AuthGate.tsx
# ML-3b: 로그인 폼 return 의 <LegalFooter /> 한 줄 제거 → 2 failed(기존 두 셀)
# MH-3a: src/legal/markdown.tsx 의 7be433e 스코프 diff 를 역방향으로 되돌림
npx vitest run src/legal src/App.test.tsx   # → 1 failed(H3 셀)
git checkout -- <절대경로>/frontend/src/legal/markdown.tsx
# 기준선 전수(백엔드): cd <repo> && python3 -m pytest -q
#   → 3026 passed / 1 skipped / 4156 subtests
```
