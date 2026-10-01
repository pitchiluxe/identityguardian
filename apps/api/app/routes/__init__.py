from . import access, changes, findings, history, investigations, lifecycle, policies, reviews, twin

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
]
