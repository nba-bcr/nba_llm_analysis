"""プレイバイプレイデータ分析モジュール"""

import os
import re
from collections import Counter
import pandas as pd


def _is_cloud_environment() -> bool:
    """クラウド環境（Streamlit Cloud）かどうかを判定"""
    return os.environ.get("DATABASE_URL") is not None


class PlayDataAnalyzer:
    """プレイバイプレイデータの分析を行うクラス"""

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
        self.play_data_path = play_data_path
        self._df = None
        self._use_db = _is_cloud_environment()

    def _get_db_connection(self):
        import psycopg2
        return psycopg2.connect(os.environ.get("DATABASE_URL"))

    def _load_data(self):
        if self._df is None:
            self._df = pd.read_csv(
                self.play_data_path,
                usecols=['event_away', 'event_home', 'game_id']
            )
        return self._df

    def _get_player_pattern(self, player_name: str) -> str:
        for abbr, full in self.PLAYER_ABBREVIATIONS.items():
            if full.lower() == player_name.lower():
                return abbr
        return player_name

    def _extract_shooter(self, event):
        if pd.isna(event):
            return None
        match = re.match(r'^([A-Z]\. [A-Za-z\'\-]+)', str(event))
        return match.group(1) if match else None

    def get_assisted_by_ranking(self, player_name: str, top_n: int = 10) -> pd.DataFrame:
        """特定選手がアシストした選手のランキングを取得"""
        pattern_name = self._get_player_pattern(player_name)
        assist_pattern = f'(assist by {pattern_name})'

        if self._use_db:
            conn = self._get_db_connection()
            query = f"""
                SELECT event_away, event_home FROM play_data
                WHERE event_away LIKE '%{assist_pattern}%'
                   OR event_home LIKE '%{assist_pattern}%'
            """
            df = pd.read_sql(query, conn)
            conn.close()
        else:
            df = self._load_data()
            regex_pattern = rf'\(assist by {re.escape(pattern_name)}\)'
            mask = (df['event_away'].str.contains(regex_pattern, na=False, regex=True) |
                    df['event_home'].str.contains(regex_pattern, na=False, regex=True))
            df = df[mask]

        shooters = []
        for _, row in df.iterrows():
            if pd.notna(row['event_away']) and assist_pattern in str(row['event_away']):
                shooter = self._extract_shooter(row['event_away'])
                if shooter:
                    shooters.append(shooter)
            if pd.notna(row['event_home']) and assist_pattern in str(row['event_home']):
                shooter = self._extract_shooter(row['event_home'])
                if shooter:
                    shooters.append(shooter)

        shooter_counts = Counter(shooters)
        return pd.DataFrame(shooter_counts.most_common(top_n), columns=['playerName', 'Count'])

    def get_assisted_to_ranking(self, player_name: str, top_n: int = 10) -> pd.DataFrame:
        """特定選手にアシストした選手のランキングを取得"""
        pattern_name = self._get_player_pattern(player_name)

        if self._use_db:
            conn = self._get_db_connection()
            query = f"""
                SELECT event_away, event_home FROM play_data
                WHERE event_away LIKE '{pattern_name} makes %(assist by %'
                   OR event_home LIKE '{pattern_name} makes %(assist by %'
            """
            df = pd.read_sql(query, conn)
            conn.close()
        else:
            df = self._load_data()
            regex_pattern = rf'^{re.escape(pattern_name)} makes .+\(assist by'
            mask = (df['event_away'].str.contains(regex_pattern, na=False, regex=True) |
                    df['event_home'].str.contains(regex_pattern, na=False, regex=True))
            df = df[mask]

        pattern = rf'^{re.escape(pattern_name)} makes .+\(assist by ([A-Z]\. [A-Za-z\'\-]+)\)'
        assisters = []
        for _, row in df.iterrows():
            for event in [row['event_away'], row['event_home']]:
                if pd.notna(event):
                    match = re.match(pattern, str(event))
                    if match:
                        assisters.append(match.group(1))

        assister_counts = Counter(assisters)
        return pd.DataFrame(assister_counts.most_common(top_n), columns=['playerName', 'Count'])

    def get_steal_by_ranking(self, player_name: str, top_n: int = 10) -> pd.DataFrame:
        """特定選手がスティールした相手のランキングを取得"""
        pattern_name = self._get_player_pattern(player_name)
        steal_pattern = f'steal by {pattern_name})'

        if self._use_db:
            conn = self._get_db_connection()
            query = f"""
                SELECT event_away, event_home FROM play_data
                WHERE event_away LIKE 'Turnover by %{steal_pattern}%'
                   OR event_home LIKE 'Turnover by %{steal_pattern}%'
            """
            df = pd.read_sql(query, conn)
            conn.close()
        else:
            df = self._load_data()
            regex_pattern = rf'Turnover by .+steal by {re.escape(pattern_name)}\)'
            mask = (df['event_away'].str.contains(regex_pattern, na=False, regex=True) |
                    df['event_home'].str.contains(regex_pattern, na=False, regex=True))
            df = df[mask]

        pattern = rf'Turnover by ([A-Z]\. [A-Za-z\'\-]+) .+steal by {re.escape(pattern_name)}\)'
        victims = []
        for _, row in df.iterrows():
            for event in [row['event_away'], row['event_home']]:
                if pd.notna(event):
                    match = re.search(pattern, str(event))
                    if match:
                        victims.append(match.group(1))

        victim_counts = Counter(victims)
        return pd.DataFrame(victim_counts.most_common(top_n), columns=['playerName', 'Count'])

    def get_block_by_ranking(self, player_name: str, top_n: int = 10) -> pd.DataFrame:
        """特定選手がブロックした相手のランキングを取得"""
        pattern_name = self._get_player_pattern(player_name)
        block_pattern = f'(block by {pattern_name})'

        if self._use_db:
            conn = self._get_db_connection()
            query = f"""
                SELECT event_away, event_home FROM play_data
                WHERE event_away LIKE '% misses %{block_pattern}%'
                   OR event_home LIKE '% misses %{block_pattern}%'
            """
            df = pd.read_sql(query, conn)
            conn.close()
        else:
            df = self._load_data()
            regex_pattern = rf'misses .+\(block by {re.escape(pattern_name)}\)'
            mask = (df['event_away'].str.contains(regex_pattern, na=False, regex=True) |
                    df['event_home'].str.contains(regex_pattern, na=False, regex=True))
            df = df[mask]

        pattern = rf'^([A-Z]\. [A-Za-z\'\-]+) misses .+\(block by {re.escape(pattern_name)}\)'
        victims = []
        for _, row in df.iterrows():
            for event in [row['event_away'], row['event_home']]:
                if pd.notna(event):
                    match = re.match(pattern, str(event))
                    if match:
                        victims.append(match.group(1))

        victim_counts = Counter(victims)
        return pd.DataFrame(victim_counts.most_common(top_n), columns=['playerName', 'Count'])
