"""EDV (Endeavors) sales ETL.

Reads the order-system export (order_detail_*.xlsx, sheet 'Orders') and writes
data/records.json -- one record per product line, VAT-inclusive amounts.

Scope: EDV's income as its own income sheet reports it (Keisuke, 2026-09-28):
retail/consignment sales plus the service fees EDV bills Barefoot Inc.
(Marketing / Marketing Ads -> 'Marketing BFT', Sales Commission -> 'Commission',
Car rent -> 'Car rent'). Voided orders and the invoices the sheet leaves out
(SHEET_EXCLUDED_INVOICES) are excluded.

Channel rules aligned with EDV's own income sheet (Keisuke, 2026-09-28):
  * Goods invoiced to Barefoot Inc. (Central CL etc.) count as 'Consignment Other'.
  * Asset-sale income (code P) counts, as Online (it is a main-warehouse TX order).
  * TX orders with a blank sales channel are Online even when shipped from a
    store warehouse (Thaniya / Kvillage stock).
  * Receipt series RC-127 on the CART Central LP till (21-24 May 2026) was an
    event, as was the Cart RV receipt in the same window -> Event.
"""
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / 'data' / 'raw' / 'order_detail_202609261433_u4ll.xlsx'  # gitignored; Downloads gets cleaned
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
OUT = ROOT / 'data' / 'records.json'

BFT_CUSTOMER_MARK = 'แบร์ฟุต'  # "บริษัท แบร์ฟุตอิงค์ (ไทยแลนด์) จำกัด"
SERVICE_CHANNEL = {'MKT': 'Marketing BFT', 'CMS': 'Commission', 'CCR': 'Car rent'}  # EDV -> BFT fees
ASSET_SALE_PREFIX = 'P'
CART_EVENT_SERIES = 'R# RC-127-'
CART_EVENT_DAYS = (date(2026, 5, 21), date(2026, 5, 24))

# EDV's income sheet is the source of truth (Keisuke, 2026-09-28). These
# invoices are absent from its sales columns, so they are not counted here.
SHEET_EXCLUDED_INVOICES = {
    'IV202607006': 'bft_goods_jul',  # Central CL goods to BFT, Jul
    'IV202607007': 'bft_goods_jul',  # Central World goods to BFT, Jul
    'IV202607008': 'bft_goods_jul',  # Terminal 21 Rama3 goods to BFT, Jul
    'IV202607013': 'fabric_sale',        # fabric sold to a company, 31 Jul
    'IV202607012': 'tabio_reissue',      # voided in Jul, reissued 31 Aug under the same number
}
# The sheet books August's goods-to-BFT invoices inside its Marketing BFT column.
SHEET_CHANNEL_OVERRIDE = {
    'IV202608010': 'Marketing BFT',  # Central CL goods to BFT, Aug
    'IV202608011': 'Marketing BFT',  # Central LP goods to BFT, Aug
}

# Consignment partners appear as their own Warehouse/Branch on IV invoices.
CONSIGNMENT_WAREHOUSES = {'Banana Run', 'Avarin', 'Runnercart', 'EastWest', 'Highlandner',
                          'Caveman', 'Anvil Camp', 'Pathwild'}
STORE_WAREHOUSES = {
    'Kvillage': 'K village',
    'Thaniya': 'Thaniya',
    'Coollabo Cen LP 3F': 'Central LP',
    'CART Central LP': 'Cart LP',
    'Event 1': 'Event',
    'Event 2': 'Event',
}
ONLINE_CHANNELS = {'Shopee': 'Shopee', 'Lazada': 'Lazada', 'Facebook': 'Online', 'LINE': 'Online'}

BRAND_PREFIX = {
    'VFF': 'VFF', 'CP': 'Coolcore', 'CC': 'Coolcore', 'OLN': 'Oleno', 'BFJ': 'BFJ',
    'MTB': 'TabiRela', 'TBO': 'Tabio', 'KC': 'Tabio', 'SW': 'Swans', 'KA': 'Knockaround',
    'VV': 'Vivo', 'KK': 'Klean Kanteen', 'LN': 'LUNA', 'AQ': 'AQOZ', 'IS': 'Others',
}


def num(v):
    if v is None or v == '':
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(',', '').strip())
    except ValueError:
        return 0.0


def parse_dmy(v):
    d, m, y = (int(x) for x in str(v).strip().split('/'))
    return date(y, m, d)


def code_prefix(code):
    m = re.match(r'^[A-Za-z]+', str(code or ''))
    return m.group(0) if m else ''


def model_from_name(name):
    return str(name).split('(')[0].strip() if name else 'Other'


def classify_channel(wh, ch, order_no, d):
    """Map one order to the 9 reporting channels."""
    order_no = str(order_no)
    if ch in ONLINE_CHANNELS:
        return ONLINE_CHANNELS[ch]
    if not ch and order_no.startswith('TX'):
        return 'Online'  # online order fulfilled from whichever warehouse had stock
    if wh == 'CART Central LP' and (order_no.startswith(CART_EVENT_SERIES) or
                                    (order_no.startswith('RV') and CART_EVENT_DAYS[0] <= d <= CART_EVENT_DAYS[1])):
        return 'Event'
    if wh in STORE_WAREHOUSES:
        return STORE_WAREHOUSES[wh]
    if wh in CONSIGNMENT_WAREHOUSES:
        return 'Consignment Other'
    if wh == 'คลังสินค้าหลัก':  # main warehouse
        # IV = B2B invoice (companies, Barefoot Inc. goods) -> Consignment Other
        return 'Consignment Other' if order_no.startswith('IV') else 'Online'
    if not wh and ch:
        return 'Online'
    return 'Consignment Other'


