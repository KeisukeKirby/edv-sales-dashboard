# EDV 販売実績ダッシュボード

Endeavors Co., Ltd.(EDV)自身の小売販売実績。Barefoot Inc. ダッシュボード([sales-1st-half-26-dashboard](https://github.com/KeisukeKirby/sales-1st-half-26-dashboard))の「対EDV」(Barefoot→EDV の卸請求額)とは別物。

## 構成

- `dashboard.html` / `index.html` — 自己完結HTML(同一内容。データ埋め込み済み、サーバー不要)
- `scripts/etl.py` — 受注システムの販売明細エクスポート `order_detail_*.xlsx` → `data/records.json`(税込・明細行単位、git管理外)
- `scripts/aggregate.py` — `records.json` → `data/dashboard_data.json`(月×チャネル×ブランド×モデル、税抜)
- `scripts/build.py` — `src/template.html` にデータを埋め込み `dashboard.html` と `index.html` を出力

## 更新手順

```
python scripts/etl.py "<path>/order_detail_xxxx.xlsx"
python scripts/aggregate.py
python scripts/build.py
```

## 集計ルール

- チャネル10区分: K village / Thaniya / Central LP(Coollabo) / Cart LP / Online(Facebook・LINE・直販) / Shopee / Lazada / Event(Event 1・2) / Consignment(委託先への請求書) / Other(本社倉庫からの法人請求)。グラフは色の判別性のため5系統(実店舗・オンライン・イベント・委託販売・その他)で色分けし、10区分は表とツールチップで表示
- 除外: EDV→Barefoot Inc. への請求(サービス料・商品のグループ内取引)、商品以外の行、Voided
- 金額は注文の `Amount`(注文単位値引き後の実請求額)を明細行の金額比で按分。VAT 7% は `aggregate.py` の `ser()` で1回だけ除算
- 注文番号は店舗間で重複することがあるため、注文番号+倉庫+チャネル+日付で1伝票
- 検算: 計上分+除外分 = 元ファイルの `Amount` 合計(Voided除く)と一致すること
