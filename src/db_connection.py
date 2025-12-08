"""
CockroachDB接続モジュール
"""

import os
import psycopg2
from contextlib import contextmanager


def get_database_url() -> str:
    """データベース接続URLを取得"""
    # 環境変数から取得（Streamlit Cloud用）
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    # ローカル開発用のデフォルト
    return "postgresql://nba_bcr2022_gmail_co:BAME23qA4SFzHMvrnIGvOQ@hot-sawfish-19099.j77.aws-us-east-1.cockroachlabs.cloud:26257/defaultdb?sslmode=require"


@contextmanager
def get_connection():
    """データベース接続を取得（コンテキストマネージャー）"""
    conn = psycopg2.connect(get_database_url())
    try:
        yield conn
    finally:
        conn.close()


def execute_query(query: str, params: tuple = None) -> list:
    """SQLクエリを実行して結果を返す"""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        return columns, rows
