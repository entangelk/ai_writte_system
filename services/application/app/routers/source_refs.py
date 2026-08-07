"""근거 포인터(source ref)·source block 색인 route (4 operation).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다.

**`source_ref` 는 이 제품의 "모든 주장에는 근거가 붙는다" 원칙이 물리적으로
사는 자리다** — span 은 단일 ``source_block`` 안에 들고, offset 은 raw Unicode
code point, ``content_hash`` 는 raw UTF-8 SHA-256 이다(Core SOT 계약).

``rebuild`` 만 색인 협력자 셋(``shared_vector_index``·``shared_embeddings``·
``shared_backend``)을 쓴다 — 나머지 셋은 ``core_sot`` 만 본다.
"""

from __future__ import annotations

from fastapi import HTTPException

from services.application.app.core_sot.service import CoreSotError, NotFound
from services.application.app.indexing.embedding import EmbeddingProviderError
from services.application.app.indexing.service import (
    rebuild_source_block_index_summary,
)

from ..api.models import CreateSourceRefRequest
from ..api.errors import (
    _ERRORS_400_404,
    _ERRORS_404,
    _ERRORS_404_502,
    _owned,
)
from ..api.dependencies import _REQUIRE_PROJECT_OWNER


def register_source_refs(
    app, *, core_sot, shared_vector_index, shared_embeddings, shared_backend
) -> None:
    def _source_ref_payload(source_ref) -> dict[str, object]:
        return {
            "id": source_ref.id,
            "project_id": source_ref.project_id,
            "snapshot_id": source_ref.snapshot_id,
            "block_id": source_ref.block_id,
            "start_offset": source_ref.start_offset,
            "end_offset": source_ref.end_offset,
            "quote": source_ref.quote,
            "content_hash": source_ref.content_hash,
        }

    def _rebuild_source_block_index_payload(
        *, project_id: str, snapshot_id: str
    ) -> dict[str, object]:
        summary = rebuild_source_block_index_summary(
            core_sot=core_sot,
            project_id=project_id,
            snapshot_id=snapshot_id,
            vector_index=shared_vector_index,
            embeddings=shared_embeddings,
        )
        return summary.to_dict(backend=shared_backend)

    @app.post("/projects/{project_id}/snapshots/{snapshot_id}/source-refs",
              responses=_owned(_ERRORS_400_404),
              dependencies=_REQUIRE_PROJECT_OWNER)
    async def create_source_ref(
        project_id: str,
        snapshot_id: str,
        request: CreateSourceRefRequest,
    ) -> dict[str, object]:
        try:
            source_ref = core_sot.create_source_ref(
                project_id=project_id,
                snapshot_id=snapshot_id,
                start_offset=request.start_offset,
                end_offset=request.end_offset,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CoreSotError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _source_ref_payload(source_ref)

    @app.get("/projects/{project_id}/snapshots/{snapshot_id}/source-refs",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def list_source_refs(
        project_id: str,
        snapshot_id: str,
    ) -> dict[str, object]:
        try:
            source_refs = core_sot.list_source_refs(
                project_id=project_id,
                snapshot_id=snapshot_id,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"source_refs": [_source_ref_payload(ref) for ref in source_refs]}

    @app.get("/projects/{project_id}/source-refs/{source_ref_id}",
             responses=_owned(_ERRORS_404),
             dependencies=_REQUIRE_PROJECT_OWNER)
    async def get_source_ref(
        project_id: str,
        source_ref_id: str,
    ) -> dict[str, object]:
        try:
            source_ref = core_sot.get_source_ref(
                project_id=project_id,
                source_ref_id=source_ref_id,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _source_ref_payload(source_ref)

    @app.post(
        "/projects/{project_id}/snapshots/{snapshot_id}/index/source-blocks/rebuild",
        responses=_owned(_ERRORS_404_502),
        dependencies=_REQUIRE_PROJECT_OWNER,
    )
    async def rebuild_source_block_index(
        project_id: str,
        snapshot_id: str,
    ) -> dict[str, object]:
        try:
            return _rebuild_source_block_index_payload(
                project_id=project_id,
                snapshot_id=snapshot_id,
            )
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EmbeddingProviderError as exc:
            # The rebuild embeds every source block, so a configured-but-failing
            # embedding service (timeout / unreachable / malformed response) used
            # to escape as an opaque 500. It is an upstream collaborator failure,
            # not a missing one, so it is 502 rather than 503 — the same call this
            # endpoint's sibling already makes: context search's vector step maps
            # an embedding failure to BACKEND_ERROR, which surfaces as 502
            # (context_search/service.py::_run_vector_step).
            raise HTTPException(status_code=502, detail=str(exc)) from exc
