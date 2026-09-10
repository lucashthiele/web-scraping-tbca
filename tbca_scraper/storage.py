import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from pymongo import ASCENDING, MongoClient, ReturnDocument

from .constants import CHECKPOINT_ID, SCHEMA_VERSION
from .parsing import FoodPayload, FoodReference


RunDocument = Dict[str, Any]
QueueDocument = Dict[str, Any]


def utcnow() -> datetime:
    return datetime.utcnow()


class MongoCheckpointStore:
    """Persist the queue, food documents, and high-water mark in MongoDB."""

    def __init__(self, uri: str, database_name: str) -> None:
        self.client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        self.client.admin.command("ping")

        database = self.client[database_name]
        self.runs = database.scrape_runs
        self.queue = database.scrape_queue
        self.foods = database.foods
        self.owner = str(uuid.uuid4())
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self.queue.create_index(
            [("run_id", ASCENDING), ("position", ASCENDING)], unique=True
        )
        self.queue.create_index(
            [("run_id", ASCENDING), ("externalId", ASCENDING)],
            name="unique_run_external_id",
            unique=True,
        )
        self.foods.create_index(
            [("externalId", ASCENDING)],
            name="unique_external_id",
            unique=True,
        )

    def reset(self) -> None:
        self.foods.delete_many({})
        self.queue.delete_many({})
        self.runs.delete_many({})

    def get_run(self) -> Optional[RunDocument]:
        return self.runs.find_one({"_id": CHECKPOINT_ID})

    def create_run(
        self, queue_items: Iterable[FoodReference], max_pages: Optional[int]
    ) -> RunDocument:
        items = list(queue_items)
        run_id = str(uuid.uuid4())
        now = utcnow()
        self.runs.insert_one(
            {
                "_id": CHECKPOINT_ID,
                "run_id": run_id,
                "schema_version": SCHEMA_VERSION,
                "status": "pending",
                "max_pages": max_pages,
                "next_index": 0,
                "last_completed_code": None,
                "total": len(items),
                "created_at": now,
                "updated_at": now,
            }
        )
        if items:
            self.queue.insert_many(
                [
                    dict(item, run_id=run_id, position=position)
                    for position, item in enumerate(items)
                ]
            )
        run = self.get_run()
        if run is None:
            raise RuntimeError("The run was not created in MongoDB")
        return run

    def acquire(self, run_id: str) -> RunDocument:
        now = utcnow()
        run = self.runs.find_one_and_update(
            {
                "_id": CHECKPOINT_ID,
                "run_id": run_id,
                "$or": [
                    {"lease_expires_at": {"$lt": now}},
                    {"lease_expires_at": {"$exists": False}},
                    {"lease_owner": self.owner},
                ],
            },
            {
                "$set": {
                    "lease_owner": self.owner,
                    "lease_expires_at": now + timedelta(seconds=30),
                    "status": "running",
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if run is None:
            raise RuntimeError("Another scraper instance already holds this run")
        return run

    def get_queue_item(self, run_id: str, position: int) -> Optional[QueueDocument]:
        return self.queue.find_one({"run_id": run_id, "position": position})

    def has_food(self, external_id: str) -> bool:
        return self.foods.count_documents({"externalId": external_id}, limit=1) == 1

    def save_food(self, run_id: str, position: int, payload: FoodPayload) -> None:
        self.foods.replace_one(
            {"externalId": payload["externalId"]},
            payload,
            upsert=True,
        )

    def advance(self, run_id: str, next_index: int, code: str) -> None:
        now = utcnow()
        result = self.runs.update_one(
            {
                "_id": CHECKPOINT_ID,
                "run_id": run_id,
                "lease_owner": self.owner,
            },
            {
                "$set": {
                    "next_index": next_index,
                    "last_completed_code": code,
                    "lease_expires_at": now + timedelta(seconds=30),
                    "updated_at": now,
                }
            },
        )
        if result.matched_count != 1:
            raise RuntimeError("Could not advance the checkpoint")

    def complete(self, run_id: str, request_count: int, retry_count: int) -> None:
        self.runs.update_one(
            {
                "_id": CHECKPOINT_ID,
                "run_id": run_id,
                "lease_owner": self.owner,
            },
            {
                "$set": {
                    "status": "completed",
                    "completed_at": utcnow(),
                    "updated_at": utcnow(),
                    "last_run_request_count": request_count,
                    "last_run_retry_count": retry_count,
                },
                "$unset": {"lease_owner": "", "lease_expires_at": ""},
            },
        )

    def fail(self, run_id: str, error: Exception) -> None:
        self.runs.update_one(
            {
                "_id": CHECKPOINT_ID,
                "run_id": run_id,
                "lease_owner": self.owner,
            },
            {
                "$set": {
                    "status": "failed",
                    "last_error": str(error),
                    "updated_at": utcnow(),
                },
                "$unset": {"lease_owner": "", "lease_expires_at": ""},
            },
        )

    def export(self, run_id: str, output_path: str) -> int:
        foods = list(self.foods.find({}, {"_id": False}).sort("externalId", ASCENDING))
        self._atomic_json_write(foods, Path(output_path).resolve())
        return len(foods)

    @staticmethod
    def _atomic_json_write(foods: Iterable[FoodPayload], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=output_path.name + ".",
            suffix=".tmp",
            dir=str(output_path.parent),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
                json.dump(list(foods), output_file, ensure_ascii=False, indent=2)
                output_file.write("\n")
            os.replace(temporary_name, str(output_path))
        except Exception:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise
