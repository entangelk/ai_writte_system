#!/usr/bin/env bash
# 독립 검증 재현 — Slice 10.3 typeScale.test.ts 뮤테이션 M1–M5.
# (docs/verifications/2026-08-12/slice_10_3_typography_scale.md §Reproduction)
#
# 전제: 트리 clean & 커밋됨(HEAD=a4ec45c). verification.md "clean-tree" 브랜치 —
# 복원은 git checkout --. 추가 안전망: cp 백업 + 복원 후 diff -q byte-identical 증명
# + git status --short empty. 인터럽트돼도 복원되도록 trap 부착.
#
# 실행: bash docs/verifications/2026-08-12/repro_typescale_mutations.sh
set -u
REPO="/mnt/d/devel/에베베/ai_writte_system"
cd "$REPO/frontend" || { echo "frontend dir not found at $REPO"; exit 1; }
STYLES=src/styles.css
TEST=src/typeScale.test.ts

cleanup() { git checkout -- "$STYLES" "$TEST" 2>/dev/null; }
trap cleanup EXIT

# 안전에 필요한 건 *타깃 두 파일*이 커밋된 상태인지뿐(git checkout 이 다른 파일을
# 덮어쓰지 않으므로). verification.md 의 전수 gate 는 전체 트리지만, 재현 스크립트는
# 다른 작업이 있는 트리에서도 돌아야 하므로 타깃 파일로 좁힌다.
assert_clean() {
  local s; s=$(git status --short -- "$STYLES" "$TEST")
  [ -z "$s" ] || { echo "PRE-FLIGHT FAIL(target files dirty): $s"; exit 1; }
}
restore_and_verify() {
  local name="$1" file="$2" bak="/tmp/$1.bak"
  git checkout -- "$file"
  diff -q "$file" "$bak" >/dev/null || { echo "RESTORE FAIL($name)"; diff "$file" "$bak"; exit 1; }
  [ -z "$(git status --short -- "$file")" ] || { echo "POST-RESTORE DIRTY($name)"; exit 1; }
  echo "  [restored byte-identical, target clean]"
}
run_cell() { echo "----- $1 -----"; npx vitest run "$TEST" 2>&1 | grep -E '✓|×|Tests ' | tail -6; }

# M1: 값 0.889→0.9 (지수 주석 유지) — expect cell 1 FAIL (under-strict)
assert_clean; cp "$STYLES" /tmp/M1.bak
python3 - <<'PY'
p="src/styles.css"; s=open(p).read(); n=s.replace("  --type-small: 0.889rem;","  --type-small: 0.9rem;",1)
assert n!=s; open(p,"w").write(n)
PY
echo "### M1 expect: 'derives every step from the 1.125 ramp' FAIL"; run_cell M1; restore_and_verify M1 "$STYLES"

# M2: 지수 주석 ^-1→^-2 (값 유지) — expect SAME cell 1 FAIL (over-strict)
assert_clean; cp "$STYLES" /tmp/M2.bak
python3 - <<'PY'
p="src/styles.css"; s=open(p).read()
old="  --type-small: 0.889rem;   /* 1.125^-1 · 안내·알림·목록 보조 문구 */"
new="  --type-small: 0.889rem;   /* 1.125^-2 · 안내·알림·목록 보조 문구 */"
assert old in s; open(p,"w").write(s.replace(old,new,1))
PY
echo "### M2 expect: SAME cell FAIL"; run_cell M2; restore_and_verify M2 "$STYLES"

# M3: .workspace-status 의 var(--type-meta)→0.78rem (블록 한정) — expect cell 3 ONLY FAIL
assert_clean; cp "$STYLES" /tmp/M3.bak
python3 - <<'PY'
import re
p="src/styles.css"; s=open(p).read()
pat=r"(\.workspace-status\s*\{[^}]*?font-size:\s*)var\(\s*--type-meta\s*\)(;)"
n2,n=re.subn(pat, r"\g<1>0.78rem\g<2>", s, count=1, flags=re.S)
assert n==1, f"M3 expected 1 sub, got {n}"; open(p,"w").write(n2)
PY
echo "### M3 expect: 'keeps the migrated rules on the scale' FAIL (only)"; run_cell M3; restore_and_verify M3 "$STYLES"

# M4: 죽은 계단 추가(3.653/^11, ramp-correct, 미사용) — expect cell 2 FAIL
assert_clean; cp "$STYLES" /tmp/M4.bak
python3 - <<'PY'
p="src/styles.css"; s=open(p).read()
anchor="  --type-title: 2.027rem;   /* 1.125^6  · 화면 제목 */\n"
add="  --type-huge: 3.653rem;   /* 1.125^11 · 죽은 계단 */\n"
assert anchor in s; open(p,"w").write(s.replace(anchor, anchor+add, 1))
PY
echo "### M4 expect: 'leaves no step declared that nothing draws with' FAIL"; run_cell M4; restore_and_verify M4 "$STYLES"

# M5: MIGRATED 행 삭제 — expect NO failure (3 passed, 공식 한계)
assert_clean; cp "$TEST" /tmp/M5.bak
python3 - <<'PY'
p="src/typeScale.test.ts"; s=open(p).read()
old='  ".workspace-status": "meta",\n'; assert old in s; open(p,"w").write(s.replace(old,"",1))
PY
echo "### M5 expect: NO failure — 3 passed (documented limitation)"; run_cell M5; restore_and_verify M5 "$TEST"

echo "=== done; final target state ==="; git status --short -- "$STYLES" "$TEST" && echo "(targets clean)"
