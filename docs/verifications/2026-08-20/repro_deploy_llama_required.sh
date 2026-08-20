#!/usr/bin/env bash
# 독립 검증 재현 — cd1d82d (배포 override LLAMA_BASE_URL 필수화 = B2 시행 · over-strict 셀 = B1 폐쇄).
# (docs/verifications/2026-08-20/deploy_llama_required_b1_b2.md §Reproduction)
#
# 전제: 트리 clean & 커밋됨. verification.md "clean-tree" 브렌치 — 복원은 git checkout --.
# 안전망: 매 뮤테이션 전 status 공백 확인 + cp 백업 + diff -q byte-identical 증명 + trap.
#
# ★ 환경 통제가 이 재현의 핵심 축이다: 이 머신 .env(기계 로컬, 커밋 금지)이
# LLAMA_BASE_URL=http://192.168.1.22:9080 를 제공하므로, compose 가 .env 를 자동
# 로드하면 "주소 없음 → rc=1" 이 재현되지 않는다. 그래서 Part 1은 --env-file /dev/null
# 로 .env 를 우회하고 셸 env 로만 값을 준다(구현자 work_log 는 이 통제 방법을 적지 않았다).
#
# 실행: bash docs/verifications/2026-08-20/repro_deploy_llama_required.sh
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1

BASE=docker-compose.yml
LLAMA=docker-compose.llama.yml
EXT=docker-compose.external.yml
TESTF=tests/test_compose_backend_env.py
THREE="EMBEDDING_SERVICE_URL=https://ext-embed.example CHROMA_HOST=ext-chroma ELASTICSEARCH_URL=https://ext-es.example"

chk() { [ -z "$(git status --short)" ] || { echo "PRE-FLIGHT FAIL(tree dirty)"; exit 1; }; }
mut() {  # mut <파일> <기존 리터럴> <뮤테이션 리터럴> <백업명>
  local f="$1" old="$2" new="$3" bak="$4"
  chk; cp "$f" "/tmp/$bak.bak"
  python3 - "$f" "$old" "$new" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
assert s.count(sys.argv[2]) == 1, f"literal count={s.count(sys.argv[2])}"
p.write_text(s.replace(sys.argv[2], sys.argv[3]), encoding="utf-8")
PY
  python3 -m pytest -q "$TESTF" 2>&1 | grep -E "FAILED|failed|passed" | tail -4
  git checkout -- "$f"; diff -q "$f" "/tmp/$bak.bak" >/dev/null || { echo "RESTORE FAIL $bak"; exit 1; }
  chk; echo "  [restored $bak — tree clean]"
}

echo "═══ Part 1. compose config 실측(환경 통제) ═══"
unset LLAMA_BASE_URL EMBEDDING_SERVICE_URL CHROMA_HOST ELASTICSEARCH_URL
echo "── P0 배포, .env 있는 그대로 + 셸 3개 → rc=0(.env 의 LLAMA 가 :? 를 마스킹 — 중립화 필요성의 실증)"
env $THREE docker compose -f $BASE -f $EXT config >/dev/null 2>/tmp/p0.err; echo "rc=$? : $(head -1 /tmp/p0.err)"
echo "── P0b 배포, 아무것도 안 줌(.env 활성) → LLAMA 아닌 다른 필수부터 rc=1(어떤 서비스가 먼저 걸리는지는 실행마다 다르다; LLAMA 는 .env 가 채운다)"
docker compose -f $BASE -f $EXT config >/dev/null 2>/tmp/p0b.err; echo "rc=$? : $(head -1 /tmp/p0b.err)"
echo "── A2 배포, 넷 중 LLAMA 만 빼기(.env 우회) → rc=1 + 한국어 사유"
env $THREE docker compose --env-file /dev/null -f $BASE -f $EXT config >/dev/null 2>/tmp/a2.err; echo "rc=$? : $(head -1 /tmp/a2.err)"
echo "── A3 배포, 넷 다 지정 → rc=0 · 병합 후 base env 키 생존 확인"
env $THREE LLAMA_BASE_URL=https://ext-llm.example docker compose --env-file /dev/null -f $BASE -f $EXT config >/tmp/a3.yml 2>/dev/null; echo "rc=$?"
sed -n '/^  gateway:/,/^  [a-z]/p' /tmp/a3.yml | grep -E "LLAMA_|extra_hosts|host.docker" | sed 's/^ *//;s/^/  /'
grep -qE "^  llama:" /tmp/a3.yml && echo "  llama 서비스: 있음(비정상)" || echo "  llama 서비스: 없음(정상 — 배포엔 in-stack 모델이 없다)"
echo "── A4 배포, 호스트 llama 명시 → 값이 그대로 통과(선택지 유지 = 감사 F2 실측)"
env $THREE LLAMA_BASE_URL=http://host.docker.internal:9080 docker compose --env-file /dev/null -f $BASE -f $EXT config 2>/dev/null | grep -m1 "LLAMA_BASE_URL:"
echo "── A5 배포, LLAMA 빈 값 → rc=1(:? 는 빈 값도 거부)"
env $THREE LLAMA_BASE_URL= docker compose --env-file /dev/null -f $BASE -f $EXT config >/dev/null 2>/tmp/a5.err; echo "rc=$? : $(head -1 /tmp/a5.err | tail -c 60)"
echo "── B1a base 단독, env 완전 무변 → host.docker.internal:9080 폴백(기본 방식 = ②의 '내부'가 호스트 llama)"
docker compose --env-file /dev/null -f $BASE config 2>/dev/null | grep -m1 "LLAMA_BASE_URL:"
echo "── B1b base 단독, .env 있는 그대로 → .env 값이 이긴다(① env 우선)"
docker compose -f $BASE config 2>/dev/null | grep -m1 "LLAMA_BASE_URL:"
echo "── B2 base+llama(알파), env 무변 → llama:9080 폴백 · llama 서비스 · gateway depends_on"
docker compose --env-file /dev/null -f $BASE -f $LLAMA config >/tmp/b2.yml 2>/dev/null; grep -m1 "LLAMA_BASE_URL:" /tmp/b2.yml
grep -qE "^  llama:" /tmp/b2.yml && echo "  llama 서비스: 있음" ; sed -n '/^  gateway:/,/^  [a-z]/p' /tmp/b2.yml | grep -A2 "depends_on:" | sed 's/^ *//;s/^/  /'
echo "── B3 base+llama(알파), LLAMA 셸 지정 → env 값이 이긴다(① '모델이 있어도 API 면 API 로')"
env LLAMA_BASE_URL=http://192.168.1.22:9080 docker compose --env-file /dev/null -f $BASE -f $LLAMA config 2>/dev/null | grep -m1 "LLAMA_BASE_URL:"

