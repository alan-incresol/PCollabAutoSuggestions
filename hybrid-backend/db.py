from pymongo import MongoClient

from config import get_settings

_client: MongoClient | None = None
_client_uri: str | None = None


def get_client() -> MongoClient:
    global _client, _client_uri
    uri = get_settings().mongodb_uri
    if _client is None or _client_uri != uri:
        if _client is not None:
            _client.close()
        _client = MongoClient(uri)
        _client_uri = uri
    return _client


def get_collection(collection_name: str):
    return get_client()[get_settings().mongodb_db][collection_name]
