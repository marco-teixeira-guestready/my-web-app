"""DataForSEO API client wrapper."""

import base64
import os
import requests
from typing import Any


class DataForSEOClient:
    BASE_URL = "https://api.dataforseo.com/v3"

    def __init__(self, login: str = None, password: str = None):
        self.login = login or os.environ["DATAFORSEO_LOGIN"]
        self.password = password or os.environ["DATAFORSEO_PASSWORD"]
        credentials = base64.b64encode(
            f"{self.login}:{self.password}".encode()
        ).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

    def _post(self, endpoint: str, payload: list[dict]) -> dict:
        url = f"{self.BASE_URL}/{endpoint}"
        response = requests.post(url, headers=self.headers, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

    def keyword_suggestions(
        self,
        keyword: str,
        location_code: int = 2840,  # USA
        language_code: str = "en",
        limit: int = 100,
    ) -> list[dict]:
        """Get keyword suggestions and search volume data."""
        payload = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
                "include_seed_keyword": True,
            }
        ]
        result = self._post(
            "dataforseo_labs/google/keyword_suggestions/live", payload
        )
        items = []
        for task in result.get("tasks", []):
            for res in task.get("result", []):
                items.extend(res.get("items", []))
        return items

    def related_keywords(
        self,
        keyword: str,
        location_code: int = 2840,
        language_code: str = "en",
        limit: int = 100,
    ) -> list[dict]:
        """Get related keywords."""
        payload = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
            }
        ]
        result = self._post(
            "dataforseo_labs/google/related_keywords/live", payload
        )
        items = []
        for task in result.get("tasks", []):
            for res in task.get("result", []):
                items.extend(res.get("items", []))
        return items

    def keyword_search_volume(
        self,
        keywords: list[str],
        location_code: int = 2840,
        language_code: str = "en",
    ) -> list[dict]:
        """Get search volume for a list of keywords."""
        payload = [
            {
                "keywords": keywords,
                "location_code": location_code,
                "language_code": language_code,
            }
        ]
        result = self._post(
            "keywords_data/google_ads/search_volume/live", payload
        )
        items = []
        for task in result.get("tasks", []):
            for res in task.get("result", []):
                items.extend(res if isinstance(res, list) else [res])
        return items

    def serp_overview(
        self,
        keyword: str,
        location_code: int = 2840,
        language_code: str = "en",
    ) -> list[dict]:
        """Get SERP overview for a keyword (top results + featured snippets)."""
        payload = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
            }
        ]
        result = self._post(
            "serp/google/organic/live/advanced", payload
        )
        items = []
        for task in result.get("tasks", []):
            for res in task.get("result", []):
                items.extend(res.get("items", []))
        return items

    def on_page_audit(self, url: str) -> dict[str, Any]:
        """Run a basic on-page audit for a URL (title, description, headings, content)."""
        payload = [{"url": url, "enable_javascript": False}]
        result = self._post("on_page/instant_pages", payload)
        pages = []
        for task in result.get("tasks", []):
            for res in task.get("result", []):
                pages.extend(res.get("items", []))
        return pages[0] if pages else {}
