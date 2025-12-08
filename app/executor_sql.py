"""分析実行モジュール - NBAAnalyzerSQLを呼び出して結果を返す（SQL版）"""

import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

# srcモジュールへのパスを追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_sql import NBAAnalyzerSQL
from src.db_connection import get_connection


# 利用可能な関数のマッピング
AVAILABLE_FUNCTIONS = {
    "get_ranking_by_age",
    "get_consecutive_games",
    "get_games_to_reach",
    "get_n_game_span_ranking",
    "get_season_achievement_count",
    "get_duel_ranking",
    "get_filtered_achievement_count",
    "get_player_career_high",
    "get_player_starter_comparison",
    "get_bench_player_ranking",
    "get_combined_achievement_count",
}


@st.cache_resource(show_spinner=False)
def get_analyzer():
    """
    アナライザーを取得（キャッシュ）
    """
    return NBAAnalyzerSQL(exclude_duplicate_names=True)


def get_player_images() -> pd.DataFrame:
    """選手画像データを取得"""
    query = """
    SELECT "playerName", image_url AS player_image
    FROM player_image
    """
    try:
        with get_connection() as conn:
            return pd.read_sql(query, conn)
    except Exception:
        return pd.DataFrame(columns=["playerName", "player_image"])


def merge_player_image(df: pd.DataFrame) -> pd.DataFrame:
    """結果DataFrameに選手画像をマージ"""
    if "playerName" not in df.columns:
        return df

    images = get_player_images()
    if images.empty:
        return df

    # マージ
    result = df.merge(images, on="playerName", how="left")
    return result


def execute_analysis(parsed: dict):
    """
    LLMが解釈した結果を元に分析を実行

    Args:
        parsed: LLMの解釈結果
            {
                "function": "get_ranking_by_age",
                "params": {"label": "PTS", "max_age": 25, ...},
                "description": "説明文"
            }

    Returns:
        tuple: (結果DataFrame, メッセージ)
    """
    func_name = parsed.get("function")
    params = parsed.get("params", {})
    description = parsed.get("description", "分析を実行しました")

    # 関数が指定されていない場合
    if func_name is None:
        return None, description

    # 許可されていない関数の場合
    if func_name not in AVAILABLE_FUNCTIONS:
        return None, f"「{func_name}」は対応していない分析タイプです"

    try:
        # アナライザーを取得（キャッシュ済み）
        analyzer = get_analyzer()

        # パラメータのクリーンアップ
        params = _clean_params(func_name, params)

        # 関数を取得して実行
        method = getattr(analyzer, func_name)
        result = method(**params)

        # 結果が空の場合
        if result is None or len(result) == 0:
            return None, "条件に一致するデータが見つかりませんでした"

        # 選手画像をマージ
        if "playerName" in result.columns:
            result = merge_player_image(result)

        return result, description

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, f"分析中にエラーが発生しました: {str(e)}"


def _clean_params(func_name: str, params: dict) -> dict:
    """
    パラメータをクリーンアップ（型変換、不要パラメータの除去）
    """
    cleaned = {}

    # 各関数で許可されているパラメータ
    allowed_params = {
        "get_ranking_by_age": {
            "label", "max_age", "min_age", "min_games", "aggfunc",
            "league", "game_type", "top_n", "is_starter", "team"
        },
        "get_consecutive_games": {
            "label", "game_type", "league", "top_n", "team"
        },
        "get_games_to_reach": {
            "label", "threshold", "game_type", "league", "top_n"
        },
        "get_n_game_span_ranking": {
            "label", "n_games", "game_type", "league", "top_n"
        },
        "get_season_achievement_count": {
            "label", "threshold", "league", "top_n"
        },
        "get_duel_ranking": {
            "label", "game_type", "min_total", "player1", "player2", "top_n"
        },
        "get_filtered_achievement_count": {
            "count_column", "count_threshold", "filter_column", "filter_op",
            "filter_value", "game_type", "league", "top_n"
        },
        "get_player_career_high": {
            "player_name", "label", "game_type", "league", "top_n"
        },
        "get_player_starter_comparison": {
            "player_name", "label", "game_type", "league"
        },
        "get_bench_player_ranking": {
            "label", "game_type", "league", "min_games", "top_n", "season"
        },
        "get_combined_achievement_count": {
            "thresholds", "game_type", "league", "top_n"
        },
    }

    allowed = allowed_params.get(func_name, set())

    for key, value in params.items():
        # 許可されていないパラメータはスキップ
        if key not in allowed:
            continue

        # None値はスキップ
        if value is None:
            continue

        # 型変換
        if key in ("max_age", "min_age", "min_games", "threshold", "n_games", "top_n", "min_total", "count_threshold", "filter_value", "season"):
            try:
                value = int(value)
            except (ValueError, TypeError):
                continue

        # dict型（thresholds）の処理
        if key == "thresholds":
            if isinstance(value, dict):
                # 値を整数に変換
                value = {k: int(v) for k, v in value.items()}
            else:
                continue

        # bool型変換
        if key == "is_starter":
            if isinstance(value, bool):
                pass  # そのまま
            elif isinstance(value, str):
                value = value.lower() in ("true", "1", "yes")
            elif isinstance(value, (int, float)):
                value = bool(value)
            else:
                continue

        cleaned[key] = value

    # デフォルト値の設定
    if "top_n" not in cleaned:
        cleaned["top_n"] = 10  # デフォルトはTOP10

    if "game_type" not in cleaned:
        cleaned["game_type"] = "regular"

    # aggfuncのデフォルトは"sum"（回数をカウントする場合が多いため）
    if func_name == "get_ranking_by_age" and "aggfunc" not in cleaned:
        cleaned["aggfunc"] = "sum"

    return cleaned


def get_value_column(result: pd.DataFrame, parsed: dict) -> Optional[str]:
    """
    グラフ表示用の値列を特定

    Args:
        result: 結果DataFrame
        parsed: LLMの解釈結果

    Returns:
        str: 値列の名前
    """
    # パラメータからラベルを取得
    label = parsed.get("params", {}).get("label")

    if label and label in result.columns:
        return label

    # 一般的な値列名を探す
    for col in ["TotalPTS", "PTS", "TRB", "AST", "STL", "BLK", "3P", "Win", "DD", "TD", "Games", "Count"]:
        if col in result.columns:
            return col

    # playerName以外の数値列を探す
    numeric_cols = result.select_dtypes(include=["int64", "float64"]).columns
    for col in numeric_cols:
        if col != "playerName":
            return col

    return None
