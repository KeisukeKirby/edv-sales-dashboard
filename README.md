# EDV 販売実績ダッシュボード

Endeavors Co., Ltd.(EDV)の売上実績。EDV の収入表(Before Vat)を正とし、顧客への販売に加えて Barefoot Inc. へのサービス収入(Marketing BFT / Commission / Car rent)を含む。Barefoot Inc. ダッシュボード([sales-1st-half-26-dashboard](https://github.com/KeisukeKirby/sales-1st-half-26-dashboard))の「対EDV」(Barefoot→EDV の卸請求額)とは別物。

## 構成

- `dashboard.html` / `index.html` — 自己完結HTML(同一内容。データ埋め込み済み、サーバー不要)
- `scripts/etl.py` — 受注システムの販売明細エクスポート `order_detail_*.xlsx` → `data/records.json`(税込・明細行単位、git管理外)
- `scripts/aggregate.py` — `records.json` → `data/dashboard_data.json`(月×チャネル×ブランド×モデル、税抜)
- `scripts/build.py` — `src/template.html` にデータを埋め込み `dashboard.html` と `index.html` を出力

## 更新手順

```
python scripts/etl.py "<path>/order_detail_xxxx.xlsx"   # 省略時は data/raw/ のファイル
python scripts/aggregate.py
python scripts/build.py
```

## 集計ルール

- チャネル12区分(EDV の収入表と同じ列): K village / Thaniya / Central LP(Coollabo) / Cart LP / Online / Shopee / Lazada / Event / Consignment Other / Marketing BFT / Commission / Car rent。グラフは色の判別性のため5系統(実店舗・オンライン・イベント・委託・法人・BFT向けサービス)で色分けし、12区分は表とツールチップで表示
  - Online: Facebook・LINE、販売チャネル空欄の TX 注文(店舗在庫から発送した分を含む)、資産売却収入
  - Event: Event 1・2 に加え、Cart LP のレジで行ったイベント(RC-127、2026/5/21〜24 と同期間の RV)
  - Consignment Other: 委託先への請求書+本社倉庫からの法人・個人請求(1〜6月の Barefoot Inc. への商品請求を含む)
  - Marketing BFT / Commission / Car rent: 商品コード MKT / CMS / CCR の BFT 宛請求。8月の BFT への商品請求は収入表に合わせて Marketing BFT。点数・伝票数・客単価・ブランド分析からは除外
- 除外: Voided、EDV 収入表に無い請求書(etl.py の SHEET_EXCLUDED_INVOICES)
- 正: EDV の収入表(Before Vat)。全12列+Total が月別で一致することを確認済み(2026-09-28、合計 18,889,538.59)
- 金額は注文の `Amount`(注文単位値引き後の実請求額)を明細行の金額比で按分。VAT 7% は `aggregate.py` の `ser()` で1回だけ除算
- 注文番号は店舗間で重複することがあるため、注文番号+倉庫+チャネル+日付で1伝票
- 検算: 計上分+除外分 = 元ファイルの `Amount` 合計(Voided除く)と一致すること
