# Decision brief — Phase S-3 signup 표면 속박(레이트리밋)

상태: **Resolved(2026-09-05) — C 채택 · 구현 완료**
정본 연결: [`../verifications/2026-09-05/security_audit_dual_workflow.md`](../verifications/2026-09-05/security_audit_dual_workflow.md) §A.5·§A.11 · [`auth-signup-approval-decisions.md`](auth-signup-approval-decisions.md) P-6 및 "유예" 절 · [`../system-contract-sot.md`](../system-contract-sot.md) v1.7.97
목적: HANDOFF "Next Tasks 0" 이 지목한 **오늘 도달 가능한 유일한 보안 항목**을 착수하기 전에, 2026-08-22 에 "공개 배포 전"으로 유예된 **`X-Forwarded-For` 신뢰 정책**을 오너가 정하게 한다.

---

## Owner decisions — 2026-09-05

- **축은 C — 앱 IP축 + XFF 신뢰 정책 확립.** 브리프의 추천(B, 전역 비용 상한)이
  아니라 정확한 축을 택했다. 그 결과 2026-08-22 의 *"IP 축 rate limit —
  `X-Forwarded-For` 신뢰 정책이 선행돼야 한다(공개 배포 전)"* 유예가 **닫혔다.**
- **터널 경로는 원격에서 직접 확인**하라는 지시(읽기 전용 접근 승인). 아래
  "착수 전 확인" 절이 그 실측으로 대체됐다.
- 브리프가 B 전제로 제안했던 계약 literal 은 C 에서 **IP당** 값으로 옮겨 채택했다
  (아래 "확정된 계약 literal").

**C 의 단점(브리프가 적은 것)이 실측으로 해소됐다.** 브리프는 *"신뢰 정책을
틀리면 위조 헤더로 우회되어 가드가 조용히 무력해진다"* 를 C 의 최대 위험으로
적었다. 실측 결과 그 위조 경로가 **둘 다 막힌다**: ① 터널 뒤에서는 엣지가 진짜
주소를 **오른쪽에 덧붙이므로** 오른쪽에서 읽으면 위조가 무의미하고 ② 앱에 직결하는
LAN 경로는 발신 주소가 **SNAT 되지 않고 그대로 도착**하므로 신뢰 대역 밖이라
XFF 자체를 읽지 않는다. 두 성질은 회귀로 잠갔다(`tests/test_signup_throttle.py`).

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

### ★ 착수 전 확인 — 2026-09-05 원격 실측으로 답했다 (오너 승인, 읽기 전용)

브리프 초판은 이것을 *"오너만 답할 수 있다"* 고 적었다. 오너가 서버 접근을 열어
줘서 **직접 쟀고**, 답은 추정과 **달랐다.**

| 물음 | 실측 답 |
|---|---|
| 터널 ingress 가 어디로 가는가 | **`frontend` nginx 로 간다.** 공개 오리진으로 보낸 표식 요청이 그 컨테이너 접근 로그에 그대로 찍혔다 |
| 공유 호스트의 **공용 리버스 프록시**를 지나는가 | **지나지 않는다.** 터널이 호스트에서 이 프로젝트의 frontend 포트로 바로 붙는다 — 공용 프록시는 경로 밖이다 |
| 그 공용 프록시에 이 프로젝트용 vhost 가 있는가 | **있으나 죽어 있다** — upstream 이름이 그 프록시의 네트워크에서 **해석되지 않는다**. 즉 살아 있는 경로가 아니라 **낡은 설정**이다(타 프로젝트 저장소 소관 → 아래 "Follow-up") |
| origin 이 보는 `remote_addr` 는 무엇인가 | 터널 트래픽 전부가 **도커 게이트웨이 한 주소**다 → 이 축으로 버킷을 나누면 전 인터넷이 한 버킷 |
| origin 이 보는 `X-Forwarded-For` 는 | **`<클라이언트가 보낸 값>, <진짜 클라이언트 IP>`** — 엣지가 지우지 않고 **오른쪽에 덧붙인다** |
| 클라이언트가 `CF-Connecting-IP` 를 보내면 | **엣지가 403 으로 거절**한다(오리진에 닿지 않는다) |
| 앱 포트(:8520)에 LAN 에서 직결하면 앱이 보는 주소는 | **발신자 주소 그대로**(SNAT 없음) |

