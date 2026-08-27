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


# 원고 본문(유닛 raw_text) 한 글자수 상한 — 오너 결정 D5-2(2026-08-27, "전 경로 4000자").
# 근거는 창 안전이 아니라 **이어쓰기 품질**: 생성 검색이 현재 장면 문단 전부(제목 없는
# 유닛이면 유닛 전체)+직전 문단 5개를 조각으로 싣고 예산(요청 상한 8192)까지 편집하므로,
# 유닛이 길어지면 현재 장면이 예산을 대량 차지해 다른 조각이 밀리고 이어쓰기가 직전
# 흐름·기억을 잃는다(실패 아닌 조용한 저하). 4000자 ≈ 2,353 tok(1.7자/tok) = 예산의 ~29%.
# 소비자는 두 축 — 저장 스키마(api/models.py SaveDraftRequest)와 채택 합성(writing/accept.py,
# provider 호출 앞에 시행해 유료 enrich/gate 를 아낀다). env 로 override, fail-loud.
DRAFT_RAW_TEXT_MAX_CHARS = 4000


def draft_raw_text_max_chars() -> int:
    value = _env_int("DRAFT_RAW_TEXT_MAX_CHARS", DRAFT_RAW_TEXT_MAX_CHARS)
    if value < 1:
        raise ValueError("DRAFT_RAW_TEXT_MAX_CHARS must be at least 1")
    return value

