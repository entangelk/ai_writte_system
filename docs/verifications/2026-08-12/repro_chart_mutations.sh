#!/usr/bin/env bash
# 독립 검증 재현 — Slice 10.3 관측 차트 뮤테이션 C1–C5.
# (docs/verifications/2026-08-12/slice_10_3_observation_chart.md §Reproduction)
#
# 전제: 트리 clean & 커밋됨(HEAD=b60e90d). verification.md "clean-tree" 브랜치 —
# 복원은 git checkout --. 안전망: cp 백업 + diff -q byte-identical 증명 + trap.
# 매 뮤테이션마다 두 가드(chartColors·designTokens)를 함께 돌려 어느 셀이 물었는지
# (단독 물림) 확인한다. 안전에 필요한 건 타깃 파일 3개가 커밋된 상태인지뿐.
#
# 실행: bash docs/verifications/2026-08-12/repro_chart_mutations.sh
set -u
FE="/mnt/d/devel/에베베/ai_writte_system/frontend"
cd "$FE" || { echo "frontend not found"; exit 1; }
CC=src/observability/chartColors.ts
CSS=src/styles.css
DASH=src/observability/ObservabilityDashboard.tsx
cleanup() { git checkout -- "$CC" "$CSS" "$DASH" 2>/dev/null; }
trap cleanup EXIT
chk() { [ -z "$(git status --short -- "$CC" "$CSS" "$DASH")" ] || { echo "PRE-FLIGHT FAIL(targets dirty)"; exit 1; }; }
restore() { local n="$1" f="$2"; git checkout -- "$f"; diff -q "$f" "/tmp/$n.bak" >/dev/null || { echo "RESTORE FAIL $n"; exit 1; }; echo "  [restored $n]"; }
runboth() { echo "  --- vitest chartColors+designTokens ---"; npx vitest run src/observability/chartColors.test.ts src/designTokens.test.ts 2>&1 | grep -E '×|Tests |Test Files' | tail -8; }

# C1: parseError 토큰 이름 오타 → chartColors 3셀 전부
chk; cp "$CC" /tmp/C1.bak
python3 - <<'PY'
p="src/observability/chartColors.ts"; s=open(p).read()
n=s.replace('parseError: "--chart-parse-error"','parseError: "--chart-parse-eror"',1); assert n!=s; open(p,"w").write(n)
PY
echo "### C1 expect: chartColors 3 cells ALL FAIL"; runboth; restore C1 "$CC"

# C2: :root 에서 --chart-provider-error 삭제 → chartColors 1·3
chk; cp "$CSS" /tmp/C2.bak
python3 - <<'PY'
p="src/styles.css"; s=open(p).read()
n=s.replace("  --chart-provider-error: #8c1f4a;\n","",1); assert n!=s; open(p,"w").write(n)
PY
echo "### C2 expect: chartColors cells 1 & 3 FAIL"; runboth; restore C2 "$CSS"

# C3: --chart-parse-error 를 크림슨(#8c1f4a) 동값으로 → chartColors cell 3 ONLY
chk; cp "$CSS" /tmp/C3.bak
python3 - <<'PY'
p="src/styles.css"; s=open(p).read()
n=s.replace("  --chart-parse-error: #9a6a24;","  --chart-parse-error: #8c1f4a;",1); assert n!=s; open(p,"w").write(n)
PY
echo "### C3 expect: chartColors cell 3 ONLY (series distinct)"; runboth; restore C3 "$CSS"

# C4: --chart-legacy(미사용) 추가 → chartColors cell 2 ONLY (dead token)
chk; cp "$CSS" /tmp/C4.bak
python3 - <<'PY'
p="src/styles.css"; s=open(p).read()
anchor="  --chart-parse-error: #9a6a24;\n"; add="  --chart-legacy: #123456;\n"; assert anchor in s
open(p,"w").write(s.replace(anchor, anchor+add, 1))
PY
echo "### C4 expect: chartColors cell 2 ONLY (dead chart token)"; runboth; restore C4 "$CSS"

# C5: 대시보드 첫 CartesianGrid stroke 를 리터럴 #d8d0c1 로 되박기 → designTokens TS셀 ONLY
chk; cp "$DASH" /tmp/C5.bak
python3 - <<'PY'
p="src/observability/ObservabilityDashboard.tsx"; s=open(p).read()
n=s.replace('stroke={color.grid}','stroke="#d8d0c1"',1); assert n!=s; open(p,"w").write(n)
PY
echo "### C5 expect: designTokens TS-literal cell ONLY (defect recurrence)"; runboth; restore C5 "$DASH"

echo "=== done; targets ==="; git status --short -- "$CC" "$CSS" "$DASH" && echo "(targets clean)"
