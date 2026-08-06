"""환경변수 파싱 헬퍼.

`api/` 아래가 아닌 이유: 이것은 **API 계약이 아니라 인프라 설정 읽기**이고,
`create_app` 조립부(main.py 잔류분)와 API 계약 모듈이 **둘 다** 쓴다. 어느 한쪽에
두면 다른 쪽이 그것을 import 하면서 방향이 뒤집힌다.
"""

from __future__ import annotations

import os



def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() not in {"0", "false", "no"}
