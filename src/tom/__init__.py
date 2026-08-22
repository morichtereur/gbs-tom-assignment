"""Target operating model assignment for purchase-to-pay.

The solver core is importable and testable without the web layer:

    from tom import load_instance, solve
    instance = load_instance()
    result = solve(instance, handoff_price=6.0)
"""

from tom.config import load_instance, load_settings           # noqa: F401
from tom.solve import solve                                    # noqa: F401
from tom.baseline import naive_baseline                        # noqa: F401
from tom.types import (                                        # noqa: F401
    Activity, Assignment, Edge, Instance, Location, Settings, Unit,
)

__all__ = [
    "load_instance", "load_settings", "solve", "naive_baseline",
    "Activity", "Assignment", "Edge", "Instance", "Location", "Settings", "Unit",
]
