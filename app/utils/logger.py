# app/utils/logger.py
# ERP-056: get_logger(name) is a one-line wrapper around logging.getLogger(name)
# that adds no value. It is kept here for backward compatibility so that all
# existing callers (`from app.utils.logger import get_logger`) continue to work
# without a mass-refactor.
#
# New code should import directly:
#     import logging
#     logger = logging.getLogger(__name__)
#
# This file can be deleted once all callers have been updated to the stdlib pattern.

import logging

def get_logger(name: str) -> logging.Logger:
    """Deprecated thin wrapper — use `logging.getLogger(name)` directly."""
    return logging.getLogger(name)
