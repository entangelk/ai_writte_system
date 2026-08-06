#!/usr/bin/env python3
"""검증 기록 원장을 디스크에서 다시 센다 — 건수·일수·판정 분포·파일별 판정 대조.

왜 스크립트인가: 2026-08-06 검증이 이 집계를 `/tmp/tally_ledger.py` 로 돌렸는데,
`/tmp` 는 재부팅 한 번에 사라진다(선례 `repro_outbox_retry.py`·`repro_router_split.py` 와
같은 이유로 기록 옆에 커밋한다).

무엇을 재는가 — `tests/test_docs_indexes.py::VerificationCountClaimsTest` 가 **잡는 것**과
**안 잡는 것**을 나란히 낸다:

  (a) 건수·일수                — 가드 안. 네 문서의 숫자 주장이 디스크와 맞는지.
  (b) 인덱스 표 분포의 합       — 가드 안. 합계만 맞으면 green.
  (c) 파일별 판정 ↔ 인덱스 분류 — **가드 밖.** 한 건을 잘못 분류해도 합계가 맞으면
                                  아무 테스트도 실패하지 않는다. 여기가 이 스크립트의 존재 이유다.

(c) 는 휴리스틱이다 — `## Verdict` 절 서두의 판정 문구를 읽는다. **불일치는 결함 후보이지
결함 판정이 아니다** — 사람이 그 파일을 열어 확인해야 한다.

★ **그 한계는 2026-08-06 에 실측으로 확인됐다.** 판정 표현이 영·한 혼용에 형식도 제각각이라
(`PASS` · `Conditional pass` · `조건부 승인` · `합격(조건부)` · 한 기록 안에 커밋별로 두 판정)
규칙을 바꿔 두 번 돌렸더니 각각 **5건·4건을 오분류**했다(두 번째는 `불합격` 을 4건으로 읽었는데
정본은 2건이다). 그래서 **분류는 사람이 하고**, 상시 가드
(`tests/test_docs_indexes.py::VerificationsIndexTest::test_every_record_row_states_a_verdict`)는
판정 문구를 파싱하지 않고 **행 구조와 판정 열이 비어 있지 않은가**만 잠근다.

**판정 열의 정본은 그 기록의 *최종* 판정이다**(오너 2026-08-06). 조건부로 나갔다가 조건이
닫혀 승격된 기록은 그 기록 자신의 최종 문구를 따른다.

    python3 docs/verifications/2026-08-06/tally_verification_ledger.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERIFICATIONS = ROOT / "docs" / "verifications"
INDEX = VERIFICATIONS / "README.md"

# 판정 문구는 파일마다 다르다 — "조건부 합격 (Conditional Pass)" · "합격(PASS) · Blocking 0" ·
# **"합격(조건부)"(어순이 뒤집힌 표기)**. 그래서 단순 부분문자열 스캔은 못 쓴다:
#   · 넓은 창을 보면 "합격 — 단, …조건부…" 같은 **뒤 문장**을 판정으로 오독한다.
#   · "조건부 합격"만 찾으면 "합격(조건부)"를 놓친다.
# 그래서 **판정 문장의 첫 매치 한 자리**만 보고, 같은 자리에서는 긴 것을 이긴다
# (초판이 이 둘을 다 밟아 5건을 오분류했다 — 이 주석이 그 실측 기록이다).
_VERDICT_PATTERN = re.compile(r"불합격|조건부\s*합격|합격\s*\(\s*조건부\s*\)|합격")
_CONDITIONAL = re.compile(r"조건부")


def verdict_of(record: Path) -> str:
    """`## Verdict` 절의 **판정 문장 한 줄**에서 판정을 읽는다. 못 읽으면 NONE."""
    text = record.read_text(encoding="utf-8")
    heading = re.search(r"^## +Verdict.*$", text, re.MULTILINE)
    if heading is None:
        return "NONE"
    lines = text[heading.start():].splitlines()
    # 판정은 제목 줄 뒤(`## Verdict — 조건부 합격`)이거나 그 아래 첫 비어 있지 않은
    # 줄이다. 그 한 줄을 넘어가면 근거 서술이라 판정이 아니다.
    statement = lines[0]
    if not _VERDICT_PATTERN.search(statement):
        statement = next((line for line in lines[1:] if line.strip()), "")
    found = _VERDICT_PATTERN.search(statement)
    if found is None:
        return "NONE"
    word = found.group()
    if word == "불합격":
        return "불합격"
    return "조건부 합격" if _CONDITIONAL.search(word) else "합격"


def index_verdict_of(record: Path) -> str:
    """인덱스 표에서 이 기록의 판정 열을 읽는다. 행이 없으면 MISSING."""
    link = f"({record.parent.name}/{record.name})"
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        if link in line and line.startswith("|"):
            cells = [cell.strip().strip("*") for cell in line.split("|") if cell.strip()]
            return cells[-1] if cells else "MISSING"
    return "MISSING"


def stated_distribution() -> dict[str, int]:
    """인덱스 '판정 분포' 표(가드가 읽는 그 표)를 파싱한다."""
    rows = re.findall(
        r"^\| \*{0,2}([^|*]+?)\*{0,2} \| \*{0,2}(\d+)\*{0,2} \|",
        INDEX.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return {label.strip(): int(count) for label, count in rows}


def main() -> int:
    records = sorted(VERIFICATIONS.glob("*/*.md"))
    days = {record.parent.name for record in records}

    print(f"(a) 디스크 실측       : {len(records)}건 / {len(days)}일치")

    stated = stated_distribution()
    print(f"(b) 인덱스 표 분포     : {stated} (합 {sum(stated.values())})")
    if sum(stated.values()) != len(records):
        print(f"    ★ 합이 파일 수와 다르다 — 가드가 잡는 자리다")

    mismatches = []
    for record in records:
        actual, indexed = verdict_of(record), index_verdict_of(record)
        if actual == "NONE":
            continue  # 판정 절이 없는 초기 기록 — 대조 대상 아님
        if actual != indexed:
            mismatches.append((record.relative_to(ROOT), actual, indexed))

    print(f"(c) 파일별 판정 대조   : 불일치 {len(mismatches)}건 (가드 밖)")
    for path, actual, indexed in mismatches:
        print(f"    - {path}\n        파일='{actual}'  인덱스='{indexed}'")
    if mismatches:
        print("    ※ 불일치는 결함 '후보'다 — 해당 파일을 열어 확인한 뒤 분류를 정한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
