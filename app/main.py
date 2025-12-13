"""NBA Stats Chat - Streamlitアプリ メインエントリポイント"""

import sys
import random
import urllib.parse
import csv
import re
from pathlib import Path
from typing import Optional

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Streamlitバージョン互換性対応
def rerun():
    """st.rerun() または rerun() を呼び出す"""
    if hasattr(st, 'rerun'):
        st.rerun()
    else:
        rerun()

from app.styles import CUSTOM_CSS, get_plotly_theme, get_bar_color, COLORS, get_team_color
from app.llm_interpreter import (
    interpret_query,
    is_valid_interpretation,
    generate_analysis_comment,
    generate_fallback_response,
)
from app.executor_sql import execute_analysis, get_value_column
from app.query_history import save_query, get_recent_queries


# NBAハイライト動画設定
# data/videos.csv からYouTube動画リストを読み込み
VIDEOS_CSV = Path(__file__).parent.parent / "data" / "videos.csv"


def load_videos_from_csv() -> list[dict]:
    """CSVからYouTube動画リストを読み込む"""
    if not VIDEOS_CSV.exists():
        return []
    videos = []
    with open(VIDEOS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            videos.append({
                "title": row.get("Title", ""),
                "url": row.get("URL", ""),
            })
    return videos


def get_random_video() -> Optional[dict]:
    """ランダムなYouTube動画を返す"""
    videos = load_videos_from_csv()
    if not videos:
        return None
    return random.choice(videos)


def get_youtube_embed_url(url: str) -> str:
    """YouTube URLを埋め込み用URLに変換"""
    # watch?v=VIDEO_ID 形式からVIDEO_IDを抽出
    match = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]+)', url)
    if match:
        video_id = match.group(1)
        return f"https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1"
    return url


def show_loading_video(use_expander: bool = True) -> Optional[dict]:
    """ローディング中のYouTube動画を表示し、動画情報を返す

    Args:
        use_expander: Trueの場合、expanderで開閉可能にする（デフォルト: True）
    """
    video = get_random_video()
    if video and video.get("url"):
        embed_url = get_youtube_embed_url(video["url"])

        # レスポンシブなYouTube埋め込み（16:9アスペクト比を維持）
        responsive_iframe = f'''
        <div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%;">
            <iframe
                src="{embed_url}"
                style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"
                frameborder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen>
            </iframe>
        </div>
        '''

        if use_expander:
            # トグルで開閉可能なexpander
            with st.expander(f"🎬 {video['title']}（クリックで開閉）", expanded=True):
                st.markdown(responsive_iframe, unsafe_allow_html=True)
        else:
            # 従来通りの表示
            st.markdown(f"**🎬 {video['title']}**")
            st.markdown(responsive_iframe, unsafe_allow_html=True)
        return video
    return None


def get_suggested_analyses(query: str) -> list[str]:
    """
    ユーザークエリに基づいて関連する分析を提案

    Args:
        query: ユーザーの質問

    Returns:
        list: 提案する分析例のリスト
    """
    query_lower = query.lower()

    # キーワードベースの提案マッピング
    suggestions_map = {
        # 得点関連
        ("得点", "スコアラー", "点", "pts", "ポイント", "scoring"): [
            "通算得点ランキング",
            "プレイオフでの40得点ゲーム回数",
            "10試合スパンでの合計得点",
        ],
        # アシスト関連
        ("アシスト", "パス", "ast", "assist"): [
            "通算アシストランキング",
            "連続2桁アシスト記録",
            "ターンオーバー0で10アシスト以上の回数",
        ],
        # リバウンド関連
        ("リバウンド", "trb", "reb", "rebound"): [
            "通算リバウンドランキング",
            "連続ダブルダブル記録",
            "20リバウンド以上の試合回数",
        ],
        # GOAT・最高関連
        ("goat", "最高", "史上最高", "ベスト", "最強", "best"): [
            "通算得点ランキング",
            "ファイナルでの得点ランキング",
            "連続ダブルダブル記録TOP20",
        ],
        # 特定選手
        ("レブロン", "lebron", "ジェームズ"): [
            "レブロンのデュエル記録",
            "35歳以上の通算得点ランキング",
        ],
        ("コービー", "kobe", "ブライアント"): [
            "コービーのデュエル記録",
            "プレイオフでの40得点ゲーム回数",
        ],
        ("マイケル", "ジョーダン", "jordan", "mj"): [
            "ファイナルでの得点ランキング",
            "プレイオフ通算得点ランキング",
        ],
        # 年齢関連
        ("若い", "若手", "年齢", "age"): [
            "25歳時点での通算得点ランキング",
            "1万得点到達までの試合数",
        ],
        # プレイオフ関連
        ("プレイオフ", "playoff", "ポストシーズン"): [
            "プレイオフでの40得点ゲーム回数",
            "ファイナルでの得点ランキング",
        ],
        # 連続記録関連
        ("連続", "streak", "連勝", "consecutive"): [
            "連続ダブルダブル記録TOP20",
            "連勝記録ランキング",
        ],
        # 対戦関連
        ("対戦", "デュエル", "vs", "対決", "head to head"): [
            "ゲーム別のベストデュエルランキング",
            "レブロン対カリーのデュエル",
        ],
    }

    suggestions = []
    for keywords, examples in suggestions_map.items():
        if any(kw in query_lower for kw in keywords):
            suggestions.extend(examples)

    # 重複を除去し、最大3件に制限
    seen = set()
    unique_suggestions = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique_suggestions.append(s)
        if len(unique_suggestions) >= 3:
            break

    # 該当なしの場合はデフォルト提案
    if not unique_suggestions:
        unique_suggestions = [
            "25歳時点での通算得点ランキング",
            "連続ダブルダブル記録TOP20",
            "ゲーム別のベストデュエルランキング",
        ]

    return unique_suggestions


