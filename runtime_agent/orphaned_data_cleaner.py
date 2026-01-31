"""
部署态孤立数据清理（定时任务）

清理内容：
1. 89 MongoDB 服务器上的孤立数据库（db_u{userId}_a{appId}）

执行时间：每天凌晨 3:00（通过 cron 或 systemd timer 调度）

使用方法：
1. 通过 cron 调度：
   0 3 * * * cd /opt/fun-ai-studio/fun-ai-studio-runtime && /usr/bin/python3 -m runtime_agent.orphaned_data_cleaner

2. 通过 systemd timer 调度：
   创建 /etc/systemd/system/funai-runtime-cleanup.service 和 .timer

3. 手动执行：
   cd /opt/fun-ai-studio/fun-ai-studio-runtime
   python3 -m runtime_agent.orphaned_data_cleaner
"""

import re
import sys
import logging
from typing import Set
import requests

try:
    from pymongo import MongoClient
except ImportError:
    print("Error: pymongo not installed. Please install: pip install pymongo")
    sys.exit(1)

from runtime_agent import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


def load_existing_app_ids() -> Set[str]:
    """
    从 deploy 服务（100 服务器）加载所有存在的应用 ID
    
    注意：需要配置 DEPLOY_BASE_URL 环境变量
    """
    if not settings.DEPLOY_BASE_URL:
        log.error("DEPLOY_BASE_URL 未配置，无法加载应用列表")
        return set()
    
    try:
        # 调用 deploy 服务的 API 获取所有应用 ID
        # 注意：这个 API 需要在 deploy 服务中实现
        url = f"{settings.DEPLOY_BASE_URL.rstrip('/')}/api/fun-ai/internal/apps/ids"
        
        # 使用 runtime-agent token 进行认证
        headers = {}
        if settings.RUNTIME_AGENT_TOKEN:
            headers["X-Runtime-Token"] = settings.RUNTIME_AGENT_TOKEN
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            app_ids = set(str(app_id) for app_id in data.get("appIds", []))
            log.info(f"从 deploy 服务加载了 {len(app_ids)} 个应用 ID")
            return app_ids
        else:
            log.error(f"加载应用列表失败: HTTP {response.status_code}")
            return set()
    except Exception as e:
        log.error(f"加载应用列表失败: {e}")
        return set()


def list_mongo_databases() -> list[str]:
    """
    列出 MongoDB 中的所有数据库
    """
    if not settings.RUNTIME_MONGO_HOST:
        log.error("RUNTIME_MONGO_HOST 未配置")
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


def main():
    """
    主函数：执行孤立数据清理
    """
    log.info("=== 开始清理部署态孤立数据 ===")
    
    try:
        # 1. 加载所有存在的应用 ID
        existing_app_ids = load_existing_app_ids()
        
        if not existing_app_ids:
            log.warning("未能加载应用列表，跳过清理")
            return
        
        log.info(f"数据库中存在的应用数量: {len(existing_app_ids)}")
        
        # 2. 清理孤立的 MongoDB 数据库
        cleaned = clean_orphaned_mongo_databases(existing_app_ids)
        
        log.info(f"=== 部署态孤立数据清理完成，清理了 {cleaned} 个数据库 ===")
    except Exception as e:
        log.error(f"孤立数据清理失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
