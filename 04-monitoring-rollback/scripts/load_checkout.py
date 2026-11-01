"""Synthetic CHECKOUT requests, no real payments or writes."""
import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PAYLOAD = json.dumps({'items':[{'sku':'keyboard','quantity':2}]}).encode()

def send_one(url: str) -> str:
    request = Request(url, data=PAYLOAD, headers={'Content-Type':'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=5) as response:
            response_data = json.load(response)
            if response_data.get('total_cents') != 9599:
                return 'WRONG_TOTAL'
            return str(response.status)
    except HTTPError as err:
        return str(err.code)
    except (URLError, OSError, ValueError, KeyError):
        return 'NETWORK_ERROR'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:18083/api/checkout')
    parser.add_argument('--requests', type=int, default=400)
    parser.add_argument('--workers', type=int, default=8)
    args=parser.parse_args()
    if not 1 <= args.requests <= 3000 or not 1 <= args.workers <= 20:
        parser.error('requests must be 1..3000, workers must be 1..20')
    results=Counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs=[pool.submit(send_one,args.url) for _ in range(args.requests)]
        for job in as_completed(jobs):
            results[job.result()]+=1
    print(f'Checkout demo requests: {args.requests}')
    for k,v in sorted(results.items()):
        print(f'  {k}: {v}')
    print('All responses are simulated; no payment or persistence exists.')

if __name__=='__main__':
    main()
