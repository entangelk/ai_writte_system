# 검증 기록 — 스택 기동 + HANDOFF 머신 구분 절 (2026-07-27)

## Subject metadata
- **날짜**: 2026-07-27
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? 완료 상태를 정리")
- **검증자**: Claude(독립 검증, max effort)
- **대상 작업**: 작업 AI가 보고한 두 가지 — (1) HANDOFF.md 알파·베타·감마 머신 구분 절 신설, (2) 베타 머신 스택 기동(데이터 볼륨 초기화 포함) 및 health/route/LLM 응답 확인
- **정본 계약 참조**: `CLAUDE.md` "HANDOFF.md" 절(특히 "Never record machine-local observations as project facts" · 자가 검수 줄 형식 · "완료 서술 금지" 규칙) + `services/application/app/analysis/prompt_templates.py` 프롬프트 불변 계약
- **작업 출처**: working tree, uncommitted (`git status`: `M HANDOFF.md`만 변경, +19/-2). 본 검증은 커밋이 아닌 작업 트리 상태를 기준.

## Scope
이 검증은 명세 governed 기능 슬라이스가 아니라 **운용 + 문서 편집** 작업이다. 따라서 boundary matrix를 "스펙의 should-fire / should-NOT-fire 분기"가 아니라 **"작업자가 기록/보고한 사실 주장 ↔ 1차 사료(코드·live 상태·compose·테스트)"** 로 재정의해 적용했다.

점검 표면:
1. HANDOFF.md 편집 — CLAUDE.md HANDOFF 규칙 준수 여부 + 기록된 관측치의 진위
2. PromptTemplateConflict 진단 — 코드 메커니즘과 일치성 + "코드↔테스트 핀 일치" 주장
3. 운용 상태 주장 — "/health 200" · "9개 서비스 전부 healthy" · "operation 62개" · "관측 route 등록" · "외부 12B 응답"
4. 프로세스 — work_log / 결정 기록 존재 여부

## Methodology
독립 재도출. 작업자 주장을 복사하지 않고 각각 1차 사료에서 재확인.

- HANDOFF 편집: `git diff HANDOFF.md`(전체), `wc -l HANDOFF.md`
- live 상태: `docker compose ps --format ...`(health 컬럼), `docker inspect ... --format '{{json .State.Health}}'`, `docker exec ... netstat`/`nginx -T`
- 엔드포인트: `curl http://localhost:8520/health`, `/openapi.json`(operation 수 및 observability path 추출, python), `curl http://localhost:5520/...`
- LLM 경로: host `curl 192.168.1.22:9080/health` + gateway 컨테이너 내 `python3 socket.create_connection` / `urllib` (컨테이너에 wget/curl 없음)
- 프롬프트 sha: `python3 -c "hashlib.sha256(ANALYSIS_EXTRACT_TEMPLATE_V3...)"`
- compose/코드: `grep`, `Read` (conflict 메커니즘, nginx listen, healthcheck 정의)
- 로그 존재: `ls docs/daily_logs/2026-07-27/`, `ls docs/verifications/2026-07-27/`

## Findings

### 1. HANDOFF.md 편집 — 형식은 대체로 준수, 그러나 **거짓 관측치 1건 기록**
- **형식 OK**: 기존 "이 머신, 2026-07-26 기준 배포 스택은 내려가 있다" 줄을 **삭제 후 재작성**(append 아님) — CLAUDE.md "완료 서술 누적 금지" 규칙 준수. `> 마지막 자가 검수` 줄 갱신됨(2026-07-27). 머신-로컬 vs 항구적 성질 구분 절 명시적으로 추가. 길이 146줄(자가 검수 트리거 ~200줄 미만).
- **거짓 관측치(차단)**: HANDOFF에 **"전체 스택이 ... 9개 서비스 전부 Up·healthy로 떠 있다"** 라고 기록. 그러나 `docker compose ps` 실측:
  - healthy 7 — `application`·`gateway`·`mongo`·`elasticsearch`·`embedding`·`chroma` (+ 정확히는 6개에 healthcheck 있는 것 중 frontend 제외 → healthy 6... 재확인: application/gateway/mongo/elasticsearch/embedding/chroma = 6 healthy). `worker`/`generation_worker`는 healthcheck 자체가 없어 "Up" 상태일 뿐 "healthy" 아님(compose 246/288, generation_worker는 async 배경 워커 — 288-291). `frontend`는 **unhealthy**.
  - 실측 합산: **healthy 6 · unhealthy 1(frontend) · healthcheck 없음 2(worker/generation_worker)**.
  - 즉 "전부 healthy"는 **사실이 아니다**. 이는 CLAUDE.md가 금지하는 "machine-local 관측치를 부정확하게 사실로 기록"하는 정확한 실패 양상이다. 작업자 본인이 "머신-로컬 관측치를 믿지 말라"는 절을 같이 써 놓고도, 직접 `docker compose ps`로 확인하지 않은 듯한 상태로 "전부 healthy"를 적었다.
