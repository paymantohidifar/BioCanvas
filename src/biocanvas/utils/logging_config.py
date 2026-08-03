# biocanvas/utils/logging_config.py
"""Logging configuration, log-level helpers, and the HTML display utility."""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional
from IPython.display import display, HTML  # type: ignore
from ipywidgets import widgets  # type: ignore
import biocanvas.styles as styles
from biocanvas.utils.helpers import LogEntry

logger = logging.getLogger(__name__)


class _PackageLogFilter(logging.Filter):
    """Only allows log records from loggers whose name starts with package_prefix."""

    def __init__(self, package_prefix: str) -> None:
        super().__init__()
        self.package_prefix = package_prefix

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith(self.package_prefix)


LOG_LEVEL_MAP: Dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def setup_logging(
    log_level: int = logging.INFO,
    log_file: Optional[str] = None,
    reset_handlers: bool = True,
    console: bool = True,
    file_only_package: Optional[str] = "biocanvas",
    update_root_level: bool = True,
) -> None:
    """Set up logging for the current module.

    Use DEBUG during development for full logger.debug() output; use INFO or
    WARNING for production or less verbose runs.

    Args:
        log_level: The logging level to use for new handlers and, when
            update_root_level is True, for the root logger itself.
        log_file: The file to log to.
        reset_handlers: Whether to reset the handlers.
        console: If True, add a handler that writes to stdout. Set to False in
            notebooks to avoid cluttering cell output (logs still go to log_file
            if provided).
        file_only_package: If set, only log records from loggers whose name
            starts with this string are written to the log file. Use None to
            log everything. Default 'biocanvas' limits the file to this
            package.
        update_root_level: If True (default), also set the root logger level to
            log_level. Pass False when appending a secondary handler (e.g. the
            meta_qc file) so that the root level set by an earlier call is
            preserved — without this guard the root would be raised to INFO,
            silently discarding DEBUG records before any handler sees them.
    """
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )

    root_logger = logging.getLogger()
    if update_root_level:
        root_logger.setLevel(log_level)

    # Avoid duplicate logs if setup_logging() is called multiple times (common in Jupyter)
    if reset_handlers and root_logger.handlers:
        root_logger.handlers.clear()

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        if file_only_package is not None:
            file_handler.addFilter(_PackageLogFilter(file_only_package))
        root_logger.addHandler(file_handler)


def apply_root_log_level(
    level: int, *, preserve_meta_qc_min_level: int = logging.INFO
) -> None:
    """Apply a new log level to the root logger and all its handlers at runtime.

    The meta_qc file handler is protected by preserve_meta_qc_min_level so it
    never drops below INFO; all other handlers (including the debug file) follow
    the requested level exactly.

    Args:
        level: New logging level to apply (e.g. logging.DEBUG, logging.INFO).
        preserve_meta_qc_min_level: Floor level for the meta_qc.log handler.
            Defaults to logging.INFO so that QC records are always captured.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        basename = os.path.basename(getattr(handler, "baseFilename", ""))
        if basename == "meta_qc.log":
            handler.setLevel(max(level, preserve_meta_qc_min_level))
        else:
            handler.setLevel(level)


def classify_msg_level(msg: str) -> str:
    """Infers an HTML log severity level from the content of a message string.

    Args:
        msg: The log message to classify.

    Returns:
        'success' if the message indicates success, 'error' if it indicates a
        failure, or 'warning' for anything else.
    """
    lower = msg.lower()
    if lower.startswith("successfully"):
        return "success"
    if any(lower.startswith(kw) for kw in ("error", "failed")):
        return "error"
    return "warning"


def display_log_html(
    output_widget: widgets.Output, log_entries: List[LogEntry]
) -> None:
    """Renders structured log entries as styled HTML into an ipywidgets Output widget.

    Each entry is rendered as a styled <div>; 'separator' entries render as an <hr>.
    Must be called from the main thread — writes directly to the output widget.

    Args:
        output_widget: The ipywidgets Output widget to render into.
        log_entries: A list of (message, level) tuples. Accepted levels are
            'header', 'success', 'warning', 'error', and 'separator'.
    """
    html_parts: List[str] = []
    for message, level in log_entries:
        if level == "separator":
            html_parts.append(f'<hr style="{styles.LOG_STYLES["separator"]}">')
        else:
            css = styles.LOG_STYLES.get(level, "")
            html_parts.append(f'<div style="{css}">{message}</div>')
    with output_widget:
        display(HTML("".join(html_parts)))
