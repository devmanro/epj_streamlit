import pandas as pd
from tools.tools import _canonical_sort_group, normalize_type, commodity_sort_priority

tests = [
    "colis",
    "COLIS",
    "Coli",
    "package",
    "PACKAGES",
    "pkgs",
    "caisses",
    "bobine",
    "BOBINES",
    "coil",
    "COILS",
    "unite",
    "unité",
    "unités",
    "UNITS",
    "pipe",
    "tubes",
    "poutrelles",
    "cornieres",
]

print("=== CANONICAL SORT GROUP & PRIORITY ===")
for t in tests:
    group = _canonical_sort_group(t)
    prio = commodity_sort_priority(t)
    norm = normalize_type(t)
    print(f"'{t}' -> norm: '{norm}', group: '{group}', priority: {prio}")
