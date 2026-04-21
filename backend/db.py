from pymongo import MongoClient

from config import settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.mongodb_uri)
    return _client


def get_collection():
    return get_client()[settings.mongodb_db][settings.collection_name]
