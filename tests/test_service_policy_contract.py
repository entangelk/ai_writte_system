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
_PACKAGE = "services.application.app"

#: 표 한 행: | 축 | 값 | `모듈::상수`(들) |
_ROW = re.compile(r"^\|(?P<axis>[^|]+)\|(?P<value>[^|]+)\|(?P<sources>[^|]+)\|\s*$")
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
