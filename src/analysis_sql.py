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
    ) -> pd.DataFrame:
        """
        任意の年齢範囲でのランキングを取得
        """
        game_type_clause = self._get_game_type_clause(game_type, league)
        exclude_clause = self._get_exclude_clause()

        # 年齢フィルタ（CockroachDB互換: AGE()関数の代わりに日付差分を使用）
        # 年齢 = 年の差 - (誕生日がまだ来ていなければ1を引く)
        age_clauses = []
        age_expr = "EXTRACT(YEAR FROM g.datetime) - EXTRACT(YEAR FROM pi.birth_date) - CASE WHEN EXTRACT(DOY FROM g.datetime) < EXTRACT(DOY FROM pi.birth_date) THEN 1 ELSE 0 END"
        if max_age is not None:
            age_clauses.append(f"pi.birth_date IS NOT NULL AND ({age_expr}) <= {max_age}")
        if min_age is not None:
            age_clauses.append(f"pi.birth_date IS NOT NULL AND ({age_expr}) >= {min_age}")

        age_clause = " AND ".join(age_clauses) if age_clauses else "1=1"

        # 集計関数
        if aggfunc == "sum":
            agg_expr = f'SUM(COALESCE(b."{label}", 0))::INTEGER'
        else:
            agg_expr = f'ROUND(AVG(b."{label}")::numeric, 1)'

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

    def _get_stat_expression(self, label: str) -> str:
        """
        統計ラベルに対応するSQL式を返す
        DD/TDは計算式で動的に判定する
        """
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
        # 通常のカラム
        else:
            return f'COALESCE(b."{label}", 0)'

    def get_consecutive_games(
        self,
        label: str,
        game_type: Literal["regular", "playoff", "final", "all"] = "regular",
        league: str = "NBA",
        top_n: int = 100,
    ) -> pd.DataFrame:
        """
        連続試合記録（例: ダブルダブル連続試合数）のランキングを取得

        SQLでグループ番号を計算し、連続記録を効率的に取得
        """
        game_type_clause = self._get_game_type_clause(game_type, league)
        exclude_clause = self._get_exclude_clause()

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
    # 7. 条件付き達成回数分析
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
