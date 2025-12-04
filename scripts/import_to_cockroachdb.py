"""
CockroachDBにCSVデータをインポートするスクリプト
"""

import os
import sys
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from pathlib import Path

# 接続情報
DATABASE_URL = "postgresql://nba_bcr2022_gmail_co:BAME23qA4SFzHMvrnIGvOQ@hot-sawfish-19099.j77.aws-us-east-1.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full&sslrootcert=/Users/adachi-yuya/.postgresql/root.crt"

DATA_DIR = Path("/Users/adachi-yuya/Code/nba_llm_analysis_app/data")


def drop_tables(conn):
    """テーブルを削除（再インポート用）"""
    cur = conn.cursor()
    print("既存テーブルを削除中...")
    cur.execute("DROP TABLE IF EXISTS boxscore CASCADE")
    cur.execute("DROP TABLE IF EXISTS games CASCADE")
    cur.execute("DROP TABLE IF EXISTS player_info CASCADE")
    cur.execute("DROP TABLE IF EXISTS player_image CASCADE")
    conn.commit()
    print("テーブル削除完了")


def create_tables(conn):
    """テーブルを作成（カラム名を引用符で囲んで大文字小文字を保持）"""
    cur = conn.cursor()

    # boxscoreテーブル
    cur.execute("""
    CREATE TABLE IF NOT EXISTS boxscore (
        id SERIAL PRIMARY KEY,
        "game_id" INT,
        "teamName" VARCHAR(100),
        "playerName" VARCHAR(100),
        "MP" VARCHAR(20),
        "FG" FLOAT,
        "FGA" FLOAT,
        "3P" FLOAT,
        "3PA" FLOAT,
        "FT" FLOAT,
        "FTA" FLOAT,
        "ORB" FLOAT,
        "DRB" FLOAT,
        "TRB" FLOAT,
        "AST" FLOAT,
        "STL" FLOAT,
        "BLK" FLOAT,
        "TOV" FLOAT,
        "PF" FLOAT,
        "PTS" FLOAT,
        "+/-" FLOAT,
        "isStarter" INT,
        "GmSc" FLOAT
    )
    """)

    # gamesテーブル
    cur.execute("""
    CREATE TABLE IF NOT EXISTS games (
        id SERIAL PRIMARY KEY,
        "seasonStartYear" INT,
        "awayTeam" VARCHAR(100),
        "pointsAway" INT,
        "homeTeam" VARCHAR(100),
        "pointsHome" INT,
        "attendance" INT,
        "notes" TEXT,
        "startET" VARCHAR(20),
        "datetime" DATE,
        "isRegular" INT,
        "game_id" INT,
        "League" VARCHAR(20),
        "isFinal" INT,
        "isPlayin" INT,
        "Winner" VARCHAR(100),
        "Arena" VARCHAR(200)
    )
    """)

    # player_infoテーブル
    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_info (
        id SERIAL PRIMARY KEY,
        "name" VARCHAR(100),
        "year_start" INT,
        "year_end" INT,
        "position" VARCHAR(20),
        "height" VARCHAR(20),
        "weight" VARCHAR(20),
        "birth_date" DATE,
        "college" VARCHAR(200)
    )
    """)

    # player_imageテーブル
    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_image (
        id SERIAL PRIMARY KEY,
        "playerName" VARCHAR(100),
        "image_url" VARCHAR(500),
        "Shooter" VARCHAR(100),
        "Assister" VARCHAR(100)
    )
    """)

    conn.commit()
    print("テーブル作成完了")


def import_csv_chunked(conn, table_name, csv_path, chunk_size=5000):
    """CSVをチャンクでインポート（execute_values高速版）"""
    cur = conn.cursor()

    print(f"{table_name}のインポート開始: {csv_path}")
    sys.stdout.flush()

    total_rows = 0
    for i, chunk in enumerate(pd.read_csv(csv_path, chunksize=chunk_size)):
        # NaNをNoneに変換
        chunk = chunk.where(pd.notnull(chunk), None)

        # カラム名を取得
        columns = chunk.columns.tolist()

        # カラム名のエスケープ
        columns_str = ', '.join([f'"{c}"' if c in ['3P', '3PA', '+/-'] else f'"{c}"' for c in columns])

        insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES %s"

        # execute_valuesを使用（非常に高速）
        try:
            data = [tuple(row) for row in chunk.values]
            execute_values(cur, insert_query, data, page_size=1000)
            conn.commit()
            total_rows += len(chunk)
            print(f"  {total_rows}行インポート完了...")
            sys.stdout.flush()
        except Exception as e:
            print(f"Error inserting batch: {e}")
            sys.stdout.flush()
            conn.rollback()
            raise

    print(f"{table_name}のインポート完了: {total_rows}行")
    sys.stdout.flush()
    return total_rows


def create_indexes(conn):
    """インデックスを作成"""
    cur = conn.cursor()

    print("インデックス作成中...")

    # boxscoreのインデックス
    cur.execute('CREATE INDEX IF NOT EXISTS idx_boxscore_player ON boxscore("playerName")')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_boxscore_game ON boxscore("game_id")')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_boxscore_team ON boxscore("teamName")')

    # gamesのインデックス
    cur.execute('CREATE INDEX IF NOT EXISTS idx_games_game_id ON games("game_id")')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_games_season ON games("seasonStartYear")')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_games_datetime ON games("datetime")')

    # player_infoのインデックス
    cur.execute('CREATE INDEX IF NOT EXISTS idx_player_info_name ON player_info("name")')

    # player_imageのインデックス
    cur.execute('CREATE INDEX IF NOT EXISTS idx_player_image_name ON player_image("playerName")')

    conn.commit()
    print("インデックス作成完了")


def main():
    print("CockroachDBに接続中...")
    conn = psycopg2.connect(DATABASE_URL)

    try:
        # テーブル削除・再作成
        drop_tables(conn)
        create_tables(conn)

        # CSVインポート（小さいファイルから順に）
        import_csv_chunked(conn, "player_image", DATA_DIR / "player_imageURL.csv")
        import_csv_chunked(conn, "player_info", DATA_DIR / "Players_data_Latest.csv")
        import_csv_chunked(conn, "games", DATA_DIR / "games1946-2025.csv")

        # boxscore（大きいので最後に）
        import_csv_chunked(conn, "boxscore", DATA_DIR / "boxscore1946-2025.csv", chunk_size=50000)

        # インデックス作成
        create_indexes(conn)

        print("\n全てのインポートが完了しました！")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
