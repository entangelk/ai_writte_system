"""`scripts/` 의 진입점이 **파일로 실행될 때** import 되는가 (2026-09-07).

**왜 필요한가 — 이 자리는 pytest 가 절대 안 밟는다.** 테스트는 저장소 루트가 이미
`sys.path` 에 있는 상태로 돌기 때문에, 스크립트를 *모듈로* import 하면 언제나 성공한다.
그런데 사람은 스크립트를 **파일로** 실행한다(`python scripts/x.py`), 그리고 그때
`sys.path[0]` 은 CWD 가 아니라 **스크립트의 디렉터리**다 — `services` 를 못 찾는다.

**실제로 배포를 멈췄다**(2026-09-07): `migrate_ledger_user_axis.py` 가 부트스트랩 없이
나갔고, 오너가 배포 호스트에서 컨테이너 안으로 들어가 실행하자
``ModuleNotFoundError: No module named 'services'`` 로 죽었다. 그때까지 이 스크립트는
**단위 테스트 5셀이 초록**이었다 — 셀은 `migrate()` 를 import 해서 부르지 진입점을 밟지
않는다. HANDOFF 미수리 표의 *"`scripts/` 를 pytest 가 실행하지 않는다"* 가 문 자리다.

재는 것은 **정적 조건 하나**다: `from services.` 를 쓰는 스크립트는 그 import 앞에
루트를 얹는 부트스트랩을 갖는다. 실행해서 재지 않는 이유는 스크립트 다수가 실행 즉시
mongo·LLM 에 붙기 때문이다(그것이 이 파일이 오래 비어 있던 이유이기도 하다).

**양방향**: 부트스트랩 없는 새 스크립트를 더하면 실패한다(under). 부트스트랩을 지워도
실패한다(under). `services` 를 안 쓰는 스크립트는 대상이 아니다(over) — 그런 스크립트에
필요 없는 줄을 요구하면 그것도 결함이다.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

#: 저장소 루트를 sys.path 맨 앞에 얹는 줄. **두 형태가 다 쓰인다** — 인라인
#: (`index_sync_worker.py`)과 `REPO_ROOT` 변수 경유(`phase3a_deployed_rebuild_smoke.py`).
#: 재는 것은 *어떤 모양이냐* 가 아니라 **services 를 import 하기 전에 0번 자리에 얹는가**다
#: (2026-09-07: 처음엔 인라인만 인정해 멀쩡한 8개를 잡았다 — 가드가 좁았던 것이다).
_BOOTSTRAP = re.compile(r"sys\.path\.insert\(\s*0\s*,")
#: 얹는 값이 저장소 루트여야 한다 — 인라인이든 변수든 여기서 온다.
_ROOT_EXPR = re.compile(r"Path\(__file__\)\.resolve\(\)\.parents\[1\]")
_IMPORTS_SERVICES = re.compile(r"^from services\.", re.MULTILINE)


def _scripts_importing_services() -> list[Path]:
    return sorted(
        path for path in _SCRIPTS.glob("*.py")
        if _IMPORTS_SERVICES.search(path.read_text(encoding="utf-8"))
    )


class ScriptEntrypointPathTest(unittest.TestCase):
    def test_there_are_scripts_to_check(self) -> None:
        # 0개면 아래 셀이 공허하게 만족된다.
        self.assertGreaterEqual(len(_scripts_importing_services()), 20)

    def test_every_script_that_imports_services_adds_the_repo_root_first(self) -> None:
        for path in _scripts_importing_services():
            with self.subTest(script=path.name):
                source = path.read_text(encoding="utf-8")
                boot = _BOOTSTRAP.search(source)
                self.assertIsNotNone(
                    boot,
                    f"{path.name} 을 `python scripts/{path.name}` 로 실행하면 "
                    "ModuleNotFoundError 다 — `index_sync_worker.py` 의 부트스트랩을 넣는다",
                )
                self.assertRegex(
                    source, _ROOT_EXPR,
                    f"{path.name} 이 sys.path 에 얹는 값이 저장소 루트가 아니다",
                )
                first_import = _IMPORTS_SERVICES.search(source)
                self.assertLess(
                    boot.start(), first_import.start(),
                    f"{path.name} 의 부트스트랩이 `from services.` 보다 뒤에 있다",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
