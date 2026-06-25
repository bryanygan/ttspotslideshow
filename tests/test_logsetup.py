import logging

from logsetup import setup_logging

NAME = "ttspot_test_logsetup"


def test_setup_logging_writes_file_and_is_idempotent(tmp_path):
    logging.getLogger(NAME).handlers.clear()  # clean slate for a stable assertion

    lg = setup_logging(NAME, log_dir=tmp_path)
    assert len(lg.handlers) == 2  # console + rotating file

    lg.info("hello world")
    for h in lg.handlers:
        h.flush()

    log_file = tmp_path / f"{NAME}.log"
    assert log_file.exists()
    assert "hello world" in log_file.read_text(encoding="utf-8")

    # Calling again must not stack duplicate handlers.
    lg2 = setup_logging(NAME, log_dir=tmp_path)
    assert lg2 is lg
    assert len(lg2.handlers) == 2

    for h in list(lg.handlers):  # avoid leaking an open file handle to other tests
        h.close()
        lg.removeHandler(h)
