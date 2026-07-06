from typing import List, Optional


PROFILE_SERVICES = [
    "settings_service",
    "player_service",
    "stream_resolver_service",
    "search_service",
    "thumbnail_service",
    "user_profile_service",
    "history_service",
    "likes_service",
    "playlist_service",
    "recommendation_service",
]


class ServiceContainer:
    def __init__(self, event_bus=None):
        self._services = {}
        self._event_bus = event_bus

    def create_services(self):
        self._services = {}

        from services.logging_service import LoggingService
        from services.user_manager_service import UserManagerService
        from services.settings_service import SettingsService
        from services.player_service import PlayerService
        from services.stream_resolver_service import StreamResolverService
        from services.search_service import SearchService
        from services.thumbnail_cache_service import ThumbnailCacheService
        from services.user_profile_service import UserProfileService
        from services.history_service import HistoryService
        from services.likes_service import LikesService
        from services.playlist_service import PlaylistService
        from services.recommendation_service import RecommendationService

        logging_service = LoggingService()
        logger = logging_service.get_logger(__name__)
        logger.info("Starting service initialization")

        user_manager = UserManagerService(base_dir="User", event_bus=self._event_bus)
        profile_dir = user_manager.current_profile_dir()

        settings = SettingsService(event_bus=self._event_bus, data_dir=profile_dir)
        player = PlayerService(event_bus=self._event_bus, logger=logging_service.get_logger("services.player_service"))
        stream_resolver = StreamResolverService(event_bus=self._event_bus, logger=logging_service.get_logger("services.stream_resolver_service"))
        search = SearchService(event_bus=self._event_bus, logger=logging_service.get_logger("services.search_service"))
        thumbnail = ThumbnailCacheService(event_bus=self._event_bus, disk_dir=profile_dir + "/cache/thumbnails")
        user_profile = UserProfileService(event_bus=self._event_bus, data_dir=profile_dir)
        history = HistoryService(event_bus=self._event_bus, data_dir=profile_dir)
        likes = LikesService(event_bus=self._event_bus, data_dir=profile_dir)
        playlists = PlaylistService(event_bus=self._event_bus, data_dir=profile_dir)
        recommendations = RecommendationService(event_bus=self._event_bus, logger=logging_service.get_logger("services.recommendation_service"))

        self._services['logging_service'] = logging_service
        self._services['user_manager_service'] = user_manager
        self._services['settings_service'] = settings
        self._services['player_service'] = player
        self._services['stream_resolver_service'] = stream_resolver
        self._services['search_service'] = search
        self._services['thumbnail_service'] = thumbnail
        self._services['user_profile_service'] = user_profile
        self._services['history_service'] = history
        self._services['likes_service'] = likes
        self._services['playlist_service'] = playlists
        self._services['recommendation_service'] = recommendations

        logger.info("All services initialized")

    def get(self, service_type):
        service_keys = {
            'logging_service': 'logging_service',
            'user_manager_service': 'user_manager_service',
            'settings_service': 'settings_service',
            'player_service': 'player_service',
            'stream_resolver_service': 'stream_resolver_service',
            'search_service': 'search_service',
            'thumbnail_service': 'thumbnail_service',
            'user_profile_service': 'user_profile_service',
            'history_service': 'history_service',
            'likes_service': 'likes_service',
            'playlist_service': 'playlist_service',
            'recommendation_service': 'recommendation_service',
        }
        key = service_keys.get(service_type)
        if key and key in self._services:
            return self._services[key]
        return None

    def reload_profile_services(self, profile_dir: str):
        thumbnail_disk_dir = profile_dir + "/cache/thumbnails"
        for name in PROFILE_SERVICES:
            service = self._services.get(name)
            if not service:
                continue
            if name == "settings_service":
                service.reload(data_dir=profile_dir)
            elif name == "history_service":
                service.reload(data_dir=profile_dir)
            elif name == "likes_service":
                service.reload(data_dir=profile_dir)
            elif name == "playlist_service":
                service.reload(data_dir=profile_dir)
            elif name == "user_profile_service":
                service.reload(data_dir=profile_dir)
            elif name == "thumbnail_service":
                service.reload(disk_dir=thumbnail_disk_dir)
            elif name == "player_service":
                pass
            elif name == "stream_resolver_service":
                pass
            elif name == "search_service":
                pass
            elif name == "recommendation_service":
                service.reload()

    def shutdown(self):
        for name, service in self._services.items():
            if hasattr(service, 'shutdown'):
                try:
                    service.shutdown()
                except Exception:
                    pass
        self._services.clear()

    @property
    def logging_service(self):
        return self.get('logging_service')

    @property
    def user_manager_service(self):
        return self.get('user_manager_service')

    @property
    def settings_service(self):
        return self.get('settings_service')

    @property
    def player_service(self):
        return self.get('player_service')

    @property
    def stream_resolver_service(self):
        return self.get('stream_resolver_service')

    @property
    def search_service(self):
        return self.get('search_service')

    @property
    def thumbnail_service(self):
        return self.get('thumbnail_service')

    @property
    def user_profile_service(self):
        return self.get('user_profile_service')

    @property
    def history_service(self):
        return self.get('history_service')

    @property
    def likes_service(self):
        return self.get('likes_service')

    @property
    def playlist_service(self):
        return self.get('playlist_service')

    @property
    def recommendation_service(self):
        return self.get('recommendation_service')
