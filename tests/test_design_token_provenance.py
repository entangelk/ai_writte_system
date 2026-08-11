"""팔레트의 **출처를 잇는 연결선** (Phase 10 Slice 10.1, D2=ⓑ).

두 정본은 중복이 아니다 —

- ``docs/plans/10_palette_contrast.py`` = *"그 값이 왜 그 값인가"*(OKLCH 램프 ·
  색역 처리 · WCAG 검산). 값을 **만드는** 자리.
- ``frontend/src/styles.css`` 의 ``:root`` = *"화면이 실제로 쓰는 값"*. 값을
  **소비하는** 자리.

**이 파일이 그 연결이다.** ``styles.css`` 주석은 *"여기 hex 를 손으로 고치지 말 것 —
스크립트를 고치고 다시 돌린 뒤 옮긴다"* 라고 적고 있지만, **적어 두는 것만으로는 아무도
막지 못한다.** 손으로 한 글자 고치면 그 순간 팔레트는 "계산해서 세웠다"가 아니게 되고,
**대비 검산은 더 이상 화면에 뜨는 색을 말하지 않는다** — 그런데 회귀는 전부 green 이다
(CSS 값을 재는 것은 프론트 가드 ``designTokens.test.ts`` 이고, 그쪽은 *토큰 체계의
무결성*을 보지 이 값이 **어디서 왔는지**는 모른다).

**★ 왜 프론트가 아니라 여기(pytest)인가**: 생성기가 파이썬이다. vitest 에서 이 스크립트를
돌리려면 서브프로세스로 파이썬을 불러야 하고, 그러면 프론트 스위트가 파이썬 런타임에
의존하게 된다. 두 정본을 **같은 프로세스에서** 볼 수 있는 자리가 여기뿐이다. 파이썬
테스트가 저장소의 비-파이썬 파일을 읽는 것은 ``test_activity_ui_labels.py``(TS/CSS)·
``test_docs_indexes.py``(문서)·``test_compose_exposure.py``(compose YAML) 의 선례를 따른다.

**양방향**:

- under-strict — CSS 의 hex 를 손으로 고치면 ``test_every_primitive_matches`` 가 실패한다.
- over-strict — 스크립트만 고치고 CSS 로 옮기지 않아도 **같은 셀이** 실패한다(값이 갈리는
  것 자체가 결함이지 방향이 문제가 아니다).
- 그리고 ``test_the_generator_still_passes_its_own_contrast_check`` 가 **검산 자체**를
  지킨다 — 램프를 고쳐 CSS 까지 성실히 옮겼는데 그 값이 WCAG 를 깨는 경우가 남기 때문이다.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_GENERATOR = _ROOT / "docs" / "plans" / "10_palette_contrast.py"
_STYLESHEET = _ROOT / "frontend" / "src" / "styles.css"


def _load_generator():
    spec = importlib.util.spec_from_file_location("_palette", _GENERATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_palette"] = module
    spec.loader.exec_module(module)
    return module


def _primitives_declared_in_css() -> dict[str, str]:
    """``:root`` 에 적힌 primitive 선언만. semantic 은 ``var(...)`` 참조라 안 잡힌다."""
    text = _STYLESHEET.read_text(encoding="utf-8")
    root = text[: text.index("\n}\n")]
    return {
        name: value
        for name, value in re.findall(
            r"^\s*--((?:blue|slate|danger|warn|ok)-\d+)\s*:\s*(#[0-9a-f]{6})\s*;",
            root,
            re.MULTILINE,
        )
    }


class PaletteProvenanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = _load_generator()
        self.css = _primitives_declared_in_css()

    def test_every_primitive_matches_the_generator_output(self) -> None:
        """CSS 의 primitive 전부가 스크립트가 지금 내는 값과 같아야 한다."""
        expected = self.generator.P

        # 이름 집합부터 — CSS 에만 있거나 스크립트에만 있는 토큰은 그 자체로 결함이다.
        self.assertEqual(
            sorted(self.css), sorted(expected),
            "CSS 의 primitive 목록과 생성기의 목록이 다르다 — 한쪽만 고쳤다",
        )

        for name in sorted(expected):
            with self.subTest(token=name):
                self.assertEqual(
                    self.css[name], expected[name],
                    f"--{name} 가 갈렸다. CSS={self.css[name]} 생성기={expected[name]} — "
                    "손으로 고쳤거나 스크립트 수정을 옮기지 않았다. "
                    "`python3 docs/plans/10_palette_contrast.py` 출력을 옮긴다",
                )

    def test_the_generator_still_passes_its_own_contrast_check(self) -> None:
        """램프를 바꾸더라도 **WCAG 2.2 AA 를 깨면서** 바꾸지는 못하게 한다.

        위 셀만 있으면 "둘이 같기만 하면" 통과하므로, 둘을 나란히 나쁘게 바꾸는 변경이
        빠져나간다. 여기서 검산 자체를 돌린다 — 브리프가 *"통과 여부가 아니라 설계 입력"*
        이라고 적은 그 기준이다.
        """
        failures = []
        for foreground, background, required, purpose in self.generator.PAIRS:
            ratio = self.generator.contrast(
                self.generator.P[foreground], self.generator.P[background]
            )
            with self.subTest(pair=f"{foreground} on {background}"):
                self.assertGreaterEqual(
                    round(ratio, 2), required,
                    f"{purpose}: {ratio:.2f}:1 < {required}:1",
                )
            if round(ratio, 2) < required:
                failures.append(purpose)
        self.assertEqual(failures, [])

    def test_prose_that_states_the_pair_count_matches_the_generator(self) -> None:
        """검산 짝 수를 **글로 적은 자리**가 실제 `PAIRS` 와 같아야 한다.

        위 셀들은 값(hex·대비)을 묶지만 **서술은 안 묶는다.** 그래서 표면 계층이
        늘며 짝이 18 → 30 이 됐을 때 **세 곳이 서로 다른 수를 말하는 상태**가
        됐다(브리프 18 · `styles.css` 주석 28 · work_log 18). 독립 검증 H1 이
        잡았고, *"세는 사람이 여럿이면 언젠가 갈린다"* 는 이 저장소가
        `test_docs_indexes.py` 로 이미 한 번 배운 병이다 — 같은 처방을 쓴다.

        **여기서 재는 것은 서술이지 값이 아니다.** 짝을 늘리거나 줄이면 이 셀이
        실패하고, 그때 **문서를 함께 고치라는 뜻**이다.
        """
        expected = len(self.generator.PAIRS)
        claims = {
            "frontend/src/styles.css": r"WCAG 2\.2 AA (\d+)짝 전수 검산",
            "docs/daily_logs/2026-08-11/work_log.md": r"WCAG 2\.2 AA (\d+)짝 전수 검산",
            "docs/plans/10-frontend-design-system-decisions.md":
                r"#### WCAG 2\.2 검산 — \*\*(\d+)짝\*\* 전수",
        }
        for relative, pattern in claims.items():
            with self.subTest(document=relative):
                text = (_ROOT / relative).read_text(encoding="utf-8")
                found = re.findall(pattern, text)
                self.assertEqual(
                    len(found), 1,
                    f"{relative}: 이 주장을 정확히 한 번 찾지 못했다 — 문구가 "
                    "바뀌었으면 위 claims 도 함께 고친다",
                )
                self.assertEqual(
                    int(found[0]), expected,
                    f"{relative} 가 {found[0]}짝이라 적었지만 실제 PAIRS 는 {expected}짝",
                )

    def test_the_brief_semantic_table_matches_the_stylesheet(self) -> None:
        """결정 브리프의 semantic 표가 `:root` 와 갈리지 못하게 한다.

        **같은 병의 세 번째다.** ① primitive hex 가 갈림(→ 위 출처 셀) ② 짝 수
        prose 가 세 곳에서 갈림(→ 위 prose 셀) ③ 그리고 semantic 표가 **9행이
        빠지고** `--border-hairline` 매핑까지 틀린 채로 남아 있었다(독립 검증
        잔여 니트). 앞의 둘을 가드로 닫으면서 이 표만 손으로 두면 **다음 슬라이스가
        토큰을 하나 더할 때 또 갈린다** — 사람이 두 곳을 동시에 기억해야 하는 구조가
        원인이지 부주의가 원인이 아니다.

        **표는 정본이 아니라 사본이다.** 정본은 `:root` 이고, 토큰을 먼저 만든 뒤
        표를 맞춘다. 양방향 — 어느 한쪽만 고쳐도 실패한다.
        """
        css = _STYLESHEET.read_text(encoding="utf-8")
        root = css[: css.index("\n}\n")]
        actual = dict(
            re.findall(
                r"^\s*(--[a-z0-9-]+)\s*:\s*var\((--[a-z0-9-]+)\)\s*;", root, re.MULTILINE
            )
        )

        brief_path = _ROOT / "docs" / "plans" / "10-frontend-design-system-decisions.md"
        brief = brief_path.read_text(encoding="utf-8")
        section = brief[
            brief.index("#### semantic (2계층)") : brief.index("#### WCAG")
        ]
        listed = dict(
            re.findall(r"^\|\s*`(--[a-z0-9-]+)`\s*\|\s*`([a-z0-9-]+)`\s*\|", section, re.MULTILINE)
        )

        self.assertEqual(
            sorted(listed), sorted(actual),
            "브리프 semantic 표와 :root 의 토큰 목록이 다르다 — 한쪽만 고쳤다",
        )
        for token in sorted(actual):
            with self.subTest(token=token):
                self.assertEqual(
                    listed[token], actual[token][2:],
                    f"{token} 의 primitive 매핑이 갈렸다. "
                    f"브리프={listed[token]} :root={actual[token][2:]}",
                )

    def test_body_text_clears_the_stricter_AAA_bar_on_every_surface(self) -> None:
        """본문만은 AA 로 만족하지 않기로 한 결정(장시간 읽고 쓰는 도구)을 잠근다.

        이것이 없으면 본문 잉크를 AA 경계(4.5)까지 밝혀도 위 셀이 통과한다.
        """
        surfaces = ("blue-50", "slate-50", "slate-0", "blue-100")
        for surface in surfaces:
            with self.subTest(surface=surface):
                ratio = self.generator.contrast(
                    self.generator.P["blue-900"], self.generator.P[surface]
                )
                self.assertGreaterEqual(round(ratio, 2), 7.0)
