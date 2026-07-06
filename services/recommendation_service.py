import logging
import re
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

from youtube_api import YouTubeAPI
from core.events import (
    RecommendationsLoadingEvent, RecommendationsLoadedEvent, RecommendationsFailedEvent,
)

STOP_WORDS: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "can", "could",
    "shall", "should", "may", "might", "must", "to", "of", "in", "for", "on",
    "with", "at", "by", "from", "as", "into", "through", "during", "before",
    "after", "above", "below", "between", "out", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "when", "where",
    "why", "how", "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "because", "and", "but", "or",
    "if", "while", "that", "this", "it", "its", "i", "me", "my", "we",
    "our", "you", "your", "he", "she", "they", "them", "their", "his",
    "her", "what", "which", "who", "whom", "about", "up", "down",
    "one", "two", "three", "first", "last", "new", "old", "get", "got",
    "make", "made", "like", "really", "vs", "de", "la", "le", "en",
}

TRENDING_QUERIES = [
    "trending",
    "viral videos",
    "popular",
    "trending now",
]

CACHE_TTL = 1800  # 30 minutes
MAX_CONTINUE_WATCHING = 10
MAX_RECOMMENDED = 12
MAX_TRENDING = 12
MAX_HISTORY_BASED = 10
MAX_RECENTLY_PLAYED = 10
MAX_WATCH_LATER = 8
MAX_LIKED = 8


