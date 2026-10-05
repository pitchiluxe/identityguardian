"""Structured logging for packaged deployments (`LOG_FORMAT=json`): one JSON object per line."""

import json
import logging
import time


class JsonFormatter(logging.Formatter):
    def format(self, record):
        line = dict(
            time=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            level=record.levelname,
            logger=record.name,
            message=record.getMessage(),
        )
        if getattr(record, "correlation_id", None):
            line["correlation_id"] = str(record.correlation_id)
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line)


def configure(log_format):
    """Configure the root handler once; text stays the local default."""
    root = logging.getLogger()
    if log_format != "json" or any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
