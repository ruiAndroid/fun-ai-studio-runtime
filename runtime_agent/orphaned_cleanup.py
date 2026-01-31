"""
部署态孤立数据清理 API

提供 HTTP 接口供主项目（91）调用，清理部署态的孤立数据：
1. 89 MongoDB 服务器上的孤立数据库（db_u{userId}_a{appId}）
"""

import re
import logging
from typing import Set
from fastapi import APIRouter, Depends
from pydantic import BaseModel

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

from runtime_agent import settings
from runtime_agent.auth import require_runtime_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["cleanup"])


class CleanupRequest(BaseModel):
    """清理请求"""
    existingAppIds: list[int]


class CleanupResponse(BaseModel):
    """清理响应"""
    cleanedDatabases: int
    message: str


@router.post("/cleanup-orphaned", dependencies=[Depends(require_runtime_token)])
def cleanup_orphaned_data(req: CleanupRequest) -> CleanupResponse:
    """
    清理孤立数据（部署态）
    
    由主项目（91）调用，传入数据库中存在的应用 ID 列表，
    清理 89 MongoDB 服务器上不在列表中的数据库。
    """
    try:
        existing_app_ids = set(str(app_id) for app_id in req.existingAppIds)
        log.info(f"开始清理部署态孤立数据，应用数量: {len(existing_app_ids)}")
        
        cleaned = clean_orphaned_mongo_databases(existing_app_ids)
        
        log.info(f"部署态孤立数据清理完成，清理了 {cleaned} 个数据库")
        return CleanupResponse(
            cleanedDatabases=cleaned,
            message="success"
        )
    except Exception as e:
        log.error(f"部署态孤立数据清理失败: {e}", exc_info=True)
        return CleanupResponse(
            cleanedDatabases=0,
            message=f"error: {str(e)}"
        )


def list_mongo_databases() -> list[str]:
    """
    列出 MongoDB 中的所有数据库
    """
    if not settings.RUNTIME_MONGO_HOST:
        log.error("RUNTIME_MONGO_HOST 未配置")
        return []
    
    if MongoClient is None:
        log.error("pymongo 未安装")
        return []
    
    try:
        # 构建连接字符串
        host = settings.RUNTIME_MONGO_HOST
        port = int(settings.RUNTIME_MONGO_PORT or 27017)
        username = settings.RUNTIME_MONGO_USERNAME
        password = settings.RUNTIME_MONGO_PASSWORD
        auth_source = settings.RUNTIME_MONGO_AUTH_SOURCE or "admin"
        
        if username and password:
            uri = f"mongodb://{username}:{password}@{host}:{port}/admin?authSource={auth_source}"
        else:
            uri = f"mongodb://{host}:{port}/admin"
        
        # 连接 MongoDB
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        
        # 列出所有数据库
        db_list = client.list_database_names()
        
        client.close()
        
        return db_list
    except Exception as e:
        log.error(f"列出 MongoDB 数据库失败: {e}")
        return []


def drop_database(db_name: str) -> bool:
    """
    删除指定的 MongoDB 数据库
    """
    if not settings.RUNTIME_MONGO_HOST:
        log.error("RUNTIME_MONGO_HOST 未配置")
        return False
    
    if MongoClient is None:
        log.error("pymongo 未安装")
        return False
    
    try:
        # 构建连接字符串
        host = settings.RUNTIME_MONGO_HOST
        port = int(settings.RUNTIME_MONGO_PORT or 27017)
        username = settings.RUNTIME_MONGO_USERNAME
        password = settings.RUNTIME_MONGO_PASSWORD
        auth_source = settings.RUNTIME_MONGO_AUTH_SOURCE or "admin"
        
        if username and password:
            uri = f"mongodb://{username}:{password}@{host}:{port}/{db_name}?authSource={auth_source}"
        else:
            uri = f"mongodb://{host}:{port}/{db_name}"
        
        # 连接 MongoDB
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        
        # 删除数据库
        client.drop_database(db_name)
        
        client.close()
        
        return True
    except Exception as e:
        log.error(f"删除 MongoDB 数据库失败: {db_name}, error: {e}")
        return False


def clean_orphaned_mongo_databases(existing_app_ids: Set[str]) -> int:
    """
    清理孤立的 MongoDB 数据库
    
    数据库命名格式：db_u{userId}_a{appId}
    """
    log.info("开始清理孤立的 MongoDB 数据库...")
    
    # 列出所有数据库
    databases = list_mongo_databases()
    log.info(f"MongoDB 中的数据库数量: {len(databases)}")
    
    # 数据库命名格式：db_u{userId}_a{appId}
    db_pattern = re.compile(r"^db_u\d+_a(\d+)$")
    
    cleaned = 0
    for db_name in databases:
        match = db_pattern.match(db_name)
        if match:
            app_id = match.group(1)
            if app_id not in existing_app_ids:
                log.info(f"清理孤立 MongoDB 数据库: appId={app_id}, dbName={db_name}")
                if drop_database(db_name):
                    cleaned += 1
                else:
                    log.warning(f"删除 MongoDB 数据库失败: {db_name}")
    
    log.info(f"清理 MongoDB 数据库完成: 已清理={cleaned}")
    return cleaned
