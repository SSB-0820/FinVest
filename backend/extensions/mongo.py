from pymongo import MongoClient


mongo_client = None
mongo_db = None


def init_mongo(app):
    global mongo_client, mongo_db

    uri = app.config.get("MONGO_URI", "mongodb://127.0.0.1:27017/")
    db_name = app.config.get("MONGO_DB_NAME", "finvest_mongo")

    try:
        mongo_client = MongoClient(uri, serverSelectionTimeoutMS=1000)
        mongo_client.admin.command("ping")
        mongo_db = mongo_client[db_name]
    except Exception:
        mongo_client = None
        mongo_db = None


def get_collection(name):
    if mongo_db is None:
        return None
    return mongo_db[name]


def insert_document(collection_name, document):
    collection = get_collection(collection_name)
    if collection is None:
        return None
    return collection.insert_one(document)
