"""Run inside gbs-location-selection's virtualenv, from its repo root.

Emits the scored panel as JSON on stdout: the eleven evidenced GBS cities plus
the country-level markets, with wage carried per ISCO group rather than
pre-blended. Which ISCO group an activity draws on is the downstream study's
own mapping, so it has to be able to choose the components itself.
"""

import json

from src import config as C
from src.panel import build, with_centres

panel = with_centres(build())

print(json.dumps({
    "source": "gbs-location-selection",
    "hq": C.HQ,
    "hq_label": C.HQ_BY_KEY[C.HQ][0],
    "isco_groups": list(C.ISCO_GROUPS),
    "wage_blend_declared": C.WAGE_BLEND,
    "locations": [
        {
            "key": key,
            "city": key.split(":", 1)[1] if ":" in key else None,
            "market": m.iso2,
            "market_name": m.name,
            "market_type": m.market_type,
            "is_city": ":" in key,
            "cost_usd_month": m.cost_usd_aged if m.cost_usd_aged is not None else m.cost_usd,
            "cost_year": m.cost_year,
            "wage_components_usd": m.wage_components_usd,
            "cost_city_level": m.region_index is not None,
            "wage_drift": m.wage_cagr,
            "timezone_overlap_hours": m.timezone_overlap,
            "governance": m.risk_score,
            "employers": m.employers,
            "postings_in_scope": m.postings_in_scope,
            "language_share": m.language_share,
            "languages": list(m.languages or ()),
            "transactional_share": m.transactional_share,
            "judgment_share": m.judgment_share,
        }
        for key, m in panel.items()
    ],
}))
