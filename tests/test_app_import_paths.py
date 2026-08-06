"""앱이 **어느 import 이름·어느 로드 순서로도** 뜨는가.

원래 이 파일은 H-3(2026-08-05)를 잠갔다 — 라우터 분해가 `main` 과 `routers` 사이에
순환을 만들었고, `main.py` 가 절대 경로로 부르면 짧은 이름 로드에서 모듈 사본이 둘
생겨 ImportError 로 죽었다.

**2026-08-06 공유 prelude 추출로 그 순환 자체가 사라졌다**(`app/api/*`·`app/env.py`).
그래서 이 파일이 잠그는 성질도 바뀌었다 — 아래 셀들은 이제 **두 가지 다른 것**을 잰다.

1. `test_the_*_name_loads` 2건 — **모듈 동일성**. 순환은 없어졌지만 `main.py` 가 routers 를
   절대 경로로 부르면 짧은 이름 로드에서 `app.main` 과
   `services.application.app.main` 이 여전히 **서로 다른 객체**가 되고, 다른 테스트의
   `patch("services.application.app.main....")` 가 엉뚱한 사본을 건드린다.
2. `test_a_router_module_loads_before_main` — **순환 부재(H-3-A)**. 추출 전에는 `routers`
   를 먼저 import 하면 죽었다. 이것이 순환을 직접 겨냥하는 셀이며, `routers/*` 에
   `from ..main import` 를 되살리면 여기서 잡힌다.
3. `test_the_module_runs_as_a_script` — 같은 순환의 다른 얼굴. `python -m` 은 모듈을
   `__main__` 으로 올리므로 `main` 이 **두 번** 로드되고, 순환이 있으면 그 두 번째가 죽는다.
   저장소 진입점이 쓰는 명령은 아니지만(Dockerfile=uvicorn) **순환의 값싼 관측 창**이다.

**서브프로세스로 돈다.** 한 프로세스 안에서 두 이름으로 import 하면 모듈 객체가 둘 생겨
다른 테스트의 patch 대상이 흔들린다 — 잠그려는 성질이 프로세스 시작 시점의 것이므로
격리가 맞다.
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


class ImportOrderIndependenceTest(unittest.TestCase):
    """순환이 없다 = **main 보다 먼저 로드돼도 된다**(H-3-A, 2026-08-06 추출로 폐쇄).

    under-strict: `routers/*` 가 `from ..main import` 로 공유 심볼을 되가져오면 —
    즉 추출을 되돌리면 — 두 셀 다 circular import 로 재실패한다(실측).
    over-strict: 정상 배포 경로(`main` 을 먼저 import)는 위 `AppImportPathTest` 가
    따로 잠그므로, 순환을 없애려다 앱을 못 뜨게 만들면 그쪽이 먼저 죽는다.
    """

    def test_a_router_module_loads_before_main(self):
        """라우터 모듈을 **먼저** import 해도 뜬다.

        Slice 2(관리자 표면 별도 진입점)가 하려는 일이 정확히 이것이다 —
        `create_admin_app()` 은 `register_admin` 만 필요하고 제품 앱을 짓지 않는다.
        """
        for module in ("services.application.app.routers.admin",
                       "services.application.app.routers.auth"):
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-c", f"import {module}; print('LOAD OK')"],
                    cwd=_ROOT, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(_ROOT)},
                    capture_output=True, text=True, timeout=300,
                )
                self.assertEqual(
                    result.returncode, 0,
                    "라우터를 먼저 import 하면 죽는다 — `routers/*` 가 `..main` 을 다시 "
                    f"보고 있는지 확인한다(공유 심볼은 `..api`):\n{result.stderr[-2000:]}",
                )

    def test_the_module_runs_as_a_script(self):
        """`python -m …app.main` — 모듈이 두 번 로드돼도 순환이 없다."""
        result = subprocess.run(
            [sys.executable, "-m", "services.application.app.main"],
            cwd=_ROOT, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(_ROOT)},
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(
            result.returncode, 0,
            f"`python -m` 이 죽는다 — main ↔ routers 순환이 돌아왔다:\n{result.stderr[-2000:]}",
        )


if __name__ == "__main__":
    unittest.main()
