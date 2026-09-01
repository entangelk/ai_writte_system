"""최종 저장 endpoint의 S1~S13 회귀 프로브를 pytest 전수에 편입한다.

under-strict: dedupe·저장·marker·동기 분석·재시도 중 하나라도 깨지면 프로브의
기명 단정이 실패한다. over-strict: final 뒤 일반 저장·수동 분석·보관/없는 draft의
정상 경계를 더 조이면 해당 시나리오가 실패한다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_PROBE = Path(__file__).parents[1] / "docs" / "verifications" / "2026-09-01" / "repro_final_save_flow.py"


def test_final_save_analysis_contract_s1_to_s13() -> None:
    spec = importlib.util.spec_from_file_location("final_save_repro", _PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.FAILURES.clear()
    assert module.main() == 0