class RecommendationService:
    def __init__(self, youtube_api: Optional[YouTubeAPI] = None,
                 event_bus=None, logger=None):
        self._youtube_api = youtube_api or YouTubeAPI()
        self._event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)
        self._lock = threading.RLock()
        self._cache: Dict[str, Tuple[float, list]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_continue_watching(self, history_service, max_count: int = MAX_CONTINUE_WATCHING) -> List[dict]:
        history = history_service.get_all() if history_service else []
        # Return the most recent videos that were started but not finished
        return history[:max_count]

    def get_recommended(self, history_service, likes_service,
                        playlist_service, max_count: int = MAX_RECOMMENDED) -> List[dict]:
        cached = self._get_cached("recommended")
        if cached is not None:
            return cached

        keywords = self._extract_keywords(history_service, likes_service, playlist_service)
        channel_ids = self._score_channels(history_service, likes_service)

        results = []
        if channel_ids:
            for channel in channel_ids[:3]:
                batch = self._search_yt(f"{channel} video", 4)
                results.extend(batch)
                if len(results) >= max_count:
                    break

        if len(results) < max_count and keywords:
            top_kw = [k for k, _ in keywords[:5]]
            queries = self._generate_queries(top_kw)
            for q in queries[:3]:
                batch = self._search_yt(q, 4)
                results.extend(batch)
                if len(results) >= max_count:
                    break

        results = self._deduplicate(results)[:max_count]
        self._set_cached("recommended", results)
        return results

    def get_trending(self, max_count: int = MAX_TRENDING) -> List[dict]:
        cached = self._get_cached("trending")
        if cached is not None:
            return cached

        results = []
        for q in TRENDING_QUERIES:
            batch = self._search_yt(q, 4)
            results.extend(batch)
            if len(results) >= max_count:
                break
        results = self._deduplicate(results)[:max_count]
        self._set_cached("trending", results)
        return results

    def get_history_based(self, history_service, max_count: int = MAX_HISTORY_BASED) -> List[dict]:
        cached = self._get_cached("history_based")
        if cached is not None:
            return cached

        keywords = self._extract_keywords(history_service, None)
        if not keywords:
            return []

        top_kw = [k for k, _ in keywords[:8]]
        queries = self._generate_queries(top_kw)

        results = []
        for q in queries[:4]:
            batch = self._search_yt(q, 3)
            results.extend(batch)
            if len(results) >= max_count:
                break
        results = self._deduplicate(results)[:max_count]
        self._set_cached("history_based", results)
        return results

    def get_recently_played(self, history_service, max_count: int = MAX_RECENTLY_PLAYED) -> List[dict]:
        if not history_service:
            return []
        return history_service.get_recent(max_count)

    def get_watch_later_preview(self, playlist_service, max_count: int = MAX_WATCH_LATER) -> List[dict]:
        if not playlist_service:
            return []
        return playlist_service.get_watch_later()[:max_count]

    def get_liked_preview(self, likes_service, max_count: int = MAX_LIKED) -> List[dict]:
        if not likes_service:
            return []
        return likes_service.get_liked_videos()[:max_count]

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------

    def _extract_keywords(self, history_service, likes_service,
                          playlist_service=None) -> List[Tuple[str, int]]:
        titles: List[str] = []
        channels: List[str] = []

        if history_service:
            for entry in history_service.get_all():
                if entry.get("title"):
                    titles.append(entry["title"])
                if entry.get("channel"):
                    channels.append(entry["channel"])

        if likes_service:
            for entry in likes_service.get_liked_videos():
                if entry.get("title"):
                    titles.append(entry["title"])
                if entry.get("channel"):
                    channels.append(entry["channel"])

        if playlist_service:
            try:
                for pl in playlist_service.get_all_playlists():
                    for v in pl.videos:
                        if v.title:
                            titles.append(v.title)
                        if v.channel:
                            channels.append(v.channel)
            except Exception:
                pass

        word_counts: Dict[str, int] = {}
        for title in titles:
            tokens = self._tokenize(title)
            for token in tokens:
                word_counts[token] = word_counts.get(token, 0) + 1

        # Add channel names with 2x weight
        for channel in channels:
            tokens = self._tokenize(channel)
            for token in tokens:
                word_counts[token] = word_counts.get(token, 0) + 2

        sorted_words = sorted(word_counts.items(), key=lambda x: -x[1])
        return sorted_words[:30]

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        tokens = re.findall(r"[a-z0-9]+(?:[.+-][a-z0-9]+)*", text)
        return [t for t in tokens if len(t) > 2 and t not in STOP_WORDS]

    def _generate_queries(self, keywords: List[str]) -> List[str]:
        queries = []
        for i in range(0, len(keywords) - 1, 2):
            pair = f"{keywords[i]} {keywords[i + 1]}"
            queries.append(pair)

        if len(keywords) >= 3:
            queries.append(f"{keywords[0]} {keywords[1]} {keywords[2]}")

        if queries:
            queries.append(keywords[0])

        return queries[:6]

    # ------------------------------------------------------------------
    # Channel scoring
    # ------------------------------------------------------------------

    def _score_channels(self, history_service, likes_service) -> List[str]:
        channel_counts: Dict[str, int] = {}

        if history_service:
            for entry in history_service.get_all():
                ch = entry.get("channel", "").strip()
                if ch:
                    channel_counts[ch] = channel_counts.get(ch, 0) + 1

        if likes_service:
            for entry in likes_service.get_liked_videos():
                ch = entry.get("channel", "").strip()
                if ch:
                    channel_counts[ch] = channel_counts.get(ch, 0) + 3

        sorted_channels = sorted(channel_counts.items(), key=lambda x: -x[1])
        return [ch for ch, _ in sorted_channels[:10]]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _search_yt(self, query: str, max_results: int = 4) -> List[dict]:
        try:
            return self._youtube_api.search_videos(query, max_results) or []
        except Exception as e:
            self._logger.warning("Recommendation search failed for '%s': %s", query, e)
            return []

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    def _get_cached(self, key: str):
        with self._lock:
            entry = self._cache.get(key)
            if entry and (time.time() - entry[0]) < CACHE_TTL:
                return entry[1]
            return None

    def _set_cached(self, key: str, data: list):
        with self._lock:
            self._cache[key] = (time.time(), list(data))

    def invalidate_cache(self, key: Optional[str] = None):
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

    def _deduplicate(self, videos: List[dict]) -> List[dict]:
        seen: Set[str] = set()
        result = []
        for v in videos:
            vid = v.get("videoId", v.get("id", ""))
            if vid and vid not in seen:
                seen.add(vid)
                result.append(v)
        return result

    # ------------------------------------------------------------------
    # Orchestrated load with events
    # ------------------------------------------------------------------

    def load_section(self, section_name: str, **kwargs) -> List[dict]:
        if self._event_bus:
            self._event_bus.publish(RecommendationsLoadingEvent(section=section_name))

        try:
            loader = getattr(self, f"get_{section_name}", None)
            if not loader:
                raise ValueError(f"Unknown section: {section_name}")
            videos = loader(**kwargs)
            if self._event_bus:
                self._event_bus.publish(RecommendationsLoadedEvent(
                    section=section_name, videos=videos
                ))
            return videos
        except Exception as e:
            self._logger.error("Failed to load section '%s': %s", section_name, e)
            if self._event_bus:
                self._event_bus.publish(RecommendationsFailedEvent(
                    section=section_name, error=str(e)
                ))
            return []

    def reload(self, data_dir: str = ""):
        self.invalidate_cache()
