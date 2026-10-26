from pymongo import MongoClient

from config import settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.mongodb_uri)
    return _client


def get_collection(collection_name: str | None = None):
    name = collection_name or settings.collection_name
    return get_client()[settings.mongodb_db][name]
