import logging

_logger = logging.getLogger(__name__)

PROFILE_SERVICES = [
    "settings_service",
    "analytics_service",
    "player_service",
    "stream_resolver_service",
    "playback_service",
    "search_service",
    "thumbnail_service",
    "user_profile_service",
    "history_service",
    "likes_service",
    "playlist_service",
    "recommendation_service",
    "data_import_service",
]


class ServiceContainer:
    def __init__(self, event_bus=None):
        self._services = {}
        self._event_bus = event_bus

    def create_services(self):
        self._services = {}

        from player import MpvPlayer
        from services.analytics_service import AnalyticsService
        from services.data_import_service import DataImportService
        from services.history_service import HistoryService
        from services.likes_service import LikesService
        from services.logging_service import LoggingService
        from services.playback_service import PlaybackService
        from services.player_service import PlayerService
        from services.playlist_service import PlaylistService
        from services.recommendation_service import RecommendationService
        from services.search_service import SearchService
        from services.settings_service import SettingsService
        from services.stream_resolver_service import StreamResolverService
        from services.thumbnail_cache_service import ThumbnailCacheService
        from services.user_manager_service import UserManagerService
        from services.user_profile_service import UserProfileService
        from services.ytdlp_update_service import YtDlpUpdateService
        from youtube_api import YouTubeAPI

        logging_service = LoggingService()
        logger = logging_service.get_logger(__name__)
        logger.info("Starting service initialization")

        user_manager = UserManagerService(base_dir="User", event_bus=self._event_bus)
        profile_dir = user_manager.current_profile_dir()

        settings = SettingsService(event_bus=self._event_bus, data_dir=profile_dir)
        analytics = AnalyticsService(event_bus=self._event_bus, data_dir=profile_dir)
        update = YtDlpUpdateService(
            event_bus=self._event_bus,
            settings_service=settings,
            data_dir="User",
            logger=logging_service.get_logger("services.ytdlp_update"),
        )
        youtube_api = YouTubeAPI(
            logger=logging_service.get_logger("youtube_api"),
            preferred_update_path=update.binary_path,
        )
        mpv_player = MpvPlayer(logger=logging_service.get_logger("services.player_service"))
        player = PlayerService(mpv_player=mpv_player, event_bus=self._event_bus, logger=logging_service.get_logger("services.player_service"))
        stream_resolver = StreamResolverService(
            event_bus=self._event_bus,
            logger=logging_service.get_logger("services.stream_resolver_service"),
            youtube_api=youtube_api,
        )
        search = SearchService(
            youtube_api=youtube_api,
            event_bus=self._event_bus,
            logger=logging_service.get_logger("services.search_service"),
        )
        thumbnail = ThumbnailCacheService(event_bus=self._event_bus, disk_dir=profile_dir + "/cache/thumbnails")
        user_profile = UserProfileService(event_bus=self._event_bus, data_dir=profile_dir)
        history = HistoryService(event_bus=self._event_bus, data_dir=profile_dir)
        likes = LikesService(event_bus=self._event_bus, data_dir=profile_dir)
        playlists = PlaylistService(event_bus=self._event_bus, data_dir=profile_dir)
        recommendations = RecommendationService(event_bus=self._event_bus, logger=logging_service.get_logger("services.recommendation_service"))
        playback = PlaybackService(
            stream_resolver,
            player,
            event_bus=self._event_bus,
            logger=logging_service.get_logger("services.playback_service"),
        )
        data_import = DataImportService(
            event_bus=self._event_bus,
            history_service=history,
            likes_service=likes,
            playlist_service=playlists,
            data_dir=profile_dir,
        )

        player.set_volume(int(settings.get("volume", 80)))
        update.check_in_background()

        self._services['logging_service'] = logging_service
        self._services['user_manager_service'] = user_manager
        self._services['settings_service'] = settings
        self._services['analytics_service'] = analytics
        self._services['player_service'] = player
        self._services['stream_resolver_service'] = stream_resolver
        self._services['search_service'] = search
        self._services['thumbnail_service'] = thumbnail
        self._services['user_profile_service'] = user_profile
        self._services['history_service'] = history
        self._services['likes_service'] = likes
        self._services['playlist_service'] = playlists
        self._services['recommendation_service'] = recommendations
        self._services['playback_service'] = playback
        self._services['update_service'] = update
        self._services['data_import_service'] = data_import

        logger.info("All services initialized")

    def get(self, service_type):
        service_keys = {
            'logging_service': 'logging_service',
            'user_manager_service': 'user_manager_service',
            'settings_service': 'settings_service',
            'analytics_service': 'analytics_service',
            'player_service': 'player_service',
            'stream_resolver_service': 'stream_resolver_service',
            'search_service': 'search_service',
            'thumbnail_service': 'thumbnail_service',
            'user_profile_service': 'user_profile_service',
            'history_service': 'history_service',
            'likes_service': 'likes_service',
            'playlist_service': 'playlist_service',
            'recommendation_service': 'recommendation_service',
            'playback_service': 'playback_service',
            'update_service': 'update_service',
            'data_import_service': 'data_import_service',
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
                player = self._services.get("player_service")
                if player is not None:
                    player.set_volume(int(service.get("volume", 80)))
            elif name == "analytics_service" or name == "history_service" or name == "likes_service" or name == "playlist_service" or name == "user_profile_service":
                service.reload(data_dir=profile_dir)
            elif name == "thumbnail_service":
                service.reload(disk_dir=thumbnail_disk_dir)
            elif name == "player_service" or name == "stream_resolver_service":
                pass
            elif name == "playback_service":
                service.stop()
            elif name == "search_service":
                pass
            elif name == "recommendation_service":
                service.reload()
            elif name == "data_import_service":
                service._data_dir = profile_dir

    def shutdown(self):
        """Shut services down in reverse creation order, idempotently."""
        services = list(self._services.items())
        self._services.clear()
        for name, service in reversed(services):
            shutdown = getattr(service, "shutdown", None)
            if not callable(shutdown):
                continue
            try:
                shutdown()
            except Exception:
                _logger.exception("Service '%s' failed during shutdown", name)

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
    def analytics_service(self):
        return self.get('analytics_service')

    @property
    def player_service(self):
        return self.get('player_service')

    @property
    def stream_resolver_service(self):
        return self.get('stream_resolver_service')

    @property
    def playback_service(self):
        return self.get('playback_service')

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

    @property
    def update_service(self):
        return self.get('update_service')

    @property
    def data_import_service(self):
        return self.get('data_import_service')
