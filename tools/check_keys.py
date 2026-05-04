"""Quick diagnostic: check ZQ calendar spread key alignment."""
import sys; sys.path.insert(0, '.')
from config.ls_config import TT_MAPPING
from config.fomc_dates import ALL_FOMC_MEETINGS

M2C = {1:'F',2:'G',3:'H',4:'J',5:'K',6:'M',7:'N',8:'Q',9:'U',10:'V',11:'X',12:'Z'}
def _next_ym(ym):
    return (ym[0], ym[1]+1) if ym[1] < 12 else (ym[0]+1, 1)

zq_cals = {k: v for k, v in TT_MAPPING.items() if 'ZQ_CAL' in k}
print(f"ZQ Calendar Spreads configured: {len(zq_cals)}")
for k in sorted(zq_cals):
    print(f"  {k}")

print("\nExpected cal_keys for meetings:")
for mtg in ALL_FOMC_MEETINGS[:12]:
    dec = mtg['decision_date']
    eff = mtg['effective_date']
    ym = (eff.year, eff.month)
    if eff.day > 20:
        front_ym = ym
        back_ym = _next_ym(ym)
    else:
        front_ym = (ym[0], ym[1]-1) if ym[1] > 1 else (ym[0]-1, 12)
        back_ym = _next_ym(ym)
    fc = M2C[front_ym[1]] + str(front_ym[0])[-2:]
    bc = M2C[back_ym[1]] + str(back_ym[0])[-2:]
    cal_key = f"ZQ_CAL_{fc}{bc}"
    configured = cal_key in TT_MAPPING
    print(f"  {dec} eff={eff} day={eff.day} -> {cal_key}  configured={configured}")