def main():
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    rows = list(wb['Orders'].iter_rows(values_only=True))
    header = rows[1]  # row 0 is the Orders/Payments/Product data group banner
    ix = {h: i for i, h in enumerate(header) if h}
    data = [r for r in rows[2:] if r[ix['Type']] == 'Sell']  # drops blank + 2 footer rows

    def g(r, k):
        return r[ix[k]]

    # order-level: summed product-line total, and the order's Amount (first line only)
    orders = defaultdict(lambda: {'lines': [], 'line_total': 0.0, 'amount': None})
    excluded = defaultdict(float)
    for r in data:
        if g(r, 'Status') == 'Voided':
            continue
        # order numbers are not unique across branches (TX202606106 is both a
        # Shopee order and a Central LP receipt), so key on branch/channel/date too
        o = orders[(g(r, 'Sales order No.'), g(r, 'Warehouse/Branch'), g(r, 'Sales channel'), g(r, 'Date'))]
        amt = g(r, 'Amount')
        if amt not in (None, ''):
            o['amount'] = num(amt)
        if not g(r, 'Product code') and not g(r, 'Product name'):
            continue  # split-payment rows carry payment info only
        # (code-less lines with a name are real sales, e.g. a fabric B2B invoice)
        o['lines'].append(r)
        o['line_total'] += num(g(r, 'Total amount'))

    records = []
    stats = defaultdict(float)
    included = defaultdict(float)  # judgement-call lines counted as sales, shown on the About tab
    for okey, o in orders.items():
        order_no = okey[0]
        order_key = '|'.join(str(x or '') for x in okey)
        if not o['lines']:
            continue
        first = o['lines'][0]
        cust = g(first, 'Customer name') or ''
        # 'Amount' is what the order actually billed (after order-level %
        # discounts, e.g. consignment invoices at 30% off); prorate it over the
        # product lines. Fall back to the line sum when Amount is missing.
        billed = o['amount'] if o['amount'] is not None else o['line_total']
        ratio = (billed / o['line_total']) if o['line_total'] else 0.0
        for r in o['lines']:
            pc = g(r, 'Product code')
            prefix = code_prefix(pc)
            line_amt = num(g(r, 'Total amount')) * ratio
            if order_no in SHEET_EXCLUDED_INVOICES:
                excluded[SHEET_EXCLUDED_INVOICES[order_no]] += line_amt
                continue
            d = parse_dmy(g(r, 'Date'))
            qty = num(g(r, 'Quantity'))
            if prefix in SERVICE_CHANNEL:
                # a fee, not goods: own brand, and no units so unit KPIs stay product-only
                channel, brand, model, qty = SERVICE_CHANNEL[prefix], 'Service', SERVICE_CHANNEL[prefix], 0.0
            else:
                channel = SHEET_CHANNEL_OVERRIDE.get(order_no) or classify_channel(
                    g(r, 'Warehouse/Branch'), g(r, 'Sales channel'), order_no, d)
                brand = BRAND_PREFIX.get(prefix, 'Others')
                model = model_from_name(g(r, 'Product name'))
                if prefix == ASSET_SALE_PREFIX and re.fullmatch(r'P\d+', str(pc)):
                    model = 'Asset sale'
                    included['asset_sale'] += line_amt
                if BFT_CUSTOMER_MARK in cust:
                    included['bft_goods'] += line_amt
            records.append({
                'date': d.isoformat(),
                'month': d.strftime('%Y-%m'),
                'channel': channel,
                'warehouse': g(r, 'Warehouse/Branch') or '',
                'order_id': order_no,
                'order_key': order_key,
                'brand': brand,
                'model': model,
                'code': pc,
                'category': g(r, 'Category') or '',
                'qty': qty,
                'amount_vat_incl': round(line_amt, 4),
                'payment_status': g(r, 'Payment status'),
            })
            stats['kept_line_total'] += num(g(r, 'Total amount'))
            stats['kept_billed'] += line_amt

    OUT.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        'source_file': SRC.name,
        'excluded_vat_incl': {k: round(v, 2) for k, v in excluded.items()},
        'included_vat_incl': {k: round(v, 2) for k, v in included.items()},
        'kept_line_total_vat_incl': round(stats['kept_line_total'], 2),
        'kept_billed_vat_incl': round(stats['kept_billed'], 2),
    }
    OUT.write_text(json.dumps({'meta': meta, 'records': records}, ensure_ascii=False), encoding='utf-8')

    by_ch = defaultdict(float)
    for rec in records:
        by_ch[rec['channel']] += rec['amount_vat_incl']
    print(f'{len(records)} product lines, {len({r["order_key"] for r in records})} orders -> {OUT}')
    for k, v in sorted(by_ch.items(), key=lambda x: -x[1]):
        print(f'  {k:12s} {v:>14,.2f}')
    print('  total       ', f'{sum(by_ch.values()):>14,.2f}')
    print('excluded:', meta['excluded_vat_incl'])


if __name__ == '__main__':
    main()
