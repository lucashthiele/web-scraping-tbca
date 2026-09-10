import random
import sys
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Tuple

import requests

from .constants import DEFAULT_TBCA_URL, RETRYABLE_STATUS_CODES
from .parsing import FoodPayload, FoodReference, parse_food_detail, parse_listing


class RateLimiter:
    """Enforce a minimum interval between request start times."""

    def __init__(self, requests_per_second: float) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be greater than zero")
        self.minimum_interval = 1.0 / requests_per_second
        self.last_request_started = None  # type: Optional[float]

    def wait(self) -> None:
        now = time.monotonic()
        if self.last_request_started is not None:
            remaining = self.minimum_interval - (now - self.last_request_started)
            if remaining > 0:
                time.sleep(remaining)

        time.sleep(random.uniform(0, min(0.05, self.minimum_interval / 10)))
        self.last_request_started = time.monotonic()


class TbcaClient:
    """TBCA HTTP client with global rate limiting and retries."""

    def __init__(
        self,
        requests_per_second: float = 2.0,
        timeout: Tuple[int, int] = (10, 30),
        max_attempts: int = 5,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "web-scraping-tbca/1.0"})
        self.rate_limiter = RateLimiter(requests_per_second)
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.request_count = 0
        self.retry_count = 0

    @staticmethod
    def _retry_after_seconds(value: Optional[str]) -> Optional[float]:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                now = datetime.now(retry_at.tzinfo)
                return max(0.0, (retry_at - now).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None

    def get(self, url: str, params: Optional[Dict[str, int]] = None) -> requests.Response:
        last_error = None  # type: Optional[Exception]
        for attempt in range(1, self.max_attempts + 1):
            self.rate_limiter.wait()
            self.request_count += 1
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    response.raise_for_status()
                    return response
                last_error = requests.HTTPError(
                    "status HTTP {}".format(response.status_code), response=response
                )
                retry_after = self._retry_after_seconds(
                    response.headers.get("Retry-After")
                )
            except (requests.Timeout, requests.ConnectionError) as error:
                last_error = error
                retry_after = None

            if attempt == self.max_attempts:
                break

            self.retry_count += 1
            delay = retry_after
            if delay is None:
                delay = min(60.0, 2 ** (attempt - 1)) + random.uniform(0, 0.25)
            print(
                "Request failed (attempt {}/{}); retrying in {:.1f}s".format(
                    attempt, self.max_attempts, delay
                ),
                file=sys.stderr,
            )
            time.sleep(delay)

        raise RuntimeError(
            "Request failed after {} attempts: {}".format(self.max_attempts, last_error)
        )

    def list_foods(
        self, max_pages: Optional[int] = None, url: str = DEFAULT_TBCA_URL
    ) -> List[FoodReference]:
        foods = []
        seen_codes = set()
        page = 1

        while max_pages is None or page <= max_pages:
            response = self.get(url, params={"pagina": page})
            page_foods = parse_listing(response.text, url)
            if not page_foods:
                break

            for food in page_foods:
                if food["externalId"] not in seen_codes:
                    seen_codes.add(food["externalId"])
                    foods.append(food)

            print("Listing page {}: {} foods".format(page, len(page_foods)))
            page += 1

        return foods

    def fetch_food(self, queue_item: FoodReference) -> FoodPayload:
        response = self.get(queue_item["url"])
        return parse_food_detail(response.content, queue_item)
