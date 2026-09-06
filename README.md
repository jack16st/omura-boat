# ボートレースAI予測・資金配分アプリ

## 実行方法
```bash
pip install streamlit pandas beautifulsoup4 curl_cffi
streamlit run app.py
```

## ファイル構成
- `constants.py` — 会場コード、券種、コース基礎勝率などの定数
- `parsing_utils.py` — rowspan/colspanを展開するテーブル解析共通処理
- `scraper.py` — ①boatrace.jpスクレイピング（出走表・直前情報・オッズ・確定結果）
- `scorer.py` — ②AIスコアリング・推奨フォーメーション選定
- `allocator.py` — ③資金配分（トリガミ防止・利益均等化）
- `settlement.py` — ④収支自動集計・的中判定
- `app.py` — Streamlit UI（①〜④を統合）
- `test_offline.py` — ネットワーク不要な範囲のオフライン検証テスト

## 検証状況（重要）
このサンドボックス環境はネットワークアクセスができないため、`curl_cffi` によるboatrace.jp
への実アクセスはテストできていません。代わりに以下を実施済みです。

- `web_fetch` で実際の以下4ページを取得し、列構成・データ構造を確認済み:
  出走表(racelist)、直前情報(beforeinfo)、3連単オッズ(odds3t)、確定結果(raceresult)
- 上記で確認した列構成を模したHTML断片を使い、`test_offline.py` でパーサ・スコアリング・
  資金配分・収支判定の各ロジックをオフライン検証済み（`python3 test_offline.py` で全件PASS）

### 未検証・要確認の項目
- 実際のHTMLのrowspan/colspanの入り方が、確認した表示内容から推測した構造と完全に一致するか
  （`scraper.py` の出走表・直前情報・3連単オッズパーサ）
- 2連単・2連複 / 拡連複 / 単勝・複勝 のオッズページ構造は未取得のため `_parse_matrix_odds` /
  `_parse_single_odds` は暫定実装（`scraper.py`内に要調整の旨コメント記載）
- 実際のリクエスト頻度に対するサイト側のブロック挙動（`curl_cffi` の `impersonate="chrome110"`
  で回避できるかどうか）

初回はネットワーク接続がある環境で `streamlit run app.py` を実行し、①予測・スコアタブに
実データが表示されるか確認してください。パースに失敗した場合はアプリ画面にエラー内容が
表示され、自動的にモックデータへフォールバックします。
