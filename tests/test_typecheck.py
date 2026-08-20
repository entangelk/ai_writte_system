"""타입체커 가드 — docs/plans/script-rot-guard-decisions.md 결정 1=B · 1-b=가.

**이 셀들이 막는 것은 "타입이 없는 코드" 가 아니라 "돌지 않는 코드의 시그니처
부패" 다.** `scripts/calibrate_character_identity_threshold.py:20` 이 키워드 전용
생성자를 위치 인자로 불러 2026-07-12 부터 한 달 넘게 `TypeError` 로 깨진 채 green
이었다. 그 파일을 부르는 테스트가 0건이었고, CI·타입체커·린터가 전부 없어 검출 층이
하나도 없었기 때문이다.

**★ 이 파일은 mypy 가 없으면 skip 하지 않고 실패한다.** skip 은 가드를 조용히
없앤다 — 설치를 안 한 머신에서 초록이 뜨고, 그 초록이 "부패가 없다" 로 읽힌다.
그것이 애초에 이 가드가 막으려는 실패 모양이다(결정 1-b=가).
"""

from __future__ import annotations

import configparser
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG = _ROOT / "mypy.ini"

_INSTALL_HINT = (
    "mypy 가 이 머신에 없다. 이 가드는 skip 하지 않는다 — "
    "`python3 -m pip install -r requirements-dev.txt` 로 설치한다. "
    "(개발 전용 의존성이며 프로덕션 이미지에 들어가지 않는다.)"
)

#: mypy 가 억제로 받아들이는 주석 표기 전부. 공백은 선택이고(`#type:ignore`),
#: 파일 단위 프라그마(`# mypy: …`)도 같은 일을 한다 — 초판이 정준형 하나만 봤다가
#: 독립 검증에 셋으로 뚫렸다(2026-08-20 B1).
_SUPPRESSION = re.compile(r"#\s*(type:\s*ignore|mypy:)")

#: `[mypy]` 섹션에 허용된 키. 이 밖은 전부 "조용해지는 길" 이다 — `ignore_errors`,
#: `exclude`, `follow_imports = skip` 이 대표적이다.
_ALLOWED_KEYS = frozenset({
    "mypy_path", "ignore_missing_imports", "files", "disable_error_code",
})

#: 지금 끈 코드. 셀은 **부분집합**만 단정한다 — 넓히기(빼기)는 자유여야 한다.
_PINNED_DISABLED = frozenset({
    "arg-type", "operator", "attr-defined", "union-attr", "return-value",
    "assignment", "type-var", "var-annotated",
})

#: 표적 결함과 **같은 모양**의 최소 재현. 저장소 파일에 의존하지 않는다 — 그 파일이
#: 리팩터링되면 함께 죽는 가드는 가드가 아니다.
_PROBE = """\
class Thing:
    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url


def calls_it_wrong() -> Thing:
    return Thing("http://example")


def calls_it_right() -> Thing:
    return Thing(base_url="http://example")
"""

_PROBE_CLEAN = _PROBE.replace('return Thing("http://example")',
                              'return Thing(base_url="http://example")')


def _mypy(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mypy", *args],
        cwd=_ROOT, capture_output=True, text=True,
    )


