import sqlite3

import pytest

import health_check as hc


def boom():
    raise RuntimeError("nope")


def test_failing_check_is_captured_not_raised():
    results = hc.run_checks([("x", True, boom)])
    assert results[0].ok is False
    assert "nope" in results[0].detail


def test_fatal_failure_blocks_startup():
    assert not hc.startup_ok(hc.run_checks([("x", True, boom)]))


def test_warn_failure_does_not_block_startup():
    results = hc.run_checks([("warn", False, boom), ("fine", True, lambda: "ok")])
    assert hc.startup_ok(results)


def test_db_check_passes_on_healthy_db(tmp_path, monkeypatch):
    path = tmp_path / "ok.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (id INTEGER)")
    con.commit()
    con.close()
    monkeypatch.setenv("TRADE_DB_PATH", str(path))
    assert "ok" in hc.check_db()


def test_db_check_fails_on_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "bad.db"
    path.write_bytes(b"this is not a database" * 200)
    monkeypatch.setenv("TRADE_DB_PATH", str(path))
    with pytest.raises(Exception):
        hc.check_db()


def test_env_check_requires_alpaca_keys_for_stocks(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        hc.check_env_core("stocks")
    assert hc.check_env_core("crypto")


def test_altcoin_not_live_by_default(monkeypatch):
    monkeypatch.delenv("ALTCOINTRADER_DRY_RUN", raising=False)
    monkeypatch.delenv("ALTCOINTRADER_LIVE_CONFIRM", raising=False)
    assert hc.altcoin_is_live() is False
