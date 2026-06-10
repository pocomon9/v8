from __future__ import annotations

import json
import re
from datetime import datetime, timedelta


MISSION_TERMS = {
    "entertainment",
    "celebrity",
    "celebrities",
    "movie",
    "movies",
    "music",
    "gaming",
    "streaming",
    "viral",
    "culture",
    "geopolitics",
    "war",
    "conflict",
    "foreign",
    "policy",
    "world",
    "politics",
    "political",
    "election",
    "government",
    "crypto",
    "bitcoin",
    "ethereum",
    "solana",
    "blockchain",
    "defi",
    "web3",
    "meme",
    "memes",
    "humor",
    "funny",
}

MISSION_PHRASES = {
    "world order",
    "foreign policy",
    "war update",
    "global conflict",
    "crypto market",
    "bitcoin etf",
    "crypto regulation",
    "political meme",
    "geopolitics meme",
    "internet meme",
    "entertainment news",
    "box office",
    "streaming war",
}

SHOPPING_TERMS = {
    "shopping",
    "shop",
    "store",
    "stores",
    "fashion",
    "clothing",
    "outfit",
    "dress",
    "shoes",
    "beauty",
    "makeup",
    "skincare",
    "product",
    "products",
    "order",
    "orders",
    "checkout",
    "cart",
    "coupon",
    "discount",
    "sale",
    "delivery",
    "returns",
    "exchange",
    "sizes",
}

SHOPPING_PHRASES = {
    "product info",
    "order support",
    "customer support",
    "customer service",
    "find a store",
    "store locator",
    "size guide",
    "new collection",
    "zara sale",
    "buy now",
    "add to cart",
}


class TrendHunter:
    def __init__(self) -> None:
        self.topic_groups = {
            "entertainment": [
                "entertainment news",
                "celebrity drama",
                "movie buzz",
                "music industry",
                "streaming war",
                "gaming culture",
            ],
            "memes": [
                "political meme",
                "geopolitics meme",
                "crypto meme",
                "internet meme",
                "viral meme",
            ],
            "geopolitics": [
                "geopolitics",
                "war update",
                "global conflict",
                "world order",
                "foreign policy",
            ],
            "politics": [
                "politics",
                "policy debate",
                "election strategy",
                "government reform",
            ],
            "crypto": [
                "crypto",
                "bitcoin",
                "ethereum",
                "solana",
                "crypto regulation",
                "crypto market",
            ],
        }
        self.seed_topics = [item for values in self.topic_groups.values() for item in values]

    def default_queries(self) -> list[str]:
        since = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
        return [
            f"entertainment news filter:videos min_faves:1 min_retweets:0 min_replies:0 lang:en since:{since}",
            f"politics OR geopolitics min_faves:1 min_replies:0 lang:en since:{since}",
            f"political meme OR geopolitics meme filter:videos min_faves:1 min_retweets:0 min_replies:0 lang:en since:{since}",
            f"war OR military min_faves:1 min_replies:0 lang:en since:{since}",
            f"geopolitics filter:videos min_faves:1 min_retweets:0 min_replies:0 lang:en since:{since}",
            f"war update filter:videos min_faves:1 min_retweets:0 min_replies:0 lang:en since:{since}",
            f"memes OR entertainment min_faves:1 min_replies:0 lang:en since:{since}",
            f"foreign policy filter:images min_faves:1 min_retweets:0 min_replies:0 lang:en since:{since}",
            f"politics filter:images min_faves:1 min_retweets:0 min_replies:0 lang:en since:{since}",
            f"war OR military filter:images min_faves:1 min_retweets:0 min_replies:0 lang:en since:{since}",
            f"crypto regulation OR bitcoin ETF filter:videos min_faves:1 min_retweets:0 min_replies:0 lang:en since:{since}",
        ]

    def parse_queries(self, raw: str) -> list[str]:
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []
        queries: list[str] = []
        seen = set()
        for item in parsed:
            query = str(item or "").strip()
            if not query or query in seen:
                continue
            if not self._query_is_on_mission(query):
                continue
            seen.add(query)
            queries.append(query)
        return queries

    def _query_is_on_mission(self, query: str) -> bool:
        lowered = (query or "").lower()
        tokens = set(re.findall(r"[a-z]{3,}", lowered))
        has_mission_phrase = any(phrase in lowered for phrase in MISSION_PHRASES)
        if any(phrase in lowered for phrase in SHOPPING_PHRASES):
            return False
        if (tokens & SHOPPING_TERMS) and not has_mission_phrase:
            return False
        return bool((tokens & MISSION_TERMS) or has_mission_phrase)

    def compose_queries(self, memory_briefs: list[str], limit: int = 8) -> list[str]:
        since = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
        queries: list[str] = []
        seen = set()

        def add(query: str) -> None:
            query = " ".join((query or "").split()).strip()
            if not query or query in seen:
                return
            seen.add(query)
            queries.append(query)

        for query in self.default_queries():
            add(query)

        boosted_topics: list[str] = []
        for item in memory_briefs:
            text = (item or "").strip().lower()
            if not text:
                continue
            for match in re.findall(r"[a-z]{4,}", text):
                if match in {"signal", "source", "trend", "memory", "posts", "fresh", "strongest", "ignored"}:
                    continue
                if match in SHOPPING_TERMS or match not in MISSION_TERMS:
                    continue
                boosted_topics.append(match)

        for index, topic in enumerate(boosted_topics[:12]):
            media_filter = "filter:videos" if index % 2 == 0 else "filter:images"
            add(f"{topic} {media_filter} min_faves:1 min_retweets:0 min_replies:0 lang:en since:{since}")

        return queries[:limit]

    def fallback_results(self, queries: list[str]) -> list[dict]:
        results = []
        for query in queries[:6]:
            topic = query.split("min_", 1)[0].replace("lang:en", "").replace("since:", "").strip()
            results.append(
                {
                    "query": query,
                    "topic": topic,
                    "user": "trend-sim",
                    "text": f"{topic.title()} is shifting faster than most people realize. The strongest signal is still being ignored.",
                    "url": "",
                    "image_url": "",
                    "simulated": True,
                    "metrics": {"engagement_hint": 1200},
                }
            )
        return results
