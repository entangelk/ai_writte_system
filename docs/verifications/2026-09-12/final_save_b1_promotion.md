# 최종 저장·분석 연동 6차(승격) 재검증 — B1 폐쇄 판정

**합격** — 5차 재검증의 조건 **B1**(확정 계약 *"final marker 뒤의 일반 저장은 허용한다"* 의 프런트 과잉교정 방향 무가드)가 폐쇄 커밋 **`0a2fee4`**(2026-09-06 · 처방 셀 1개)로 닫혔고, 이 재검이 **변이 재적용 양방향**으로 그 폐쇄를 확증했다. 선행 기록 [`final_save_n1_promotion.md`](../2026-09-06/final_save_n1_promotion.md) 의 판정 **조건부 합격을 합격으로 승격**한다(발행 시점 판정은 인용으로 아래 보존). 5차 기록 Outstanding 이 정한 최소 범위("*그 셀 + MV-D 재적용만으로 승격 판정이 가능하다*)를 채우고 under 방향을 하나 더 잰다.

- **일시**: 2026-09-12 · **검증자**: 독립 세션 — 5차 재검증(2026-09-06)·B1 폐쇄(`0a2fee4`) 어느 쪽도 아니다
- **검증 트리**: HEAD `0769cc9`(폐쇄 커밋 `0a2fee4` 이후 Phase W 등 여러 슬라이스가 같은 파일을 건드린 뒤 — **승격 판정은 오늘의 코드에서 한다**, 5차가 4차 스냅샷이 아니라 현행 코드에서 재유했던 원칙과 같다). **검증 중 다른 AI 의 미커밋 작업이 같은 트리에 있었다**(변이 대상 아님 — 원복은 대상 파일만 개별 경로로 `git checkout -- <절대경로>` + 백업 `cmp` 바이트 대조).
- **환경**: WSL2 · `frontend/` 안에서 `npx vitest`(단일 파일 — 발행 기록 지시와 같은 범위 제한, 전수는 공유 트리의 동시 작업으로 돌리지 않았다)

## 셀 수의 이동(증분 설명)

`DraftEditor.test.tsx` 집중 스위트는 5차 시점 **68 passed** → 현재 **65 passed (1 file) EXIT=0**. 차이는 5차 이후 같은 파일을 건드린 슬라이스들(Phase W 시각 개선 등)의 증감이고, 판정에 필요한 것은 **B1 폐쇄 셀(`:1807` "final 뒤의 일반 저장: 저장은 실제로 나가고 배지가 최종 저장 후 수정됨으로 전이한다")이 존재하고 기준선에서 통과한다**는 것 — 둘 다 확인했다.

## 변이 재적용 — 양방향 모두 B1 폐쇄 셀이 물었다

| 변이 | 적용한 diff(실제 텍스트) | 5차 시점 | 실측(현행 트리) |
|---|---|---|---|
| **MV-D** (over) | `DraftEditor.tsx` 일반 저장 버튼(현행 `:743`) `disabled={!dirty \|\| saving \|\| selecting \|\| overLimit}` → `disabled={isFinalized \|\| !dirty \|\| saving \|\| selecting \|\| overLimit}` | **프런트 전수 418 전건 초록 — 무물림**(이것이 B1 이었다) | **1 실패 \| 64 passed** — 실패 셀이 정확히 **B1 폐쇄 셀**("final 뒤의 일반 저장…"). *저장 차단* 방향을 문다 |
| **M1 계열** (under) | 배지 삼항(현행 `:646`) `{isFinalized ? latestSnapshotId === draft.finalized_snapshot_id ? "최종 저장됨" : "최종 저장 후 수정됨" : "초안"}` → `{isFinalized ? "최종 저장됨" : "초안"}` (세 번째 상태 파괴) | 1 실패(`marker 보다 최신 version…` 셀) | **2 실패 \| 63 passed** — `marker 보다 최신 version…`(5차와 같은 셀) **+ B1 폐쇄 셀**. *배지 전이 파괴* 방향도 폐쇄 셀이 잡는다(폐쇄 보고의 under 변이 "2 재실패"와 짝이 같다) |

두 방향 모두에서 **같은 폐쇄 셀이 첫 줄에 물린다** — 셀 하나가 계약 분기의 양면(저장은 나간다 · 배지는 전이한다)을 함께 잠근다는 처방 설계의 실증이다.

## Verdict

**합격** — B1 폐쇄 셀(0a2fee4)이 현행 코드에서 살아 있고, 5차가 *전수 전건 초록*으로 실측한 MV-D 가 이제 그 셀을 물며 under 방향(배지 전이 파괴)까지 잰다. 선행 기록 발행 시점 판정 원문:

> **조건부 합격** — 조건: 확정 계약 *"final marker 뒤의 일반 저장은 허용한다"* 의 프런트 과잉교정 방향 무가드(**B1**) 폐쇄.

이로써 **최종 저장·분석 연동 재검증 축(1~6차)이 닫힌다.**

## Outstanding items

- **하드닝 H1·H2(비차단·오너 값 인정 대기)**: finalize 키 "매 클릭 새 UUID" 전제 셀 · finalize() 함수 층 가드 셀 — 5차 기록 그대로.
- **N3(같은 finalize 키 재전송의 활동 행 중복)은 여전히 오너 결정 대기** — H1 을 닫으면 "도달 불가" 분류의 전제가 잠긴다(5차 기록 그대로).
- 이 기록 등재로 검증 건수·분포 주장이 갱신된다(등재 직후 문서 가드 단독 실행으로 확인).

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system/frontend && git status --short   # 변이 대상 파일 diff 0
npx vitest run src/drafts/DraftEditor.test.tsx    # 65 passed — B1 셀 포함
# MV-D(over): src/drafts/DraftEditor.tsx 일반 저장 버튼 disabled= 에 isFinalized || 추가
npx vitest run src/drafts/DraftEditor.test.tsx    # 1 failed("final 뒤의 일반 저장…")
git checkout -- /mnt/f/devel/ai_writte_system/frontend/src/drafts/DraftEditor.tsx
# M1 계열(under): 배지 삼항에서 세 번째 상태 제거 → 2 failed(같은 셀 + marker 보다 최신 셀)
# 매 변이: 원복 후 백업과 cmp 바이트 대조
```