**이 실측이 설계를 바꿨다.** ① nginx `limit_req`(선택지 A)는 **경로 위에 있기는
하나**, `remote_addr` 가 한 주소라 real-ip 설정 없이는 전역 상한으로 퇴화한다 —
"nginx 라서 싸다"는 이점이 그대로 오지 않는다. ② XFF 를 **오른쪽에서** 읽으면
경로를 몰라도 정답이 나온다. 그래서 C 를 앱에 두되 축 해석을 이 규칙으로 못박았다.

---

## 선택지

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. nginx `limit_req` + Cloudflare real-ip** | `location = /api/auth/signup` 에 `limit_req_zone $binary_remote_addr rate=5r/m`, 앞단에 `set_real_ip_from <터널 소스>` + `real_ip_header CF-Connecting-IP` | **요청이 앱에 닿기 전에 거절** — Argon2·이벤트 루프를 아예 안 태운다. 앱 코드 무변. 가장 싼 방어 | 터널이 nginx 로 가야만 효과가 있다(미확인). **LAN 직접 :8520 경로는 그대로 무방비**. `set_real_ip_from` 대상이 컨테이너 재시작으로 바뀔 수 있다. 회귀 테스트가 pytest 밖(nginx 설정) |
| **B. 앱 축 — IP 를 보지 않는 전역 비용 상한** | signup 전용 전역 토큰버킷(예: 분당 N건) + pending 행 상한 + username/password 최대 길이. **IP 를 전혀 안 본다** | XFF 신뢰 정책을 정하지 않고 **오늘 닫힌다**. 진입 경로(터널·nginx·직접 :8520·LAN) 무관하게 동일 적용. pytest 회귀로 양방향 가드 가능. 코드가 작다 | 공격자 1명이 **정상 가입을 막는다**(가용성 DoS). 다만 가입은 희소 행위 + 승인제라 피해가 "몇 분 뒤 다시 시도"에 그친다 |
| **C. 앱 축 IP 레이트리밋 + XFF 신뢰 정책 확립** | `TRUSTED_PROXY_HOPS`/`CF-Connecting-IP` 파싱 정책을 세우고 IP별 카운터를 Mongo 에 둔다(P-6 `login_guard` 패턴 재사용) | 축이 정확하다. **P-6 이 유예한 로그인 IP 축도 같이 닫힌다**. 배포 경로와 무관 | 가장 비싸다(신뢰 정책 + 파서 + 저장소 + 테스트). 거절해도 **요청은 이미 앱까지 와서 이벤트 루프를 점유**한다(Argon2 만 회피). 신뢰 정책을 틀리면 위조 헤더로 우회되어 **가드가 조용히 무력해진다** |
| **D. 가입 표면을 닫는다** | `AUTH_SIGNUP_ENABLED=false` 토글(또는 초대 코드 요구). 켜는 날 A~C 중 하나를 정한다 | 한 줄. 승인된 계정이 오너뿐이라 **실사용 손실 0**. 오늘의 노출이 즉시 0 | 문제를 미룬다 — 공개 전환 시 이 결정이 그대로 되돌아온다. 프론트 "새 계정 요청" 폼이 죽은 UI 가 된다(S-1 랜딩·약관 트리거와 함께 다뤄야 함) |

---

## Recommendation(구현자 추천 — **채택되지 않았다**. 오너는 C 를 골랐다)

> 아래는 실측 **전에** 쓴 추천이라 그대로 남긴다. 추천이 빗나간 지점이 기록으로
> 값이 있다: B 를 민 이유는 *"C 는 신뢰 정책을 틀리면 조용히 무력해진다"* 였는데,
> 실측이 **틀릴 여지 자체를 좁혔다**(엣지가 오른쪽에 덧붙인다 · 직결은 SNAT 되지
> 않는다). 즉 이 추천의 근거는 사실이 아니라 **모르는 상태**였다.

### 원문 — B 를 지금, A 를 터널 확인 후 얹는다(2단)

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

---

## 확정된 계약 literal (C, 2026-09-05 시행)

