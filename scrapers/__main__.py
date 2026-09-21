"""Build entrypoint.

  uv run python -m scrapers [out_dir]              # daily (default)
  uv run python -m scrapers --continue [out_dir]   # resume today's partial run
  uv run python -m scrapers --all [out_dir]        # force everyone (ignore cache)

Exit codes: 0 = complete, 2 = published but incomplete (some member missed a
stage — CI should run `--continue`), 1 = hard failure (nothing published).
"""

import argparse
import logging
import os
import signal
import sys
import time

from scrapers.build import raport, ruleaza, valideaza
from scrapers.fetch import Fetcher


def _pe_semnal(signum, frame):
    raise KeyboardInterrupt(signal.Signals(signum).name)


def instaleaza_semnale():
    """SIGINT/SIGTERM/SIGHUP -> KeyboardInterrupt: iesim curat (flush loguri),
    fara cleanup. Ce s-a scrapat e deja pe disc (run/membri) -> `--continue` reia."""
    for nume in ("SIGINT", "SIGTERM", "SIGHUP"):
        s = getattr(signal, nume, None)
        if s is not None:
            signal.signal(s, _pe_semnal)


def configure_logging(run_dir: str, spre_stdout: bool) -> str:
    """Logfile (DEBUG — fiecare request) + consola. Consola: INFO pe stderr;
    cu --stdout mutam pe stdout la DEBUG (vezi tot: pasi + fiecare request)."""
    os.makedirs(run_dir, exist_ok=True)
    log_file = os.path.join(run_dir, "scrape.log")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    fisier = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    fisier.setLevel(logging.DEBUG)
    fisier.setFormatter(fmt)
    consola = logging.StreamHandler(sys.stdout if spre_stdout else sys.stderr)
    consola.setLevel(logging.DEBUG if spre_stdout else logging.INFO)
    consola.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(fisier)
    root.addHandler(consola)
    return log_file

if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="scrapers")
    ap.add_argument("out_dir", nargs="?", default="site/data")
    ap.add_argument("--run-dir", default="run")
    grup = ap.add_mutually_exclusive_group()
    grup.add_argument("--daily", action="store_const", dest="mod", const="daily")
    grup.add_argument("--continue", action="store_const", dest="mod", const="continue")
    grup.add_argument("--all", action="store_const", dest="mod", const="all")
    ap.add_argument("--stdout", action="store_true",
                    help="trimite logurile pe stdout (implicit stderr)")
    ap.set_defaults(mod="daily")
    args = ap.parse_args()

    log_file = configure_logging(args.run_dir, args.stdout)
    logging.getLogger("demnitari.build").info("log: %s", log_file)
    instaleaza_semnale()
    fetcher = Fetcher()
    start = time.monotonic()
    try:
        rez = ruleaza(fetcher, args.out_dir, client="auto", mod=args.mod,
                      run_dir=args.run_dir)
        # validarea = pas separat de build; daca pica, nu declaram succes
        if rez["circumscriptii"]:
            valideaza(rez["circumscriptii"])
    except KeyboardInterrupt as e:
        durata = int(time.monotonic() - start)
        logging.getLogger("demnitari.build").warning(
            "intrerupt (%s) dupa %dm%02ds — starea e pe disc, reia cu --continue",
            e, durata // 60, durata % 60)
        print(f"\n=== INTRERUPT ({e}) — reia cu `just scrape --continue` ===")
        sys.exit(130)
    except Exception as e:
        durata = int(time.monotonic() - start)
        print(f"\n=== BUILD FAILED dupa {durata//60}m{durata%60:02d}s ===")
        print(f"requesturi: {fetcher.stats['requests']} (retry-uri: {fetcher.stats['retries']})")
        print(f"eroare: {type(e).__name__}: {e}")
        sys.exit(1)
    lipsa = rez["incomplet"]
    durata = int(time.monotonic() - start)
    print(f"\n=== BUILD OK in {durata//60}m{durata%60:02d}s (mod: {args.mod}) ===")
    print(f"requesturi: {fetcher.stats['requests']} (retry-uri: {fetcher.stats['retries']})")
    for camera, a in raport(rez["circumscriptii"]).items():
        print(f"{camera}: {a['total']} | email oficial {a['email_oficial']} | "
              f"birouri {a['birouri']} | cv {a['cv']} | foto {a['foto']} | "
              f"telefon {a['telefon']} | email personal {a['email_personal']}")
    print(f"scris: {args.out_dir}")

    if lipsa:
        print(f"INCOMPLET: {len(lipsa)} membri fara stage1+stage2 -> ruleaza `--continue`")
        sys.exit(2)
    print("COMPLET: toti membrii au trecut")
