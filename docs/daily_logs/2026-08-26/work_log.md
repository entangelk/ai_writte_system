# 2026-08-26 작업 로그 (알파)

> **[세션 2] ads.txt 반영 + 스택 배포 (오너 승인 하 파일 1줄 · 테스트 0셀).**
> 오너 문의(*"ads.txt는 넣으면 좋은건가? 내가 이 부분은 잘 몰라"*)에 배경 설명(경고 예방·손해 0·
> 심사 무관·pub ID 일치가 유일 조건)을 드렸더니 *"그래 해줘. 그냥 넣기만 해줘. 실제 서버에 올려서
> 내가 직접 확인하는게 더 좋을꺼같아"*로 승인했다.
> - [`frontend/public/ads.txt`](../../frontend/public/ads.txt) 한 줄 — pub ID는 세션 1 스니펫에서
> 그대로(Vite `public/` → dist 루트, Dockerfile `COPY frontend/ ./`가 포함).
> - **배포 실측**: 프론트 이미지 재빌드 + `up -d --no-deps frontend`(dev-stack 함정 — 포트 충돌
> 회피) 후 `curl /ads.txt` = **200 · text/plain · 본문 일치**. **같은 재빌드로 세션 1 로더도
> 서빙 HTML에 반영됐다**(grep 1건 확인 — 이전 컨테이너는 재빌드 전 이미지였음).
> - **가드 없음은 오너 명시적 요청**(*"그냥 넣기만"*) — 유일한 침묵 실패 모드(public/ 누락 시
> try_files가 index.html을 200으로 돌려줌)는 알려진 채 남긴다.
> - **오너 결정**: 광고 자동/수동은 **승인 후로 미룸**(콘솔 토글이라 코드 무관).

> **[세션 1] 애드센스 로더 정착 + HANDOFF 낡은 op 표기 갱신 (프론트 1줄 + 가드 1셀).**
> 오너 지시: *"에드센스 넣을꺼거든? 코드 스니펫 줄테니 추가해줘"* — 스니펫(`ca-pub-6325442421128026`)
> 과 함께 제공됐다. 구현은 [`frontend/index.html`](../../frontend/index.html) `<head>` 삽입
> 한 건뿐이지만, `<head>`는 렌더 테스트가 원리적으로 못 보는 자리라(`productName.test.ts`
> 서두가 정확히 이 병을 다룬다) 같은 선례의 파일 읽기 가드를 붙였다.
> - **SRI 미부착은 결정이 아니라 예외**: 세션 중 보안 훅이 `integrity` 부착을 권고했으나
>   `adsbygoogle.js`는 Google이 실험 단위로 내용을 바꿔 serve하는 스크립트라 해시 고정이
>   로딩을 깬다 — 공식 스니펫에도 없다. 사유를 가드 docstring과 HANDOFF에 남겼다.
> - **부수 정리**: HANDOFF 자가검수 트리거(544줄) 발동 + 08-25 세션 1이 "다음 인계 때 실측
>   갱신"으로 넘겨 둔 operation 77 낡은 표기를 닫았다(실측 87).
> - **다음 후보(트리거 있음)**: ads.txt(콘솔 경고·수익화 개시 시) · 광고 배치 자동/수동(오너) ·
>   AdSense 심사 상태 확인(오너).

## Goals

- 오너가 제공한 애드센스 로더 스니펫을 제품 프론트에 반영한다 — 모든 페이지가 거치는 유일한
  HTML 엔트리는 `frontend/index.html`(Vite SPA)이므로 여기 한 곳이면 충분하다.
- 매출 하부구조가 조용히 사라져도 아무 테스트·런타임 에러가 없는 사고(스니펫 삭제 = 에러 0,
  매출만 0)를 가드로 예방한다.

## User Decisions and Rationale

- **오너(2026-08-26, 세션 1)**: 애드센스 도입 선언 + 스니펫 제공(*"코드 스니펫 줄테니 추가해줘"*).
  퍼블리셔 ID `ca-pub-6325442421128026`는 오너 계정에서 나온 값이며 모든 페이지 HTML에
  노출되는 공개 값이라 저장소에 두는 데 민감성이 없다.
- **오너(2026-08-26, 세션 2)**: ads.txt 반영 승인(*"그냥 넣기만"*) + **배포해서 직접 확인하겠다**.
  광고 자동/수동 선택은 승인이 안 났다는 이유로 미루기로 함.

## Decisions (구현자 판단)

