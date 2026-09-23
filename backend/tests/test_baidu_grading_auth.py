import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app import database
from app.grading import baidu_grading


def test_concurrent_db_token_load_waits_for_first_reader(monkeypatch):
    token = "database-baidu-access-token"
    query_count = 0
    query_count_lock = threading.Lock()

    class FakeQuery:
        def first(self):
            nonlocal query_count
            with query_count_lock:
                query_count += 1
            time.sleep(0.05)
            return type("SettingsRow", (), {"baidu_access_token": token})()

    class FakeSession:
        def query(self, _model):
            return FakeQuery()

        def close(self):
            return None

    monkeypatch.setattr(database, "SessionLocal", FakeSession)

    with baidu_grading._token_lock:
        old_cache = dict(baidu_grading._db_token_cache)
        baidu_grading._db_token_cache["access_token"] = None
        baidu_grading._db_token_cache["checked_at"] = 0.0

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _i: baidu_grading._get_db_access_token(), range(8)))
    finally:
        with baidu_grading._token_lock:
            baidu_grading._db_token_cache.clear()
            baidu_grading._db_token_cache.update(old_cache)

    assert results == [token] * 8
    assert query_count == 1


def test_force_refresh_uses_database_credentials_and_persists_token(monkeypatch):
    old_token = "expired-token"
    new_token = "renewed-token"
    persisted = []

    monkeypatch.setattr(
        baidu_grading,
        "_get_db_baidu_credentials",
        lambda: (old_token, "baidu-api-key", "baidu-secret-key"),
    )
    monkeypatch.setattr(
        baidu_grading,
        "request_baidu_access_token",
        lambda _api_key, _secret_key: (new_token, 3600.0),
    )
    monkeypatch.setattr(baidu_grading, "_persist_db_access_token", persisted.append)

    with baidu_grading._token_lock:
        old_cache = dict(baidu_grading._token_cache)
        baidu_grading._token_cache.update(
            {
                "access_token": old_token,
                "expires_at": time.time() + 3600,
                "last_db_token": old_token,
                "db_token_invalid": False,
            }
        )

    try:
        token = baidu_grading._get_access_token(
            force_refresh=True,
            invalid_token=old_token,
        )
    finally:
        with baidu_grading._token_lock:
            baidu_grading._token_cache.clear()
            baidu_grading._token_cache.update(old_cache)

    assert token == new_token
    assert persisted == [new_token]


def test_concurrent_expired_token_refreshes_once(monkeypatch):
    old_token = "expired-token"
    new_token = "renewed-token"
    state = {"token": old_token, "refresh_count": 0}
    state_lock = threading.Lock()

    def get_credentials():
        with state_lock:
            return state["token"], "baidu-api-key", "baidu-secret-key"

    def request_token(_api_key, _secret_key):
        with state_lock:
            state["refresh_count"] += 1
        time.sleep(0.05)
        return new_token, 3600.0

    def persist_token(token):
        with state_lock:
            state["token"] = token

    monkeypatch.setattr(baidu_grading, "_get_db_baidu_credentials", get_credentials)
    monkeypatch.setattr(baidu_grading, "request_baidu_access_token", request_token)
    monkeypatch.setattr(baidu_grading, "_persist_db_access_token", persist_token)

    with baidu_grading._token_lock:
        old_cache = dict(baidu_grading._token_cache)
        baidu_grading._token_cache.update(
            {
                "access_token": old_token,
                "expires_at": time.time() + 3600,
                "last_db_token": old_token,
                "db_token_invalid": False,
            }
        )

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda _i: baidu_grading._get_access_token(
                        force_refresh=True,
                        invalid_token=old_token,
                    ),
                    range(8),
                )
            )
    finally:
        with baidu_grading._token_lock:
            baidu_grading._token_cache.clear()
            baidu_grading._token_cache.update(old_cache)

    assert results == [new_token] * 8
    assert state["refresh_count"] == 1
