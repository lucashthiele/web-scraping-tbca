import argparse
import os
import sys
from typing import List, Optional

from dotenv import load_dotenv

from .http import TbcaClient
from .service import ScrapeService
from .storage import MongoCheckpointStore


DEFAULT_MONGODB_URI = (
    "mongodb://tbca:tbca-local@127.0.0.1:27017/?authSource=admin"
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import food data from TBCA")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="limit listing pages; all pages are scraped by default",
    )
    parser.add_argument(
        "--requests-per-second",
        type=float,
        default=2.0,
        help="maximum global HTTP request rate (default: 2)",
    )
    parser.add_argument("--output", default="foods.json")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="clear the checkpoint and results before starting",
    )
    args = parser.parse_args(argv)
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be greater than zero")
    if args.requests_per_second <= 0:
        parser.error("--requests-per-second must be greater than zero")
    return args


def build_service(args: argparse.Namespace) -> ScrapeService:
    load_dotenv()
    store = MongoCheckpointStore(
        os.environ.get("MONGODB_URI", DEFAULT_MONGODB_URI),
        os.environ.get("MONGODB_DATABASE", "tbca"),
    )
    client = TbcaClient(args.requests_per_second)
    return ScrapeService(client, store, args.output, args.max_pages)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        build_service(args).execute(reset=args.reset)
    except Exception as error:
        print("Error: {}".format(error), file=sys.stderr)
        return 1
    return 0
