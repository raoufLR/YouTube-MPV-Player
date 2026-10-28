import time
import uuid
from dataclasses import dataclass, field

from core.security import sanitize_local_path
from core.validation import coerce_id, coerce_text, coerce_timestamp

MAX_PROFILE_NAME_LENGTH = 64
MAX_AVATAR_PATH = 2048
MAX_THEME = 32
MAX_LANGUAGE = 16


@dataclass
class Profile:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = "Default"
    avatar: str = ""
    created_at: float = field(default_factory=time.time)
    last_opened: float = field(default_factory=time.time)
    theme: str = "dark"
    language: str = "en"

    def __post_init__(self):
        self.id = coerce_id(self.id, uuid.uuid4().hex[:12], max_length=128)
        self.name = (
            coerce_text(self.name, "Default", max_length=MAX_PROFILE_NAME_LENGTH)
            or "Default"
        )
        self.avatar = sanitize_local_path(
            coerce_text(self.avatar, "", max_length=MAX_AVATAR_PATH), ""
        )
        self.created_at = coerce_timestamp(self.created_at, 0.0)
        self.last_opened = coerce_timestamp(self.last_opened, 0.0)
        self.theme = coerce_text(self.theme, "dark", max_length=MAX_THEME) or "dark"
        self.language = (
            coerce_text(self.language, "en", max_length=MAX_LANGUAGE) or "en"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "avatar": self.avatar,
            "created_at": self.created_at,
            "last_opened": self.last_opened,
            "theme": self.theme,
            "language": self.language,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Profile:
        if not isinstance(data, dict):
            return cls()
        return cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            name=data.get("name", "Default"),
            avatar=data.get("avatar", ""),
            created_at=data.get("created_at", 0.0),
            last_opened=data.get("last_opened", 0.0),
            theme=data.get("theme", "dark"),
            language=data.get("language", "en"),
        )

    def touch(self):
        self.last_opened = time.time()
