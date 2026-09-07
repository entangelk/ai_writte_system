"""서비스 정책 계약 문서가 코드와 갈라지지 않는지 (오너 지시 2026-09-05).

**왜 필요한가 — 이 문서는 값을 옮겨 적었다.** `docs/service-policy-contract.md` 는
*"이 서비스가 회원에게 무엇을 약속하는가"* 를 한 장에서 답하는 것이 목적이라, 값을
안 적으면 목적을 못 이룬다. 그런데 값을 적는 순간 **두 번째 정본**이 되고, 상수를
고친 사람은 문서를 안 고친다(이 저장소에서 실제로 일어난 계열: README 절차 표의 SoT
버전이 v1.7.89 동안 v1.7.87 이었다).

그래서 문서를 **파생본으로 만든다** — 각 행이 자기 정본을 `모듈::상수` 로 가리키고,
이 가드가 그 상수를 실제로 import 해서 문서에 적힌 수와 대조한다. 상수를 고치고
문서를 안 고치면 전수가 빨개진다.

**양방향**:
- under-strict — 상수를 고치고 문서를 안 고치면 2번이 실패한다.
- under-strict — 정본을 잘못 가리키면(오타·이름 변경) 1번이 실패한다.
- over-strict — 값을 안 바꾸고 문장만 다듬는 것은 통과해야 한다. 그래서 재는 것은
  **셀 안의 수**이지 문장이 아니다.

★ **한계를 적어 둔다**: 이 가드는 *문서에 있는 행* 만 본다. 행을 통째로 지우면
아무것도 실패하지 않는다(`typeScale.test.ts` 의 M5 와 같은 계열). 거기를 닫으려면
"정책 상수의 전집합"을 코드에서 유도해야 하는데 그 집합의 정의가 없다 —
`DEFAULT_*`·`MAX_*` 를 전부 긁으면 정책이 아닌 상수가 섞인다. 행 삭제는 사람이
읽어서 잡는다.
"""

from __future__ import annotations

import importlib
import re
import unittest
from datetime import timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DOC = _ROOT / "docs" / "service-policy-contract.md"
_LEGAL_MAP = _ROOT / "docs" / "legal" / "README.md"
_PACKAGE = "services.application.app"

#: 표 한 행: | 축 | 값 | `모듈::상수`(들) |
_ROW = re.compile(r"^\|(?P<axis>[^|]+)\|(?P<value>[^|]+)\|(?P<sources>[^|]*)\|")
_POINTER = re.compile(r"`([a-z_0-9/]+\.py)::([A-Z_][A-Z_0-9]*)`")


def _rows() -> list[tuple[str, str, list[tuple[str, str]]]]:
    """문서에서 정본 포인터를 가진 표 행만 걷는다."""
    found = []
    for line in _DOC.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        pointers = _POINTER.findall(match["sources"])
        if not pointers:
            continue
        found.append((match["axis"].strip(), match["value"].strip(), pointers))
    return found


#: 표의 머리 행(대조 대상이 아니다).
_HEADERS = {"축", "정책", "정책 문서의 축", "조항", "구분", "공백"}


def _axes() -> list[str]:
    """정책 문서의 **모든 표 행**에서 축 이름을 걷는다.

    `_rows()` 와 달리 정본 포인터를 요구하지 않는다 — §8(정해졌으나 미시행)은
    아직 상수가 없어 포인터가 없지만, **약관이 담아야 하는 정책이라는 점은 같다.**
    """
    found = []
    for line in _DOC.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        axis = match["axis"].strip().strip("*").strip()
        if axis in _HEADERS or set(axis) <= {"-", ":", " "}:
            continue
        found.append(axis)
    return found


def _mapped_axes() -> set[str]:
    """대조표가 **첫 칸으로** 이름을 든 축.

    본문 어디든 문자열이 있으면 통과하게 두면 안 된다 — 변이 ML-1 실측: 행
    이름을 `계정 탈퇴` → `계정 탈퇴(미기재)` 로 바꿔도 부분 문자열이라 초록이었다.
    표의 첫 칸을 **정확히** 대조해야 잠긴다.
    """
    mapped = set()
    for line in _LEGAL_MAP.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        mapped.add(match["axis"].strip().strip("*").strip())
    return mapped


def _load(module_path: str, name: str) -> object:
    dotted = f"{_PACKAGE}.{module_path[:-len('.py')].replace('/', '.')}"
    return getattr(importlib.import_module(dotted), name)


