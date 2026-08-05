"""Repro for verification 2026-08-05 / router-split Slice 1 (auth·admin).

라우터를 ``main.py`` 밖으로 옮긴 리팩터의 계약은 "행위 무변"이다. 이 스크립트는
앱의 **공개 표면을 정규 JSON 지문으로** 찍는다 — 분해 전/후 트리에서 각각 돌려
`diff` 하면 무변이 한 줄로 증명된다. 소스 텍스트를 비교하지 않고 조립된
``create_app()`` 을 실측하므로, 파일이 어디로 갔는지와 무관하게 성립한다.

지문에 들어가는 것(= 이 리팩터가 깨뜨릴 수 있는 것):
  - (path, method) 76개 집합
  - route 별 **해석된 의존성 트리**(``require_admin_user`` 등) — OpenAPI 에는
    안 나오는 ``dependencies=_REQUIRE_*`` 보안 배선이 여기서 잡힌다
  - status_code · response_model · responses 키
  - ``app.openapi()`` 전체의 sha256 — 프런트 TS 코드젠이 먹는 계약 그 자체
  - **order-sensitive pair 수** — 분해로 등록 *순서* 가 바뀌었으므로(이동한
    route 는 이제 ``register_*()`` 호출 지점에서 등록된다), literal 과 {param}
    이 같은 자리에서 겹쳐 first-match 결과가 달라질 쌍이 있는지 센다. 0 이어야
    순서 변화가 무해하다.

``endpoint.__module__`` 은 **일부러 지문에서 뺐다** — 파일 이동이 이 리팩터의
목적이므로 그것만은 달라야 정상이다. 대신 stderr 에 이동 현황으로 찍는다.

Run:
    git worktree add /tmp/pre e8b9908~5
    (cd /tmp/pre && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/pre.json)
    python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/post.json
    diff /tmp/pre.json /tmp/post.json && echo IDENTICAL

Expected (2026-08-05, e8b9908~5 vs e8b9908):
    diff 없음. routes=76, order-sensitive pairs=0,
    openapi sha256=f8b42ef191d95a2341debb0c879805b31ebc5c351dac1ca3c4ee51b2f809cfa1
    stderr 의 이동 현황만 다르다(pre: in-routers=0 / post: in-routers=12).

    (같은 스키마를 저장소 제공 ``scripts/dump_openapi.py`` 로 뽑으면 sha 는
    ``1e275ab8…`` 이다 — 끝의 개행 한 바이트 차이일 뿐, 양쪽 다 pre/post 동일.)
"""
import hashlib
import json
import sys

sys.path.insert(0, ".")

from fastapi.routing import APIRoute  # noqa: E402

from services.application.app.main import create_app  # noqa: E402


def _dep_names(dependant, out):
    """해석된 의존성 트리를 이름으로 평탄화한다(중첩 dep 포함)."""
    if dependant.call is not None:
        out.append(getattr(dependant.call, "__qualname__", repr(dependant.call)))
    for sub in dependant.dependencies:
        _dep_names(sub, out)


def main() -> int:
    app = create_app()

    surface = {}
    modules = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods):
            if method == "HEAD":
                continue
            deps = []
            for sub in route.dependant.dependencies:
                _dep_names(sub, deps)
            key = f"{method} {route.path}"
            surface[key] = {
                "deps": sorted(deps),
                "status_code": route.status_code,
                "response_model": getattr(route.response_model, "__name__", None),
                "responses": sorted(str(code) for code in (route.responses or {})),
            }
            modules[key] = route.endpoint.__module__

    # 등록 순서가 바뀌어도 매칭이 안 바뀌는가: literal 과 {param} 이 같은 자리에서
    # 겹치는 동일-method 쌍이 하나도 없으면 first-match 는 순서에 무관하다.
    keys = list(surface)
    order_pairs = []
    for i, left in enumerate(keys):
        lm, lp = left.split(" ", 1)
        for right in keys[i + 1 :]:
            rm, rp = right.split(" ", 1)
            if lm != rm or lp == rp:
                continue
            a, b = lp.strip("/").split("/"), rp.strip("/").split("/")
            if len(a) != len(b):
                continue
            if all(x == y or x.startswith("{") or y.startswith("{") for x, y in zip(a, b)):
                order_pairs.append(f"{lm} {lp} <-> {rp}")

    openapi_bytes = json.dumps(
        app.openapi(), indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")

    fingerprint = {
        "route_count": len(surface),
        "order_sensitive_pairs": sorted(order_pairs),
        "openapi_sha256": hashlib.sha256(openapi_bytes).hexdigest(),
        "routes": surface,
    }
    json.dump(fingerprint, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")

    moved = sorted(k for k, m in modules.items() if ".routers." in m)
    print(
        f"routes={len(surface)} order-sensitive-pairs={len(order_pairs)} "
        f"in-routers={len(moved)}",
        file=sys.stderr,
    )
    for key in moved:
        print(f"  {key:52s} {modules[key]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