def render_fallback_response(query: str, error_message: str):
    """
    フォールバック応答を表示（LLM回答 + 代替分析提案）

    Args:
        query: ユーザーの元のクエリ
        error_message: エラーメッセージまたは説明
    """
    st.warning(f"⚠️ この質問はデータベース分析の対象外です")

    # LLMによる一般回答を生成
    with st.spinner("一般的な情報を検索中..."):
        fallback_text = generate_fallback_response(query)

    st.markdown("### 💬 一般的な情報")
    st.info(fallback_text)

    # 代替分析の提案
    st.markdown("### 📊 代わりにこんな分析はいかがですか？")
    suggestions = get_suggested_analyses(query)

    cols = st.columns(len(suggestions))
    for idx, suggestion in enumerate(suggestions):
        with cols[idx]:
            if st.button(f"📊 {suggestion}", key=f"suggest_{hash(query)}_{idx}"):
                st.session_state.pending_query = suggestion
                rerun()


# ページ設定
st.set_page_config(
    page_title="NBA Player Analytics",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed",  # 初期状態で閉じる（特にモバイル向け）
)

# カスタムCSS適用
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def init_session_state():
    """セッション状態の初期化"""
    if "messages" not in st.session_state:
        st.session_state.messages = []


def render_sidebar():
    """サイドバーを描画"""
    with st.sidebar:
        st.markdown("### 💡 質問例をタップしてみてね！")
        examples = [
            "25歳時点での通算得点ランキング",
            "連続ダブルダブル記録TOP20",
            "連勝記録ランキング",
            "1万得点到達までの試合数TOP15",
            "プレイオフでの40得点ゲーム回数",
            "10試合スパンでの合計得点",
            "35歳以上の通算アシストTOP5",
            "コービー対アイバーソンの直接対決",
            "八村塁のキャリアハイ3P",
            "LALの通算得点ランキング",
        ]
        for example in examples:
            if st.button(example, key=f"example_{example}", use_container_width=True):
                st.session_state.pending_query = example
                rerun()

        # 過去の質問履歴
        recent_queries = get_recent_queries(limit=10)
        if recent_queries:
            st.markdown("---")
            st.markdown("### 📜 過去の質問")
            for q in recent_queries:
                if st.button(q, key=f"history_{q}", use_container_width=True):
                    st.session_state.pending_query = q
                    rerun()

        # フッター
        st.markdown("---")
        st.markdown(
            "📬 こんな分析ほしい！などあれば "
            "[こちら](mailto:nba.bcr2022@gmail.com) "
            "まで気軽にどうぞ〜"
        )

        st.markdown("---")
        st.markdown("### 🔗 フォローしてね！")
        st.markdown(
            "[![YouTube](https://img.shields.io/badge/YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/channel/UChsV5BHncBfIkYejdENFwog) "
            "[![X](https://img.shields.io/badge/X-000000?style=for-the-badge&logo=x&logoColor=white)](https://twitter.com/BcrNba)"
        )


def shorten_player_name(name: str) -> str:
    """選手名を短縮形式に変換（モバイル向け）
    例: "LeBron James" → "L. James"
    """
    parts = name.split()
    if len(parts) >= 2:
        # ファーストネームをイニシャルに
        return f"{parts[0][0]}. {' '.join(parts[1:])}"
    return name


