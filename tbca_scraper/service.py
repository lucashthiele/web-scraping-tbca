import sys
from pathlib import Path
from typing import Optional

from .constants import SCHEMA_VERSION
from .http import TbcaClient
from .storage import MongoCheckpointStore, RunDocument


class ScrapeService:
    """Orchestrate discovery, resume behavior, persistence, and export."""

    def __init__(
        self,
        client: TbcaClient,
        store: MongoCheckpointStore,
        output_path: str,
        max_pages: Optional[int],
    ) -> None:
        self.client = client
        self.store = store
        self.output_path = output_path
        self.max_pages = max_pages

    def execute(self, reset: bool = False) -> None:
        if reset:
            self._reset()

        run = self.store.get_run()
        if run is None:
            run = self._start_run()
        else:
            self._validate_scope(run)

        run_id = run["run_id"]
        if run["status"] == "completed":
            exported = self.store.export(run_id, self.output_path)
            print("Run was already complete; exported {} foods".format(exported))
            return

        run = self.store.acquire(run_id)
        try:
            self._process_queue(run)
            exported = self.store.export(run_id, self.output_path)
            self.store.complete(
                run_id, self.client.request_count, self.client.retry_count
            )
            print(
                "Completed: {} foods, {} requests, {} retries".format(
                    exported, self.client.request_count, self.client.retry_count
                )
            )
        except Exception as error:
            self.store.fail(run_id, error)
            raise

    def _reset(self) -> None:
        self.store.reset()
        output = Path(self.output_path)
        if output.exists():
            output.unlink()
        print("Removed the previous checkpoint and results")

    def _start_run(self) -> RunDocument:
        queue_items = self.client.list_foods(max_pages=self.max_pages)
        if not queue_items:
            raise RuntimeError("No foods were found in the listing")
        run = self.store.create_run(queue_items, self.max_pages)
        print("Created a new queue with {} foods".format(len(queue_items)))
        return run

    def _validate_scope(self, run: RunDocument) -> None:
        if run.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeError(
                "The existing checkpoint uses an incompatible schema; use --reset"
            )
        if run.get("max_pages") != self.max_pages:
            raise RuntimeError(
                "The existing checkpoint uses --max-pages={}; run again with "
                "that value or use --reset".format(run.get("max_pages"))
            )

    def _process_queue(self, run: RunDocument) -> None:
        run_id = run["run_id"]
        for position in range(run["next_index"], run["total"]):
            item = self.store.get_queue_item(run_id, position)
            if item is None:
                raise RuntimeError("Queue item {} was not found".format(position))

            if not self.store.has_food(item["externalId"]):
                payload = self.client.fetch_food(item)
                self.store.save_food(run_id, position, payload)
                for warning in payload.get("qualityWarnings", []):
                    print(
                        "Warning for {}: {}".format(item["externalId"], warning),
                        file=sys.stderr,
                    )

            self.store.advance(run_id, position + 1, item["externalId"])
            print(
                "[{}/{}] persisted {}".format(
                    position + 1, run["total"], item["externalId"]
                )
            )
