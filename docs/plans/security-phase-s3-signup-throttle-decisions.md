# Decision brief — Phase S-3 signup 표면 속박(레이트리밋)

상태: **Proposed — 오너 결정 대기**
정본 연결: [`../verifications/2026-09-05/security_audit_dual_workflow.md`](../verifications/2026-09-05/security_audit_dual_workflow.md) §A.5·§A.11 · [`auth-signup-approval-decisions.md`](auth-signup-approval-decisions.md) P-6 및 "유예" 절 · [`../system-contract-sot.md`](../system-contract-sot.md) v1.7.97
목적: HANDOFF "Next Tasks 0" 이 지목한 **오늘 도달 가능한 유일한 보안 항목**을 착수하기 전에, 2026-08-22 에 "공개 배포 전"으로 유예된 **`X-Forwarded-For` 신뢰 정책**을 오너가 정하게 한다.

---

## Decision needed

**공개 `POST /auth/signup` 의 속박을 *어떤 축*으로, *어디에* 거는가.**

선례에서 유도되지 않는 이유: P-6(로그인 잠금)은 축을 **username** 으로 골랐고, IP 축은
*"nginx 경유(5520)와 직접(8520)의 `X-Forwarded-For` 신뢰가 갈려"* 명시적으로 **유예**했다
([`auth-signup-approval-decisions.md:92-96`](auth-signup-approval-decisions.md) · `:136`).
signup 은 **username 이 매번 다른 것이 공격 그 자체**라 P-6 축을 그대로 재사용할 수 없다 —
축을 새로 골라야 하고, 그 선택이 곧 유예됐던 신뢰 정책 결정이다.

### 지금 사실관계 (2026-09-05 실측)

