"""Training-only rollback decision via Prometheus API, opt-in to execution.

Requires local Docker Compose CLI and access to the same machine as the lab.
A real production controller also needs RBAC, auditing, HA, metrics freshness,
release identity, timeouts and rollout serialization.
"""
import argparse
import json
import time
from urllib.parse import urlencode
from urllib.request import urlopen

from traffic_control import current_profile, set_profile

ERRORS = ('sum(increase(shop_http_requests_total{app_version="v2",route="/api/checkout",status=~"5.."}[1m])) or vector(0)')
TOTAL = ('sum(increase(shop_http_requests_total{app_version="v2",route="/api/checkout"}[1m])) or vector(0)')


def query_scalar(base_url: str, expression: str) -> float:
    url = base_url.rstrip('/') + '/api/v1/query?' + urlencode({'query': expression})
    with urlopen(url, timeout=5) as response:
        payload = json.load(response)
    if payload.get('status') != 'success' or payload.get('data',{}).get('resultType') != 'vector':
        raise ValueError('Prometheus did not return a valid instant vector')
    series = payload['data'].get('result',[])
    if len(series) != 1:
        raise ValueError(f'Unexpected Prometheus series count: {len(series)}')
    n = float(series[0]['value'][1])
    if not (0 <= n < float('inf')):
        raise ValueError('Non-finite or negative Prometheus metric')
    return n


def evaluate(base_url: str, error_threshold: float, min_requests: float, execute: bool = False) -> bool:
    # Both numbers are collected independently and require successful Prometheus API responses.
    failed = query_scalar(base_url, ERRORS)
    total = query_scalar(base_url, TOTAL)
    print(f'v2 checkout last minute: total~{total:.2f}, 5xx~{failed:.2f}, threshold={error_threshold:g}')
    if total < min_requests:
        print(f'No rollback: fewer than {min_requests:g} observed requests')
        return False
    if failed < error_threshold:
        print('No rollback: failure threshold not exceeded')
        return False
    if current_profile() == '100-0':
        print('No action: already routing all traffic to v1')
        return False
    print('CANARY UNHEALTHY: rollback condition met')
    return set_profile('100-0', execute=execute)


def main():
    parser = argparse.ArgumentParser(description='Prometheus-driven local canary rollback demo')
    parser.add_argument('--prometheus-url', default='http://127.0.0.1:19090')
    parser.add_argument('--error-threshold', type=int, default=3)
    parser.add_argument('--min-requests', type=int, default=5)
    parser.add_argument('--watch', type=float, metavar='SECONDS', help='Poll repeatedly (otherwise check once)')
    parser.add_argument('--execute', action='store_true', help='Actually change NGINX; default is dry-run')
    args = parser.parse_args()
    if args.error_threshold < 1 or args.min_requests < 1 or (args.watch is not None and args.watch < 1):
        parser.error('Thresholds must be positive; --watch must be >= 1 second')
    print(f'Mode: {"EXECUTE" if args.execute else "DRY RUN"}. Only for local training stack.')
    while True:
        try:
            changed = evaluate(args.prometheus_url, args.error_threshold, args.min_requests, args.execute)
            if changed:
                print('Rollback applied; stopping controller')
                return
        except (ValueError, OSError, RuntimeError, TimeoutError) as exc:
            print(f'Controller could not decide or act: {exc}. No blind rollback performed.')
            if args.watch is None:
                raise SystemExit(1)
        if args.watch is None:
            return
        time.sleep(args.watch)


if __name__ == '__main__':
    main()
