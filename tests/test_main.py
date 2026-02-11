from unittest.mock import patch, MagicMock

import pytest

from main import parse_args, main


def test_parse_args_fronius_url_required():
    args = parse_args(["--fronius-url", "http://192.168.1.10"])
    assert args.fronius_url == "http://192.168.1.10"


def test_parse_args_defaults():
    args = parse_args(["--fronius-url", "http://x"])
    assert args.metrics_port == 9687
    assert args.listen_address == "0.0.0.0"
    assert args.prefix == "fronius_"


def test_parse_args_listen_addr_with_port():
    with patch.dict("os.environ", {"LISTEN_ADDR": "127.0.0.1:8080"}, clear=False):
        args = parse_args(["--fronius-url", "http://x"])
    assert args.listen_address == "127.0.0.1"
    assert args.metrics_port == 8080


def test_parse_args_listen_addr_without_port():
    with patch.dict("os.environ", {"LISTEN_ADDR": "10.0.0.1"}, clear=False):
        args = parse_args(["--fronius-url", "http://x"])
    assert args.listen_address == "10.0.0.1"


def test_parse_args_debug_flag():
    args = parse_args(["--fronius-url", "http://x", "--debug"])
    assert args.debug is True


def test_main_exits_without_url():
    with pytest.raises(SystemExit) as exc_info:
        main(["--fronius-url", ""])
    assert exc_info.value.code == 1


def test_main_starts_server():
    with (
        patch("main.start_http_server") as mock_server,
        patch("main.signal.signal"),
        patch("main.threading.Event") as mock_event_cls,
    ):
        stop_event = MagicMock()
        stop_event.wait.return_value = None
        mock_event_cls.return_value = stop_event

        main(["--fronius-url", "http://192.168.1.10", "--debug"])

        mock_server.assert_called_once()
        stop_event.wait.assert_called_once()
