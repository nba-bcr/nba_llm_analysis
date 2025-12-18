"""プレイバイプレイデータ分析モジュール"""

import pandas as pd


class PlayDataAnalyzer:
    """プレイバイプレイデータの分析を行うクラス"""

    # 選手名の短縮形→フルネーム変換（主要選手）
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

    def __init__(self, play_data_path: str):
        """
        Parameters
        ----------
        play_data_path : str
            play_data CSVファイルのパス
        """
        self.play_data_path = play_data_path
        self._df = None

    def _load_data(self):
        """データを遅延読み込み"""
        if self._df is None:
            self._df = pd.read_csv(
                self.play_data_path,
                usecols=['event_away', 'event_home', 'game_id']
            )
        return self._df

    def _get_player_pattern(self, player_name: str) -> str:
        """選手名からパターン用の短縮形を取得"""
        # フルネームから短縮形を逆引き
        for abbr, full in self.PLAYER_ABBREVIATIONS.items():
            if full.lower() == player_name.lower():
                return abbr
        # 見つからない場合はそのまま使用（例: "S. Curry"）
        return player_name

    def get_assisted_by_ranking(
        self,
        player_name: str,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """
        特定選手がアシストした選手のランキングを取得

        Parameters
        ----------
        player_name : str
            アシスターの名前（例: "Stephen Curry" または "S. Curry"）
        top_n : int
            上位N件を取得

        Returns
        -------
        pd.DataFrame
            columns: [playerName, Count]
        """
        import re
        from collections import Counter

        df = self._load_data()
        pattern_name = self._get_player_pattern(player_name)
        pattern = rf'\(assist by {re.escape(pattern_name)}\)'

        # event_awayとevent_homeの両方をチェック
        assists_away = df[df['event_away'].str.contains(pattern, na=False, regex=True)]
        assists_home = df[df['event_home'].str.contains(pattern, na=False, regex=True)]

        # シューター名を抽出
        def extract_shooter(event):
            if pd.isna(event):
                return None
            match = re.match(r'^([A-Z]\. [A-Za-z\'\-]+)', str(event))
            if match:
                return match.group(1)
            return None

        shooters = []
        for event in assists_away['event_away']:
            shooter = extract_shooter(event)
            if shooter:
                shooters.append(shooter)
        for event in assists_home['event_home']:
            shooter = extract_shooter(event)
            if shooter:
                shooters.append(shooter)

        # カウント
        shooter_counts = Counter(shooters)
        result = pd.DataFrame(
            shooter_counts.most_common(top_n),
            columns=['playerName', 'Count']
        )
        return result

    def get_assisted_to_ranking(
        self,
        player_name: str,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """
        特定選手にアシストした選手のランキングを取得

        Parameters
        ----------
        player_name : str
            シューターの名前（例: "Kevin Durant" または "K. Durant"）
        top_n : int
            上位N件を取得

        Returns
        -------
        pd.DataFrame
            columns: [playerName, Count]
        """
        import re
        from collections import Counter

        df = self._load_data()
        pattern_name = self._get_player_pattern(player_name)

        # シューターが得点した行でアシスターを抽出
        pattern = rf'^{re.escape(pattern_name)} makes .+\(assist by ([A-Z]\. [A-Za-z\'\-]+)\)'

        assisters = []
        for event in df['event_away'].dropna():
            match = re.match(pattern, str(event))
            if match:
                assisters.append(match.group(1))
        for event in df['event_home'].dropna():
            match = re.match(pattern, str(event))
            if match:
                assisters.append(match.group(1))

        # カウント
        assister_counts = Counter(assisters)
        result = pd.DataFrame(
            assister_counts.most_common(top_n),
            columns=['playerName', 'Count']
        )
        return result

    def get_steal_by_ranking(
        self,
        player_name: str,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """
        特定選手がスティールした相手のランキングを取得

        Parameters
        ----------
        player_name : str
            スティールした選手の名前
        top_n : int
            上位N件を取得

        Returns
        -------
        pd.DataFrame
            columns: [playerName, Count]
        """
        import re
        from collections import Counter

        df = self._load_data()
        pattern_name = self._get_player_pattern(player_name)

        # "Turnover by X (... steal by player_name)" のパターン
        pattern = rf'Turnover by ([A-Z]\. [A-Za-z\'\-]+) .+steal by {re.escape(pattern_name)}\)'

        victims = []
        for event in df['event_away'].dropna():
            match = re.search(pattern, str(event))
            if match:
                victims.append(match.group(1))
        for event in df['event_home'].dropna():
            match = re.search(pattern, str(event))
            if match:
                victims.append(match.group(1))

        # カウント
        victim_counts = Counter(victims)
        result = pd.DataFrame(
            victim_counts.most_common(top_n),
            columns=['playerName', 'Count']
        )
        return result

    def get_block_by_ranking(
        self,
        player_name: str,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """
        特定選手がブロックした相手のランキングを取得

        Parameters
        ----------
        player_name : str
            ブロックした選手の名前
        top_n : int
            上位N件を取得

        Returns
        -------
        pd.DataFrame
            columns: [playerName, Count]
        """
        import re
        from collections import Counter

        df = self._load_data()
        pattern_name = self._get_player_pattern(player_name)

        # "X misses ... (block by player_name)" のパターン
        pattern = rf'^([A-Z]\. [A-Za-z\'\-]+) misses .+\(block by {re.escape(pattern_name)}\)'

        victims = []
        for event in df['event_away'].dropna():
            match = re.match(pattern, str(event))
            if match:
                victims.append(match.group(1))
        for event in df['event_home'].dropna():
            match = re.match(pattern, str(event))
            if match:
                victims.append(match.group(1))

        # カウント
        victim_counts = Counter(victims)
        result = pd.DataFrame(
            victim_counts.most_common(top_n),
            columns=['playerName', 'Count']
        )
        return result
