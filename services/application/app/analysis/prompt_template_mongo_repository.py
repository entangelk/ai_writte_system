"""MongoDB adapter for versioned analysis prompt templates."""

from __future__ import annotations

from bson import ObjectId
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, OperationFailure

from services.application.app.analysis.prompt_templates import (
    DuplicatePromptTemplate,
    PromptTemplate,
)
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


class MongoPromptTemplateRepositorySetupError(RuntimeError):
    """Raised when MongoDB cannot install required prompt template indexes."""


class MongoPromptTemplateRepository:
    def __init__(
        self,
        client: MongoClient,
        *,
        db_name: str = DEFAULT_DB_NAME,
    ) -> None:
        self._db = client[db_name]
        self._templates = self._db["prompt_templates"]
        self.ensure_indexes()

    @classmethod
    def from_uri(
        cls,
        uri: str,
        *,
        db_name: str = DEFAULT_DB_NAME,
    ) -> "MongoPromptTemplateRepository":
        return cls(MongoClient(uri), db_name=db_name)

    def ensure_indexes(self) -> None:
        try:
            self._templates.create_index(
                [("task_type", ASCENDING), ("version", ASCENDING)],
                unique=True,
                name="uniq_prompt_template_version",
            )
        except OperationFailure as exc:
            raise MongoPromptTemplateRepositorySetupError(
                "failed to create required prompt template MongoDB indexes"
            ) from exc

    def next_template_id(self) -> str:
        return str(ObjectId())

    def get_template(self, *, task_type: str, version: str) -> PromptTemplate | None:
        doc = self._templates.find_one({"task_type": task_type, "version": version})
        return _to_template(doc) if doc else None

    def put_template(self, template: PromptTemplate) -> None:
        try:
            self._templates.insert_one(_template_doc(template))
        except DuplicateKeyError as exc:
            raise DuplicatePromptTemplate((template.task_type, template.version)) from exc


def _template_doc(template: PromptTemplate) -> dict:
    return {
        "_id": template.id,
        "task_type": template.task_type,
        "version": template.version,
        "template": template.template,
    }


def _to_template(doc: dict) -> PromptTemplate:
    return PromptTemplate(
        id=doc["_id"],
        task_type=doc["task_type"],
        version=doc["version"],
        template=doc["template"],
    )