class MypyAvailabilityTest(unittest.TestCase):
    def test_mypy_is_installed_and_says_how_to_get_it_when_it_is_not(self):
        result = _mypy("--version")
        self.assertEqual(result.returncode, 0,
                         f"{_INSTALL_HINT}\n\n{result.stderr}")
        self.assertTrue(result.stdout.startswith("mypy "), result.stdout)

    def test_the_dev_requirements_file_declares_it_and_production_does_not(self):
        # 결정 1-b 의 나머지 절반: 프로덕션 이미지에 타입체커가 실려 나가면 안 된다.
        dev = (_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("mypy", dev)
        for service in ("application", "embedding", "llm_gateway"):
            runtime = (_ROOT / "services" / service / "requirements.txt")
            with self.subTest(service=service):
                self.assertNotIn("mypy", runtime.read_text(encoding="utf-8"))


class RepositoryTypecheckTest(unittest.TestCase):
    def test_the_configured_scope_typechecks_clean(self):
        """억제 목록 없이 초록이어야 한다.

        좁힌 코드 집합에서 시작한 이유가 이것이다 — 기본 설정으로 열면 111건이
        나오고(2026-08-20 호스트 실측), 그것을 억제로 덮으면 억제 목록 자체가
        부채가 된다. 지금은 `# type: ignore` 가 한 줄도 없다.
        """
        result = _mypy()
        self.assertEqual(result.returncode, 0,
                         f"mypy 가 물었다:\n{result.stdout}\n{result.stderr}")

    def test_no_suppression_comment_carries_the_guard(self):
        """위 셀을 **주석으로** 초록으로 만드는 우회를 막는다.

        ★ 초판은 문자열 `"type: ignore"` 를 찾았고, 독립 검증(2026-08-20 B1)이 그
        검사를 **세 가지로 뚫었다**. mypy 가 억제로 받아들이는 표기가 하나가 아니다:

        - `#type:ignore[call-arg]` — **공백 없음**. 사람 눈에는 같고 문자열 매칭에는
          안 걸린다.
        - `# mypy: ignore-errors` — 파일 1행 프라그마. **파일 하나를 통째로** 끈다.
        - `# mypy: disable-error-code="call-arg"` — 같은 프라그마의 코드 지정형.

        그래서 정규식으로 넓혔다. **"억제 주석 0건" 이라는 계약 문언이 실제 잠금
        범위보다 넓었던 것이 그 지적의 핵심**이라, 여기서는 문언이 아니라 검사를
        넓혀 맞췄다.
        """
        offenders = []
        for path in sorted([*(_ROOT / "services").rglob("*.py"),
                            *(_ROOT / "scripts").rglob("*.py")]):
            for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                if _SUPPRESSION.search(line):
                    offenders.append(
                        f"{path.relative_to(_ROOT)}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "억제로 초록을 만들지 않는다")

    def test_the_config_cannot_be_quietly_weakened(self):
        """설정 파일로 조용해지는 길 전부를 잠근다 (2026-08-20 B1·H1 폐쇄).

        주석만 막으면 같은 일을 `mypy.ini` 에서 할 수 있다. 독립 검증이 둘을 뚫었다:

        - 퍼모듈 섹션 `[mypy-scripts.…]` + `ignore_errors = True` — **브리프가 스스로
          경고한 "억제 목록이 부채가 된다" 의 정확한 형태**다.
        - `files = services, scripts` → `files = services` — **범위 축소**. 검사 대상에서
          빼면 결함은 그대로 살아 있는데 저장소는 초록이다.

        그래서 벡터를 하나씩 막지 않고 **허용된 것만 남긴다**: 섹션은 `[mypy]` 하나,
        키는 아래 넷, 범위는 두 디렉터리, disable 목록은 고정 집합의 **부분집합**.
        부분집합인 이유는 **넓히기(코드를 목록에서 빼는 것)는 자유여야** 하기
        때문이다 — 브리프 §후속 고려의 확장 트리거를 이 셀이 막으면 안 된다.
        """
        parser = configparser.ConfigParser()
        parser.read(_CONFIG, encoding="utf-8")

        self.assertEqual(parser.sections(), ["mypy"],
                         "퍼모듈 섹션은 억제 목록이 되는 길이다")
        self.assertLessEqual(
            set(parser["mypy"]), _ALLOWED_KEYS,
            "이 키들 밖은 전부 조용해지는 길이다(ignore_errors·exclude·follow_imports 등)")

        scope = {part.strip() for part in parser["mypy"]["files"].split(",")}
        self.assertEqual(scope, {"services", "scripts"}, "범위를 줄이지 않는다")

        disabled = {code.strip().rstrip(",")
                    for code in parser["mypy"]["disable_error_code"].split()
                    if code.strip().rstrip(",")}
        self.assertLessEqual(
            disabled, _PINNED_DISABLED,
            "disable 목록에 새 코드를 더하는 것은 억제다 — 빼는 것(넓히기)은 자유다")


class GuardDirectionTest(unittest.TestCase):
    """양방향 + 함정 하나. 셋을 함께 봐야 이 설정이 무엇을 하는지가 잠긴다."""

    def _check(self, source: str, *extra: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "probe.py"
            probe.write_text(source, encoding="utf-8")
            return _mypy("--config-file", str(_CONFIG),
                         "--no-incremental", *extra, str(probe)).stdout

    def test_a_positional_call_to_a_keyword_only_constructor_is_reported(self):
        """under-strict: 설정이 표적 결함 클래스를 놓치면 실패한다.

        저장소를 초록으로 만드는 가장 쉬운 방법은 `call-arg` 를 꺼 버리는 것이다.
        그러면 위 `test_the_configured_scope_typechecks_clean` 은 그대로 초록인
        채 가드만 사라진다 — 이 셀이 그 길을 막는다.
        """
        output = self._check(_PROBE)
        self.assertIn("call-arg", output)
        self.assertIn("Too many positional arguments", output)

    def test_a_correct_keyword_call_is_not_reported(self):
        """over-strict: 정상 호출을 물면 실패한다.

        과잉교정으로 이 클래스를 넓히면(예: 키워드 호출까지 의심) 멀쩡한 코드가
        빨개지고, 다음 사람은 가드를 지운다.
        """
        output = self._check(_PROBE_CLEAN)
        self.assertNotIn("error:", output)

    def test_disabling_misc_would_hide_the_target_defect(self):
        """★ 함정: `misc` 를 끄면 `call-arg` 인 표적 결함이 함께 사라진다.

        코드 8종을 하나씩 끄며 확인했고 `misc` 에서만 일어난다(캐시 아님 —
        `--no-incremental` 로 재현). 그래서 mypy.ini 의 disable 목록에 `misc` 가
        들어가면 안 되고, 이 셀이 두 방향으로 그것을 잠근다: ① 끄면 정말
        사라진다는 사실 자체 ② 지금 설정이 그것을 안 끄고 있다는 것.
        """
        hidden = self._check(_PROBE, "--disable-error-code", "misc")
        self.assertNotIn("call-arg", hidden)

        disabled = _CONFIG.read_text(encoding="utf-8").split("disable_error_code")[1]
        self.assertNotIn("misc", disabled,
                         "misc 를 끄면 이 가드의 표적이 통과한다")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
