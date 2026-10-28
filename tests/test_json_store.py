import json
import os
import threading

import pytest

from core.json_store import JsonStore


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class TestJsonStore:
    def test_roundtrip_creates_parent_directory(self, temp_dir):
        path = os.path.join(temp_dir, "nested", "data.json")
        store = JsonStore(path)

        store.save({"name": "café", "values": [1, 2, 3]})

        assert store.exists
        assert store.load(dict) == {"name": "café", "values": [1, 2, 3]}
        assert not any(name.endswith(".tmp") for name in os.listdir(os.path.dirname(path)))

    def test_missing_file_returns_default(self, temp_dir):
        store = JsonStore(os.path.join(temp_dir, "missing.json"))

        assert store.load(list) == []
        assert store.load(lambda: {"fallback": True}) == {"fallback": True}

    def test_corrupt_primary_is_quarantined(self, temp_dir):
        path = os.path.join(temp_dir, "data.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")

        store = JsonStore(path)
        assert store.load(dict) == {}

        quarantined = [
            name for name in os.listdir(temp_dir)
            if name.startswith("data.json.corrupt-")
        ]
        assert len(quarantined) == 1
        assert not os.path.exists(path)

    def test_recovers_from_backup_and_restores_primary(self, temp_dir):
        path = os.path.join(temp_dir, "data.json")
        store = JsonStore(path)
        store.save({"version": 1})
        store.save({"version": 2})
        assert _read_json(store.backup_path) == {"version": 1}

        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{broken")

        assert store.load(dict) == {"version": 1}
        assert _read_json(path) == {"version": 1}
        assert any(
            name.startswith("data.json.corrupt-")
            for name in os.listdir(temp_dir)
        )

    def test_failed_replace_leaves_original_file_intact(self, temp_dir, monkeypatch):
        path = os.path.join(temp_dir, "data.json")
        store = JsonStore(path)
        store.save({"stable": True})
        original = _read_bytes(path)

        def fail_replace(src, dst):
            raise OSError("replace failed")

        monkeypatch.setattr("core.json_store.os.replace", fail_replace)

        with pytest.raises(OSError):
            store.save({"stable": False})

        assert _read_bytes(path) == original
        assert not any(
            name.endswith(".tmp") for name in os.listdir(temp_dir)
        )

    def test_non_serializable_data_does_not_touch_file(self, temp_dir):
        path = os.path.join(temp_dir, "data.json")
        store = JsonStore(path)
        store.save({"value": 1})

        with pytest.raises(TypeError):
            store.save({"value": object()})

        assert store.load(dict) == {"value": 1}

    def test_per_path_locks_are_shared(self, temp_dir):
        path = os.path.join(temp_dir, "data.json")
        other = os.path.join(temp_dir, "other.json")

        assert JsonStore(path)._lock is JsonStore(path)._lock
        assert JsonStore(path)._lock is not JsonStore(other)._lock

    def test_concurrent_writers_never_produce_invalid_json(self, temp_dir):
        path = os.path.join(temp_dir, "data.json")
        errors = []
        start = threading.Barrier(8)

        def writer(index):
            try:
                store = JsonStore(path)
                start.wait(timeout=5)
                for value in range(20):
                    store.save({"writer": index, "value": value})
                    store.load(dict)
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        assert not errors
        assert all(not thread.is_alive() for thread in threads)
        data = JsonStore(path).load(dict)
        assert set(data) == {"writer", "value"}

    def test_delete_removes_primary_and_backup(self, temp_dir):
        path = os.path.join(temp_dir, "data.json")
        store = JsonStore(path)
        store.save([1])
        store.save([2])

        store.delete()

        assert not os.path.exists(path)
        assert not os.path.exists(store.backup_path)