| 값 | 확정 | 자리 | 근거 |
|---|---|---|---|
| signup 상한 | **발신 IP당 시간당 5건**(고정창) | `auth/signup_guard.py` `DEFAULT_MAX_REQUESTS`·`DEFAULT_WINDOW_SECONDS` | 정상 가입은 승인제 1인 운영에서 하루 한 자릿수. IP 하나가 하루에 태울 Argon2 를 120회로 묶는다 |
| env override | `AUTH_SIGNUP_MAX_REQUESTS`·`AUTH_SIGNUP_WINDOW_SECONDS` — **파싱 실패·0 이하는 기동 거부** | `main.py::_default_signup_throttle` | `AUTH_LOGIN_MAX_FAILURES` 선례. 조용히 "no throttle" 이 되는 것이 no throttle 보다 나쁘다 |
| 신뢰 대역 | 기본 `127.0.0.0/8`·`::1/128`·`172.16.0.0/12`, env `AUTH_TRUSTED_PROXY_CIDRS` | `auth/client_ip.py` | **LAN 대역은 일부러 뺐다** — 넣는 순간 LAN 의 누구나 헤더로 자기 버킷을 고른다 |
| XFF 읽는 방향 | **오른쪽에서 왼쪽**, 신뢰 항목은 건너뛴다 | 같은 파일 | 위 실측 — 왼쪽은 공격자가 고르고 오른쪽 끝만 참이다 |
| 초과 시 응답 | **429** + `Retry-After` | `routers/auth.py` | 429 는 이 시스템에서 quota 전용이었다 → 두 번째 생산자로 **등재**(`tests/test_quota_enforcement_api.py::THROTTLED_OPERATIONS`) |
| pending 행 상한 | **200행** — 초과 시 429. 재요청(거절된 행 위)은 **면제** | `auth/users.py` `MAX_PENDING_SIGNUPS` | 승인 큐가 사람이 읽을 수 있는 크기를 넘지 않게. 면제하지 않으면 *"거절은 밴이 아니다"*(SoT v1.7.97)가 뒤집힌다 |
| `username` 최대 길이 | **64자** → 400 | `auth/users.py` `MAX_USERNAME_LENGTH` | Mongo 문서·해싱 비용 증폭 차단 |
| `password` 최대 길이 | **256자** → 400 | `auth/users.py` `MAX_PASSWORD_LENGTH` | 하한 12자는 기존(`MIN_PASSWORD_LENGTH`) |
| 저장소 | Mongo `signup_attempts`(URI 있을 때) / in-memory | `auth/signup_guard_mongo.py` | `login_guard` 선례. **다만 TTL 인덱스를 둔다** — 축이 username 이 아니라 인터넷 발신 주소라 행 집합에 상한이 없다 |

**최대 길이 둘과 pending 상한은 서비스에서 시행한다(모델 아님).** pydantic `max_length`
는 422 를 내는데 다른 signup 정책 거절은 전부 400 이라, 화면이 같은 뜻의 거절을 두
모양으로 받게 된다.

---

## Follow-up considerations

- **낡은 vhost 하나가 공유 호스트에 남아 있다** — 공용 리버스 프록시에 이 프로젝트용
  server 블록이 있는데 upstream 이 해석되지 않아 죽어 있다. 지금은 무해하지만(경로 밖),
  누군가 그 프록시의 네트워크를 손보는 순간 **살아나서 두 번째 진입로가 된다.**
  타 프로젝트 저장소 소관이라 여기서 고치지 않는다 — **오너에게 보고된 항목**이다.
- 429 는 프론트 가입 폼의 새 실패 모드다 — 문구는 넣었고(`AuthGate.tsx`), 두 상한을
  **구분하지 않는다**(어느 상한에 걸렸는지 알려 주면 홍수 쪽에 정보를 준다).
- nginx 앞단(선택지 A)을 나중에 얹는다면 `client_max_body_size` 와 S-2 의 보안 헤더가
  **같은 파일의 같은 슬라이스**다 — nginx 를 한 번만 여는 편이 싸다. 다만 `remote_addr`
  가 한 주소라 real-ip 설정이 선행돼야 IP 축이 성립한다.
- pending 행 상한은 **관리자 승인 큐의 UX 상한**이기도 하다 — 상한을 넘겼을 때 오너가
  무엇을 보는지는 아직 정해지지 않았다(현재 `GET /admin/signup-requests` 는 무제한 목록).
- 스로틀 카운터는 **키가 문자열**이라 축을 바꿔도 저장소가 재사용된다.

## Deferred / out of scope

- **로그인 IP 축**(P-6 유예) — 이 슬라이스는 signup 축만 닫았다. `client_ip.py` 가
  생겼으므로 남은 것은 "로그인에도 붙일지"라는 **정책 판단 하나**다.
- **나머지 미인증 표면 셋**(LLM 게이트웨이 · in-stack llama `:9080` · embedding `/embed`) —
  트리거는 D8-7 G2~G6 와 같은 원격·다중 호스트 배포다.
- **S-1 quota dedupe · S-2 nginx 보안 헤더 · S-0 문서 스윕** — 각각 별도 슬라이스.
- **가입 열기 자체**(자동 승인 전환) — 오너 결정이며 랜딩·약관과 같은 트리거.