echo; echo "═══ Part 2. 뮤테이션 배터리(가드 셀 페어링) ═══"
echo "── M1 under-strict: external :? → :- 되돌리기(원 결함 재현) → 신규 under-strict 셀 1"
mut $EXT \
  'LLAMA_BASE_URL: "${LLAMA_BASE_URL:?외부 LLM API 주소가 필요하다 (OpenAI 호환 /v1/chat/completions)}"' \
  'LLAMA_BASE_URL: "${LLAMA_BASE_URL:-http://host.docker.internal:9080}"' M1
echo "── M2 B1 시나리오: base :- → - 대시화 → 신규 over-strict 셀 1(종전 0셀 → 이제 1셀)"
mut $BASE \
  'LLAMA_BASE_URL: "${LLAMA_BASE_URL:-http://host.docker.internal:9080}"' \
  'LLAMA_BASE_URL: "${LLAMA_BASE_URL-http://host.docker.internal:9080}"' M2
echo "── M3 base 에 :? '통일'(과잉 교정) → 같은 over-strict 셀 1"
mut $BASE \
  'LLAMA_BASE_URL: "${LLAMA_BASE_URL:-http://host.docker.internal:9080}"' \
  'LLAMA_BASE_URL: "${LLAMA_BASE_URL:?주소 필요}"' M3
echo "── M4 배포 규칙을 llama.yml 에 유출(:?) → 기존 InStack 셀 1"
mut $LLAMA \
  'LLAMA_BASE_URL: "${LLAMA_BASE_URL:-http://llama:9080}"' \
  'LLAMA_BASE_URL: "${LLAMA_BASE_URL:?주소 필요}"' M4
echo "── M4b llama.yml 대시화 → InStack 2셀(08-15 검증의 'llama.yml 에선 2셀' 재도출)"
mut $LLAMA \
  'LLAMA_BASE_URL: "${LLAMA_BASE_URL:-http://llama:9080}"' \
  'LLAMA_BASE_URL: "${LLAMA_BASE_URL-http://llama:9080}"' M4b

echo; echo "── M2' 구(舊) 테스트 파일 × base 대시화 → 0셀(B1 원 지적의 실증)"
chk; git checkout cd1d82d~1 -- "$TESTF"
python3 - <<'PY'
import pathlib
p = pathlib.Path("docker-compose.yml"); s = p.read_text(encoding="utf-8")
old = 'LLAMA_BASE_URL: "${LLAMA_BASE_URL:-http://host.docker.internal:9080}"'
new = 'LLAMA_BASE_URL: "${LLAMA_BASE_URL-http://host.docker.internal:9080}"'
assert s.count(old) == 1
p.write_text(s.replace(old, new), encoding="utf-8")
PY
python3 -m pytest -q "$TESTF" 2>&1 | tail -1
git checkout HEAD -- "$TESTF" docker-compose.yml
chk; echo "  [restored old-file demo — tree clean]"
echo; echo "═══ 완료 ═══"
