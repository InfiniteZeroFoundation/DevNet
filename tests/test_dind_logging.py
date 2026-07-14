"""Tests for dind/logging.py — JsonFormatter + idempotent configure_logging."""

import json
import logging

from dincli.dind.logging import JsonFormatter, configure_logging


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
