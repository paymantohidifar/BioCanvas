"""Tests for biocanvas.utils.logging_config."""

import logging
import os

from biocanvas.utils import logging_config


class TestSetupLogging:
    """setup_logging and apply_root_log_level behave correctly with multiple calls."""

    def test_debug_records_reach_file_after_two_call_setup(self, tmp_path):
        """Root level stays DEBUG when the secondary call uses update_root_level=False.

        Mirrors the two-call pattern used in core._setup_project_dirs:
          1. setup_logging(DEBUG, debug_file, reset)   <- sets root to DEBUG
          2. setup_logging(INFO,  meta_file, append, update_root_level=False)
        Before the fix, call 2 raised root to INFO and the debug file received
        no DEBUG records.
        """
        debug_log = str(tmp_path / "biocanvas_debug.log")
        meta_log = str(tmp_path / "meta_qc.log")

        logging_config.setup_logging(
            log_level=logging.DEBUG,
            log_file=debug_log,
            console=False,
            file_only_package="biocanvas",
        )
        logging_config.setup_logging(
            log_level=logging.INFO,
            log_file=meta_log,
            console=False,
            reset_handlers=False,
            update_root_level=False,
            file_only_package="biocanvas.test_project.meta",
        )

        try:
            assert logging.getLogger().level == logging.DEBUG, (
                "Root logger level must remain DEBUG after the secondary INFO call"
            )

            test_logger = logging.getLogger("biocanvas.test_module")
            test_logger.debug("debug-sentinel-message")
            test_logger.info("info-sentinel-message")

            # Flush all handlers so content is on disk before we read
            for handler in logging.getLogger().handlers:
                handler.flush()

            with open(debug_log) as f:
                content = f.read()

            assert "debug-sentinel-message" in content, (
                "DEBUG record was not written to the debug log file"
            )
            assert "info-sentinel-message" in content
        finally:
            # Always clean up so handlers don't bleed into other tests on failure
            logging.getLogger().handlers.clear()

    def test_apply_root_log_level_updates_all_handlers(self, tmp_path):
        """apply_root_log_level sets root and handler levels; meta_qc never drops below INFO."""
        debug_log = str(tmp_path / "biocanvas_debug.log")
        meta_log = str(tmp_path / "meta_qc.log")

        logging_config.setup_logging(
            log_level=logging.INFO, log_file=debug_log, console=False
        )
        logging_config.setup_logging(
            log_level=logging.INFO,
            log_file=meta_log,
            console=False,
            reset_handlers=False,
            update_root_level=False,
        )

        logging_config.apply_root_log_level(logging.DEBUG)

        root = logging.getLogger()
        try:
            assert root.level == logging.DEBUG
            for handler in root.handlers:
                basename = os.path.basename(getattr(handler, "baseFilename", ""))
                if basename == "meta_qc.log":
                    assert handler.level == logging.INFO, (
                        "meta_qc handler must not drop below INFO"
                    )
                else:
                    assert handler.level == logging.DEBUG
        finally:
            # Always clean up so handlers don't bleed into other tests on failure
            logging.getLogger().handlers.clear()


class TestClassifyMsgLevel:
    """classify_msg_level maps message prefixes to severity strings."""

    def test_returns_success_for_successfully_prefix(self):
        assert (
            logging_config.classify_msg_level("Successfully augmented tables")
            == "success"
        )
        assert logging_config.classify_msg_level("SUCCESSFULLY COMPLETED") == "success"

    def test_returns_error_for_error_and_failed_prefixes(self):
        assert logging_config.classify_msg_level("Error loading file") == "error"
        assert logging_config.classify_msg_level("Failed to connect") == "error"
        assert logging_config.classify_msg_level("ERROR: unexpected value") == "error"

    def test_returns_warning_for_everything_else(self):
        assert logging_config.classify_msg_level("Running calculation") == "warning"
        assert logging_config.classify_msg_level("Data table is empty") == "warning"
        assert logging_config.classify_msg_level("") == "warning"
