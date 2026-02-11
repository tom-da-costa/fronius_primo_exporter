"""
Fronius Primo Prometheus Exporter
================================
Interroge la Fronius Solar API (onduleur ou Datamanager) et expose les
métriques sur /metrics.

Usage
-----
  uv run main.py --fronius-url http://192.168.1.10
  uv run main.py --fronius-url http://192.168.1.10 --metrics-port 9687
"""

import argparse
import logging
import os
import signal
import sys
import threading

from prometheus_client import start_http_server
from prometheus_client.core import CollectorRegistry

from client import FroniusClient
from collector import FroniusCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_LISTEN_ADDR = "0.0.0.0"
DEFAULT_METRICS_PORT = 9687
DEFAULT_TIMEOUT = 20.0


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prometheus exporter for Fronius solar inverters (Primo / Solar API)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--fronius-url",
        default=os.environ.get("FRONIUS_URL", ""),
        help="Base URL of the Fronius device or Datamanager (e.g. http://192.168.1.10)",
    )
    listen_env = os.environ.get("LISTEN_ADDR", "")
    if ":" in listen_env:
        _addr, _port = listen_env.rsplit(":", 1)
        _default_port = int(_port)
        _default_addr = _addr or DEFAULT_LISTEN_ADDR
    else:
        _default_addr = listen_env or DEFAULT_LISTEN_ADDR
        _default_port = int(os.environ.get("METRICS_PORT", DEFAULT_METRICS_PORT))

    parser.add_argument(
        "--listen-address",
        default=_default_addr,
        help="Address to bind the metrics HTTP server to",
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=_default_port,
        help="TCP port to expose Prometheus metrics on",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("FRONIUS_TIMEOUT", DEFAULT_TIMEOUT)),
        help="HTTP timeout in seconds when calling the Fronius API",
    )
    parser.add_argument(
        "--prefix",
        default="fronius_",
        help="Prefix for all Prometheus metric names",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(args)


def main(argv=None) -> None:
    args = parse_args(argv)

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.fronius_url:
        logger.error(
            "Missing --fronius-url (or FRONIUS_URL). "
            "Example: http://192.168.1.10 or http://ip-datamanager"
        )
        sys.exit(1)

    client = FroniusClient(base_url=args.fronius_url, timeout=args.timeout)
    registry = CollectorRegistry()
    registry.register(FroniusCollector(client, prefix=args.prefix))

    start_http_server(args.metrics_port, addr=args.listen_address, registry=registry)
    logger.info(
        "Metrics available at http://%s:%d/metrics",
        args.listen_address,
        args.metrics_port,
    )

    stop_event = threading.Event()

    def _shutdown(signum, frame):  # noqa: ARG001
        logger.info("Shutting down…")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    stop_event.wait()
    logger.info("Exporter stopped.")


if __name__ == "__main__":
    main()