def _numbers(text: str) -> list[int]:
    """셀에서 사람이 읽는 수를 뽑는다(`3600초당 5건` → [3600, 5])."""
    return [int(one.replace(",", "")) for one in re.findall(r"\d[\d,]*", text)]


def _as_number(value: object) -> int | None:
    """상수를 문서가 적을 법한 수 하나로 환산한다."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, timedelta):
        # 문서는 사람이 읽는 단위로 적는다 — 일이 떨어지면 일, 아니면 시간.
        if value % timedelta(days=1) == timedelta(0):
            return value.days
        return int(value.total_seconds() // 3600)
    return None


class ServicePolicyContractTest(unittest.TestCase):
    """`docs/service-policy-contract.md` 는 코드의 파생본이다."""

    def test_the_document_exists_and_carries_pinned_rows(self):
        self.assertTrue(_DOC.exists(), "정책 계약 문서가 없다")
        # 0행이면 아래 두 셀이 공허하게 만족된다 — 포인터를 다 걷어낸 것도 결함이다.
        self.assertGreaterEqual(len(_rows()), 10)

    def test_every_row_points_at_a_constant_that_still_exists(self):
        for axis, _value, pointers in _rows():
            for module_path, name in pointers:
                with self.subTest(axis=axis, source=f"{module_path}::{name}"):
                    try:
                        _load(module_path, name)
                    except (ImportError, AttributeError) as exc:  # noqa: PERF203
                        self.fail(f"정본 포인터가 죽었다: {exc}")

    def test_every_stated_number_matches_the_constant_it_cites(self):
        for axis, value, pointers in _rows():
            stated = _numbers(value)
            with self.subTest(axis=axis):
                actual = [_as_number(_load(*pointer)) for pointer in pointers]
                # 수가 아닌 상수(시간대 등)는 이 셀의 대상이 아니다.
                if any(one is None for one in actual):
                    continue
                self.assertEqual(
                    stated, actual,
                    f"'{axis}' 행이 {stated} 라고 적었는데 상수는 {actual} 다 —"
                    " 값의 정본은 상수 쪽이므로 문서를 고친다",
                )


class LegalDraftCoverageTest(unittest.TestCase):
    """약관 초안이 **우리가 정한 것을 담았는가**(오너 합격 기준 2026-09-07).

    오너가 약관 초안을 요구하며 낸 기준이 *"중요한건 우리가 정해놓은걸 제대로
    담았는가"* 였다. 그것을 **대조표의 존재**로 기계화한다 — `docs/legal/README.md`
    가 정책 문서의 각 축을 어느 조항이 받는지 적고, 이 셀이 **빠진 축이 있는지**만
    본다.

    ★ **조항의 내용이 맞는지는 재지 않는다.** 문장이 정책을 정확히 옮겼는지는
    사람이 읽어야 한다. 이 셀이 막는 것은 다른 것이다 — **정책이 늘었는데 약관이
    안 따라가는 것**(이 저장소에서 가장 흔한 문서 부패 방향이다).

    **양방향**: 정책 문서에 축을 더하고 대조표에 안 더하면 실패한다(under).
    대조표에서 행을 지우거나 **이름을 바꿔도** 실패한다(under — 변이 ML-1 이 이
    자리를 열었다: 종전 구현은 본문 부분 문자열을 봐서 이름 변경이 초록이었다).
    조항 번호만 고치는 것은 통과한다(over) — 재는 것은 **표 첫 칸의 축 이름**이지
    조항 번호가 아니다.
    """

    def test_the_mapping_table_covers_every_policy_axis(self):
        mapped = _mapped_axes()
        axes = _axes()
        # 0개면 공허하게 만족된다.
        self.assertGreaterEqual(len(axes), 15)
        missing = [axis for axis in axes if axis not in mapped]
        self.assertEqual(
            missing, [],
            "정책 문서에는 있는데 약관 대조표에 없는 축이다 — 약관 초안이 "
            "그 정책을 담았는지 확인하고 docs/legal/README.md 에 행을 더한다",
        )

    def test_both_drafts_stay_marked_as_unenforced_drafts(self):
        # 초안이 시행 중인 문서로 읽히면 안 된다. 실제 시행은 오너가 이 표식을
        # 걷어내는 것으로 시작하며, 그때 이 셀도 함께 고친다.
        for name in ("terms-of-service-draft.md", "privacy-policy-draft.md"):
            with self.subTest(document=name):
                text = (_LEGAL_MAP.parent / name).read_text(encoding="utf-8")
                self.assertIn("Draft — 법률 검토 전 · 미시행", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
