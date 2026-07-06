import logging
from typing import Optional

from core.events import SearchStartedEvent, SearchCompletedEvent, SearchFailedEvent
from youtube_api import YouTubeAPI


class SearchService:
    """Service for searching videos on YouTube"""

    def __init__(self, youtube_api=None, event_bus=None, logger=None):
        self.event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)
        self.youtube_api = youtube_api or YouTubeAPI(logger=self._logger)
    
    def search(self, query, max_results=20):
        """Search videos on YouTube using the YouTubeAPI service"""
        if self.event_bus:
            self.event_bus.publish(SearchStartedEvent(query=query))
        
        try:
            videos = self.youtube_api.search_videos(query, max_results)
            if self.event_bus:
                self.event_bus.publish(SearchCompletedEvent(videos=videos))
            return videos
        except Exception as e:
            if self.event_bus:
                self.event_bus.publish(SearchFailedEvent(error=str(e)))
            raise
    
    def search_page(self, query, page=0, page_size=20):
        """Search with pagination. Returns (videos, has_more)."""
        offset = page * page_size
        videos = self.youtube_api.search_videos(query, max_results=page_size, offset=offset)
        has_more = len(videos) >= page_size
        return videos, has_more
