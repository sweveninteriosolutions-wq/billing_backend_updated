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

            # -----------------
            # FORMATTERS
            # -----------------
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

            # -----------------
            # HANDLERS
            # -----------------
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "default",
                },
                "access_console": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "access",
                },
            },

            # -----------------
            # LOGGERS
            # -----------------
            "loggers": {
                # Used by request_logging_middleware
                "access": {
                    "handlers": ["access_console"],
                    "level": "INFO",
                    "propagate": False,
                },
            },

            # -----------------
            # ROOT LOGGER
            # -----------------
            "root": {
                "level": LOG_LEVEL,
                "handlers": ["console"],
            },
        }
    )
