"""Build entrypoint.

  uv run python -m scrapers [out_dir]              # daily (default)
  uv run python -m scrapers --continue [out_dir]   # resume today's partial run
  uv run python -m scrapers --all [out_dir]        # force everyone (ignore cache)

Exit codes: 0 = complete, 2 = published but incomplete (some member missed a
stage — CI should run `--continue`), 1 = hard failure (nothing published).
"""

import argparse
import logging
import sys
import time

from scrapers.build import ruleaza
from scrapers.fetch import Fetcher

if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="scrapers")
    ap.add_argument("out_dir", nargs="?", default="site/data")
    ap.add_argument("--run-dir", default="run")
    grup = ap.add_mutually_exclusive_group()
    grup.add_argument("--daily", action="store_const", dest="mod", const="daily")
    grup.add_argument("--continue", action="store_const", dest="mod", const="continue")
    grup.add_argument("--all", action="store_const", dest="mod", const="all")
    ap.set_defaults(mod="daily")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    fetcher = Fetcher()
    start = time.monotonic()
    try:
        raport = ruleaza(fetcher, args.out_dir, client="auto", mod=args.mod,
                         run_dir=args.run_dir)
    except Exception as e:
        durata = int(time.monotonic() - start)
        print(f"\n=== BUILD FAILED dupa {durata//60}m{durata%60:02d}s ===")
        print(f"requesturi: {fetcher.stats['requests']} (retry-uri: {fetcher.stats['retries']})")
        print(f"eroare: {type(e).__name__}: {e}")
        sys.exit(1)
    lipsa = raport.pop("_incomplet", [])
    durata = int(time.monotonic() - start)
    print(f"\n=== BUILD OK in {durata//60}m{durata%60:02d}s (mod: {args.mod}) ===")
    print(f"requesturi: {fetcher.stats['requests']} (retry-uri: {fetcher.stats['retries']})")
    for camera, a in raport.items():
        print(f"{camera}: {a['total']} | email oficial {a['email_oficial']} | "
              f"birouri {a['birouri']} | cv {a['cv']} | foto {a['foto']} | "
              f"telefon {a['telefon']} | email personal {a['email_personal']}")
    print(f"scris: {args.out_dir}")

    if lipsa:
        print(f"INCOMPLET: {len(lipsa)} membri fara stage1+stage2 -> ruleaza `--continue`")
        sys.exit(2)
    print("COMPLET: toti membrii au trecut")
