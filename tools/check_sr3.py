import sys; sys.path.insert(0, '.')
from core.contracts import build_sr3_contracts
sr3c = build_sr3_contracts()
for c in sr3c[:5]:
    code = c["code"]
    print(f"code={code!r}  last2={code[-2:]!r}")
