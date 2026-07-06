import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Profile:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = "Default"
    avatar: str = ""
    created_at: float = field(default_factory=time.time)
    last_opened: float = field(default_factory=time.time)
    theme: str = "dark"
    language: str = "en"

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
    def from_dict(cls, data: dict) -> "Profile":
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
