"""桌面版入口测试。"""
import os

import pytest

from app.desktop import _app_data_dir, find_free_port


def test_find_free_port():
    port = find_free_port()
    assert 8000 <= port < 9000
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", port))  # 端口确实空闲


def test_app_data_dir_env(monkeypatch):
    import tempfile
    from pathlib import Path

    p = Path(tempfile.gettempdir()) / "fundai_desktop_test"
    p.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FUNDAI_HOME", str(p))
    assert _app_data_dir() == p


def test_app_data_dir_windows_default(monkeypatch):
    monkeypatch.delenv("FUNDAI_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\test\AppData\Local")
    if os.name == "nt":
        assert str(_app_data_dir()).endswith("FundAI")