- **삽입 위치 = `<head>` 안, `<title>` 뒤.** Google 공식 안내 그대로 head 배치이고, Vite는
  소스 `index.html`을 빌드 산출물에 그대로 운반한다(실측 확인 — 아래 Verification).
- **dev/prod 분기 없이 무조건 삽입.** localhost에서도 스크립트가 로드되지만 무해하다(승인
  도메인이 아니면 광고가 게시되지 않는다). 조건부 로딩은 요청받지 않은 구성 가능성이다.
- **가드는 파일 읽기 1셀**(`adsense.test.ts`) — 단정은 URL+client 파라미터·`crossorigin`·
  `<head>` 배치의 본질만 보고 속성 순서·줄바꿈 재포맷에 흔들리지 않게 했다. SRI 부재를
  요구하지 않는 것도 의도(docstring에 명시).
- **ads.txt는 넣지 않았다(유예·트리거).** 오너 스니펫 범위 밖이고 내용 결정(pub ID 확인)이
  오너 몫이다. 트리거: AdSense 콘솔 경고 또는 수익화 개시 → `frontend/public/ads.txt`(nginx
  루트 서빙).

## Completed work

- **`frontend/index.html`** — `<head>`에 로더 `<script>` 추가(속성 줄바꿈은 파일 스타일에 맞춤).
- **`frontend/src/adsense.test.ts` 신설** — 파일 읽기 가드 1셀. 커밋 `d3fd43c`.
- **HANDOFF** — 08-26 세션 1 마감 메모 신규(유예 3종 트리거 포함) · operation 77 낡은 표기
  4곳 갱신 · 검수 헤더줄 갱신(526→544).
- **`frontend/public/ads.txt` 신설 + 배포(세션 2)** — 프론트 이미지 재빌드 후 컨테이너만 교체
  (`--no-deps`). 세션 1 로더의 배포 반영도 이 재빌드로 이뤄졌다.

## Verification

- **전수**: 프론트 vitest **339 passed / 339**(30 파일) — 직전 기준 338에서 +1(신규 가드).
  `tsc --noEmit` 포함 빌드 통과(`npm run build`, 9.91s).
- **빌드 산출물 반영**: `dist/index.html` `<head>`에 로더 원문 그대로 존재 — 육안 판독으로
  확인. (교훈 메모: 태그가 줄바꿈되면 `grep -o '<script[^>]*>'`는 못 잡는다 — grep은 줄
  단위라 multiline 태그 매칭이 원리적으로 안 된다.)
- **뮤테이션(양방향)**:

| 적용한 변형 | 위치 | 재실패한 셀 |
|---|---|---|
| 로더 `<script>` 블록 삭제 | `frontend/index.html:7-11` | `adsense.test.ts` "loads the AdSense script from \<head\>, which no render test can reach" — 정확히 1셀 |

  절차 준수: 구현 커밋(`d3fd43c`) → 변형 → 재실패 확인 → `git checkout --` 복원 → 트리
  clean·가드 재통과(1 passed) 확인.
- **ads.txt 서빙(세션 2, `curl -w` 실측)**: HTTP **200** · `text/plain` · 본문 한 줄 일치.
  서빙 HTML에 adsbygoogle 로더 존재(grep 1건) — 세션 1 반영분의 **배포 확인을 겸했다**(그 전
  컨테이너는 로더 이전 이미지였음).
- **op 표기 갱신 실측**: `scripts/dump_openapi.py` → **paths 76 · operations 87**(SoT v1.8.4
  "operation 87 무변"과 일치). "operation 77"은 Phase 9 시점 누적 총수(76+1)였음을 확인하고
  현재 서술로 오독되는 3곳을 시점 명시·계약 지시자("activity 읽기 계약")로 교체, 08-25 메모
  줄에 폐쇄 주석.

## Issues found

- 없음. (세션 중 Edit 도구로 HANDOFF 309행에 "뒤 뒀으니" 오타를 유입했다가 `git diff` 대조로
  즉시 발견·수정 — 커밋 전이라 무결성 영향 0.)

## 다음 세션 후보

- **오너 답변 대기**: AdSense 심사 상태(승인 시 게시 시작 확인) · 광고 배치 자동/수동 —
  **승인 후 결정으로 미룸**(오너 2026-08-26). 수동 선택 시 `<ins>` 슬롯 컴포넌트 작업 발생.
- HANDOFF 전면 압축 검수는 별도 슬라이스로 미뤄둠(544줄 — 이번엔 트리거 항목만 최소 정리).
