"""Switch each constraint off in turn and report which ones actually decide.

Same move as the pillar ablation in `gbs-location-selection`. A constraint that
changes nothing when removed is decoration: it appears in the model, it appears
on the slide, and it is not doing any work. Saying so is more useful than
listing it.
"""

from __future__ import annotations

from dataclasses import dataclass

from tom.baseline import difference_share
from tom.solve import Infeasible, Scenario, solve
from tom.sod import breaches
from tom.types import Assignment, Instance


@dataclass(frozen=True)
class AblationRow:
    constraint: str
    status: str
    moved: tuple[str, ...]
    moved_share: float
    cost_delta: float
    units_delta: int
    sod_breaches: int

    @property
    def decorative(self) -> bool:
        return self.status == "ok" and not self.moved


def run(
    instance: Instance,
    *,
    scenario: Scenario | None = None,
    **kw,
) -> tuple[Assignment, list[AblationRow]]:
    """Solve once with everything on, then once per constraint removed."""
    base_scenario = scenario or Scenario(
        handoff_price=instance.settings.objective["handoff_cost_usd"]
    )
    full = solve(instance, scenario=base_scenario, **kw)
    base_units = len({u.key for u in full.units.values()})

    rows: list[AblationRow] = []
    for constraint in instance.settings.constraints:
        if not instance.settings.enabled(constraint):
            continue
        without = Scenario(
            **{**base_scenario.__dict__, "disabled": frozenset({constraint})}
        )
        try:
            result = solve(instance, scenario=without, **kw)
        except Infeasible as exc:
            rows.append(AblationRow(constraint, f"infeasible: {exc}", (), 0.0, 0.0, 0, 0))
            continue
        share, moved = difference_share(full, result)
        rows.append(AblationRow(
            constraint=constraint,
            status="ok",
            moved=moved,
            moved_share=share,
            cost_delta=result.total_cost - full.total_cost,
            units_delta=len({u.key for u in result.units.values()}) - base_units,
            sod_breaches=len(breaches(result.units)),
        ))
    return full, rows