def create_bar_chart(df, value_col: str, title: str = "", max_display: int = 50, highlight_query: str = "", team: str = None) -> go.Figure:
    """横棒グラフを作成（スクロール対応、選手ハイライト機能付き）"""
    # 表示件数を制限
    plot_df = df.head(max_display).copy()
    n_bars = len(plot_df)

    # クエリに含まれる選手をハイライト
    highlight_color = COLORS["accent_gold"]
    # チーム指定がある場合はチームカラーを使用
    team_color = get_team_color(team) if team else None
    normal_color = team_color if team_color else get_bar_color()

    # 選手名がクエリに含まれているかチェック
    def should_highlight(player_name: str) -> bool:
        if not highlight_query:
            return False
        query_lower = highlight_query.lower()
        # フルネームまたは姓・名の一部がクエリに含まれているか
        name_parts = player_name.lower().split()
        return (
            player_name.lower() in query_lower or
            any(part in query_lower for part in name_parts if len(part) > 2)
        )

    plot_df["_highlight"] = plot_df["playerName"].apply(should_highlight)

    # ランキング番号を追加（1位から順に）- 選手名を短縮
    plot_df = plot_df.reset_index(drop=True)
    plot_df["_display_name"] = plot_df.apply(
        lambda row: f"{row.name + 1}. {shorten_player_name(row['playerName'])}", axis=1
    )

    # 逆順にする（1位が上に来るように）
    plot_df = plot_df.iloc[::-1]

    # 色リストを作成
    colors = [highlight_color if h else normal_color for h in plot_df["_highlight"]]

    fig = px.bar(
        plot_df,
        x=value_col,
        y="_display_name",
        orientation="h",
        title=title,
        text=value_col,  # バーにラベル表示
    )

    # 色を適用
    fig.update_traces(marker_color=colors)

    # バーの高さを固定（1バーあたり28px - モバイル向けにコンパクト化）
    chart_height = max(500, n_bars * 28)

    # テーマ適用
    theme = get_plotly_theme()
    fig.update_layout(
        **theme,
        height=chart_height,
        showlegend=False,
        xaxis_title="",  # X軸タイトルを削除（スペース節約）
        yaxis_title="",
        margin=dict(l=100, r=40, t=20, b=20),  # 左余白を増やして選手名表示
    )

    # ラベルのスタイル設定（モバイル向けに小さく）
    fig.update_traces(
        textposition="outside",
        textfont=dict(color="#FFFFFF", size=11),
    )

    # Y軸（選手名）のフォントサイズ（モバイル向けに小さく）
    fig.update_yaxes(tickfont=dict(size=11, color="#FFFFFF"))

    return fig


def render_result(result_df, parsed: dict, msg_idx: int, comment: str = "", query: str = "", video: dict = None):
    """分析結果を表示"""
    value_col = get_value_column(result_df, parsed)
    func_name = parsed.get("function", "")
    # チーム指定を取得（チームカラー用）
    team = parsed.get("params", {}).get("team", None)

    # デュエル分析はテーブルのみ表示
    if func_name == "get_duel_ranking":
        st.markdown(f"**{parsed.get('description', '')}**")
        display_df = result_df.copy()
        if "player_image" in display_df.columns:
            display_df = display_df.drop(columns=["player_image"])
        st.dataframe(display_df, use_container_width=True, height=500)
    else:
        # タブで表示切り替え
        tab_chart, tab_table = st.tabs(["📊 グラフ", "📋 テーブル"])

        with tab_chart:
            if value_col and "playerName" in result_df.columns:
                fig = create_bar_chart(
                    result_df,
                    value_col,
                    title="",  # タイトルは上のコメントと重複するので削除
                    max_display=50,  # 最大50件表示
                    highlight_query=query,  # クエリに含まれる選手をハイライト
                    team=team  # チーム指定時はチームカラーを使用
                )
                # スクロール可能なコンテナでラップ
                with st.container(height=600):
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{msg_idx}")
            else:
                st.info("グラフ表示には対応していないデータ形式です")
                st.dataframe(result_df.head(20), use_container_width=True)

        with tab_table:
            # 表示用に列を整理
            display_df = result_df.copy()
            if "player_image" in display_df.columns:
                display_df = display_df.drop(columns=["player_image"])
            st.dataframe(display_df, use_container_width=True, height=400)

    # 考察コメント表示
    if comment:
        st.markdown("### 💡 考察")
        st.info(comment)

    # ボタンを横並びに（左寄せ）
    col1, col2, col3 = st.columns([1, 1, 4])

    # CSVダウンロード（クエリをファイル名に使用）
    with col1:
        csv = result_df.to_csv(index=False).encode("utf-8")
        # ファイル名に使えない文字を置換
        safe_query = query.replace("/", "_").replace("\\", "_").replace(":", "_")[:50] if query else "result"
        st.download_button(
            label="📥 CSVダウンロード",
            data=csv,
            file_name=f"{safe_query}.csv",
            mime="text/csv",
            key=f"download_{msg_idx}",
        )

    # Xシェアボタン
    with col2:
        # シェア用テキストを作成（TOP3を含む）
        share_text = f"{query}\n\n"
        if "playerName" in result_df.columns and value_col:
            for i, row in result_df.head(3).iterrows():
                rank = result_df.index.get_loc(i) + 1
                share_text += f"{rank}. {row['playerName']}: {row[value_col]}\n"
        share_text += "\n#NBA #NBAStats"

        # URLエンコード
        encoded_text = urllib.parse.quote(share_text)
        twitter_url = f"https://twitter.com/intent/tweet?text={encoded_text}"

        st.markdown(
            f'<a href="{twitter_url}" target="_blank" style="'
            'display: inline-flex; align-items: center; gap: 0.5rem; '
            'padding: 0.5rem 1.2rem; '
            'background-color: #FFFFFF; color: #000000; '
            'text-decoration: none; border-radius: 2rem; '
            'font-weight: 700; font-size: 14px; '
            'box-shadow: 0 2px 4px rgba(0,0,0,0.2); '
            'transition: all 0.2s;">'
            '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">'
            '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>'
            '</svg> ポスト</a>',
            unsafe_allow_html=True
        )

    # 分析完了後の動画リンク表示
    if video and video.get("url"):
        st.markdown("---")
        st.markdown(
            f"🎬 **{video['title']}** の続きはこちら → "
            f"[YouTubeで見る]({video['url']})"
        )


