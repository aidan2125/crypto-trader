import pytest

from utils.fatal_errors import handle_symbol_error, is_fatal


def test_auth_error_is_fatal():
    assert is_fatal(Exception("401 Unauthorized"))


def test_ordinary_error_is_not_fatal():
    assert not is_fatal(Exception("connection reset"))


def test_fatal_is_reraised():
    with pytest.raises(Exception):
        handle_symbol_error(Exception("invalid api key"), "x")


def test_ordinary_is_swallowed():
    handle_symbol_error(Exception("timeout"), "x")
