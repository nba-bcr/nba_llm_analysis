"""NBA Stats Chat - Streamlitアプリ メインエントリポイント"""

import sys
import random
import urllib.parse
from pathlib import Path

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

from app.styles import CUSTOM_CSS, get_plotly_theme, get_bar_color
from app.llm_interpreter import (
    interpret_query,
    is_valid_interpretation,
    generate_analysis_comment,
    generate_fallback_response,
)
from app.executor_sql import execute_analysis, get_value_column
from app.query_history import save_query, get_recent_queries


# NBA公式YouTubeハイライト動画設定
# 複数の短いハイライト動画からランダム選択
NBA_HIGHLIGHT_VIDEOS = [
    ("MTf2fczHLVc", 0),    # NBA Top 10 Plays
    ("pMe1yxV5vY8", 0),    # Best Dunks 2024
    ("ZVkf2aTPYQk", 0),    # NBA Highlights
    ("Mz8TpX1SBCM", 0),    # Top Plays
    ("H0a5HBUvfCU", 0),    # Best Moments
]


def get_random_highlight_video() -> tuple[str, int]:
    """ランダムなハイライト動画の(video_id, start_time)を返す"""
    return random.choice(NBA_HIGHLIGHT_VIDEOS)


def show_youtube_video(video_id: str, start_time: int = 0, muted: bool = True):
    """
    YouTube動画をiframe埋め込みで表示

    Args:
        video_id: YouTube動画ID
        start_time: 開始秒数
        muted: ミュートするかどうか
    """
    import streamlit.components.v1 as components

    mute_param = "1" if muted else "0"
    iframe_html = f'''
    <div style="display: flex; justify-content: center; margin: 1rem 0;">
        <iframe
            width="560"
            height="315"
            src="https://www.youtube.com/embed/{video_id}?autoplay=1&mute={mute_param}&start={start_time}"
            frameborder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowfullscreen>
        </iframe>
    </div>
    '''
    components.html(iframe_html, height=350)


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
            "10試合スパンでの最高合計得点",
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
    initial_sidebar_state="expanded",
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
        st.markdown("## 📚 使い方")
        st.markdown("""
        質問を入力すると、NBAスタッツを分析して結果を表示します。
        """)

        st.markdown("### 💡 質問例")
        examples = [
            "25歳時点での通算得点ランキング",
            "連続ダブルダブル記録TOP20",
            "連勝記録ランキング",
            "1万得点到達までの試合数TOP15",
            "プレイオフでの40得点ゲーム回数ランキング",
            "10試合スパンでの最高合計得点",
            "35歳以上の通算アシストTOP5",
            "ゲーム別のベストデュエルランキングを見たい",
        ]
        for example in examples:
            if st.button(example, key=f"example_{example}", use_container_width=True):
                st.session_state.pending_query = example
                rerun()

        st.markdown("---")

        st.markdown("### 📊 対応スタッツ")
        st.code("PTS, TRB, AST, STL, BLK, 3P, Win, DD, TD")

        st.markdown("### 🎮 試合タイプ")
        st.markdown("- `regular`: レギュラーシーズン")
        st.markdown("- `playoff`: プレイオフ")
        st.markdown("- `final`: ファイナル")
        st.markdown("- `all`: 全試合")

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
            "📬 ご希望の分析メニューや機能がありましたら "
            "[nba.bcr2022@gmail.com](mailto:nba.bcr2022@gmail.com) "
            "までお気軽にお問い合わせください！"
        )


def create_bar_chart(df, value_col: str, title: str = "", max_display: int = 50, highlight_query: str = "") -> go.Figure:
    """横棒グラフを作成（スクロール対応、選手ハイライト機能付き）"""
    # 表示件数を制限
    plot_df = df.head(max_display).copy()
    n_bars = len(plot_df)

    # クエリに含まれる選手をハイライト
    highlight_color = "#FFD700"  # ゴールド
    normal_color = get_bar_color()

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

    # ランキング番号を追加（1位から順に）
    plot_df = plot_df.reset_index(drop=True)
    plot_df["_display_name"] = plot_df.apply(
        lambda row: f"{row.name + 1}. {row['playerName']}", axis=1
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

    # バーの高さを固定（1バーあたり30px）
    chart_height = max(600, n_bars * 30)

    # テーマ適用
    theme = get_plotly_theme()
    fig.update_layout(
        **theme,
        height=chart_height,
        showlegend=False,
        xaxis_title=value_col,
        yaxis_title="",
        margin=dict(l=10, r=10, t=40, b=10),
    )

    # ラベルのスタイル設定
    fig.update_traces(
        textposition="outside",
        textfont=dict(color="#FFFFFF", size=14),
    )

    # Y軸（選手名）のフォントサイズ（白色）
    fig.update_yaxes(tickfont=dict(size=14, color="#FFFFFF"))

    return fig


def render_result(result_df, parsed: dict, msg_idx: int, comment: str = "", query: str = ""):
    """分析結果を表示"""
    value_col = get_value_column(result_df, parsed)
    func_name = parsed.get("function", "")

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
                    highlight_query=query  # クエリに含まれる選手をハイライト
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
            'display: inline-block; padding: 0.5rem 1rem; '
            'background-color: #1DA1F2; color: white; '
            'text-decoration: none; border-radius: 0.5rem; '
            'font-weight: 600;">𝕏 シェア</a>',
            unsafe_allow_html=True
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

    # 動画を表示
    with video_placeholder.container():
        st.markdown("### 🏀 分析中...")
        st.caption("分析が完了するまでNBAハイライトをお楽しみください")
        video_id, start_time = get_random_highlight_video()
        show_youtube_video(video_id, start_time)

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
                render_result(msg["result"], msg.get("parsed", {}), idx, msg.get("comment", ""), msg.get("query", ""))
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