- **경미**: 자가 검수 줄에서 이전 형식의 "N줄" 카운트가 빠지고 작업 내용 설명으로 대체됨(`> ... · 3개 머신 구성 절 신설, stale 머신 관측치 1건 정정`). CLAUDE.md 예시는 `YYYY-MM-DD · N줄`. 146<200 이라 트리거 미발동이나, 줄을 건드인 이상 줄 수 표기 권장.
- **경미**: 베타 LLM `192.168.1.22:9080`(LAN IP)을 "항구적 성질" 표에 배치. IP는 머신/네트워크-로컬 성질. 단 `.env` 커밋 금지·머신별 덮쓰기 주의로 마킹해 두어 완화는 됨.

### 2. PromptTemplateConflict 진단 — 코드 메커니즘 일치(정본 측 재확인), 저장 측은 폐기로 비검증
- 코드(`prompt_templates.py:118-121`): `seed_template`이 저장된 동일 version의 body가 코드 body와 다르면 `PromptTemplateConflict` 발생 → 작업자 진단과 기계적으로 일치.
- **"코드↔테스트 핀 일치" 주장 — 참으로 확인**. `tests/test_prompt_templates.py:36-38`이 v3 body의 sha256을 `4376310…`로 pin. 재계산 결과 canonical v3 sha = `4376310080b4a3420be77cab53e27cc4cb3d89a9e93f136c2e908fcae27eb52a` → 작업자 인용 `4376310…`과 정확 일치.
- 이 실패 모드는 `test_seed_sequence_replays_against_previously_seeded_storage`(102-127)가 "2026-07-22 boot failure"로 명시해 둔 **기존에 문서화된 패턴**이다. 작업자가 2026-07-27에 같은 양상으로 재조우한 것은 일관됨.
- **비검증(한계)**: 작업자가 인용한 저장 old sha `fb4e272…`는 볼륨 초기화로 증거가 소거되어 재확인 불가. CLAUDE.md "Fixture grounding: manifest 신뢰 금지, 재계산" 원칙을 적용할 수 없는 상태. 진단의 저장 측은 작업자 진술에 의존. 단, 정본 측 재확인 + 알려진 실패 패턴 + 코드 메커니즘 일치로 진단 자체의 개연성은 충분.
- **부수**: dev 볼륨 비움으로 해소한 것은 dev-env 정체 데이터 정리로서 타당. 단, 볼륨 비움이 "owner 결정"이었다는 **독립적 근거가 없음**(대화 맥락에서 오너 명시 승인 확인 불가, work_log에도 미기록 — 아래 4).

### 3. 운용 상태 주장 — 대부분 참, "전부 healthy"만 거짓
- `/health` 200 — **참** (`curl localhost:8520/health` → `{"status":"ok"}` 200).
- OpenAPI operation 62개 — **참** (`/openapi.json` 실측 62).
- 관측 route `/projects/{project_id}/observability/kpi` GET 등록 — **참** (작업자 인용과 정확 일치).
- 외부 12B gemma-local 응답 — **참**(종단 확인). host `curl 192.168.1.22:9080/health`→200, 그리고 gateway 컨테이너 내 `socket.create_connection(('192.168.1.22',9080))` 성공 + `urllib /health`→200. gateway→LLM 네트워크 경로 실제 도달 확인.
- "9개 서비스 전부 healthy" — **거짓**(위 1참조). frontend unhealthy.

### 4. Frontend unhealthy 근본 원인 — **기존 결함(작업자 유발 아님)**, 그러나 보고 누락
- `docker-compose.yml:360-364` healthcheck = `wget -q -O /dev/null http://localhost/`. busybox wget이 `localhost`를 IPv6 `::1`로 풀고, nginx는 `listen 80;`(IPv4 `0.0.0.0:80` only, `::1` 미수신)이어서 **"Connection refused"**. `FailingStreak: 65`(일시 아님, 지속).
- **기능적으로는 정상** — host `curl localhost:5520`→200, 컨테이너 netstat `0.0.0.0:80 LISTEN nginx`. 즉 서빙은 되나 healthcheck만 거짓 보고.
- nginx/Dockerfile은 `46f6009`(frontend first slice) 이후 미변경 → 작업자의 `--build` 재빌드가 새로 유발한 것이 **아님**(사전 존재 결함).
- `depends_on`에 frontend를 바라보는 서비스가 없어 기능 차단은 없으나, 스택이 "완전히 healthy"가 아닌 상태로 보고되는 잠정 함정. 조치 후보: nginx `listen [::]:80;` 추가 또는 healthcheck를 `http://127.0.0.1/`로 변경.

