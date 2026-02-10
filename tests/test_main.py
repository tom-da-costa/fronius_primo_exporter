from main import parse_args


def test_parse_args_fronius_url_required():
    args = parse_args(["--fronius-url", "http://192.168.1.10"])
    assert args.fronius_url == "http://192.168.1.10"


def test_parse_args_defaults():
    args = parse_args(["--fronius-url", "http://x"])
    assert args.metrics_port == 9687
    assert args.listen_address == "0.0.0.0"
    assert args.prefix == "fronius_"