def process_query(query: str):
    """クエリを処理"""
    # ユーザーメッセージを追加
    st.session_state.messages.append({
        "role": "user",
        "content": query,
    })

    # プレースホルダーを作成
    video_placeholder = st.empty()

    # 動画を表示（動画情報を取得）
    with video_placeholder.container():
        st.markdown("### 🏀 分析を実行中です...")
        shown_video = show_loading_video()

    # LLMで解釈
    parsed = interpret_query(query)

    if is_valid_interpretation(parsed):
        # 分析実行
        result, message = execute_analysis(parsed)

        # 動画を削除
        video_placeholder.empty()

        if result is not None:
            # 考察コメントを生成
            comment = generate_analysis_comment(query, result, parsed)

            # 成功した質問を履歴に保存
            save_query(
                query=query,
                description=message,
                function=parsed.get("function")
            )

            st.session_state.messages.append({
                "role": "assistant",
                "content": message,
                "result": result,
                "parsed": parsed,
                "comment": comment,
                "query": query,
                "video": shown_video,  # 表示した動画情報を保存
            })
        else:
            # 分析失敗時のフォールバック
            st.session_state.messages.append({
                "role": "assistant",
                "content": message,
                "is_fallback": True,
                "original_query": query,
            })
    else:
        # 動画を削除
        video_placeholder.empty()
        # 解釈失敗時のフォールバック
        st.session_state.messages.append({
            "role": "assistant",
            "content": parsed.get("description", "リクエストを解釈できませんでした"),
            "is_fallback": True,
            "original_query": query,
        })


def main():
    """メイン関数"""
    init_session_state()

    # タイトル
    st.title("🏀 NBA Player Analytics")
    st.markdown("NBA選手をいろんな角度で分析できます。自然言語で好きな分析をしてみてください！")
    st.markdown("👈 **左上のメニューから質問例が選べます！**")
    st.caption(
        "💡 LLMはClaude Haiku 4.5を使用しています。"
        "選手名が正しい日本語表記にならないことがあります。"
        "APIエラーや分析エラーが発生することもありますが、ご容赦ください🙏"
    )

    # サイドバー
    render_sidebar()

    # チャット履歴を表示（古いStreamlit互換）
    for idx, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            st.markdown(f"**👤 質問:** {msg['content']}")
        else:
            st.markdown(f"**🏀 回答:** {msg['content']}")
            # 結果がある場合は表示
            if "result" in msg:
                render_result(msg["result"], msg.get("parsed", {}), idx, msg.get("comment", ""), msg.get("query", ""), msg.get("video"))
            elif msg.get("is_fallback"):
                # フォールバック応答を表示
                render_fallback_response(msg.get("original_query", ""), msg["content"])
        st.markdown("---")

    # サイドバーの例からのクエリをチェック
    if "pending_query" in st.session_state:
        query = st.session_state.pending_query
        del st.session_state.pending_query
        process_query(query)
        rerun()

    # テキスト入力
    with st.form(key="query_form", clear_on_submit=True):
        prompt = st.text_input("分析したいことを入力（例: コービー対レブロンのデュエル）")
        submit = st.form_submit_button("🔍 分析する")
        if submit and prompt:
            process_query(prompt.strip())
            rerun()


if __name__ == "__main__":
    main()