### 5. 프로세스 — work_log 결방(차단 아님, 보강)
- `docs/daily_logs/2026-07-27/` **부재**. CLAUDE.md "Always update these files after completing tasks. No exceptions." 데이터 볼륨 초기화(파괴적·owner 결정 귀속)의 결정/근거가 어디에도 내구 기록되지 않았다(HANDOFF에 1줄 서술만). 작업자가 A/B 대기 중이라 회차 종료 후 남길 의도일 수 있으나, 파괴 조치는 즉시 기록 원칙.

## Issues / Risks

### Blocking (계약 의무)
- **B-1**: HANDOFF.md에 "9개 서비스 전부 Up·healthy"라는 부정확한 머신-로컬 관측치가 사실로 기록됨. 실측 6 healthy / 1 unhealthy / 2 healthcheck 없음. CLAUDE.md machine-local 관측 규칙 위반. HANDOFF 변경을 신뢰 가능 상태로 두려면 정정 필요.

### Hardening recommendations (비차단)
- H-1: frontend healthcheck 미설정(사전 존재 결함, `46f6009`-). nginx IPv6 listen 추가 또는 healthcheck `127.0.0.1`화. 본 슬라이스 범위 밖이나, "전부 healthy" 정정과 함께 처리하면 스택이 정직하게 보고됨.
- H-2: `docs/daily_logs/2026-07-27/work_log.md` 작성 — 특히 볼륨 초기화 결정의 근거/승인/영향 범위(어떤 dev 데이터가 소거됐는지) 명시.
- H-3: 자가 검수 줄에 "N줄" 복구(형식 일관).
- H-4: 베타 LLM IP를 "항구적 성질"이 아닌 "머신-로컬 배선(날짜 표기)"으로 재분류 권장.

## Verdict — **조건부 합격(Conditional pass)**
- **합격으로 인정되는 부분**: 운용 기동 자체는 진짜로 동작한다 — app healthy, gateway→외부 12B 종단 도달 확인, /health 200, 62 operation, 관측 route 등록, PromptTemplateConflict 진단은 코드 메커니즘·테스트 pin·알려진 실패 패턴과 일치. HANDOFF 편집 형식(append 아닌 재작성, self-audit 줄 갱신)도 규칙에 부합.
- **조건(해소 전까지 합격 아님)**: **B-1**. HANDOFF의 "전부 healthy" 거짓 기록을 정본에 맞게 정정(6 healthy / frontend unhealthy / worker·generation_worker healthcheck 없음)해야 다음 작업자가 속지 않는다. 이 정정 없이는 HANDOFF 변경을 trusted로 인정할 수 없다.
- 비검증 한계 명시: 저장 old sha `fb4e272…`는 볼륨 소거로 영원히 재확인 불가(진단의 개연성은 충분하나, 1차 사료 재도출은 불가).

## Outstanding items
- HANDOFF.md 변경 미커밋(working tree). B-1 정정 후 커밋 권장.
- 작업자가 제시한 갈림길 미결: (A) 실 12B로 파이프라인 관통해 `llm_call_audits` 적재 → 관측 화면 육안 검증 가능화 / (B) 빈 상태로 오너 UI dogfood.
- 볼륨 초기화 승인의 독립 근거 확보 필요(owner 확인) — H-2 work_log에 명시되면 해소.

## Reproduction
```bash
cd "/mnt/d/devel/에베베/ai_writte_system"
# (1) HANDOFF diff / 길이
git diff HANDOFF.md; wc -l HANDOFF.md
# (2) live 상태 + frontend unhealthy 근원
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
docker inspect ai_writte_system-frontend-1 --format '{{json .State.Health}}' | python3 -m json.tool
# (3) 엔드포인트 / operation 수 / 관측 route
curl -s localhost:8520/health
curl -s localhost:8520/openapi.json | python3 -c "import sys,json;d=json.load(sys.stdin);print(sum(1 for p in d['paths'] for m in p if m in('get','post','put','delete','patch')))" 2>/dev/null
# (4) gateway→LLM 종단
docker exec ai_writte_system-gateway-1 python3 -c "import urllib.request;print(urllib.request.urlopen('http://192.168.1.22:9080/health',timeout=8).status)"
# (5) canonical v3 sha 재계산
cd services/application && python3 -c "import hashlib;from app.analysis.prompt_templates import ANALYSIS_EXTRACT_TEMPLATE_V3 as t;print(hashlib.sha256(t.encode()).hexdigest())"
# (6) 로그 부재 확인
ls docs/daily_logs/2026-07-27/ docs/verifications/2026-07-27/
```
