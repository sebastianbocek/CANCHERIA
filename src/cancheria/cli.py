from __future__ import annotations
import argparse
from cancheria.legacy_bridge import run_legacy_cli


def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(prog="cancheria", description="CANCHERIA conversational reservation engine")
    sub=parser.add_subparsers(dest="command", required=True)
    run=sub.add_parser("run", help="Run the WhatsApp Web channel")
    run.add_argument("--profile", required=True)
    sub.add_parser("eval", help="Run offline Agent V2 invariant evals")
    sub.add_parser("eval-e2e", help="Run offline Agent V2 E2E evals")
    sub.add_parser("eval-live", help="Run live semantic evals (requires API credentials)")
    learning=sub.add_parser("learning", help="Agent learning commands")
    learning.add_argument("action", choices=["status","tournament","rollback"])
    return parser


def main(argv=None) -> int:
    args=build_parser().parse_args(argv)
    if args.command == "run": return run_legacy_cli(["--profile", args.profile])
    if args.command == "eval": return run_legacy_cli(["--agentic-evals"])
    if args.command == "eval-e2e": return run_legacy_cli(["--agentic-evals-e2e"])
    if args.command == "eval-live": return run_legacy_cli(["--agentic-evals-live"])
    mapping={"status":"--learning-status","tournament":"--learning-tournament","rollback":"--learning-rollback"}
    if args.command == "learning": return run_legacy_cli([mapping[args.action]])
    return 2

if __name__ == "__main__": raise SystemExit(main())