| 사실 | 근거 |
|---|---|
| `/auth/signup` 은 승인 없이 공개, 요청마다 Argon2 hash(t=3·m=64MiB·p=4) 1회 | [`routers/auth.py:69`](../../services/application/app/routers/auth.py#L69) · [`auth/users.py:240`](../../services/application/app/auth/users.py#L240) |
| 앱은 **단일 uvicorn 워커**(`--workers` 없음) — 요청 하나가 이벤트 루프를 수십~수백 ms 점유 | [`services/application/Dockerfile:22`](../../services/application/Dockerfile#L22) |
| `SignupRequest.username`·`password` 에 **최대 길이가 없다** | [`api/models.py:78-84`](../../services/application/app/api/models.py#L78-L84) |
| pending 행에 TTL·행수 상한이 없다 — 승인 큐가 무한히 부풀 수 있다 | `auth/users.py::request_signup` |
| `frontend/nginx.conf` 에 `limit_req`·`limit_conn`·`client_max_body_size` **0건** | [`frontend/nginx.conf`](../../frontend/nginx.conf) (77행 전수) |
| `application`(8520)·`frontend`(5520) 은 `0.0.0.0` 게시 — LAN 에서 nginx 를 우회해 앱에 직접 닿는다 | `docker-compose.yml:129`·`:490` |
| 배포 진입로는 **Cloudflare Tunnel** 아웃바운드 하나 — 인바운드 포워딩 없음 | HANDOFF S-6 |

**★ 이 사실이 선택지를 가른다:** 터널 뒤에서는 nginx 가 보는 `$remote_addr` 가
**cloudflared 한 주소**다. `set_real_ip_from` + `real_ip_header CF-Connecting-IP` 를 붙이지
않으면 IP 축 레이트리밋은 **전 인터넷이 한 버킷**이 되어 사실상 전역 상한으로 퇴화한다.

### ★ 착수 전 확인이 필요한 것 (오너만 답할 수 있다)

**Cloudflare 터널 ingress 가 `frontend`(nginx, :5520)로 가는가, `application`(:8520)으로 바로 가는가?**
토큰 방식 터널이라 규칙이 대시보드에 있고 서버에서 볼 수 없다(HANDOFF S-6).
**앱을 직접 가리키면 nginx 에 무엇을 넣든 실트래픽에 효과가 0** 이다.
(추정은 있다 — 공개 도메인이 SPA 를 서빙하는데 SPA 를 서빙하는 것은 nginx 뿐이다. 그러나
*추가* ingress 규칙이 :8520 을 따로 가리키는지는 저장소에서 알 수 없다.)

---

## 선택지

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. nginx `limit_req` + Cloudflare real-ip** | `location = /api/auth/signup` 에 `limit_req_zone $binary_remote_addr rate=5r/m`, 앞단에 `set_real_ip_from <터널 소스>` + `real_ip_header CF-Connecting-IP` | **요청이 앱에 닿기 전에 거절** — Argon2·이벤트 루프를 아예 안 태운다. 앱 코드 무변. 가장 싼 방어 | 터널이 nginx 로 가야만 효과가 있다(미확인). **LAN 직접 :8520 경로는 그대로 무방비**. `set_real_ip_from` 대상이 컨테이너 재시작으로 바뀔 수 있다. 회귀 테스트가 pytest 밖(nginx 설정) |
| **B. 앱 축 — IP 를 보지 않는 전역 비용 상한** | signup 전용 전역 토큰버킷(예: 분당 N건) + pending 행 상한 + username/password 최대 길이. **IP 를 전혀 안 본다** | XFF 신뢰 정책을 정하지 않고 **오늘 닫힌다**. 진입 경로(터널·nginx·직접 :8520·LAN) 무관하게 동일 적용. pytest 회귀로 양방향 가드 가능. 코드가 작다 | 공격자 1명이 **정상 가입을 막는다**(가용성 DoS). 다만 가입은 희소 행위 + 승인제라 피해가 "몇 분 뒤 다시 시도"에 그친다 |
| **C. 앱 축 IP 레이트리밋 + XFF 신뢰 정책 확립** | `TRUSTED_PROXY_HOPS`/`CF-Connecting-IP` 파싱 정책을 세우고 IP별 카운터를 Mongo 에 둔다(P-6 `login_guard` 패턴 재사용) | 축이 정확하다. **P-6 이 유예한 로그인 IP 축도 같이 닫힌다**. 배포 경로와 무관 | 가장 비싸다(신뢰 정책 + 파서 + 저장소 + 테스트). 거절해도 **요청은 이미 앱까지 와서 이벤트 루프를 점유**한다(Argon2 만 회피). 신뢰 정책을 틀리면 위조 헤더로 우회되어 **가드가 조용히 무력해진다** |
| **D. 가입 표면을 닫는다** | `AUTH_SIGNUP_ENABLED=false` 토글(또는 초대 코드 요구). 켜는 날 A~C 중 하나를 정한다 | 한 줄. 승인된 계정이 오너뿐이라 **실사용 손실 0**. 오늘의 노출이 즉시 0 | 문제를 미룬다 — 공개 전환 시 이 결정이 그대로 되돌아온다. 프론트 "새 계정 요청" 폼이 죽은 UI 가 된다(S-1 랜딩·약관 트리거와 함께 다뤄야 함) |

---

## Recommendation — **B 를 지금, A 를 터널 확인 후 얹는다(2단)**

- **B 가 뼈대인 이유**: 현 단계는 *로컬 1인 프로젝트 + 승인제 가입*이고, 승인된 계정이
  오너뿐이라 **가입 가용성의 가치가 낮다**. B 의 유일한 단점(가입 DoS)이 지금 가장 싼 비용이다.
  반대로 B 는 **모든 진입 경로에 걸린다** — A 만 하면 LAN 의 `:8520` 직행이 남고, C 는
  신뢰 정책을 틀리는 순간 조용히 무력해진다. "가드가 조용히 없어지는" 실패 모드를
  이 저장소는 이미 한 번 명시적으로 거부했다(`AUTH_LOGIN_MAX_FAILURES` 파싱 실패 시 기동 거부).
- **A 를 얹는 이유**: B 는 요청이 앱까지 온 뒤 거절하므로 이벤트 루프 점유가 남는다.
  터널이 nginx 를 지난다고 확인되면 A 는 **그 트래픽을 앱 앞에서 잘라내는 공짜 앞단**이다.
  터널이 앱을 직접 가리킨다면 A 는 값이 0 이므로 **하지 않는다**.
- **C 는 S-1(가입 열기) 트리거로 미룬다.** IP 축이 실제로 필요해지는 시점은 *정상 가입자가
  여럿*일 때이고, 그때는 S-1 의 quota dedupe·랜딩·약관과 같은 트리거를 공유한다.
- **D 는 채택하지 않는다** — 노출을 0 으로 만들지만 프론트 가입 폼이 살아 있어
  UI 와 서버가 어긋나고, 결정이 그대로 되돌아온다. 다만 **오너가 "지금은 아무도 안 받는다"고
  판단하면 D 는 B 와 배타적이지 않다**(토글 + B 를 함께 둘 수 있다).

### B 로 갈 때 제안하는 계약 literal (오너 확정 필요)

| 값 | 제안 | 근거 |
|---|---|---|
| signup 전역 상한 | **분당 5건 / 시간당 20건** | 승인제 + 1인 운영. 정상 가입은 하루 한 자릿수 |
| 초과 시 응답 | **429** + `Retry-After` | 409(중복)·400(입력)과 구분되어야 프론트가 다른 안내를 낸다 |
| pending 행 상한 | **200행** — 초과 시 429 | 승인 큐가 사람이 읽을 수 있는 크기를 넘지 않게 |
| `username` 최대 길이 | **64자** | Mongo 문서·해싱 비용 증폭 차단 |
| `password` 최대 길이 | **256자** | 하한 12자는 기존(`MIN_PASSWORD_LENGTH`) |
| env override | `AUTH_SIGNUP_MAX_PER_MINUTE` 등, **파싱 실패 시 기동 거부** | `AUTH_LOGIN_MAX_FAILURES` 선례 |
| 저장소 | Mongo(`CORE_SOT_MONGO_URI` 있을 때) / in-memory fallback | `login_guard` 선례 그대로 |

**최대 길이 셋(username·password)은 결정이 아니라 그냥 하는 일**로 본다 — 축과 무관하고
어느 선택지에서도 필요하다. 다만 **공개 계약 변경**(5MB username 이 201 → 400)이라 여기 적어 둔다.

---

## Follow-up considerations

- B 의 카운터 저장소는 **축을 나중에 IP 로 바꿔도 재사용 가능한 모양**으로 둔다
  (`login_guard` 의 `FailureRecordRepository` 처럼 키가 문자열). C 로 가는 날 키만 바뀐다.
- 429 는 프론트 가입 폼의 **새 실패 모드**다 — S-1 랜딩·약관 슬라이스에서 문구가 필요하다.
- A 를 얹는다면 `client_max_body_size` 와 S-2 의 보안 헤더(`add_header`)가 **같은 파일의
  같은 슬라이스**다 — nginx 를 한 번만 여는 편이 싸다.
- pending 행 상한은 **관리자 승인 큐의 UX 상한**이기도 하다 — 상한을 넘겼을 때 오너가
  무엇을 보는지가 정해져야 한다(현재 `GET /admin/signup-requests` 는 무제한 목록).

## Deferred / out of scope

- **로그인 IP 축**(P-6 유예) — 이 브리프는 signup 축만 정한다.
- **나머지 미인증 표면 셋**(LLM 게이트웨이 · in-stack llama `:9080` · embedding `/embed`) —
  트리거는 D8-7 G2~G6 와 같은 원격·다중 호스트 배포다.
- **S-1 quota dedupe · S-2 nginx 보안 헤더 · S-0 문서 스윕** — 각각 별도 슬라이스.
- **가입 열기 자체**(자동 승인 전환) — 오너 결정이며 랜딩·약관과 같은 트리거.
