"""
Runtime Mongo Explorer (Read-Only)

Provides MongoDB query APIs for deployed apps.
- Direct connection from 102 server to 89 MongoDB server using pymongo
- Read-only operations: list collections, find, findOne
- Write operations: insert, update, delete (for admin/debugging)
"""

import re
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson import ObjectId, json_util
import json

from . import settings

router = APIRouter(prefix="/api/fun-ai/deploy/mongo", tags=["Deploy Mongo Explorer"])

# Safe collection name pattern
SAFE_COLLECTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")


# ============================================================================
# Request/Response Models
# ============================================================================

class FindRequest(BaseModel):
    collection: str
    filter: Optional[str] = "{}"
    projection: Optional[str] = None
    sort: Optional[str] = None
    limit: Optional[int] = Field(default=50, ge=1, le=200)
    skip: Optional[int] = Field(default=0, ge=0, le=10000)


class InsertOneRequest(BaseModel):
    collection: str
    doc: str  # JSON string


class UpdateByIdRequest(BaseModel):
    collection: str
    id: str
    update: str  # JSON string (MongoDB update operators like {$set: {...}})
    upsert: Optional[bool] = False


class DeleteByIdRequest(BaseModel):
    collection: str
    id: str


class CreateCollectionRequest(BaseModel):
    collection: str
    strict: Optional[bool] = False
    fields: Optional[str] = None  # JSON string for validator schema


# ============================================================================
# Helper Functions
# ============================================================================

def _get_db_name(user_id: str, app_id: str) -> str:
    """Generate database name using template."""
    raw = (settings.RUNTIME_MONGO_DB_TEMPLATE or "db_u{userId}_a{appId}").format(
        userId=user_id, appId=app_id
    )
    # Replace invalid characters
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", (raw or "").strip())
    if not name or set(name) == {"_"}:
        name = f"db_u{user_id}_a{app_id}"
        name = re.sub(r"[^a-zA-Z0-9_]+", "_", name)
    return name[:63]  # MongoDB DB name limit


def _get_mongo_client(db_name: str) -> MongoClient:
    """Create MongoDB client for the specified database."""
    host = (settings.RUNTIME_MONGO_HOST or "").strip()
    port = int(settings.RUNTIME_MONGO_PORT or 27017)
    
    if not host:
        raise HTTPException(status_code=500, detail="RUNTIME_MONGO_HOST not configured")
    
    user = (settings.RUNTIME_MONGO_USERNAME or "").strip()
    pwd = (settings.RUNTIME_MONGO_PASSWORD or "").strip()
    auth_source = (settings.RUNTIME_MONGO_AUTH_SOURCE or "admin").strip()
    
    if user and pwd:
        uri = f"mongodb://{user}:{pwd}@{host}:{port}/{db_name}?authSource={auth_source}"
    else:
        uri = f"mongodb://{host}:{port}/{db_name}"
    
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Test connection
        client.server_info()
        return client
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"MongoDB connection failed: {str(e)}")


def _assert_collection_name(collection: str):
    """Validate collection name for security."""
    if not collection or not collection.strip():
        raise HTTPException(status_code=400, detail="collection name cannot be empty")
    
    c = collection.strip()
    if not SAFE_COLLECTION_RE.match(c):
        raise HTTPException(
            status_code=400,
            detail="Invalid collection name (only alphanumeric, _, -, . allowed, max 120 chars)"
        )
    
    if c.startswith("system."):
        raise HTTPException(status_code=403, detail="Access to system.* collections is forbidden")


def _parse_json_safe(json_str: Optional[str], default: Any = None) -> Any:
    """Parse JSON string safely."""
    if not json_str or not json_str.strip():
        return default
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")


def _parse_object_id(id_str: str) -> Any:
    """Try to parse as ObjectId, fallback to string."""
    try:
        return ObjectId(id_str)
    except Exception:
        return id_str


def _serialize_mongo_doc(doc: Any) -> Any:
    """Serialize MongoDB document to JSON-compatible format."""
    return json.loads(json_util.dumps(doc))


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/collections")
async def list_collections(
    userId: str = Query(..., description="User ID"),
    appId: str = Query(..., description="App ID")
):
    """List all collections in the database."""
    try:
        db_name = _get_db_name(userId, appId)
        client = _get_mongo_client(db_name)
        db = client[db_name]
        
        collections = sorted(db.list_collection_names())
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "userId": userId,
                "appId": appId,
                "dbName": db_name,
                "collections": collections
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List collections failed: {str(e)}")


