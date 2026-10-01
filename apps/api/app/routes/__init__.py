from . import (
    access,
    changes,
    connectors,
    findings,
    history,
    investigations,
    labs,
    lifecycle,
    policies,
    reports,
    reviews,
    twin,
)

ROUTERS = [
    twin.router,
    access.router,
    findings.router,
    reviews.router,
    changes.router,
    lifecycle.router,
    history.router,
    investigations.router,
    policies.router,
    labs.router,
    connectors.router,
    reports.router,
]
