"""NBA公式カラーテーマ カスタムCSS"""

# カラーパレット - Official NBA Colors
COLORS = {
    "nba_blue": "#17408B",  # Official NBA Blue
    "nba_red": "#C9082A",   # Official NBA Red
    "bg_dark": "#050B14",   # Deep Navy Background
    "bg_card": "#0D1B2E",   # Lighter Navy for cards
    "bg_hover": "#1A2D45",
    "text_primary": "#FFFFFF",
    "text_secondary": "#B0B8C1",
    "accent_gold": "#FDB927", # Lakers Gold / Accent
    "chart_bar": "#17408B",   # Blue bars
    "chart_grid": "#233345",
}

# Streamlit用カスタムCSS
CUSTOM_CSS = """
<style>
/* 全体の背景 */
.stApp {
    background-color: #050B14;
}

/* ヘッダー */
.stApp header {
    background-color: #050B14;
}

/* サイドバー */
[data-testid="stSidebar"] {
    background-color: #0D1B2E;
    min-width: 350px;
    border-right: 1px solid #1A2D45;
}

[data-testid="stSidebar"] .stMarkdown {
    color: #FFFFFF;
}

/* チャット入力 */
.stChatInput {
    border-color: #17408B !important;
}

.stChatInput:focus-within {
    border-color: #C9082A !important;
    box-shadow: 0 0 0 1px #C9082A !important;
}

/* チャットメッセージ - ユーザー */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background-color: #17408B;
    border-radius: 12px;
    margin: 8px 0;
    border: 1px solid #2C5AA0;
}

/* チャットメッセージ - アシスタント */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background-color: #0D1B2E;
    border-radius: 12px;
    margin: 8px 0;
    border: 1px solid #1A2D45;
}

/* ボタン - プライマリ */
.stButton > button {
    background-color: #C9082A;
    color: white;
    border: none;
    border-radius: 4px; /* Slightly sharper corners for sports feel */
    padding: 0.5rem 1.25rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    transition: all 0.2s;
}

.stButton > button:hover {
    background-color: #E31837;
    border: none;
    transform: translateY(-1px);
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
}

/* ダウンロードボタン */
.stDownloadButton > button {
    background-color: #17408B;
    color: white;
    border: none;
    border-radius: 4px;
    font-weight: 600;
}

.stDownloadButton > button:hover {
    background-color: #2C5AA0;
}

/* タブ */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
}

.stTabs [data-baseweb="tab"] {
    background-color: #0D1B2E;
    color: #B0B8C1;
    border-radius: 4px 4px 0 0;
    padding: 8px 16px;
    border: 1px solid transparent;
}

.stTabs [aria-selected="true"] {
    background-color: #1A2D45;
    color: #FFFFFF;
    border-bottom: 2px solid #C9082A;
}

/* データフレーム */
.stDataFrame {
    background-color: #0D1B2E;
    border: 1px solid #1A2D45;
}

/* スピナー */
.stSpinner > div {
    border-top-color: #C9082A !important;
}

/* エラーメッセージ */
.stAlert {
    background-color: rgba(201, 8, 42, 0.15);
    border: 1px solid #C9082A;
    color: #FFCDD2;
}

/* 成功メッセージ */
.stSuccess {
    background-color: rgba(23, 64, 139, 0.15);
    border: 1px solid #17408B;
    color: #BBDEFB;
}

/* タイトル */
h1 {
    color: #FFFFFF !important;
    text-shadow: 2px 2px 0px #17408B; /* NBA Blue shadow */
    font-weight: 800 !important;
    letter-spacing: -1px;
}

/* サブタイトル */
h2, h3 {
    color: #FFFFFF !important;
    border-left: 4px solid #C9082A;
    padding-left: 12px;
}

/* 通常テキスト */
p, span, label, li {
    color: #E0E6ED !important;
}

/* チャットメッセージ内のテキスト */
[data-testid="stChatMessage"] p {
    color: #FFFFFF !important;
}

/* マークダウンテキスト */
.stMarkdown {
    color: #E0E6ED !important;
}

/* コード */
code {
    background-color: #1A2D45 !important;
    color: #FDB927 !important; /* Lakers Gold */
    padding: 2px 6px !important;
    border-radius: 4px !important;
    border: 1px solid #2A3F55;
    font-family: 'Courier New', Courier, monospace;
}

/* stCodeブロック */
[data-testid="stCode"] {
    background-color: #0D1B2E !important;
    border: 1px solid #1A2D45;
}

[data-testid="stCode"] code {
    color: #FDB927 !important;
    background-color: transparent !important;
    border: none;
}

[data-testid="stCode"] pre {
    background-color: #0D1B2E !important;
    color: #FDB927 !important;
}

/* エクスパンダー */
.streamlit-expanderHeader {
    background-color: #0D1B2E;
    color: #FFFFFF;
    border: 1px solid #1A2D45;
    border-radius: 4px;
}

/* メトリクス */
[data-testid="stMetricValue"] {
    color: #FFFFFF;
    text-shadow: 0 0 10px rgba(23, 64, 139, 0.8);
}

[data-testid="stMetricLabel"] {
    color: #B0B8C1;
}

/* セレクトボックス */
.stSelectbox > div > div {
    background-color: #0D1B2E;
    color: #FFFFFF;
    border-color: #1A2D45;
}

/* リンク */
a {
    color: #5C9DFF !important;
    text-decoration: none;
}
a:hover {
    text-decoration: underline;
    color: #82B6FF !important;
}
</style>
"""


def get_plotly_theme():
    """Plotlyグラフ用のテーマ設定を返す"""
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"color": COLORS["text_primary"]},
        "xaxis": {
            "gridcolor": COLORS["chart_grid"],
            "zerolinecolor": COLORS["chart_grid"],
        },
        "yaxis": {
            "gridcolor": COLORS["chart_grid"],
            "zerolinecolor": COLORS["chart_grid"],
        },
    }


def get_bar_color():
    """棒グラフの色を返す"""
    return COLORS["chart_bar"]
