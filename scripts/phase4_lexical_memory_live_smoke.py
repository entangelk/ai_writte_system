#!/usr/bin/env python3
"""Live smoke for the ⑤ §8 lexical (Elasticsearch) canonical memory retrieval.

Drives the REAL Elasticsearch backend end to end against an ephemeral, uniquely
named index (safe to run against a shared cluster):

1. create a nori-analyzed index (Korean morphology);
2. drain canonical memories into it through MemoryLexicalIndexSyncAdapter (the
   same worker path production uses), including a superseded one that must NOT
   be indexed;
3. LexicalCanonicalMemoryRetriever: a Korean keyword query returns the matching
   canonical MemoryEntry (authority re-derived from the in-memory store), and
   excludes the non-matching / superseded ones;
4. HybridCanonicalMemoryRetriever: RRF over a fake vector retriever + the real
   lexical retriever surfaces the lexical match;
5. delete the ephemeral index (always, even on failure).

Config: ELASTICSEARCH_URL (default http://localhost:9201). Exit 0 pass, 1 an
assertion failed, 2 config/connection error. Prints a JSON summary.
"""

from __future__ import annotations

import json
import os
import sys
import uuid

from services.application.app.analysis.models import (
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.context_search.service import (
    HybridCanonicalMemoryRetriever,
    LexicalCanonicalMemoryRetriever,
    VectorCanonicalMemoryRetriever,
)
from services.application.app.indexing.memory_index import (
    InMemoryMemoryVectorIndexAdapter,
    build_memory_index_record,
)
from services.application.app.indexing.memory_lexical_index import (
    ELASTICSEARCH_MEMORY_MAPPINGS,
    ELASTICSEARCH_MEMORY_SETTINGS,
    ElasticsearchMemoryIndexAdapter,
    MemoryLexicalIndexSyncAdapter,
    memory_lexical_text,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
    IndexSyncOutboxService,
    InMemoryIndexSyncRepository,
)
from services.application.app.memory.models import (
    MemoryEntry,
    MemoryStatus,
    PromotionMode,
)
from services.application.app.memory.service import (
    InMemoryMemoryRepository,
    MemoryService,
)

EVENT = AnalysisCandidateType.EVENT_OBSERVATION
PROJECT = "smoke-project"


def _memory(memory_id, event_text, *, status=MemoryStatus.CANONICAL):
    return MemoryEntry(
        id=memory_id,
        project_id=PROJECT,
        memory_type=EVENT,
        status=status,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.6,
        source_ref_ids=("s1",),
        payload={"event": event_text},
        version=1,
        analysis_job_id="job-1",
        source_candidate_id=f"c-{memory_id}",
        promotion_mode=PromotionMode.MANUAL,
        applied_threshold=None,
    )


def run() -> dict:
    url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9201")
    index_name = f"ai_writte_smoke_{uuid.uuid4().hex[:12]}"
    from elasticsearch import Elasticsearch

    client = Elasticsearch(url)
    client.indices.create(
        index=index_name,
        settings=ELASTICSEARCH_MEMORY_SETTINGS,
        mappings=ELASTICSEARCH_MEMORY_MAPPINGS,
    )
    try:
        storm = _memory("storm", "폭풍이 항구를 덮쳤다")
        calm = _memory("calm", "고요한 아침이 밝았다")
        stale = _memory("stale", "폭풍 관련 오래된 기록", status=MemoryStatus.SUPERSEDED)
        memory = MemoryService(InMemoryMemoryRepository())
        for entry in (storm, calm, stale):
            memory._repo.put_memory(entry)

        es_adapter = ElasticsearchMemoryIndexAdapter(client, index_name=index_name)

        # 2. drain through the real worker path (superseded must not be indexed).
        drain = MemoryLexicalIndexSyncAdapter(
            memory_service=memory, lexical_index=es_adapter
        )
        outbox = IndexSyncOutboxService(InMemoryIndexSyncRepository())
        for entry in (storm, calm, stale):
            drain.index_memory(
                outbox.enqueue_memory_upserted(
                    project_id=PROJECT, memory_id=entry.id, version=1
                )
            )
        client.indices.refresh(index=index_name)

        # 3. lexical retriever: Korean query matches the canonical storm memory.
        lexical = LexicalCanonicalMemoryRetriever(
            memory_service=memory, lexical_index=es_adapter
        )
        lex_hits = lexical.retrieve(project_id=PROJECT, query="폭풍", limit=5)
        lex_ids = [e.id for e in lex_hits]
        assert lex_ids == ["storm"], f"lexical expected ['storm'], got {lex_ids}"
        assert lex_hits[0].payload == {"event": "폭풍이 항구를 덮쳤다"}, (
            "lexical hit must carry the store payload (authority re-derivation)"
        )

        # 4. hybrid RRF over a fake vector retriever + the real lexical retriever.
        vector_index = InMemoryMemoryVectorIndexAdapter()
        for entry in (storm, calm):
            vector_index.upsert_memory_records(
                (
                    build_memory_index_record(
                        entry,
                        text=memory_lexical_text(entry),
                        vector=(1.0, 0.0) if entry.id == "calm" else (0.0, 1.0),
                    ),
                )
            )
        vector = VectorCanonicalMemoryRetriever(
            memory_service=memory,
            embeddings=DeterministicFakeEmbeddingProvider(),
            vector_index=vector_index,
        )
        hybrid = HybridCanonicalMemoryRetriever(
            vector_retriever=vector, lexical_retriever=lexical
        )
        hyb_ids = [e.id for e in hybrid.retrieve(
            project_id=PROJECT, query="폭풍", limit=5
        )]
        assert "storm" in hyb_ids, f"hybrid must surface lexical match, got {hyb_ids}"

        return {
            "ok": True,
            "index": index_name,
            "lexical_ids": lex_ids,
            "hybrid_ids": hyb_ids,
            "nori": True,
        }
    finally:
        client.indices.delete(index=index_name, ignore_unavailable=True)


def main() -> int:
    try:
        summary = run()
    except AssertionError as exc:
        print(json.dumps({"ok": False, "assertion": str(exc)}, ensure_ascii=False))
        return 1
    except Exception as exc:  # connection/config
        print(json.dumps({"ok": False, "error": repr(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