@router.post("/find")
async def find_documents(
    userId: str = Query(..., description="User ID"),
    appId: str = Query(..., description="App ID"),
    body: FindRequest = Body(...)
):
    """Find documents in a collection."""
    try:
        _assert_collection_name(body.collection)
        
        db_name = _get_db_name(userId, appId)
        client = _get_mongo_client(db_name)
        db = client[db_name]
        collection = db[body.collection]
        
        # Parse query parameters
        filter_doc = _parse_json_safe(body.filter, {})
        projection_doc = _parse_json_safe(body.projection, None)
        sort_doc = _parse_json_safe(body.sort, None)
        
        # Build query
        cursor = collection.find(filter_doc, projection_doc).max_time_ms(3000)
        
        if sort_doc:
            cursor = cursor.sort(list(sort_doc.items()))
        
        cursor = cursor.skip(body.skip).limit(body.limit)
        
        # Execute query
        items = list(cursor)
        items_serialized = [_serialize_mongo_doc(item) for item in items]
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "userId": userId,
                "appId": appId,
                "dbName": db_name,
                "collection": body.collection,
                "limit": body.limit,
                "skip": body.skip,
                "returned": len(items_serialized),
                "items": items_serialized
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Find failed: {str(e)}")


@router.get("/doc")
async def find_one_by_id(
    userId: str = Query(..., description="User ID"),
    appId: str = Query(..., description="App ID"),
    collection: str = Query(..., description="Collection name"),
    id: str = Query(..., description="Document _id")
):
    """Find a single document by _id."""
    try:
        _assert_collection_name(collection)
        
        db_name = _get_db_name(userId, appId)
        client = _get_mongo_client(db_name)
        db = client[db_name]
        coll = db[collection]
        
        _id = _parse_object_id(id)
        doc = coll.find_one({"_id": _id}, max_time_ms=3000)
        
        doc_serialized = _serialize_mongo_doc(doc) if doc else None
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "userId": userId,
                "appId": appId,
                "dbName": db_name,
                "collection": collection,
                "id": id,
                "doc": doc_serialized
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Find one failed: {str(e)}")


@router.post("/insert-one")
async def insert_one(
    userId: str = Query(..., description="User ID"),
    appId: str = Query(..., description="App ID"),
    body: InsertOneRequest = Body(...)
):
    """Insert a new document."""
    try:
        _assert_collection_name(body.collection)
        
        db_name = _get_db_name(userId, appId)
        client = _get_mongo_client(db_name)
        db = client[db_name]
        collection = db[body.collection]
        
        doc = _parse_json_safe(body.doc, {})
        if not doc:
            raise HTTPException(status_code=400, detail="Document cannot be empty")
        
        result = collection.insert_one(doc)
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "userId": userId,
                "appId": appId,
                "dbName": db_name,
                "collection": body.collection,
                "insertedId": str(result.inserted_id)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert failed: {str(e)}")


@router.post("/update-by-id")
async def update_by_id(
    userId: str = Query(..., description="User ID"),
    appId: str = Query(..., description="App ID"),
    body: UpdateByIdRequest = Body(...)
):
    """Update a document by _id."""
    try:
        _assert_collection_name(body.collection)
        
        db_name = _get_db_name(userId, appId)
        client = _get_mongo_client(db_name)
        db = client[db_name]
        collection = db[body.collection]
        
        _id = _parse_object_id(body.id)
        update_doc = _parse_json_safe(body.update, {})
        
        if not update_doc:
            raise HTTPException(status_code=400, detail="Update document cannot be empty")
        
        result = collection.update_one(
            {"_id": _id},
            update_doc,
            upsert=body.upsert
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "userId": userId,
                "appId": appId,
                "dbName": db_name,
                "collection": body.collection,
                "matchedCount": result.matched_count,
                "modifiedCount": result.modified_count,
                "upsertedId": str(result.upserted_id) if result.upserted_id else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")


@router.post("/delete-by-id")
async def delete_by_id(
    userId: str = Query(..., description="User ID"),
    appId: str = Query(..., description="App ID"),
    body: DeleteByIdRequest = Body(...)
):
    """Delete a document by _id."""
    try:
        _assert_collection_name(body.collection)
        
        db_name = _get_db_name(userId, appId)
        client = _get_mongo_client(db_name)
        db = client[db_name]
        collection = db[body.collection]
        
        _id = _parse_object_id(body.id)
        result = collection.delete_one({"_id": _id})
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "userId": userId,
                "appId": appId,
                "dbName": db_name,
                "collection": body.collection,
                "deletedCount": result.deleted_count
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.post("/create-collection")
async def create_collection(
    userId: str = Query(..., description="User ID"),
    appId: str = Query(..., description="App ID"),
    body: CreateCollectionRequest = Body(...)
):
    """Create a new collection (optionally with schema validation)."""
    try:
        _assert_collection_name(body.collection)
        
        db_name = _get_db_name(userId, appId)
        client = _get_mongo_client(db_name)
        db = client[db_name]
        
        # Check if collection already exists
        if body.collection in db.list_collection_names():
            raise HTTPException(status_code=400, detail=f"Collection '{body.collection}' already exists")
        
        # Parse validator schema if provided
        create_options = {}
        if body.strict and body.fields:
            fields_schema = _parse_json_safe(body.fields, {})
            if fields_schema:
                create_options["validator"] = {"$jsonSchema": fields_schema}
                create_options["validationLevel"] = "strict"
        
        db.create_collection(body.collection, **create_options)
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "userId": userId,
                "appId": appId,
                "dbName": db_name,
                "collection": body.collection,
                "created": True
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Create collection failed: {str(e)}")
