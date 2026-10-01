from . import access, changes, findings, lifecycle, reviews, twin

ROUTERS = [
    twin.router,
    access.router,
    findings.router,
    reviews.router,
    changes.router,
    lifecycle.router,
]
