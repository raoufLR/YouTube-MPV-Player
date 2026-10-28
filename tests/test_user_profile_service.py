import json
import os

from models import UserProfile
from services.user_manager_service import UserManagerService
from services.user_profile_service import PROFILE_FILENAME, UserProfileService


class TestUserProfileService:
    def test_uses_separate_file_and_never_clobbers_profile_registry(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)
        profile_dir = manager.current_profile_dir()

        service = UserProfileService(data_dir=profile_dir)
        service.update_profile(username="alice", display_name="Alice")

        registry_path = os.path.join(profile_dir, "profile.json")
        user_path = os.path.join(profile_dir, PROFILE_FILENAME)

        with open(registry_path, encoding="utf-8") as handle:
            registry = json.load(handle)
        with open(user_path, encoding="utf-8") as handle:
            user = json.load(handle)

        assert registry["name"] == "Default"
        assert registry["id"] == os.path.basename(profile_dir)
        assert user["username"] == "alice"
        assert user["display_name"] == "Alice"

    def test_migrates_user_fields_from_legacy_profile_file(self, temp_dir):
        with open(os.path.join(temp_dir, "profile.json"), "w", encoding="utf-8") as handle:
            json.dump({
                "user_id": "legacy",
                "username": "legacy-user",
                "display_name": "Legacy User",
                "avatar_path": "avatar.png",
            }, handle)

        service = UserProfileService(data_dir=temp_dir)

        profile = service.get_profile()
        assert profile.user_id == "legacy"
        assert profile.username == "legacy-user"
        assert os.path.isfile(os.path.join(temp_dir, PROFILE_FILENAME))

    def test_reload_switches_files_without_touching_previous_file(self, temp_dir):
        first = os.path.join(temp_dir, "first")
        second = os.path.join(temp_dir, "second")
        os.makedirs(first)
        os.makedirs(second)

        service = UserProfileService(data_dir=first)
        service.update_profile(username="first-user")
        service.reload(second)
        service.update_profile(username="second-user")

        assert service.get_profile().username == "second-user"
        with open(os.path.join(first, PROFILE_FILENAME), encoding="utf-8") as handle:
            assert json.load(handle)["username"] == "first-user"

    def test_reset_writes_defaults(self, temp_dir):
        service = UserProfileService(data_dir=temp_dir)
        service.update_profile(username="alice")
        service.reset()

        assert service.get_profile().username == UserProfile().username
