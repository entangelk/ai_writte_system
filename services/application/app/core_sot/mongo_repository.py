"""MongoDB adapter implementing the Core SOT repository contract.

The adapter persists the load-bearing draft-save write set
(``draft_versions``, ``source_snapshots``, ``source_blocks``) plus the
idempotency record carried on the ``draft_versions`` document.

Two write paths satisfy the approved persistence contract:

- Transaction path (Docker / replica-set runtime, default): the whole save
  write set commits in one MongoDB transaction.
- Non-transaction fallback (local / test deployments without transactions):
  immutable dependents are written first, the ``draft_versions`` commit marker
  is written last under a unique idempotency index, and a prior failed
  attempt's orphans are cleaned before re-writing. A committed version short
  circuits as an idempotent replay (retry guard). Per SoT v1.4 the fallback is
  **single-writer only**: its orphan cleanup / retry guard are defined for one
  writer's sequential retries, not for concurrent saves of the same request.
  Runtimes needing concurrency safety use the transaction path.

In both paths the success is only reported after the MongoDB write completes,
and the unique index on ``(project_id, draft_id, idempotency_key)`` is the
authoritative idempotency boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, OperationFailure

from services.application.app.core_sot.models import (
    BlockKind,
    Chapter,
    Draft,
    DraftVersion,
    Project,
    ProjectBriefVersion,
    SceneNote,
    SourceBlock,
    SourceRef,
    SourceSnapshot,
    UnitKind,
    WritingAcceptReceipt,
)
from services.application.app.core_sot.repository import (
    DuplicateProjectBriefRequest,
    DuplicateSaveRequest,
    DuplicateWritingAcceptReceipt,
    DraftSetChanged,
)

DEFAULT_DB_NAME = "ai_writing_system"


class MongoRepositorySetupError(RuntimeError):
    """Raised when MongoDB cannot install the required Core SOT indexes."""


class MongoCoreSotRepository:
    """``CoreSotRepository`` backed by MongoDB collections."""

    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
        use_transactions: bool = True,
    ) -> None:
        self._client = client
        self._db = client[db_name]
        self._use_transactions = use_transactions
        self._projects = self._db["projects"]
        self._project_briefs = self._db["project_brief_versions"]
        self._chapters = self._db["chapters"]
        self._drafts = self._db["drafts"]
        self._versions = self._db["draft_versions"]
        self._snapshots = self._db["source_snapshots"]
        self._blocks = self._db["source_blocks"]
        self._source_refs = self._db["source_refs"]
        self._writing_accept_receipts = self._db["writing_accept_receipts"]
        self._scene_notes = self._db["scene_notes"]
        self.ensure_indexes()

    @classmethod
    def from_uri(
        cls,
        uri: str,
        *,
        db_name: str = DEFAULT_DB_NAME,
        use_transactions: bool = True,
    ) -> "MongoCoreSotRepository":
        return cls(
            MongoClient(uri),
            db_name=db_name,
            use_transactions=use_transactions,
        )

    def ensure_indexes(self) -> None:
        try:
            self._versions.create_index(
                [
                    ("project_id", ASCENDING),
                    ("draft_id", ASCENDING),
                    ("idempotency_key", ASCENDING),
                ],
                unique=True,
                name="uniq_save_request",
            )
            self._project_briefs.create_index(
                [("project_id", ASCENDING), ("version_number", ASCENDING)],
                unique=True,
                name="uniq_project_brief_version",
            )
            self._project_briefs.create_index(
                [("project_id", ASCENDING), ("idempotency_key", ASCENDING)],
                unique=True,
                name="uniq_project_brief_request",
            )
            self._blocks.create_index(
                [("snapshot_id", ASCENDING), ("block_index", ASCENDING)],
                name="blocks_by_snapshot",
            )
            self._source_refs.create_index(
                [
                    ("project_id", ASCENDING),
                    ("snapshot_id", ASCENDING),
                    ("start_offset", ASCENDING),
                    ("end_offset", ASCENDING),
                    ("_id", ASCENDING),
                ],
                name="source_refs_by_project_snapshot",
            )
            self._writing_accept_receipts.create_index(
                [("project_id", ASCENDING), ("idempotency_key", ASCENDING)],
                unique=True,
                name="uniq_writing_accept_receipt",
            )
            self._chapters.create_index(
                [("project_id", ASCENDING), ("position", ASCENDING)],
                unique=True,
                name="uniq_chapter_position",
            )
            # 장면 메모: Scene 당 현재 메모 한 건이 계약이므로 unique 가 그 경계다.
            # ``project_id`` 선두라 프로젝트 단위 목록/파기 질의도 이 인덱스를 쓴다.
            self._scene_notes.create_index(
                [("project_id", ASCENDING), ("draft_id", ASCENDING)],
                unique=True,
                name="uniq_scene_note",
            )
        except OperationFailure as exc:
            raise MongoRepositorySetupError(
                "failed to create required Core SOT MongoDB indexes"
            ) from exc

    # -- identifier generation ------------------------------------------------

    def next_project_id(self) -> str:
        return str(ObjectId())

    def next_project_brief_version_id(self) -> str:
        return str(ObjectId())

    def next_chapter_id(self) -> str:
        return str(ObjectId())

    def next_draft_id(self) -> str:
        return str(ObjectId())

    def next_version_id(self) -> str:
        return str(ObjectId())

    def next_snapshot_id(self) -> str:
        return str(ObjectId())

    def next_source_ref_id(self) -> str:
        return str(ObjectId())

    # -- project / draft ------------------------------------------------------

    def get_project(self, project_id: str) -> Project | None:
        doc = self._projects.find_one({"_id": project_id})
        return _to_project(doc) if doc else None

    def put_project(self, project: Project) -> None:
        self._projects.replace_one(
            {"_id": project.id}, _project_doc(project), upsert=True
        )

    def list_projects(self) -> tuple[Project, ...]:
        cursor = self._projects.find().sort("_id", ASCENDING)
        return tuple(_to_project(doc) for doc in cursor)

    def list_projects_for_owner(self, owner_id: str) -> tuple[Project, ...]:
        cursor = self._projects.find({"owner_id": owner_id}).sort("_id", ASCENDING)
        return tuple(_to_project(doc) for doc in cursor)

    def purge_project(self, project_id: str) -> None:
        # D8-6a: project 전체 그래프 영구 파기. snapshots·blocks 도 project_id 필드를 보관하므로
        # (_snapshot_doc·_block_doc) 8컬렉션 전부 직접 project_id 스코프로 지운다. 인접 project
        # 레코드는 project_id 스코프가 다르므로 영향이 없다.
        if self._use_transactions:
            with self._client.start_session() as session:
                with session.start_transaction():
                    self._purge_project(project_id, session=session)
            return
        self._purge_project(project_id, session=None)

    def _purge_project(self, project_id: str, *, session) -> None:
        # version→snapshot_id 경유가 아니라 직접 project_id 스코프로 지운다 — in-memory 와 대칭이며
        # (비정상) 고아 snapshot 이 생겨도 잔류하지 않는다(purge 는 비가역이라 안전 방향은 더 넓게).
        # 독립 검증(2026-07-31)이 지적한 in-memory/mongo snapshot 파기 비대칭의 보강.
        self._snapshots.delete_many({"project_id": project_id}, session=session)
        self._blocks.delete_many({"project_id": project_id}, session=session)
        self._versions.delete_many({"project_id": project_id}, session=session)
        self._chapters.delete_many({"project_id": project_id}, session=session)
        self._drafts.delete_many({"project_id": project_id}, session=session)
        self._source_refs.delete_many({"project_id": project_id}, session=session)
        self._writing_accept_receipts.delete_many(
            {"project_id": project_id}, session=session
        )
        self._scene_notes.delete_many({"project_id": project_id}, session=session)
        self._project_briefs.delete_many({"project_id": project_id}, session=session)
        self._projects.delete_one({"_id": project_id}, session=session)

    def purge_draft(self, project_id: str, draft_id: str) -> None:
        # 원고 하드 삭제 — purge_project의 draft 스코프 판(2026-08-28 오너 결정).
        # project 레코드·브리프·인접 draft 는 project_id 스코프가 달라 영향이 없다.
        if self._use_transactions:
            with self._client.start_session() as session:
                with session.start_transaction():
                    self._purge_draft(project_id, draft_id, session=session)
            return
        self._purge_draft(project_id, draft_id, session=None)

    def purge_chapter(self, project_id: str, chapter_id: str) -> None:
        if self._use_transactions:
            with self._client.start_session() as session:
                with session.start_transaction():
                    self._purge_chapter(project_id, chapter_id, session=session)
            return
        self._purge_chapter(project_id, chapter_id, session=None)

    def _purge_chapter(self, project_id: str, chapter_id: str, *, session) -> None:
        child_ids = [
            doc["_id"] for doc in self._drafts.find(
                {"project_id": project_id, "chapter_id": chapter_id},
                {"_id": 1},
                session=session,
            )
        ]
        for draft_id in child_ids:
            self._purge_draft(project_id, draft_id, session=session)
        self._chapters.delete_one(
            {"_id": chapter_id, "project_id": project_id}, session=session
        )

    def _purge_draft(self, project_id: str, draft_id: str, *, session) -> None:
        # source_refs 는 draft_id 필드가 없다(_source_ref_doc) — snapshot_id 경유로
        # 지운다. snapshot 을 먼저 읽고 같은 스코프로 지우는 순서라 트랜잭션 밖에서도
        # 잔류 방향으로 안전하다(읽은 뒤 끼어든 snapshot 은 다음 purge 의 몫).
        snapshot_ids = [
            doc["_id"]
            for doc in self._snapshots.find(
                {"project_id": project_id, "draft_id": draft_id},
                {"_id": 1},
                session=session,
            )
        ]
        self._snapshots.delete_many(
            {"project_id": project_id, "draft_id": draft_id}, session=session
        )
        self._blocks.delete_many(
            {"project_id": project_id, "draft_id": draft_id}, session=session
        )
        if snapshot_ids:
            self._source_refs.delete_many(
                {"snapshot_id": {"$in": snapshot_ids}}, session=session
            )
        self._versions.delete_many(
            {"project_id": project_id, "draft_id": draft_id}, session=session
        )
        self._writing_accept_receipts.delete_many(
            {"project_id": project_id, "draft_id": draft_id}, session=session
        )
        self._scene_notes.delete_many(
            {"project_id": project_id, "draft_id": draft_id}, session=session
        )
        self._drafts.delete_one(
            {"_id": draft_id, "project_id": project_id}, session=session
        )

    def get_current_project_brief(
        self, project_id: str
    ) -> ProjectBriefVersion | None:
        doc = self._project_briefs.find_one(
            {"project_id": project_id}, sort=[("version_number", -1)]
        )
        return _to_project_brief(doc) if doc else None

    def get_project_brief_version(
        self, version_id: str
    ) -> ProjectBriefVersion | None:
        doc = self._project_briefs.find_one({"_id": version_id})
        return _to_project_brief(doc) if doc else None

    def list_project_brief_versions(
        self, project_id: str
    ) -> tuple[ProjectBriefVersion, ...]:
        cursor = self._project_briefs.find({"project_id": project_id}).sort(
            "version_number", ASCENDING
        )
        return tuple(_to_project_brief(doc) for doc in cursor)

    def find_project_brief_request(
        self, project_id: str, idempotency_key: str
    ) -> str | None:
        doc = self._project_briefs.find_one(
            {"project_id": project_id, "idempotency_key": idempotency_key},
            {"_id": 1},
        )
        return doc["_id"] if doc else None

    def record_project_brief(self, brief: ProjectBriefVersion) -> None:
        try:
            self._project_briefs.insert_one(_project_brief_doc(brief))
        except DuplicateKeyError as exc:
            raise DuplicateProjectBriefRequest(brief.idempotency_key) from exc

    def get_draft(self, draft_id: str) -> Draft | None:
        doc = self._drafts.find_one({"_id": draft_id})
        return _to_draft(doc) if doc else None

    def get_chapter(self, chapter_id: str) -> Chapter | None:
        doc = self._chapters.find_one({"_id": chapter_id})
        return _to_chapter(doc) if doc else None

    def put_chapter(self, chapter: Chapter) -> None:
        self._chapters.replace_one(
            {"_id": chapter.id}, _chapter_doc(chapter), upsert=True
        )

    def list_chapters(self, project_id: str) -> tuple[Chapter, ...]:
        cursor = self._chapters.find({"project_id": project_id}).sort(
            "position", ASCENDING
        )
        return tuple(_to_chapter(doc) for doc in cursor)

    def replace_chapter_metadata(
        self, project_id: str, chapters: tuple[Chapter, ...]
    ) -> None:
        current_ids = {
            doc["_id"] for doc in self._chapters.find(
                {"project_id": project_id}, {"_id": 1}
            )
        }
        if current_ids != {chapter.id for chapter in chapters}:
            raise DraftSetChanged("chapter set changed during write")
        for index, chapter in enumerate(chapters, start=1):
            self._chapters.update_one(
                {"_id": chapter.id, "project_id": project_id},
                {"$set": {"position": -index}},
            )
        for chapter in chapters:
            self._chapters.update_one(
                {"_id": chapter.id, "project_id": project_id},
                {"$set": {
                    "title": chapter.title,
                    "archived": chapter.archived,
                    "position": chapter.position,
                }},
            )

    def replace_hierarchy(
        self,
        project_id: str,
        chapters: tuple[Chapter, ...],
        drafts: tuple[Draft, ...],
    ) -> None:
        # The pre-v1.8.9 project-wide position index conflicts with parent-scoped
        # Scene positions and is obsolete once this maintenance migration starts.
        try:
            self._drafts.drop_index("uniq_draft_position")
        except OperationFailure:
            pass
        if self._use_transactions:
            with self._client.start_session() as session:
                with session.start_transaction():
                    self._replace_hierarchy(
                        project_id, chapters, drafts, session=session
                    )
        else:
            before_chapters = tuple(self._chapters.find({"project_id": project_id}))
            before_drafts = tuple(self._drafts.find({"project_id": project_id}))
            try:
                self._replace_hierarchy(project_id, chapters, drafts, session=None)
            except Exception:
                self._chapters.delete_many({"project_id": project_id})
                self._drafts.delete_many({"project_id": project_id})
                if before_chapters:
                    self._chapters.insert_many(before_chapters)
                if before_drafts:
                    self._drafts.insert_many(before_drafts)
                raise
        self._drafts.create_index(
            [("chapter_id", ASCENDING), ("position", ASCENDING)],
            unique=True,
            name="uniq_scene_position",
            # Migration은 프로젝트별로 replace_hierarchy를 돌리므로 중간 상태에
            # 평면(아직 chapter_id가 null인) 프로젝트들이 남는다 — (null, position)
            # 충돌로 인덱스 생성이 죽지 않도록, 귀속된 Scene에만 유일성을 적용한다
            # (운영 배포 실측 결함 2026-08-29: 멀티 프로젝트 평면에서 DuplicateKeyError).
            partialFilterExpression={"chapter_id": {"$type": "string"}},
        )

    def _replace_hierarchy(
        self, project_id, chapters, drafts, *, session
    ) -> None:
        current_ids = {
            doc["_id"] for doc in self._drafts.find(
                {"project_id": project_id}, {"_id": 1}, session=session
            )
        }
        if current_ids != {draft.id for draft in drafts}:
            raise DraftSetChanged("draft set changed during hierarchy migration")
        self._chapters.delete_many({"project_id": project_id}, session=session)
        if chapters:
            self._chapters.insert_many(
                [_chapter_doc(chapter) for chapter in chapters], session=session
            )
        for draft in drafts:
            result = self._drafts.replace_one(
                {"_id": draft.id, "project_id": project_id},
                _draft_doc(draft),
                session=session,
            )
            if result.matched_count != 1:
                raise DraftSetChanged("draft set changed during hierarchy migration")

    def put_draft(self, draft: Draft) -> None:
        self._drafts.replace_one({"_id": draft.id}, _draft_doc(draft), upsert=True)

    def list_drafts(self, project_id: str) -> tuple[Draft, ...]:
        cursor = self._drafts.find({"project_id": project_id}).sort("_id", ASCENDING)
        drafts = tuple(_to_draft(doc) for doc in cursor)
        if drafts and all(draft.position is not None for draft in drafts):
            return tuple(sorted(
                drafts,
                key=lambda draft: (draft.chapter_id or "", draft.position),
            ))
        return drafts

    def replace_draft_metadata(
        self, project_id: str, drafts: tuple[Draft, ...]
    ) -> None:
        if self._use_transactions:
            with self._client.start_session() as session:
                with session.start_transaction():
                    self._replace_draft_metadata(project_id, drafts, session=session)
            return

        before = tuple(self._drafts.find({"project_id": project_id}))
        try:
            self._replace_draft_metadata(project_id, drafts, session=None)
        except Exception:
            self._drafts.delete_many({"project_id": project_id})
            if before:
                self._drafts.insert_many(before)
            raise

    def _replace_draft_metadata(self, project_id, drafts, *, session) -> None:
        current_ids = {
            doc["_id"]
            for doc in self._drafts.find(
                {"project_id": project_id}, {"_id": 1}, session=session
            )
        }
        if current_ids != {draft.id for draft in drafts}:
            raise DraftSetChanged("draft set changed during write")
        # Temporary negative positions avoid collisions with the unique index
        # while a full permutation is being replaced.
        for index, draft in enumerate(drafts, start=1):
            self._drafts.update_one(
                {"_id": draft.id, "project_id": project_id},
                {"$set": {"position": -index}},
                session=session,
            )
        for index, draft in enumerate(drafts, start=1):
            result = self._drafts.update_one(
                {"_id": draft.id, "project_id": project_id},
                {
                    "$set": {
                        "unit_kind": (
                            str(draft.unit_kind)
                            if draft.unit_kind is not None
                            else None
                        ),
                        "chapter_id": draft.chapter_id,
                        "position": draft.position,
                    }
                },
                session=session,
            )
            if result.matched_count != 1:
                raise DraftSetChanged("draft set changed during write")
            self._after_draft_metadata_write(index, draft)

    def _after_draft_metadata_write(self, index: int, draft: Draft) -> None:
        """Failure-injection seam for the single-writer fallback regression."""

    def ensure_draft_position_index(self) -> None:
        try:
            self._drafts.create_index(
                [("project_id", ASCENDING), ("position", ASCENDING)],
                unique=True,
                name="uniq_draft_position",
            )
        except OperationFailure as exc:
            raise MongoRepositorySetupError(
                "failed to create draft position index"
            ) from exc

    # -- save / lookups -------------------------------------------------------

    def get_scene_note(self, project_id: str, draft_id: str) -> SceneNote | None:
        doc = self._scene_notes.find_one(
            {"project_id": project_id, "draft_id": draft_id}
        )
        return None if doc is None else _to_scene_note(doc)

    def put_scene_note(self, note: SceneNote) -> None:
        # D4=A: 현재 값 교체(버전 없음). upsert 라 첫 저장과 갱신이 한 경로다.
        self._scene_notes.replace_one(
            {"project_id": note.project_id, "draft_id": note.draft_id},
            _scene_note_doc(note),
            upsert=True,
        )

    def list_scene_notes(self, project_id: str) -> tuple[SceneNote, ...]:
        # uniq_scene_note 가 project_id 선두라 이 질의가 그 인덱스를 쓴다.
        # 정렬은 걸지 않는다 — 목록 순서는 service 가 Scene 순서에서 가져온다.
        return tuple(
            _to_scene_note(doc)
            for doc in self._scene_notes.find({"project_id": project_id})
        )

    def version_count(self, draft_id: str) -> int:
        return self._versions.count_documents({"draft_id": draft_id})

    def list_versions(self, draft_id: str) -> tuple[DraftVersion, ...]:
        cursor = self._versions.find({"draft_id": draft_id}).sort(
            "version_number", ASCENDING
        )
        return tuple(_to_version(doc) for doc in cursor)

    def find_save_request(
        self, project_id: str, draft_id: str, idempotency_key: str
    ) -> str | None:
        doc = self._versions.find_one(
            {
                "project_id": project_id,
                "draft_id": draft_id,
                "idempotency_key": idempotency_key,
            },
            {"_id": 1},
        )
        return doc["_id"] if doc else None

    def get_version(self, version_id: str) -> DraftVersion | None:
        doc = self._versions.find_one({"_id": version_id})
        return _to_version(doc) if doc else None

    def get_snapshot(self, snapshot_id: str) -> SourceSnapshot | None:
        doc = self._snapshots.find_one({"_id": snapshot_id})
        return _to_snapshot(doc) if doc else None

    def get_blocks(self, snapshot_id: str) -> tuple[SourceBlock, ...]:
        cursor = self._blocks.find({"snapshot_id": snapshot_id}).sort(
            "block_index", ASCENDING
        )
        return tuple(_to_block(doc) for doc in cursor)

    def record_source_ref(self, source_ref: SourceRef) -> None:
        self._source_refs.insert_one(_source_ref_doc(source_ref))

    def get_source_ref(self, source_ref_id: str) -> SourceRef | None:
        doc = self._source_refs.find_one({"_id": source_ref_id})
        return _to_source_ref(doc) if doc else None

    def list_source_refs(
        self, *, project_id: str, snapshot_id: str
    ) -> tuple[SourceRef, ...]:
        cursor = self._source_refs.find(
            {"project_id": project_id, "snapshot_id": snapshot_id}
        ).sort(
            [
                ("start_offset", ASCENDING),
                ("end_offset", ASCENDING),
                ("_id", ASCENDING),
            ]
        )
        return tuple(_to_source_ref(doc) for doc in cursor)

    def record_save(
        self,
        *,
        idempotency_key: str,
        version: DraftVersion,
        snapshot: SourceSnapshot,
        blocks: tuple[SourceBlock, ...],
    ) -> None:
        if self._use_transactions:
            self._record_save_transactional(idempotency_key, version, snapshot, blocks)
        else:
            self._record_save_fallback(idempotency_key, version, snapshot, blocks)

    def _record_save_transactional(
        self,
        idempotency_key: str,
        version: DraftVersion,
        snapshot: SourceSnapshot,
        blocks: tuple[SourceBlock, ...],
    ) -> None:
        version_doc = _version_doc(version)
        snapshot_doc = _snapshot_doc(snapshot, idempotency_key)
        block_docs = [
            _block_doc(block, idempotency_key, version.draft_id) for block in blocks
        ]
        with self._client.start_session() as session:
            try:
                with session.start_transaction():
                    # Version carries the unique idempotency key, so insert it
                    # first: a duplicate aborts the whole transaction.
                    self._versions.insert_one(version_doc, session=session)
                    self._snapshots.insert_one(snapshot_doc, session=session)
                    if block_docs:
                        self._blocks.insert_many(block_docs, session=session)
            except DuplicateKeyError as exc:
                raise DuplicateSaveRequest(idempotency_key) from exc

    def _record_save_fallback(
        self,
        idempotency_key: str,
        version: DraftVersion,
        snapshot: SourceSnapshot,
        blocks: tuple[SourceBlock, ...],
    ) -> None:
        # Single-writer only (SoT v1.4): the orphan cleanup below removes every
        # dependent matching this save request's scope, which is correct for one
        # writer's sequential retries but would drop a concurrent writer's
        # committed dependents. Concurrency safety is the transaction path's job.
        scope = {
            "project_id": version.project_id,
            "draft_id": version.draft_id,
            "idempotency_key": idempotency_key,
        }
        # Retry guard: a committed version means this is an idempotent replay;
        # never touch the committed dependents.
        if self.find_save_request(*scope.values()) is not None:
            raise DuplicateSaveRequest(idempotency_key)

        # Orphan cleanup: remove dependents left by a prior failed attempt for
        # this exact save request before re-writing.
        self._snapshots.delete_many(scope)
        self._blocks.delete_many(scope)

        # Ordered writes: immutable dependents first, commit marker last.
        self._snapshots.insert_one(_snapshot_doc(snapshot, idempotency_key))
        block_docs = [
            _block_doc(block, idempotency_key, version.draft_id) for block in blocks
        ]
        if block_docs:
            self._blocks.insert_many(block_docs)
        try:
            self._versions.insert_one(_version_doc(version))
        except DuplicateKeyError as exc:
            # Lost a concurrent race after writing our own dependents: drop only
            # what this attempt wrote, then signal the replay.
            self._snapshots.delete_many({"_id": snapshot.id})
            self._blocks.delete_many({"snapshot_id": snapshot.id})
            raise DuplicateSaveRequest(idempotency_key) from exc

    # -- start next unit (W3 six-surface atomic accept) -----------------------

    def get_writing_accept_receipt(
        self, project_id: str, idempotency_key: str
    ) -> WritingAcceptReceipt | None:
        doc = self._writing_accept_receipts.find_one(
            {"project_id": project_id, "idempotency_key": idempotency_key}
        )
        return _to_receipt(doc) if doc else None

    def record_start_next_unit(
        self,
        *,
        shifted_drafts: tuple[Draft, ...],
        new_draft: Draft,
        idempotency_key: str,
        version: DraftVersion,
        snapshot: SourceSnapshot,
        blocks: tuple[SourceBlock, ...],
        receipt: WritingAcceptReceipt,
    ) -> None:
        if self._use_transactions:
            with self._client.start_session() as session:
                with session.start_transaction():
                    self._start_next_unit(
                        shifted_drafts, new_draft, idempotency_key,
                        version, snapshot, blocks, receipt, session=session)
            return

        # Single-writer fallback: capture the full project draft set before-image
        # so a mid-write failure restores exactly the pre-accept order.
        before = tuple(
            self._drafts.find({"project_id": new_draft.project_id})
        )
        try:
            self._start_next_unit(
                shifted_drafts, new_draft, idempotency_key,
                version, snapshot, blocks, receipt, session=None)
        except Exception:
            self._drafts.delete_many({"project_id": new_draft.project_id})
            if before:
                self._drafts.insert_many(before)
            self._versions.delete_many({"_id": version.id})
            self._snapshots.delete_many({"_id": snapshot.id})
            self._blocks.delete_many({"snapshot_id": snapshot.id})
            self._writing_accept_receipts.delete_many(
                {"project_id": receipt.project_id,
                 "idempotency_key": receipt.idempotency_key})
            raise

    def _start_next_unit(
        self, shifted_drafts, new_draft, idempotency_key,
        version, snapshot, blocks, receipt, *, session
    ) -> None:
        # Shift the tail up by one. Park each shifted draft at a temporary
        # negative position first so the new unit's target slot is free without
        # violating the unique (project_id, position) index mid-write.
        for draft in shifted_drafts:
            self._drafts.update_one(
                {"_id": draft.id, "project_id": draft.project_id},
                {"$set": {"position": -draft.position}},
                session=session,
            )
        self._drafts.insert_one(_draft_doc(new_draft), session=session)
        for draft in shifted_drafts:
            self._drafts.update_one(
                {"_id": draft.id, "project_id": draft.project_id},
                {"$set": {"position": draft.position}},
                session=session,
            )
        self._after_start_next_write(new_draft)
        try:
            self._versions.insert_one(_version_doc(version), session=session)
        except DuplicateKeyError as exc:
            raise DuplicateSaveRequest(idempotency_key) from exc
        self._snapshots.insert_one(
            _snapshot_doc(snapshot, idempotency_key), session=session)
        block_docs = [
            _block_doc(block, idempotency_key, version.draft_id)
            for block in blocks
        ]
        if block_docs:
            self._blocks.insert_many(block_docs, session=session)
        try:
            self._writing_accept_receipts.insert_one(
                _receipt_doc(receipt), session=session)
        except DuplicateKeyError as exc:
            raise DuplicateWritingAcceptReceipt(receipt.idempotency_key) from exc

    def _after_start_next_write(self, new_draft: Draft) -> None:
        """Failure-injection seam for the WI-11 six-surface rollback test."""


def _project_doc(project: Project) -> dict:
    return {
        "_id": project.id,
        "name": project.name,
        "archived": project.archived,
        "owner_id": project.owner_id,
    }


def _to_project(doc: dict) -> Project:
    return Project(
        id=doc["_id"],
        name=doc["name"],
        archived=doc["archived"],
        # .get: documents written before ownership existed have no such key, and
        # they must read back as unowned rather than raising.
        owner_id=doc.get("owner_id"),
    )


def _project_brief_doc(brief: ProjectBriefVersion) -> dict:
    return {
        "_id": brief.id,
        "project_id": brief.project_id,
        "version_number": brief.version_number,
        "premise": brief.premise,
        "genre": brief.genre,
        "tone": brief.tone,
        "pov": brief.pov,
        "constraints": list(brief.constraints),
        "style_rules": list(brief.style_rules),
        "preferred_patterns": list(brief.preferred_patterns),
        "forbidden_patterns": list(brief.forbidden_patterns),
        "style_examples": list(brief.style_examples),
        "idempotency_key": brief.idempotency_key,
    }


def _to_project_brief(doc: dict) -> ProjectBriefVersion:
    return ProjectBriefVersion(
        id=doc["_id"],
        project_id=doc["project_id"],
        version_number=doc["version_number"],
        premise=doc["premise"],
        genre=doc["genre"],
        tone=doc["tone"],
        pov=doc["pov"],
        constraints=tuple(doc["constraints"]),
        idempotency_key=doc["idempotency_key"],
        # v1.7.13 ProjectBrief documents predate the style arrays. Reading them
        # as empty preserves their immutable historical meaning without a
        # migration that rewrites append-only versions.
        style_rules=tuple(doc.get("style_rules", ())),
        preferred_patterns=tuple(doc.get("preferred_patterns", ())),
        forbidden_patterns=tuple(doc.get("forbidden_patterns", ())),
        style_examples=tuple(doc.get("style_examples", ())),
    )


def _chapter_doc(chapter: Chapter) -> dict:
    return {
        "_id": chapter.id,
        "project_id": chapter.project_id,
        "title": chapter.title,
        "archived": chapter.archived,
        "position": chapter.position,
    }


def _to_chapter(doc: dict) -> Chapter:
    return Chapter(
        id=doc["_id"],
        project_id=doc["project_id"],
        title=doc["title"],
        archived=doc["archived"],
        position=doc["position"],
    )


def _draft_doc(draft: Draft) -> dict:
    return {
        "_id": draft.id,
        "project_id": draft.project_id,
        "title": draft.title,
        "archived": draft.archived,
        "chapter_id": draft.chapter_id,
        "unit_kind": str(draft.unit_kind) if draft.unit_kind is not None else None,
        "position": draft.position,
        "finalized_snapshot_id": draft.finalized_snapshot_id,
        "finalized_at": draft.finalized_at,
        "finalized_idempotency_key": draft.finalized_idempotency_key,
    }


def _to_draft(doc: dict) -> Draft:
    return Draft(
        id=doc["_id"],
        project_id=doc["project_id"],
        title=doc["title"],
        archived=doc["archived"],
        chapter_id=doc.get("chapter_id"),
        unit_kind=(
            UnitKind(doc["unit_kind"])
            if doc.get("unit_kind") is not None
            else None
        ),
        position=doc.get("position"),
        finalized_snapshot_id=doc.get("finalized_snapshot_id"),
        finalized_at=(
            _aware(doc["finalized_at"])
            if doc.get("finalized_at") is not None else None
        ),
        finalized_idempotency_key=doc.get("finalized_idempotency_key"),
    )


def _scene_note_doc(note: SceneNote) -> dict:
    # ``_id`` 를 두지 않는다 — 정체성은 uniq_scene_note 인덱스의
    # (project_id, draft_id) 이고, 메모는 자기 id 로 불리는 일이 없다.
    return {
        "project_id": note.project_id,
        "draft_id": note.draft_id,
        "body": note.body,
        "updated_at": note.updated_at,
    }


def _to_scene_note(doc: dict) -> SceneNote:
    return SceneNote(
        project_id=doc["project_id"],
        draft_id=doc["draft_id"],
        body=doc["body"],
        updated_at=_aware(doc["updated_at"]),
    )


def _aware(value: datetime) -> datetime:
    """BSON 날짜를 UTC-aware 로 되돌린다.

    pymongo 는 client 가 ``tz_aware`` 가 아니면 naive 로 돌려주고, naive 와 aware 를
    비교하면 TypeError 다. 다른 어댑터(auth·activity·quota)와 같은 경계 정규화다.
    """

    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _version_doc(version: DraftVersion) -> dict:
    return {
        "_id": version.id,
        "project_id": version.project_id,
        "draft_id": version.draft_id,
        "version_number": version.version_number,
        "snapshot_id": version.snapshot_id,
        "idempotency_key": version.idempotency_key,
    }


def _to_version(doc: dict) -> DraftVersion:
    return DraftVersion(
        id=doc["_id"],
        project_id=doc["project_id"],
        draft_id=doc["draft_id"],
        version_number=doc["version_number"],
        snapshot_id=doc["snapshot_id"],
        idempotency_key=doc["idempotency_key"],
    )


def _snapshot_doc(snapshot: SourceSnapshot, idempotency_key: str) -> dict:
    return {
        "_id": snapshot.id,
        "project_id": snapshot.project_id,
        "draft_id": snapshot.draft_id,
        "version_id": snapshot.version_id,
        "raw_text": snapshot.raw_text,
        "content_hash": snapshot.content_hash,
        "idempotency_key": idempotency_key,
    }


def _to_snapshot(doc: dict) -> SourceSnapshot:
    return SourceSnapshot(
        id=doc["_id"],
        project_id=doc["project_id"],
        draft_id=doc["draft_id"],
        version_id=doc["version_id"],
        raw_text=doc["raw_text"],
        content_hash=doc["content_hash"],
    )


def _block_doc(block: SourceBlock, idempotency_key: str, draft_id: str) -> dict:
    return {
        "_id": block.id,
        "project_id": block.project_id,
        "snapshot_id": block.snapshot_id,
        "draft_id": draft_id,
        "idempotency_key": idempotency_key,
        "block_index": block.block_index,
        "kind": str(block.kind),
        "start_offset": block.start_offset,
        "end_offset": block.end_offset,
        "text": block.text,
    }


def _to_block(doc: dict) -> SourceBlock:
    return SourceBlock(
        id=doc["_id"],
        project_id=doc["project_id"],
        snapshot_id=doc["snapshot_id"],
        block_index=doc["block_index"],
        kind=BlockKind(doc["kind"]),
        start_offset=doc["start_offset"],
        end_offset=doc["end_offset"],
        text=doc["text"],
    )


def _source_ref_doc(source_ref: SourceRef) -> dict:
    return {
        "_id": source_ref.id,
        "project_id": source_ref.project_id,
        "snapshot_id": source_ref.snapshot_id,
        "block_id": source_ref.block_id,
        "start_offset": source_ref.start_offset,
        "end_offset": source_ref.end_offset,
        "quote": source_ref.quote,
        "content_hash": source_ref.content_hash,
    }


def _to_source_ref(doc: dict) -> SourceRef:
    return SourceRef(
        id=doc["_id"],
        project_id=doc["project_id"],
        snapshot_id=doc["snapshot_id"],
        block_id=doc["block_id"],
        start_offset=doc["start_offset"],
        end_offset=doc["end_offset"],
        quote=doc["quote"],
        content_hash=doc["content_hash"],
    )


def _receipt_doc(receipt: WritingAcceptReceipt) -> dict:
    return {
        "project_id": receipt.project_id,
        "idempotency_key": receipt.idempotency_key,
        "intent": receipt.intent,
        "draft_id": receipt.draft_id,
        "draft_version_id": receipt.draft_version_id,
    }


def _to_receipt(doc: dict) -> WritingAcceptReceipt:
    return WritingAcceptReceipt(
        project_id=doc["project_id"],
        idempotency_key=doc["idempotency_key"],
        intent=doc["intent"],
        draft_id=doc["draft_id"],
        draft_version_id=doc["draft_version_id"],
    )
