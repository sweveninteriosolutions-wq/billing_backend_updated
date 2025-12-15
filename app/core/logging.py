import logging
import sys
from logging.config import dictConfig
from app.core.config import APP_ENV

LOG_LEVEL = "DEBUG" if APP_ENV == "development" else "INFO"


def setup_logging():
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": (
                        "%(asctime)s | %(levelname)s | "
                        "%(name)s | %(message)s"
                    ),
                },
                "access": {
                    "format": (
                        "%(asctime)s | ACCESS | "
                        "%(client_addr)s | %(method)s | "
                        "%(path)s | %(status_code)s | "
                        "%(process_time_ms)sms"
                    ),
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "default",
                },
            },
            "root": {
                "level": LOG_LEVEL,
                "handlers": ["console"],
            },
        }
    )
