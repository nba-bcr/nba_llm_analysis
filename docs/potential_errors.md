# NBA Stats Chat - 潜在的なエラー分析

## 質問例とエラー予測

### 1. 「25歳時点での通算得点ランキング」
- **関数**: `get_ranking_by_age`
- **パラメータ**: `label="PTS"`, `max_age=25`
- **ステータス**: ✅ 修正済み（AGE()関数をCockroachDB互換に変更）
- **潜在的エラー**: なし

### 2. 「連続ダブルダブル記録TOP20」
- **関数**: `get_consecutive_games`
- **パラメータ**: `label="DD"`, `top_n=20`
- **ステータス**: ✅ 修正済み（DD動的計算を追加）
- **潜在的エラー**: なし

### 3. 「連勝記録ランキング」 ⚠️
- **関数**: `get_consecutive_games`
- **パラメータ**: `label="Win"`
- **ステータス**: ⚠️ **エラーの可能性大**
- **問題**:
  - boxscoreテーブルに`Win`カラムが存在しない
  - `Win`はgamesテーブルの`Winner`カラムとboxscoreの`teamName`を比較して計算する必要がある
- **予想エラー**: `column "b.Win" does not exist`
- **修正案**: `_get_stat_expression`に`Win`パターンを追加し、`CASE WHEN b."teamName" = g."Winner" THEN 1 ELSE 0 END`を返す

### 4. 「1万得点到達までの試合数TOP15」
- **関数**: `get_games_to_reach`
- **パラメータ**: `label="PTS"`, `threshold=10000`, `top_n=15`
- **ステータス**: ⚠️ **潜在的な問題**
- **問題**: `b."{label}"`を直接使用しているが、DD/TD/閾値パターンには未対応
- **潜在的エラー**: PTSは通常カラムなので問題なし

### 5. 「プレイオフでの40得点ゲーム回数ランキング」
- **関数**: `get_ranking_by_age`（または`get_filtered_achievement_count`）
- **パラメータ**: `label="40PTS+"`, `game_type="playoff"`
- **ステータス**: ✅ 修正済み（閾値パターン対応を追加）
- **潜在的エラー**: なし

### 6. 「10試合スパンでの最高合計得点」
- **関数**: `get_n_game_span_ranking`
- **パラメータ**: `label="PTS"`, `n_games=10`
- **ステータス**: ⚠️ **潜在的な問題**
- **問題**: `b."{label}"`を直接使用。DD/TD/閾値パターンには未対応
- **潜在的エラー**: PTSは通常カラムなので問題なし。DD/TDを指定するとエラー

### 7. 「35歳以上の通算アシストTOP5」
- **関数**: `get_ranking_by_age`
- **パラメータ**: `label="AST"`, `min_age=35`, `top_n=5`
- **ステータス**: ✅ 動作するはず
- **潜在的エラー**: なし

### 8. 「ゲーム別のベストデュエルランキングを見たい」
- **関数**: `get_duel_ranking`
- **パラメータ**: `label="PTS"`, `game_type="all"`
- **ステータス**: ✅ 修正済み（player_filterのバグ修正）
- **潜在的エラー**: なし

---

## 存在しないカラム問題

### boxscoreテーブルのカラム
```
game_id, teamName, playerName, MP, FG, FGA, 3P, 3PA, FT, FTA,
ORB, DRB, TRB, AST, STL, BLK, TOV, PF, PTS, +/-, isStarter, GmSc
```

### gamesテーブルのカラム
```
seasonStartYear, awayTeam, pointsAway, homeTeam, pointsHome,
attendance, notes, startET, datetime, isRegular, game_id,
League, isFinal, isPlayin, Winner, Arena
```

### 計算が必要なカラム
| ラベル | 説明 | 計算式 |
|--------|------|--------|
| DD | ダブルダブル | PTS,TRB,AST,STL,BLKのうち2つ以上が10以上 |
| TD | トリプルダブル | 同上で3つ以上が10以上 |
| Win | 勝利 | `b."teamName" = g."Winner"` |
| 40PTS+ | 40得点以上 | `PTS >= 40` |
| 20TRB+ | 20リバウンド以上 | `TRB >= 20` |
| 10AST+ | 10アシスト以上 | `AST >= 10` |

---

## 優先修正項目

### 高優先度
1. **Win計算の追加** - 「連勝記録ランキング」が動作しない

### 中優先度
2. **get_games_to_reach**への`_get_stat_expression`適用
3. **get_n_game_span_ranking**への`_get_stat_expression`適用

---

## 実際に発生したエラー履歴

| 日時 | 質問 | エラー | 修正状況 |
|------|------|--------|----------|
| - | 25歳時点での通算得点ランキング | `AGE(date, date)` 未対応 | ✅ 修正済み |
| - | 連続ダブルダブル記録TOP20 | `column "b.DD" does not exist` | ✅ 修正済み |
| - | プレイオフでの40得点ゲーム回数ランキング | `column "b.40PTS+" does not exist` | ✅ 修正済み |
