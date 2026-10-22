"""
统一数据库连接管理（SQLite）

- 数据库文件路径来自 config.DATABASE_PATH（backend/data/learning_platform.db）
- 测试可临时替换路径：database.init_db() 会把 config.DATABASE_PATH 同步到本模块
"""
import json
import sqlite3
from config import DATABASE_PATH


def get_db():
    """
    获取数据库连接。

    返回原生 sqlite3.Connection（row_factory=Row），开启外键约束。
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def json_load(val):
    """兼容 TEXT 存储：dict/list 直接返回，字符串则 json.loads"""
    if val is None or val == '':
        return None
    if isinstance(val, (dict, list)):
        return val
    return json.loads(val)
