# Slice 10.2 활동 날짜 그룹 독립 검증

## Subject metadata

- 날짜: 2026-08-11
- 요청자: 오너 — *"다음작업 검증해줘. 머릿글 접힌다는데 안접히는거같기도 하고? Slice 10.2 완료."* (오너 육안 확인 중, 접힘 의문 제기)
- 검증자: 이 세션 (구현자와 다른 세션; 10.0·10.1 검증에 이어 동일 날)
- 대상: Phase 10 Slice 10.2 — 활동을 날짜로 묶음(D3=ⓓ, backend 0줄). 커밋 `34ed87f`·`c45506d`.
- 정규 스펙: [`docs/plans/10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md) §D3(ⓓ) + 슬라이스 표 10.2 행.

## Scope

1. **오너의 "접힘" 의문** — 같은 날 행이 머리글 하나로 실제로 묶이는가. 모듈 로직·화면 렌더·셀·**배포 이미지**까지.
2. 모듈 불변식 셋 — 서버 순서 미정렬·로컬 날짜 경계·못 읽는 행 미버림·`now` 주입.
3. 회귀 수치 — frontend 305/23 · build · 백엔드 가드 3종.
4. 뮤테이션 M21~M24(작업자 주장) 독립 재도출 — 특히 M22(UTC 그룹, 미묘).
5. D3=ⓓ 유지 — 상한 문구·셀.
6. 백엔드 prod 0줄(기준선 2271/1/2430 유효) 확인.

## Methodology

- 트리 clean(HEAD `c45506d`). 뮤테이션은 `cp` 백업 → 변형 → 실측 → 원복 → `diff` + `git status --short` empty.
- frontend 전체·build·백엔드 가드 3종 단독: 실구동.
- 배포 확인: `docker inspect`(이미지 생성 시각) + 서빙 CSS grep(`activity-day`).

## Findings

### 1. 기준선 수치 — 전부 독립 재현

- frontend `npx vitest run`: **23 files / 305 passed**, exit 0. 작업자 305/23 일치.
- build: **703 modules**(702→+1, `activityDays.ts`) · 진입 **421.78 kB**(420.81→+0.97) · CSS **30.66 kB**(30.47→+0.19, `.activity-day`) · lazy 무변 · `tsc` clean. 일치.
- 백엔드 "프론트 읽는 가드 3종" = `test_activity_ui_labels`(6/30) + `test_design_token_provenance`(5/89) + `test_docs_indexes`(13/245) = **24 passed / 364 subtests**. 산술 정확히 일치.
- 백엔드 prod 0줄: `git diff --stat 2e2b02c..HEAD -- services/` = empty → 기준선 **2271/1/2430 유효**.

### 2. ★ 오너의 "접힘" 의문 — 접힘은 정확하다 (배포까지 확인)

- 모듈 `groupActivityByDay`([`activityDays.ts:65`](../../../frontend/src/projects/activityDays.ts#L65)): 인접한 같은 날만 접는다(line 77-82, 마지막 그룹 key 같으면 push 아니면 새 그룹). 서버가 `at` DESC 로 날짜-연속적이므로 같은 날은 인접 → 접힌다.
- 화면 렌더([`ActivityTimelinePage.tsx:66`](../../../frontend/src/projects/ActivityTimelinePage.tsx#L66)·[`PersonalHubPage.tsx:123`](../../../frontend/src/me/PersonalHubPage.tsx#L123)): `groupActivityByDay(events).map(day => <h2/h3>{day.label}</...> + day.events.map(...))` — **그룹당 머리글 하나**, 행은 그 아래. 행마다 머리글이 붙지 않는다.
- 화면 셀([`ActivityTimelinePage.test.tsx:132`](../../../frontend/src/projects/ActivityTimelinePage.test.tsx#L132)): 같은 날 2건 + 다른 날 1건 → 헤딩 **2개** 단정(머리글이 행마다 반복 않는 것을 잠금). 주석 *"같은 날 둘은 머리글 하나로 접힌다"*.
- **배포 확인**: 프론트 컨테이너 이미지 15:46 KST 빌드(10.2 feat `34ed87f` 15:41 이후)·서빙 CSS 에 `activity-day` 존재 → 오너가 localhost:5520 에서 보는 것은 10.2 본체. stale 아님.

→ **결론: 접힘은 코드·테스트·배포 전부에서 정확하다.** 오너가 "안 접히는 것 같다"고 느낀 것은 (a) 데모 활동 5건이 같은 날이라 **머리글이 하나뿐**이라 접히는 게 시각적으로 드러나지 않는 것(정상), (b) 머리글 스타일이 작고 흐려(`0.78rem`·`--text-muted`·`letter-spacing`) 그룹 구분이 눈에 덜 띄는 것. 둘 다 비차단 시각 관찰이지 결함이 아니다.

### 3. 모듈 불변식 — 7셀이 셋 다 잠금

[`activityDays.test.ts`](../../../frontend/src/projects/activityDays.test.ts): 오늘/어제 라벨 · 연도 다를 때만 연도 · **서버 순서 미정렬**(일부러 뒤섞은 입력 그대로, 비인접 같은 날은 접지 않음 → 3 그룹) · **인접 같은 날만 접기** · **로컬 달력(UTC 아님)** · 못 읽는 행 미버림 · 빈 입력. clock-pitfall 해법(`NOW` 주입 + 2024년 날짜로 시계 독립)도 셀에 박혀 있다.

### 4. 뮤테이션 M22(UTC 그룹) — 작업자 주장 4 failed 독립 재현

`localDayKey`를 UTC(`toISOString().slice(0,10)`)로 바꾸면:
- `activityDays.test.ts`: **3 failed**(미정렬·인접접기·critical "local calendar day not UTC" 셀).
- `ActivityTimelinePage.test.tsx`: **1 failed**(화면 폴딩 셀 — `DAY_ONE_LATER` 08:00 KST 가 UTC 넘어가 3-4 가 돼 접힘이 깨짐).
- 합 **4 failed** — 작업자 주장과 정확히 일치. local-boundary 불변식이 모듈·화면 양쪽에서 잠겨 있다. (참고: 실패 셀 수는 실행 머신 TZ 에 따라 달라질 수 있는데 — 4 라는 수 자체가 그 민감도의 증거이며, 작업자가 친절히 시계 함정을 기록한 것과 같은 맥락이다.)
- M21(재정렬)·M23(배선 누락)·M24(못 읽는 행 버리기)는 코드·셀에서 기계적으로 자명(각 no-resort·화면 폴딩·미버림 셀이 곧장 잡는다) — M22 로 메커니즘 정직성 입증돼 별도 실측 생략.

### 5. D3=ⓓ 유지 — 상한 문구·셀로 잠금

상한 문구("최근 100건까지 보여줍니다") 그대로([`:55`](../../../frontend/src/projects/ActivityTimelinePage.tsx#L55)), 셀([`:157`](../../../frontend/src/projects/ActivityTimelinePage.test.tsx#L157) "still says the ceiling")가 그룹핑이 상한을 안 올렸음을 잠근다. 커서는 유예(트리거: 100건 부족 증거).

## Issues / Risks

### Blocking

- **없음.** 그룹핑은 계약(§D3 ⓓ)대로 구현됐고 접힘·불변식·상한 유지가 셀+뮤테이션으로 입증됐다.

### Hardening / 비차단

- **H1 (시각 관찰, 오너 의문 반영): 접힘은 작동하나 시각적으로 미묘하다.** 머리글이 작고 흐리고(`0.78rem`·`--text-muted`), 데모 데이터가 같은 날 5건이라 머리글 하나로 그룹핑이 눈에 안 드러난다. 결함 아님. (a) 오너가 오늘 활동을 하나 만들면 어제/오늘로 머리글이 갈려 그룹핑이 보인다(작업자 권고와 동일). (b) 머리글 시각 강조는 10.3~ 화면별 다듬기에서 자연스럽게 다룰 자리.

## Verdict

**합격** — blocking 0.

이유: 활동 날짜 그룹핑은 모듈(`groupActivityByDay`)·두 화면(`/me`·`/projects/:id/activity`)·셀 전부에서 계약대로 정확하다. 같은 날 행이 머리글 하나로 접히고(화면 셀이 2-날짜→2-헤딩으로 잠금), 서버 순서를 다시 정렬하지 않으며, 그룹 경계를 로컬 달력으로 잡고(M22 뮤테이션 4 failed 로 입증), 못 읽는 행을 버리지 않는다. `now` 주입+2024 날짜로 시계 함정을 피한 층 분리도 건전. D3=ⓓ(커서 유예·상한 유지) 지켜졌고 backend prod 0줄. **오너의 "접힘" 의문은 코드·배포에서 해소됐다** — 같은 날 데이터의 머리글 하나는 정상 동작이며 시각 강조는 10.3~ 과제(H1).

## Outstanding items

- **오너**: 13표면 육안 확인의 일환으로 `/me`·`/projects/:id/activity` 확인. 다른 날 활동을 만들어 보면 그룹핑이 시각적으로 드러난다.
- **10.3~ (작업 AI)**: 화면별 다듬기에서 활동 머리글 시각 강조를 자연스럽게 다룰 자리(H1). 첫 화면은 사용 빈도 순 `DraftEditor` 권장(작업자 제안).
- 본 검증은 **검증으로 끝**.

## Reproduction

```bash
# 기준선
cd frontend && npx vitest run                              # 23 files / 305 passed
cd frontend && npm run build                               # 703 modules, 진입 421.78, CSS 30.66
python3 -m pytest tests/test_activity_ui_labels.py -q      # 6/30
python3 -m pytest tests/test_design_token_provenance.py -q # 5/89
python3 -m pytest tests/test_docs_indexes.py -q            # 13/245  (합 24/364)

# M22 (UTC 그룹) — cp 백업 → localDayKey 를 toISOString().slice(0,10) 로 →
#   activityDays.test.ts 3 failed + ActivityTimelinePage.test.tsx 1 failed = 4

# 배포 확인
docker inspect ai_writte_system-frontend-1 --format '{{.Created}}'   # 10.2 이후 빌드
curl -s http://localhost:5520/ | grep -oE 'assets/index-[^"]+\.css' | head -1 \
  | xargs -I{} curl -s http://localhost:5520/{} | grep -o activity-day
```
