"""
NBA統計分析モジュール（SQL版）

CockroachDBを使用してクエリベースで分析を実行
"""

import pandas as pd
from typing import List, Optional, Union
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

from .db_connection import get_connection


# 同姓同名の選手（複数人が存在するため分析から除外）
DUPLICATE_NAME_PLAYERS = [
    "Eddie Johnson",
    "George Johnson",
    "Mike Dunleavy",
    "David Lee",
    "Jim Paxson",
    "Larry Johnson",
    "Matt Guokas",
]


class NBAAnalyzerSQL:
    """NBA統計データの分析を行うクラス（SQL版）"""

    def __init__(
        self,
        exclude_duplicate_names: bool = True,
        exclude_players: Optional[List[str]] = None,
    ):
        """
        Parameters
        ----------
        exclude_duplicate_names : bool
            同姓同名の選手を自動除外するか（デフォルト: True）
        exclude_players : List[str], optional
            追加で除外する選手名リスト
        """
        # 除外リストを作成
        self._exclude_players = []
        if exclude_duplicate_names:
            self._exclude_players.extend(DUPLICATE_NAME_PLAYERS)
        if exclude_players:
            self._exclude_players.extend(exclude_players)

    def _get_exclude_clause(self) -> str:
        """除外選手のWHERE句を生成"""
        if not self._exclude_players:
            return ""
        placeholders = ", ".join([f"'{p}'" for p in self._exclude_players])
        return f"AND b.\"playerName\" NOT IN ({placeholders})"

    def _get_game_type_clause(self, game_type: str, league: str = "NBA") -> str:
        """試合タイプのWHERE句を生成"""
        clauses = [f"g.\"League\" = '{league}'"]

        if game_type == "regular":
            clauses.append("g.\"isRegular\" = 1")
        elif game_type == "playoff":
            clauses.append("g.\"isRegular\" = 0")
            clauses.append("COALESCE(g.\"isPlayin\", 0) = 0")
        elif game_type == "final":
            clauses.append("g.\"isFinal\" = 1")
        # "all" の場合は追加条件なし

        return " AND ".join(clauses)

    # =========================================================================
    # 1. 年齢別記録の分析
    # =========================================================================

    def _get_starter_clause(self, is_starter: Optional[bool]) -> str:
        """スターター/ベンチのWHERE句を生成"""
        if is_starter is None:
            return ""
        if is_starter:
            return 'AND b."isStarter" = 1'
        else:
            return 'AND b."isStarter" = 0'

    def _get_team_clause(self, team: Optional[str]) -> str:
        """チームフィルタのWHERE句を生成"""
        if team is None:
            return ""
        return f'AND b."teamName" LIKE \'%{team}%\''

    def get_ranking_by_age(
        self,
        label: str,
        max_age: Optional[int] = None,
        min_age: Optional[int] = None,
        min_games: int = 1,
        aggfunc: str = "sum",
        league: str = "NBA",
        game_type: Literal["regular", "playoff", "final", "all"] = "regular",
        top_n: int = 100,
        is_starter: Optional[bool] = None,
        team: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        任意の年齢範囲でのランキングを取得
        """
        game_type_clause = self._get_game_type_clause(game_type, league)
        exclude_clause = self._get_exclude_clause()
        starter_clause = self._get_starter_clause(is_starter)
        team_clause = self._get_team_clause(team)

        # 年齢フィルタ（CockroachDB互換: AGE()関数の代わりに日付差分を使用）
        # 年齢 = 年の差 - (誕生日がまだ来ていなければ1を引く)
        age_clauses = []
        age_expr = "EXTRACT(YEAR FROM g.datetime) - EXTRACT(YEAR FROM pi.birth_date) - CASE WHEN EXTRACT(DOY FROM g.datetime) < EXTRACT(DOY FROM pi.birth_date) THEN 1 ELSE 0 END"
        if max_age is not None:
            age_clauses.append(f"pi.birth_date IS NOT NULL AND ({age_expr}) <= {max_age}")
        if min_age is not None:
            age_clauses.append(f"pi.birth_date IS NOT NULL AND ({age_expr}) >= {min_age}")

        age_clause = " AND ".join(age_clauses) if age_clauses else "1=1"

        # DD/TD/閾値パターンに対応した統計式を取得
        # DD/TD/40PTS+などはカウント用(0/1)、通常カラムは実際の値
        stat_expr = self._get_stat_expression(label, for_count=False)

        # 集計関数
        if aggfunc == "sum":
            agg_expr = f'SUM({stat_expr})::INTEGER'
        else:
            agg_expr = f'ROUND(AVG({stat_expr})::numeric, 1)'

        query = f"""
        SELECT
            b."playerName",
            {agg_expr} AS "{label}",
            COUNT(*) AS "Games"
        FROM boxscore b
        JOIN games g ON b.game_id = g.game_id
        LEFT JOIN player_info pi ON b."playerName" = pi.name
        WHERE {game_type_clause}
            AND b."PTS" IS NOT NULL
            {exclude_clause}
            {starter_clause}
            {team_clause}
            AND {age_clause}
        GROUP BY b."playerName"
        HAVING COUNT(*) >= {min_games}
        ORDER BY "{label}" DESC
        LIMIT {top_n}
        """

        with get_connection() as conn:
            return pd.read_sql(query, conn)

    # =========================================================================
    # 2. 到達試合数の分析
    # =========================================================================

    def get_games_to_reach(
        self,
        label: str,
        threshold: int,
        game_type: Literal["regular", "playoff", "final", "all"] = "regular",
        league: str = "NBA",
        top_n: int = 100,
    ) -> pd.DataFrame:
        """
        累計〇〇に到達するまでの試合数ランキングを取得
        """
        game_type_clause = self._get_game_type_clause(game_type, league)
        exclude_clause = self._get_exclude_clause()

        query = f"""
        WITH cumulative AS (
            SELECT
                b."playerName",
                g.datetime,
                b."{label}",
                SUM(COALESCE(b."{label}", 0)) OVER (
                    PARTITION BY b."playerName"
                    ORDER BY g.datetime
                ) AS cumsum,
                ROW_NUMBER() OVER (
                    PARTITION BY b."playerName"
                    ORDER BY g.datetime
                ) AS game_num
            FROM boxscore b
            JOIN games g ON b.game_id = g.game_id
            WHERE {game_type_clause}
                AND b."PTS" IS NOT NULL
                {exclude_clause}
        ),
        reached AS (
            SELECT
                "playerName",
                MIN(game_num) AS "Games"
            FROM cumulative
            WHERE cumsum >= {threshold}
            GROUP BY "playerName"
        )
        SELECT "playerName", "Games"
        FROM reached
        ORDER BY "Games" ASC
        LIMIT {top_n}
        """

        with get_connection() as conn:
            return pd.read_sql(query, conn)

    # =========================================================================
    # 3. 年間スタッツ達成回数の分析
    # =========================================================================

    def get_season_achievement_count(
        self,
        label: str,
        threshold: int,
        league: str = "NBA",
        top_n: int = 100,
    ) -> pd.DataFrame:
        """
        年間〇〇達成回数のランキングを取得
        """
        exclude_clause = self._get_exclude_clause()
        col_name = f"{threshold}+{label}"

        query = f"""
        WITH season_totals AS (
            SELECT
                b."playerName",
                g."seasonStartYear",
                SUM(COALESCE(b."{label}", 0)) AS total
            FROM boxscore b
            JOIN games g ON b.game_id = g.game_id
            WHERE g."League" = '{league}'
                AND g."isRegular" = 1
                AND b."PTS" IS NOT NULL
                {exclude_clause}
            GROUP BY b."playerName", g."seasonStartYear"
        )
        SELECT
            "playerName",
            SUM(CASE WHEN total >= {threshold} THEN 1 ELSE 0 END) AS "{col_name}"
        FROM season_totals
        GROUP BY "playerName"
        HAVING SUM(CASE WHEN total >= {threshold} THEN 1 ELSE 0 END) > 0
        ORDER BY "{col_name}" DESC
        LIMIT {top_n}
        """

        with get_connection() as conn:
            return pd.read_sql(query, conn)

    # =========================================================================
    # 4. 連続試合記録の分析
    # =========================================================================

    def _get_stat_expression(self, label: str, for_count: bool = False) -> str:
        """
        統計ラベルに対応するSQL式を返す

        Parameters
        ----------
        label : str
            統計ラベル（例: PTS, DD, TD, 40PTS+, 20TRB+）
        for_count : bool
            True の場合、閾値達成時に1を返す式を生成（回数カウント用）

        Returns
        -------
        str
            SQL式
        """
        import re

        # ダブルダブル: 5カテゴリのうち2つ以上で10以上
        if label == "DD":
            return """
                CASE WHEN (
                    (CASE WHEN COALESCE(b."PTS", 0) >= 10 THEN 1 ELSE 0 END) +
                    (CASE WHEN COALESCE(b."TRB", 0) >= 10 THEN 1 ELSE 0 END) +
                    (CASE WHEN COALESCE(b."AST", 0) >= 10 THEN 1 ELSE 0 END) +
                    (CASE WHEN COALESCE(b."STL", 0) >= 10 THEN 1 ELSE 0 END) +
                    (CASE WHEN COALESCE(b."BLK", 0) >= 10 THEN 1 ELSE 0 END)
                ) >= 2 THEN 1 ELSE 0 END
            """
        # トリプルダブル: 5カテゴリのうち3つ以上で10以上
        elif label == "TD":
            return """
                CASE WHEN (
                    (CASE WHEN COALESCE(b."PTS", 0) >= 10 THEN 1 ELSE 0 END) +
                    (CASE WHEN COALESCE(b."TRB", 0) >= 10 THEN 1 ELSE 0 END) +
                    (CASE WHEN COALESCE(b."AST", 0) >= 10 THEN 1 ELSE 0 END) +
                    (CASE WHEN COALESCE(b."STL", 0) >= 10 THEN 1 ELSE 0 END) +
                    (CASE WHEN COALESCE(b."BLK", 0) >= 10 THEN 1 ELSE 0 END)
                ) >= 3 THEN 1 ELSE 0 END
            """

        # 勝利: 選手のチームが試合の勝者と一致するか
        # gamesテーブルのWinnerカラムと比較
        elif label == "Win":
            return 'CASE WHEN b."teamName" = g."Winner" THEN 1 ELSE 0 END'

        # 閾値パターン: "40PTS+", "20TRB+", "10AST+" など
        threshold_match = re.match(r'^(\d+)([A-Z0-9]+)\+$', label)
        if threshold_match:
            threshold = int(threshold_match.group(1))
            stat_col = threshold_match.group(2)
            # 回数カウント用: 達成時に1、未達成時に0
            return f'CASE WHEN COALESCE(b."{stat_col}", 0) >= {threshold} THEN 1 ELSE 0 END'

        # 通常のカラム
        if for_count:
            return f'CASE WHEN COALESCE(b."{label}", 0) >= 1 THEN 1 ELSE 0 END'
        return f'COALESCE(b."{label}", 0)'

    def get_consecutive_games(
        self,
        label: str,
        game_type: Literal["regular", "playoff", "final", "all"] = "regular",
        league: str = "NBA",
        top_n: int = 100,
        team: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        連続試合記録（例: ダブルダブル連続試合数）のランキングを取得

        SQLでグループ番号を計算し、連続記録を効率的に取得
        """
        game_type_clause = self._get_game_type_clause(game_type, league)
        exclude_clause = self._get_exclude_clause()
        team_clause = self._get_team_clause(team)

        # DD/TDは計算式、それ以外は通常のカラム参照
        stat_expr = self._get_stat_expression(label)
        # DD/TDの場合はすでに0/1なので >= 1 チェック、通常カラムも >= 1
        achieved_expr = f"CASE WHEN ({stat_expr}) >= 1 THEN 1 ELSE 0 END"

        # SQLで連続記録を計算（gaps and islands法）
        query = f"""
        WITH numbered AS (
            SELECT
                b."playerName",
                g.datetime,
                {achieved_expr} AS achieved,
                ROW_NUMBER() OVER (PARTITION BY b."playerName" ORDER BY g.datetime) AS rn
            FROM boxscore b
            JOIN games g ON b.game_id = g.game_id
            WHERE {game_type_clause}
                AND b."PTS" IS NOT NULL
                {exclude_clause}
                {team_clause}
        ),
        achieved_only AS (
            SELECT
                "playerName",
                rn,
                ROW_NUMBER() OVER (PARTITION BY "playerName" ORDER BY rn) AS achieved_rn
            FROM numbered
            WHERE achieved = 1
        ),
        grouped AS (
            SELECT
                "playerName",
                rn - achieved_rn AS grp,
                COUNT(*) AS streak
            FROM achieved_only
            GROUP BY "playerName", rn - achieved_rn
        )
        SELECT
            "playerName",
            MAX(streak)::INTEGER AS "{label}"
        FROM grouped
        GROUP BY "playerName"
        ORDER BY "{label}" DESC
        LIMIT {top_n}
        """

        with get_connection() as conn:
            df = pd.read_sql(query, conn)

        if df.empty:
            return pd.DataFrame(columns=["playerName", label])

        return df

    # =========================================================================
    # 5. n試合スパン分析
    # =========================================================================

    def get_n_game_span_ranking(
        self,
        label: str,
        n_games: int = 2,
        game_type: Literal["regular", "playoff", "final", "all"] = "regular",
        league: str = "NBA",
        top_n: int = 100,
    ) -> pd.DataFrame:
        """
        連続n試合スパンでの合計ランキングを取得
        """
        game_type_clause = self._get_game_type_clause(game_type, league)
        exclude_clause = self._get_exclude_clause()

        query = f"""
        WITH numbered AS (
            SELECT
                b."playerName",
                b."{label}",
                ROW_NUMBER() OVER (
                    PARTITION BY b."playerName"
                    ORDER BY g.datetime
                ) AS rn
            FROM boxscore b
            JOIN games g ON b.game_id = g.game_id
            WHERE {game_type_clause}
                AND b."PTS" IS NOT NULL
                {exclude_clause}
        ),
        spans AS (
            SELECT
                n1."playerName",
                SUM(n2."{label}") AS span_total
            FROM numbered n1
            JOIN numbered n2
                ON n1."playerName" = n2."playerName"
                AND n2.rn BETWEEN n1.rn AND n1.rn + {n_games - 1}
            GROUP BY n1."playerName", n1.rn
            HAVING COUNT(*) = {n_games}
        )
        SELECT
            "playerName",
            MAX(span_total)::INTEGER AS "{label}"
        FROM spans
        GROUP BY "playerName"
        ORDER BY "{label}" DESC
        LIMIT {top_n}
        """

        with get_connection() as conn:
            return pd.read_sql(query, conn)

    # =========================================================================
    # 6. デュエル分析
    # =========================================================================

    def get_duel_ranking(
        self,
        games_df=None,  # 互換性のため維持（使用しない）
        label: str = "PTS",
        game_type: Literal["regular", "playoff", "final", "all"] = "final",
        min_total: int = 0,
        player1: Optional[str] = None,
        player2: Optional[str] = None,
        top_n: int = 100,
    ) -> pd.DataFrame:
        """
        両チームのトップスコアラー対決ランキングを取得
        """
        game_type_clause = self._get_game_type_clause(game_type)
        exclude_clause = self._get_exclude_clause()

        # 特定選手フィルタ（duelsのカラム名はplayer1, player2）
        player_filter = ""
        if player1:
            player_filter += f" AND (d.player1 LIKE '%{player1}%' OR d.player2 LIKE '%{player1}%')"
        if player2:
            player_filter += f" AND (d.player1 LIKE '%{player2}%' OR d.player2 LIKE '%{player2}%')"

        query = f"""
        WITH top_scorers AS (
            SELECT DISTINCT ON (b.game_id, b."teamName")
                b.game_id,
                b."teamName",
                b."playerName",
                b."{label}"
            FROM boxscore b
            JOIN games g ON b.game_id = g.game_id
            WHERE {game_type_clause}
                AND b."PTS" IS NOT NULL
                {exclude_clause}
            ORDER BY b.game_id, b."teamName", b."{label}" DESC
        ),
        duels AS (
            SELECT
                t1.game_id,
                t1."playerName" AS player1,
                t1."{label}" AS score1,
                t2."playerName" AS player2,
                t2."{label}" AS score2,
                t1."{label}" + t2."{label}" AS "Total{label}"
            FROM top_scorers t1
            JOIN top_scorers t2
                ON t1.game_id = t2.game_id
                AND t1."teamName" < t2."teamName"
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY d."Total{label}" DESC) AS "Rank",
            g.datetime,
            g."seasonStartYear"::TEXT || '-' || (g."seasonStartYear" + 1)::TEXT AS "Season",
            d.player1 || ' vs ' || d.player2 AS "playerName",
            d.score1::TEXT || ' - ' || d.score2::TEXT AS "Score",
            d."Total{label}",
            g."awayTeam" || ' @ ' || g."homeTeam" AS "MatchUp",
            g."pointsAway"::TEXT || '-' || g."pointsHome"::TEXT AS "GameScore"
        FROM duels d
        JOIN games g ON d.game_id = g.game_id
        WHERE d."Total{label}" >= {min_total}
            {player_filter}
        ORDER BY d."Total{label}" DESC
        LIMIT {top_n}
        """

        with get_connection() as conn:
            return pd.read_sql(query, conn)

    # =========================================================================
    # 7. キャリアハイ分析
    # =========================================================================

    def get_player_career_high(
        self,
        player_name: str,
        label: str = "PTS",
        game_type: Literal["regular", "playoff", "final", "all"] = "all",
        league: str = "NBA",
        top_n: int = 20,
    ) -> pd.DataFrame:
        """
        特定選手のキャリアハイゲームを取得（日付付き）

        Parameters
        ----------
        player_name : str
            選手名（部分一致）
        label : str
            スタッツラベル（PTS, TRB, AST等）
        game_type : str
            試合タイプ
        top_n : int
            取得件数

        Returns
        -------
        pd.DataFrame
            日付、対戦相手、スタッツを含むDataFrame
        """
        game_type_clause = self._get_game_type_clause(game_type, league)

        query = f"""
        SELECT
            TO_CHAR(g.datetime, 'YYYY-MM-DD') || ' ' ||
            CASE
                WHEN b."teamName" = g."homeTeam" THEN 'vs ' || g."awayTeam"
                ELSE '@ ' || g."homeTeam"
            END AS "playerName",
            TO_CHAR(g.datetime, 'YYYY-MM-DD') AS "Date",
            g."seasonStartYear"::TEXT || '-' || (g."seasonStartYear" + 1)::TEXT AS "Season",
            CASE
                WHEN b."teamName" = g."homeTeam" THEN 'vs ' || g."awayTeam"
                ELSE '@ ' || g."homeTeam"
            END AS "Opponent",
            b."{label}" AS "{label}",
            b."PTS",
            b."TRB",
            b."AST"
        FROM boxscore b
        JOIN games g ON b.game_id = g.game_id
        WHERE {game_type_clause}
            AND b."playerName" LIKE '%{player_name}%'
            AND b."PTS" IS NOT NULL
        ORDER BY b."{label}" DESC
        LIMIT {top_n}
        """

        with get_connection() as conn:
            return pd.read_sql(query, conn)

    # =========================================================================
    # 8. 条件付き達成回数分析
    # =========================================================================

    def get_filtered_achievement_count(
        self,
        count_column: str,
        count_threshold: int,
        filter_column: Optional[str] = None,
        filter_op: Optional[str] = None,
        filter_value: Optional[Union[int, float]] = None,
        game_type: Literal["regular", "playoff", "final", "all"] = "regular",
        league: str = "NBA",
        top_n: int = 100,
    ) -> pd.DataFrame:
        """
        条件付き達成回数ランキングを取得
        """
        game_type_clause = self._get_game_type_clause(game_type, league)
        exclude_clause = self._get_exclude_clause()

        # フィルタ条件
        filter_clause = ""
        if filter_column and filter_op and filter_value is not None:
            op_map = {
                "eq": "=",
                "ne": "!=",
                "lt": "<",
                "le": "<=",
                "gt": ">",
                "ge": ">="
            }
            sql_op = op_map.get(filter_op, "=")
            filter_clause = f'AND b."{filter_column}" {sql_op} {filter_value}'

        query = f"""
        SELECT
            b."playerName",
            SUM(CASE WHEN b."{count_column}" >= {count_threshold} THEN 1 ELSE 0 END) AS "Count"
        FROM boxscore b
        JOIN games g ON b.game_id = g.game_id
        WHERE {game_type_clause}
            AND b."PTS" IS NOT NULL
            {exclude_clause}
            {filter_clause}
        GROUP BY b."playerName"
        HAVING SUM(CASE WHEN b."{count_column}" >= {count_threshold} THEN 1 ELSE 0 END) > 0
        ORDER BY "Count" DESC
        LIMIT {top_n}
        """

        with get_connection() as conn:
            return pd.read_sql(query, conn)

    # =========================================================================
    # 9. スターター vs ベンチ比較分析
    # =========================================================================

    def get_player_starter_comparison(
        self,
        player_name: str,
        label: str = "PTS",
        game_type: Literal["regular", "playoff", "final", "all"] = "regular",
        league: str = "NBA",
    ) -> pd.DataFrame:
        """
        選手のスターター時 vs ベンチ時の成績比較

        Parameters
        ----------
        player_name : str
            選手名（部分一致）
        label : str
            スタッツラベル
        game_type : str
            試合タイプ

        Returns
        -------
        pd.DataFrame
            スターター/ベンチ別の平均成績
        """
        game_type_clause = self._get_game_type_clause(game_type, league)

        query = f"""
        SELECT
            b."playerName",
            CASE WHEN b."isStarter" = 1 THEN 'Starter' ELSE 'Bench' END AS "Role",
            COUNT(*) AS "Games",
            ROUND(AVG(b."PTS")::numeric, 1) AS "PPG",
            ROUND(AVG(b."TRB")::numeric, 1) AS "RPG",
            ROUND(AVG(b."AST")::numeric, 1) AS "APG",
            ROUND(AVG(b."MP")::numeric, 1) AS "MPG"
        FROM boxscore b
        JOIN games g ON b.game_id = g.game_id
        WHERE {game_type_clause}
            AND b."playerName" LIKE '%{player_name}%'
            AND b."PTS" IS NOT NULL
        GROUP BY b."playerName", b."isStarter"
        ORDER BY b."isStarter" DESC
        """

        with get_connection() as conn:
            return pd.read_sql(query, conn)

    # =========================================================================
    # 10. ベンチプレイヤーランキング（シックスマン的分析）
    # =========================================================================

    def get_combined_achievement_count(
        self,
        thresholds: dict,
        game_type: Literal["regular", "playoff", "final", "all"] = "regular",
        league: str = "NBA",
        top_n: int = 100,
    ) -> pd.DataFrame:
        """
        複合スタッツ達成回数ランキングを取得

        Parameters
        ----------
        thresholds : dict
            各スタッツの閾値（例: {"PTS": 25, "TRB": 5, "AST": 5}）
        game_type : str
            試合タイプ
        top_n : int
            取得件数

        Returns
        -------
        pd.DataFrame
            達成回数ランキング
        """
        game_type_clause = self._get_game_type_clause(game_type, league)
        exclude_clause = self._get_exclude_clause()

        # 条件式を構築（すべての閾値を満たす）
        conditions = []
        label_parts = []
        for stat, threshold in thresholds.items():
            conditions.append(f'COALESCE(b."{stat}", 0) >= {threshold}')
            label_parts.append(f"{threshold}{stat}")

        combined_label = " & ".join(label_parts)
        condition_expr = " AND ".join(conditions)

        query = f"""
        SELECT
            b."playerName",
            SUM(CASE WHEN {condition_expr} THEN 1 ELSE 0 END) AS "Count"
        FROM boxscore b
        JOIN games g ON b.game_id = g.game_id
        WHERE {game_type_clause}
            AND b."PTS" IS NOT NULL
            {exclude_clause}
        GROUP BY b."playerName"
        HAVING SUM(CASE WHEN {condition_expr} THEN 1 ELSE 0 END) > 0
        ORDER BY "Count" DESC
        LIMIT {top_n}
        """

        with get_connection() as conn:
            df = pd.read_sql(query, conn)

        # カラム名を分かりやすく変更
        if not df.empty:
            df = df.rename(columns={"Count": combined_label})

        return df

    def get_bench_player_ranking(
        self,
        label: str = "PTS",
        game_type: Literal["regular", "playoff", "final", "all"] = "regular",
        league: str = "NBA",
        min_games: int = 50,
        top_n: int = 50,
        season: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        ベンチ出場時の成績ランキング（シックスマン的分析）

        Parameters
        ----------
        label : str
            スタッツラベル（PTS, TRB, AST等）
        game_type : str
            試合タイプ
        min_games : int
            最低試合数（ベンチ出場）
        top_n : int
            取得件数
        season : int, optional
            シーズン開始年（例: 2023で2023-24シーズン）

        Returns
        -------
        pd.DataFrame
            ベンチ出場時の成績ランキング
        """
        game_type_clause = self._get_game_type_clause(game_type, league)
        exclude_clause = self._get_exclude_clause()

        season_clause = ""
        if season:
            season_clause = f'AND g."seasonStartYear" = {season}'

        query = f"""
        SELECT
            b."playerName",
            COUNT(*) AS "BenchGames",
            ROUND(AVG(b."PTS")::numeric, 1) AS "PPG",
            ROUND(AVG(b."TRB")::numeric, 1) AS "RPG",
            ROUND(AVG(b."AST")::numeric, 1) AS "APG",
            ROUND(AVG(b."MP")::numeric, 1) AS "MPG",
            SUM(b."{label}")::INTEGER AS "{label}"
        FROM boxscore b
        JOIN games g ON b.game_id = g.game_id
        WHERE {game_type_clause}
            AND b."isStarter" = 0
            AND b."PTS" IS NOT NULL
            AND b."MP" > 0
            {exclude_clause}
            {season_clause}
        GROUP BY b."playerName"
        HAVING COUNT(*) >= {min_games}
        ORDER BY AVG(b."{label}") DESC
        LIMIT {top_n}
        """

        with get_connection() as conn:
            return pd.read_sql(query, conn)
