#!/usr/bin/env bash
# 독립 검증 재현 — Slice 10.4 pageLayout.test.ts 뮤테이션 3종(LM1–LM3).
# (docs/verifications/2026-08-12/slice_10_4_layout.md §Reproduction)
#
# 전제: 트리 clean & 커밋됨(HEAD=822bf10). verification.md "clean-tree" 브랜치 —
# 복원은 git checkout -- + cp 백업 + diff -q byte-identical 증명 + trap.
# 실행: bash docs/verifications/2026-08-12/repro_layout_mutations.sh
set -u
FE="/mnt/d/devel/에베베/ai_writte_system/frontend"
cd "$FE" || { echo "frontend not found"; exit 1; }
CSS=src/styles.css
cleanup() { git checkout -- "$CSS" 2>/dev/null; }
trap cleanup EXIT
chk() { [ -z "$(git status --short -- "$CSS")" ] || { echo "PRE-FLIGHT FAIL(dirty)"; exit 1; }; }
restore() { git checkout -- "$CSS"; diff -q "$CSS" "/tmp/$1.bak" >/dev/null || { echo "RESTORE FAIL $1"; exit 1; }; echo "  [restored $1]"; }
runguard() { echo "  --- pageLayout ---"; npx vitest run src/pageLayout.test.ts 2>&1 | grep -E '×|Tests ' | tail -5; }

# LM1: 페이지 수식자(overview-page)에 폭 override 재삽입 → cell 2 ONLY
chk; cp "$CSS" /tmp/LM1.bak
python3 - <<'PY'
p="src/styles.css"; s=open(p).read()
anchor="  padding-top: clamp(var(--space-8), 4vw, 3rem);\n}\n"   # workspace/admin 폭 블록의 끝
add=anchor+"\n.overview-page {\n  width: min(100%, 62rem);\n}\n"
assert anchor in s; open(p,"w").write(s.replace(anchor, add, 1))
PY
echo "### LM1 expect: 'lets no page modifier override that width' ONLY"; runguard; restore LM1

# LM2: 공통 폭 규칙에서 admin-page 누락 → cell 1 ONLY
chk; cp "$CSS" /tmp/LM2.bak
python3 - <<'PY'
p="src/styles.css"; s=open(p).read()
old=".workspace-page,\n.admin-page {\n"; new=".workspace-page {\n"
assert old in s; open(p,"w").write(s.replace(old,new,1))
PY
echo "### LM2 expect: 'sets the page width in exactly one place' ONLY"; runguard; restore LM2

# LM3: 컨테이너 폭(68)과 main max-width(68) 어긋매기기 → cell 3 ONLY
chk; cp "$CSS" /tmp/LM3.bak
python3 - <<'PY'
p="src/styles.css"; s=open(p).read()
old="  width: min(100%, 68rem);\n  padding-top: clamp(var(--space-8), 4vw, 3rem);"
new="  width: min(100%, 67rem);\n  padding-top: clamp(var(--space-8), 4vw, 3rem);"
assert old in s; open(p,"w").write(s.replace(old,new,1))
PY
echo "### LM3 expect: 'keeps the container width equal to the shell' ONLY"; runguard; restore LM3

echo "=== done; target ==="; git status --short -- "$CSS" && echo "(clean)"
