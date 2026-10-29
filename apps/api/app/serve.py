"""Phase 17 — API launcher (docs/43 §3.2): JSON logs, internal metrics port, then uvicorn.

Uvicorn's access log is off (it prints query strings); the HTTP middleware logs instead.
"""
import uvicorn

from app.core.logging import configure_logging
from app.core.metrics import start_metrics_server


def main() -> None:
    configure_logging()
    start_metrics_server()
    # log_config=None: uvicorn's loggers propagate to the root handler configured above
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, access_log=False, log_config=None)


if __name__ == "__main__":
    main()
