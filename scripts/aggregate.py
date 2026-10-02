"""records.json -> dashboard_data.json (month x channel x brand x model).

records.json amounts are VAT-inclusive; ser() divides by 1.07 exactly once,
here, on the way out. Do not pre-divide anywhere upstream.
"""
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'data' / 'records.json'
OUT = ROOT / 'data' / 'dashboard_data.json'
VAT_RATE = 0.07

CHANNELS = [  # display order; group = chart color family
    ('K village', 'store'), ('Thaniya', 'store'), ('Central LP', 'store'), ('Cart LP', 'store'),
    ('Online', 'online'), ('Shopee', 'online'), ('Lazada', 'online'),
    ('Event', 'event'), ('Consignment Other', 'consignment'),
    ('Marketing BFT', 'service'), ('Commission', 'service'), ('Car rent', 'service'),
]
GROUPS = ['store', 'online', 'event', 'consignment', 'service']
SERVICE_BRAND = 'Service'  # fee lines: kept out of the brand list and model ranking


def ser(v_vat_incl):
    return round(v_vat_incl / (1 + VAT_RATE), 2)


def main():
    src = json.loads(SRC.read_text(encoding='utf-8'))
    recs = src['records']
    months = sorted({r['month'] for r in recs})

    ch = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, set()]))
    ch_brand = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0])))
    model = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    brand_total = defaultdict(float)
    for r in recs:
        a, q, m, c = r['amount_vat_incl'], r['qty'], r['month'], r['channel']
        e = ch[c][m]; e[0] += a; e[1] += q; e[2].add(r['order_key'])
        b = ch_brand[c][m][r['brand']]; b[0] += a; b[1] += q
        if r['brand'] == SERVICE_BRAND:
            continue
        k = model[m][r['brand'] + '\t' + r['model']]; k[0] += a; k[1] += q
        brand_total[r['brand']] += a

    # VFF shoes: one row per month x channel x model x gender x size x color -> [pairs, amount]
    vff = defaultdict(lambda: [0.0, 0.0])
    for r in recs:
        if r.get('vff_shoe'):
            k = (r['month'], r['channel'], r['model'], r['gender'], r['size'], r['color'])
            vff[k][0] += r['qty']; vff[k][1] += r['amount_vat_incl']
    # payment methods: channel -> month -> method -> amount
    pay = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for p in src.get('payments', []):
        pay[p['channel']][p['month']][p['method']] += p['amount_vat_incl']

    known = {c for c, _ in CHANNELS}
    unknown = set(ch) - known
    assert not unknown, f'unmapped channels: {unknown}'

    out = {
        'generated_at': datetime.now(timezone(timedelta(hours=7))).strftime('%Y-%m-%d %H:%M'),
        'source_file': src['meta']['source_file'],
        'vat_rate': VAT_RATE,
        'months': months,
        'channels': [{'key': c, 'group': g} for c, g in CHANNELS],
        'groups': GROUPS,
        'brands': [b for b, _ in sorted(brand_total.items(), key=lambda x: -x[1])],
        'ch': {c: {m: [ser(v[0]), round(v[1]), len(v[2])] for m, v in mm.items()} for c, mm in ch.items()},
        'ch_brand': {c: {m: {b: [ser(v[0]), round(v[1])] for b, v in bb.items()} for m, bb in mm.items()}
                     for c, mm in ch_brand.items()},
        'model': {m: {k: [ser(v[0]), round(v[1])] for k, v in kk.items()} for m, kk in model.items()},
        'vff': [[*k, round(v[0]), ser(v[1])] for k, v in sorted(vff.items())],
        'pay': {c: {m: {k: ser(v) for k, v in mm.items()} for m, mm in cm.items()} for c, cm in pay.items()},
        'excluded': {k: ser(v) for k, v in src['meta']['excluded_vat_incl'].items()},
        'included': {k: ser(v) for k, v in src['meta'].get('included_vat_incl', {}).items()},
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    total = sum(v[0] for mm in out['ch'].values() for v in mm.values())
    print(f'{len(months)} months, {len(out["brands"])} brands -> {OUT} ({OUT.stat().st_size:,} bytes)')
    print(f'total ex-VAT {total:,.2f}  (VAT-incl {sum(r["amount_vat_incl"] for r in recs):,.2f})')


if __name__ == '__main__':
    main()
