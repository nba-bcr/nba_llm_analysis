"""プレイバイプレイデータ分析モジュール"""

import re
import pandas as pd

from src.db_connection import get_database_url


class PlayDataAnalyzer:
    """プレイバイプレイデータの分析を行うクラス（CockroachDB使用）"""

    PLAYER_ABBREVIATIONS = {
        "S. Curry": "Stephen Curry",
        "L. James": "LeBron James",
        "K. Durant": "Kevin Durant",
        "K. Thompson": "Klay Thompson",
        "D. Green": "Draymond Green",
        "K. Bryant": "Kobe Bryant",
        "M. Jordan": "Michael Jordan",
        "S. O'Neal": "Shaquille O'Neal",
        "T. Duncan": "Tim Duncan",
        "D. Nowitzki": "Dirk Nowitzki",
        "J. Harden": "James Harden",
        "R. Westbrook": "Russell Westbrook",
        "G. Antetokounmpo": "Giannis Antetokounmpo",
        "L. Dončić": "Luka Dončić",
        "N. Jokić": "Nikola Jokić",
        "J. Embiid": "Joel Embiid",
        "A. Davis": "Anthony Davis",
        "D. Booker": "Devin Booker",
        "J. Tatum": "Jayson Tatum",
        "J. Brown": "Jaylen Brown",
        "A. Edwards": "Anthony Edwards",
        "S. Gilgeous-Alexander": "Shai Gilgeous-Alexander",
        "D. Wade": "Dwyane Wade",
        "C. Paul": "Chris Paul",
        "C. Anthony": "Carmelo Anthony",
        "P. Pierce": "Paul Pierce",
        "K. Garnett": "Kevin Garnett",
        "R. Allen": "Ray Allen",
        "D. Rose": "Derrick Rose",
        "K. Irving": "Kyrie Irving",
        "D. Lillard": "Damian Lillard",
        "P. George": "Paul George",
        "K. Leonard": "Kawhi Leonard",
        "J. Butler": "Jimmy Butler",
        "B. Griffin": "Blake Griffin",
        "R. Rondo": "Rajon Rondo",
        "T. Parker": "Tony Parker",
        "M. Ginobili": "Manu Ginobili",
        "P. Gasol": "Pau Gasol",
        "D. Howard": "Dwight Howard",
        "V. Carter": "Vince Carter",
        "A. Iverson": "Allen Iverson",
    }

    def __init__(self, play_data_path: str = None):
        """初期化（play_data_pathは互換性のため残すが未使用）"""
        self.play_data_path = play_data_path

    def _get_db_connection(self):
        import psycopg2
        return psycopg2.connect(get_database_url())

    def _get_player_pattern(self, player_name: str) -> str:
        for abbr, full in self.PLAYER_ABBREVIATIONS.items():
            if full.lower() == player_name.lower():
                return abbr
        return player_name

    def _escape_sql(self, value: str) -> str:
        """SQLのシングルクォートをエスケープ"""
        return value.replace("'", "''")

    def get_assisted_by_ranking(self, player_name: str, top_n: int = 10) -> pd.DataFrame:
        """特定選手がアシストした選手のランキングを取得"""
        pattern_name = self._get_player_pattern(player_name)
        assist_pattern = f'(assist by {pattern_name})'
        sql_pattern = self._escape_sql(assist_pattern)

        conn = self._get_db_connection()
        query = f"""
            SELECT event_away, event_home FROM play_data
            WHERE event_away LIKE '%{sql_pattern}%'
               OR event_home LIKE '%{sql_pattern}%'
        """
        df = pd.read_sql(query, conn)
        conn.close()

        # ベクトル化処理: 両カラムを結合してパターンでフィルタ
        events = pd.concat([df['event_away'], df['event_home']]).dropna()
        events = events[events.str.contains(re.escape(assist_pattern), regex=True)]

        # シューター名を抽出
        shooters = events.str.extract(r'^([A-Z]\. [A-Za-z\'\-]+)')[0].dropna()

        # カウントしてランキング作成
        shooter_counts = shooters.value_counts().head(top_n).reset_index()
        shooter_counts.columns = ['playerName', 'Count']
        return shooter_counts

    def get_assisted_to_ranking(self, player_name: str, top_n: int = 10) -> pd.DataFrame:
        """特定選手にアシストした選手のランキングを取得"""
        pattern_name = self._get_player_pattern(player_name)
        sql_pattern = self._escape_sql(pattern_name)

        conn = self._get_db_connection()
        query = f"""
            SELECT event_away, event_home FROM play_data
            WHERE event_away LIKE '{sql_pattern} makes %(assist by %'
               OR event_home LIKE '{sql_pattern} makes %(assist by %'
        """
        df = pd.read_sql(query, conn)
        conn.close()

        # ベクトル化処理: 両カラムを結合
        events = pd.concat([df['event_away'], df['event_home']]).dropna()

        # アシスター名を抽出
        pattern = rf'^{re.escape(pattern_name)} makes .+\(assist by ([A-Z]\. [A-Za-z\'\-]+)\)'
        assisters = events.str.extract(pattern)[0].dropna()

        # カウントしてランキング作成
        assister_counts = assisters.value_counts().head(top_n).reset_index()
        assister_counts.columns = ['playerName', 'Count']
        return assister_counts

    def get_steal_by_ranking(self, player_name: str, top_n: int = 10) -> pd.DataFrame:
        """特定選手がスティールした相手のランキングを取得"""
        pattern_name = self._get_player_pattern(player_name)
        steal_pattern = f'steal by {pattern_name})'
        sql_pattern = self._escape_sql(steal_pattern)

        conn = self._get_db_connection()
        query = f"""
            SELECT event_away, event_home FROM play_data
            WHERE event_away LIKE 'Turnover by %{sql_pattern}%'
               OR event_home LIKE 'Turnover by %{sql_pattern}%'
        """
        df = pd.read_sql(query, conn)
        conn.close()

        # ベクトル化処理: 両カラムを結合
        events = pd.concat([df['event_away'], df['event_home']]).dropna()

        # ターンオーバーした選手名を抽出
        pattern = rf'Turnover by ([A-Z]\. [A-Za-z\'\-]+) .+steal by {re.escape(pattern_name)}\)'
        victims = events.str.extract(pattern)[0].dropna()

        # カウントしてランキング作成
        victim_counts = victims.value_counts().head(top_n).reset_index()
        victim_counts.columns = ['playerName', 'Count']
        return victim_counts

    def get_block_by_ranking(self, player_name: str, top_n: int = 10) -> pd.DataFrame:
        """特定選手がブロックした相手のランキングを取得"""
        pattern_name = self._get_player_pattern(player_name)
        block_pattern = f'(block by {pattern_name})'
        sql_pattern = self._escape_sql(block_pattern)

        conn = self._get_db_connection()
        query = f"""
            SELECT event_away, event_home FROM play_data
            WHERE event_away LIKE '% misses %{sql_pattern}%'
               OR event_home LIKE '% misses %{sql_pattern}%'
        """
        df = pd.read_sql(query, conn)
        conn.close()

        # ベクトル化処理: 両カラムを結合
        events = pd.concat([df['event_away'], df['event_home']]).dropna()

        # ブロックされた選手名を抽出
        pattern = rf'^([A-Z]\. [A-Za-z\'\-]+) misses .+\(block by {re.escape(pattern_name)}\)'
        victims = events.str.extract(pattern)[0].dropna()

        # カウントしてランキング作成
        victim_counts = victims.value_counts().head(top_n).reset_index()
        victim_counts.columns = ['playerName', 'Count']
        return victim_counts
