"""앱이 **두 import 이름 모두**로 로드되는가 (H-3, 라우터 분해 2026-08-05).

라우터 분해가 `main` 과 `routers/*` 사이에 순환을 만들었다. 그 순환은 심볼 순서로
풀리지만, **import 이름이 섞이면** 안 풀린다 — `main.py` 가 절대 경로
(`from services.application.app.routers.admin import ...`)로 부르고 router 가 상대
경로(`from ..main import ...`)로 되부르면, 짧은 이름으로 들어온 로드에서
`app.main` 과 `services.application.app.main` 이 **서로 다른 모듈 객체**가 되고 두
번째 로드가 반쯤 초기화된 `routers.admin` 을 만나 ImportError 로 죽는다.

분해 전에는 두 이름 다 살아 있었고 분해가 짧은 이름을 죽였다(독립 검증 H-3 실측).
지금 저장소의 진입점은 전부 FQ 라 사고는 없었지만, 실패 메시지가 원인과 동떨어진
"순환 import" 라 처음 밟는 사람이 시간을 태운다. 그래서 **두 방향 다** 잠근다.

- under-strict: `main.py` 의 두 import 를 절대 경로로 되돌리면 짧은 이름 셀이 죽는다.
- over-strict: 상대 import 로 고치다 FQ 를 깨뜨리면(배포 진입점 —
  `Dockerfile` 의 `uvicorn services.application.app.main:app`) FQ 셀이 죽는다.

**서브프로세스로 돈다.** 한 프로세스 안에서 두 이름으로 import 하면 모듈 객체가
둘 생겨 다른 테스트의 `patch("services.application.app.main....")` 가 엉뚱한 사본을
건드린다 — 잠그려는 성질이 프로세스 시작 시점의 것이므로 격리가 맞다.
"""
import pathlib
import subprocess
import sys
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_PROGRAM = "from {module} import create_app; create_app(); print('LOAD OK')"


def _load_app_in_subprocess(*, module: str, pythonpath: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _PROGRAM.format(module=module)],
        cwd=_ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(pythonpath)},
        capture_output=True,
        text=True,
        timeout=300,
    )


class AppImportPathTest(unittest.TestCase):
    def test_the_fully_qualified_name_loads(self):
        """배포 진입점. `Dockerfile` 의 `uvicorn services.application.app.main:app`."""
        result = _load_app_in_subprocess(
            module="services.application.app.main", pythonpath=_ROOT
        )
        self.assertEqual(
            result.returncode, 0,
            f"FQ 이름으로 앱이 안 뜬다 — 배포 진입점이다:\n{result.stderr[-2000:]}",
        )
        self.assertIn("LOAD OK", result.stdout)

    def test_the_short_package_name_also_loads(self):
        """`PYTHONPATH=services/application` + `import app.main`.

        저장소 진입점은 전부 FQ 라 이 경로를 지금 아무도 안 쓴다. 그래도 잠그는
        이유는 **분해 전에는 됐기 때문**이다 — 되던 것이 조용히 죽으면, 다음에
        진입점을 하나 더 만드는 사람(Slice 2 = 관리자 표면 별도 compose)이 원인과
        동떨어진 "순환 import" 메시지를 받는다.
        """
        result = _load_app_in_subprocess(
            module="app.main", pythonpath=_ROOT / "services" / "application"
        )
        self.assertEqual(
            result.returncode, 0,
            "짧은 패키지 이름으로 앱이 안 뜬다 — `main.py` 의 routers import 가 절대 "
            f"경로로 돌아갔는지 본다(상대 경로여야 한다):\n{result.stderr[-2000:]}",
        )
        self.assertIn("LOAD OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
