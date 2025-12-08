# 無料データベースホスティング比較（2024年12月調査）

## 背景

NBAスタッツ分析アプリのデータ（約193MB）をホスティングするため、無料のデータベースサービスを調査。

### データサイズ
| ファイル | サイズ | 行数 |
|----------|--------|------|
| boxscore1946-2025.csv | 177MB | 168万行 |
| games1946-2025.csv | 7.5MB | 7.6万行 |
| Players_data_Latest.csv | 340KB | - |
| player_imageURL.csv | 716KB | - |
| **合計** | **約193MB** | - |

---

## サービス比較

| サービス | 無料ストレージ | アップロード制限 | 特徴 |
|----------|---------------|------------------|------|
| **CockroachDB** | 10 GB | なし | 分散DB、$15/月クレジット |
| **Neon** | 3 GB | なし | サーバーレス、PostgreSQL互換 |
| **Aiven** | 5 GB | なし | 専用リソース |
| Supabase | 500 MB | **100MB** | Firebase代替、機能豊富 |
| ElephantSQL | 20 MB | - | テスト用途のみ |

---

## 各サービス詳細

### 1. CockroachDB（推奨候補）

**無料枠：**
- 10GB ストレージ
- 50M Request Units/月
- $15/月相当のクレジット

**メリット：**
- 大容量（10GB）で余裕がある
- 分散DBで高可用性
- クレジットカード不要

**デメリット：**
- PostgreSQL「互換」だが100%同じではない
- 一部SQL構文の違いがある可能性

**料金体系：**
- SELECTクエリ: 1〜15 RU
- INSERT/UPDATE: 10〜25 RU
- 月50M RU = 数百万クエリ可能

### 2. Neon（推奨候補）

**無料枠：**
- 3GB ストレージ（193MBに十分）
- 1プロジェクト
- 10ブランチ
- 共有コンピュート（1GB RAM）

**メリット：**
- PostgreSQL完全互換
- サーバーレス（使わない時はコスト0）
- psqlで直接インポート可能
- ブランチ機能（開発/本番分離）

**デメリット：**
- 共有リソースなのでピーク時に遅くなる可能性

### 3. Supabase

**無料枠：**
- 500MB ストレージ
- 2プロジェクト
- 1GB ファイルストレージ

**メリット：**
- Firebase代替として人気
- 認証、リアルタイム機能付き
- 日本語ドキュメント豊富

**デメリット：**
- **CSVアップロード100MB制限** ← 今回の問題
- GUIでの大量データインポートが困難

### 4. Aiven

**無料枠：**
- 5GB ストレージ
- 1 CPU、1GB RAM
- 専用VM（リソース共有なし）

**メリット：**
- 専用リソースで安定
- PostgreSQL完全互換

**デメリット：**
- 無料枠は1ノードのみ

---

## 結論

### 今回のアプリに最適なサービス

**第1候補: Neon**
- 理由: PostgreSQL完全互換、3GBで十分、psqlインポート可能

**第2候補: CockroachDB**
- 理由: 10GBの大容量、評判が良い、ただしSQL互換性要確認

**見送り: Supabase**
- 理由: 100MBアップロード制限で168万行のCSVインポートが困難

---

## 参考リンク

- [Neon](https://neon.tech)
- [CockroachDB Cloud](https://cockroachlabs.cloud)
- [Supabase](https://supabase.com)
- [Aiven](https://aiven.io)
- [Top PostgreSQL Database Free Tiers - Koyeb](https://www.koyeb.com/blog/top-postgresql-database-free-tiers-in-2025)
