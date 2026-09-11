"""Tests for dind/logging.py — JsonFormatter + idempotent configure_logging."""

import json
import logging
from logging.handlers import RotatingFileHandler

import pytest

from dincli.dind.logging import JsonFormatter, configure_logging


@pytest.fixture
def dincli_logger():
    """Detaches AND closes every handler this test attached, so a later
    test never writes into a tmp_path that's already been torn down."""
    logger = logging.getLogger("dincli")
    yield logger
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


def test_json_formatter_emits_valid_json():
    fmt = JsonFormatter()
    record = logging.LogRecord(
        "dincli", logging.INFO, "", 0, "hello world", (), None
    )
    output = fmt.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "dincli"
    assert parsed["msg"] == "hello world"
    assert "ts" in parsed


def test_json_formatter_context_extra():
    fmt = JsonFormatter()
    record = logging.LogRecord(
        "dincli", logging.WARNING, "", 0, "test message", (), None
    )
    record.job_id = 42
    record.role = "aggregator"
    output = fmt.format(record)
    parsed = json.loads(output)
    assert parsed["job_id"] == 42
    assert parsed["role"] == "aggregator"


def test_json_formatter_exception():
    fmt = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "dincli", logging.ERROR, "", 0, "fail", (), None
        )
        import sys
        record.exc_info = sys.exc_info()

    output = fmt.format(record)
    parsed = json.loads(output)
    assert "exception" in parsed
    assert "boom" in parsed["exception"]


def test_configure_logging_idempotent():
    logger = logging.getLogger("dincli")
    initial_handlers = len(logger.handlers)
    initial_propagate = logger.propagate

    configure_logging("json")
    after_first = len(logger.handlers)

    configure_logging("json")
    after_second = len(logger.handlers)

    assert after_first == after_second
    assert logger.propagate is False

    logger.handlers.clear()
    logger.propagate = initial_propagate


def test_configure_logging_sets_info_level_by_default():
    logger = logging.getLogger("dincli")
    logger.setLevel(logging.WARNING)

    configure_logging("json")

    assert logger.getEffectiveLevel() <= logging.INFO

    logger.handlers.clear()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


def test_configure_logging_respects_config_file(monkeypatch, tmp_path):
    import json

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"log_level": "DEBUG"}), encoding="utf-8")

    from dincli.dind import logging as dlog
    monkeypatch.setattr(dlog, "CONFIG_FILE", config_file)

    logger = logging.getLogger("dincli")
    logger.setLevel(logging.WARNING)

    configure_logging("json")

    assert logger.getEffectiveLevel() == logging.DEBUG

    logger.handlers.clear()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


# ── BL-21: rotating file logs ────────────────────────────────────────────────


def test_configure_logging_writes_json_to_file(tmp_path, dincli_logger):
    configure_logging("json", state_dir=tmp_path)
    dincli_logger.info("hello from file")

    log_path = tmp_path / "dind.log"
    assert log_path.exists()

    last_line = log_path.read_text().strip().splitlines()[-1]
    parsed = json.loads(last_line)
    assert parsed["msg"] == "hello from file"
    assert parsed["level"] == "INFO"


def test_configure_logging_file_idempotent(tmp_path, dincli_logger):
    configure_logging("json", state_dir=tmp_path)
    configure_logging("json", state_dir=tmp_path)

    # RotatingFileHandler is a StreamHandler subclass (via FileHandler) —
    # identify by exact type, never a bare isinstance, or it double-counts.
    stream_handlers = [
        h for h in dincli_logger.handlers if type(h) is logging.StreamHandler
    ]
    file_handlers = [
        h for h in dincli_logger.handlers if type(h) is RotatingFileHandler
    ]
    assert len(stream_handlers) == 1
    assert len(file_handlers) == 1


def test_configure_logging_rotates(tmp_path, monkeypatch, dincli_logger):
    monkeypatch.setenv("DIN_DIND_LOG_MAX_BYTES", "500")
    monkeypatch.setenv("DIN_DIND_LOG_BACKUP_COUNT", "2")

    configure_logging("json", state_dir=tmp_path)

    for i in range(200):
        dincli_logger.info(
            "filler message %d padded to exceed the rotation threshold quickly",
            i,
        )

    assert (tmp_path / "dind.log.1").exists()


def test_configure_logging_file_open_failure_is_non_fatal(
    tmp_path, dincli_logger, capsys
):
    # state_dir points under a regular file, not a directory, so opening
    # <state_dir>/dind.log fails. A chmod-based unwritable-dir test would
    # silently pass under root (the CI container case), so this avoids that.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")

    configure_logging("json", state_dir=blocker)

    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()

    # The stderr handler is still attached and functional; only the file
    # handler was lost.
    stream_handlers = [
        h for h in dincli_logger.handlers if type(h) is logging.StreamHandler
    ]
    file_handlers = [
        h for h in dincli_logger.handlers if type(h) is RotatingFileHandler
    ]
    assert len(stream_handlers) == 1
    assert len(file_handlers) == 0
