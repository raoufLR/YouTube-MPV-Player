import json
import os
import uuid

import pytest

from models import Profile
from services.user_manager_service import (
    PROFILES_DIRNAME,
    UserManagerService,
    normalize_profile_name,
)


def _profile_dirs(base_dir):
    root = os.path.join(base_dir, PROFILES_DIRNAME)
    return sorted(
        entry.name for entry in os.scandir(root) if entry.is_dir()
    )


class TestProfileValidation:
    @pytest.mark.parametrize("name", [
        "Alice",
        "Default",
        "Work 2026",
        "Ünïcode",
        "A.B",
    ])
    def test_valid_names(self, name):
        assert normalize_profile_name(name) == name.strip()

    @pytest.mark.parametrize("name", [
        "",
        "   ",
        ".",
        "..",
        "../escape",
        r"..\escape",
        "a/b",
        r"a\b",
        "bad\x00name",
        "bad\nname",
        "trailing.",
        "CON",
        "nul.txt",
        "COM1",
        "LPT9",
        "x" * 65,
        None,
    ])
    def test_invalid_names(self, name):
        assert normalize_profile_name(name) is None


class TestUserManagerService:
    def test_default_profile_uses_opaque_directory(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)

        assert manager.profile_count() == 1
        assert manager.current_profile_name() == "Default"
        profile_dir = manager.current_profile_dir()
        assert os.path.dirname(profile_dir) == os.path.join(temp_dir, PROFILES_DIRNAME)
        assert os.path.basename(profile_dir) != "Default"
        assert os.path.isdir(os.path.join(profile_dir, "playlists"))
        assert os.path.isdir(os.path.join(profile_dir, "cache", "thumbnails"))
        assert manager.current_profile().name == "Default"

    def test_create_profile_rejects_traversal_and_duplicates(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)
        escape_name = f"escape-{uuid.uuid4().hex}"

        assert manager.create_profile(f"..\\{escape_name}") is None
        assert manager.create_profile("a/b") is None
        assert not os.path.exists(os.path.join(temp_dir, "..", escape_name))

        created = manager.create_profile("Alice")
        assert created is not None
        assert manager.create_profile("alice") is None
        assert manager.create_profile("  Alice  ") is None
        assert manager.has_profile("ALICE") is True

    def test_create_profile_writes_metadata_and_returns_copy(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)
        profile = manager.create_profile("Alice")

        path = os.path.join(manager.profile_dir("Alice"), "profile.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)

        assert data["id"] == os.path.basename(manager.profile_dir("Alice"))
        assert data["name"] == "Alice"
        assert manager.has_profile(profile.name)

    def test_rename_changes_metadata_not_directory(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)
        manager.create_profile("Alice")
        old_dir = manager.profile_dir("Alice")

        assert manager.rename_profile("Alice", "Alicia") is True
        new_dir = manager.profile_dir("Alicia")

        assert new_dir == old_dir
        assert not manager.has_profile("Alice")
        assert manager.profile_dir("Alicia") == old_dir
        assert manager.rename_profile("Alicia", "bad/name") is False
        assert manager.rename_profile("Alicia", "Alicia") is True

    def test_rename_current_profile_updates_current_name(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)
        manager.create_profile("Alice")
        manager.switch_profile("Alice")

        assert manager.rename_profile("Alice", "Alicia") is True
        assert manager.current_profile_name() == "Alicia"
        assert manager.current_profile().name == "Alicia"

    def test_delete_profile_and_default_protection(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)
        manager.create_profile("Alice")
        alice_dir = manager.profile_dir("Alice")
        manager.switch_profile("Alice")

        assert manager.delete_profile("Default") is False
        # The active profile cannot be removed from under its services.
        assert manager.delete_profile("Alice") is False
        assert manager.current_profile_name() == "Alice"
        assert manager.has_profile("Alice") is True

        manager.switch_profile("Default")
        assert manager.delete_profile("Alice") is True
        assert not os.path.exists(alice_dir)
        assert manager.current_profile_name() == "Default"
        assert manager.has_profile("Alice") is False
        assert manager.delete_profile("Alice") is False

    def test_duplicate_profile_gets_new_id_and_copies_data(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)
        manager.create_profile("Source")
        source_dir = manager.profile_dir("Source")
        with open(os.path.join(source_dir, "history.json"), "w", encoding="utf-8") as handle:
            json.dump([{"id": "v1"}], handle)

        duplicate = manager.duplicate_profile("Source", "Copy")

        assert duplicate is not None
        copy_dir = manager.profile_dir("Copy")
        assert copy_dir != source_dir
        assert os.path.basename(copy_dir) == duplicate.id
        assert os.path.isfile(os.path.join(copy_dir, "history.json"))
        assert manager.duplicate_profile("Source", "Copy") is None

    def test_legacy_profile_directory_is_migrated(self, temp_dir):
        legacy_dir = os.path.join(temp_dir, "Default")
        os.makedirs(os.path.join(legacy_dir, "playlists"))
        with open(os.path.join(legacy_dir, "profile.json"), "w", encoding="utf-8") as handle:
            json.dump(Profile(name="Default", id="legacyid").to_dict(), handle)
        with open(os.path.join(legacy_dir, "history.json"), "w", encoding="utf-8") as handle:
            json.dump([{"id": "v1"}], handle)

        manager = UserManagerService(base_dir=temp_dir)

        assert not os.path.exists(legacy_dir)
        profile_dir = manager.current_profile_dir()
        assert os.path.dirname(profile_dir) == os.path.join(temp_dir, PROFILES_DIRNAME)
        assert os.path.basename(profile_dir) != "Default"
        assert manager.current_profile_name() == "Default"
        assert manager.current_profile().id == os.path.basename(profile_dir)
        assert os.path.isfile(os.path.join(profile_dir, "history.json"))
        assert os.path.isdir(os.path.join(profile_dir, "playlists"))

    def test_two_existing_profiles_remain_distinct(self, temp_dir):
        manager = UserManagerService(base_dir=temp_dir)
        manager.create_profile("Alice")
        manager.create_profile("Bob")

        names = [profile.name for profile in manager.list_profiles()]
        dirs = {profile.name: manager.profile_dir(profile.name) for profile in manager.list_profiles()}

        assert names == ["Alice", "Bob", "Default"]
        assert len(set(dirs.values())) == 3
        assert all(os.path.basename(path) in _profile_dirs(temp_dir) for path in dirs.values())
