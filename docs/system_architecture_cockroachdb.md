# システム構成（CockroachDB版）

## アーキテクチャ概要

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Streamlit      │────▶│  Claude API     │     │  CockroachDB    │
│  Cloud          │     │  (Haiku 4.5)    │     │  Cloud          │
│                 │◀────│                 │     │                 │
│  - UI表示       │     │  - クエリ解析   │     │  - データ保存   │
│  - 可視化       │─────────────────────────────▶│  - SQL実行      │
│  - テーブル表示 │◀─────────────────────────────│                 │
│                 │                             │                 │
└─────────────────┘                             └─────────────────┘
```

## 処理フロー

1. **ユーザー入力** → Streamlit Cloud
2. **プロンプト解析** → Claude Haiku API でSQLまたは分析パラメータに変換
3. **データ取得** → CockroachDB にSQLクエリ実行
4. **結果処理** → pandas/Polars で集計・加工
5. **可視化** → Plotly でグラフ生成
6. **表示** → Streamlit で結果表示

---

## スピードに関する考慮点

### 懸念と対策

| 懸念 | 影響 | 対策 |
|------|------|------|
| DB接続のレイテンシ | 毎回接続で100-200ms | コネクションプーリング |
| 大量データの転送 | 168万行全取得は遅い | **SQLで集計してから取得** |
| 無料枠の共有リソース | ピーク時に遅延 | インデックス最適化 |

### 最適化戦略

**従来（全データメモリ読み込み）:**
```python
# ❌ 遅い: 168万行をメモリに読み込んでからフィルタ
df = pd.read_csv("boxscore.csv")  # 数GB使用
result = df[df["playerName"] == "LeBron James"]
```

**新方式（SQLで事前フィルタ）:**
```python
# ✅ 速い: DBで集計してから必要な行だけ取得
query = """
SELECT playerName, SUM(PTS) as total_pts
FROM boxscore
WHERE age <= 25
GROUP BY playerName
ORDER BY total_pts DESC
LIMIT 30
"""
result = pd.read_sql(query, connection)  # 30行のみ
```

### 期待されるレスポンス時間

| 処理 | 時間（目安） |
|------|-------------|
| Claude API呼び出し | 1-2秒 |
| シンプルなSQLクエリ | 100-500ms |
| 集計クエリ（GROUP BY） | 500ms-2秒 |
| **合計** | **2-4秒** |

※ 現在の全データ読み込み方式より**速くなる可能性が高い**

---

## 必要なインデックス

パフォーマンス向上のため、以下のインデックスを作成：

```sql
-- boxscoreテーブル
CREATE INDEX idx_boxscore_player ON boxscore(playerName);
CREATE INDEX idx_boxscore_game ON boxscore(game_id);
CREATE INDEX idx_boxscore_team ON boxscore(teamName);

-- gamesテーブル
CREATE INDEX idx_games_season ON games(seasonStartYear);
CREATE INDEX idx_games_type ON games(isRegular);
CREATE INDEX idx_games_datetime ON games(datetime);
```

---

## 環境変数

### Streamlit Cloud で設定する secrets

```toml
# .streamlit/secrets.toml（ローカル開発用）
# Streamlit Cloud では Secrets 管理画面で設定

ANTHROPIC_API_KEY = "sk-ant-api03-..."
COCKROACH_DATABASE_URL = "postgresql://username:password@host:26257/database?sslmode=verify-full"
```

---

## 依存パッケージ

```txt
# requirements.txt に追加
psycopg2-binary>=2.9.0  # PostgreSQL接続
sqlalchemy>=2.0.0       # ORM/接続管理
```

---

## CockroachDB 無料枠の制限

| 項目 | 制限 |
|------|------|
| ストレージ | 10 GB |
| Request Units | 50M RU/月 |
| 月額クレジット | $15相当 |

### RU消費の目安

- SELECT（インデックス使用）: 1-5 RU
- SELECT（フルスキャン）: 10-100+ RU
- INSERT: 10-25 RU

**月50M RU = 1日約160万クエリ（軽量SELECT）**

→ 通常利用では全く問題なし

---

## PostgreSQL互換性の注意点

CockroachDBはPostgreSQL互換ですが、一部制限があります：

### 使用可能
- 基本的なSELECT/INSERT/UPDATE/DELETE
- JOIN, GROUP BY, ORDER BY
- ウィンドウ関数
- CTEを (WITH句)

### 注意が必要
- 一部のPostgreSQL拡張機能は未サポート
- COPY FROM STDINの代わりにIMPORT INTO を使用
- 一部のデータ型（geometry等）は未サポート

→ **今回のアプリでは問題になる可能性は低い**

---

## 移行手順

1. CockroachDB Cloud でクラスタ作成
2. テーブル作成（CREATE TABLE）
3. CSVデータインポート（IMPORT INTO）
4. インデックス作成
5. `data_loader.py` をSQL版に書き換え
6. Streamlit Cloud にデプロイ
7. 動作確認
