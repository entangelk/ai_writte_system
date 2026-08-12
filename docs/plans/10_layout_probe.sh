#!/usr/bin/env bash
# Phase 10 배치 실측 (Slice 10.4). 결과를 표로 찍는다.
#
# ★ 함정: snap 으로 설치된 chromium 은 $HOME 밖(예: /mnt/d, /tmp/claude-*)을 못 읽는다.
#   file:// 로 열면 조용히 **네트워크 오류 페이지**가 렌더되고 측정값이 빈다 —
#   실패처럼 안 보여서 오독하기 쉽다. 그래서 $HOME 아래로 복사해서 돌린다.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d "$HOME/.layout-probe.XXXXXX")"
trap 'rm -rf "$work"' EXIT
cp "$root/frontend/src/styles.css" "$root/docs/plans/10_layout_probe.html" "$work/"

for width in "${@:-1440}"; do
  printf '\n=== %spx 폭 ===\n' "$width"
  chromium --headless --disable-gpu --no-sandbox --virtual-time-budget=3000 \
    --window-size="$width",900 --dump-dom "file://$work/10_layout_probe.html" 2>/dev/null \
  | tr -d '\n' | grep -o '<pre id="probe-result">[^<]*' | sed 's/<pre id="probe-result">//' \
  | python3 "$root/docs/plans/10_layout_probe_report.py"

done
