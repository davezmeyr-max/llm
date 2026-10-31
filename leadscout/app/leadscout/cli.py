"""Research one company synchronously and print the profile. For testing.

    python -m leadscout.cli "Joe Inc" --hints "Chicago, IL"
"""

from __future__ import annotations

import argparse
import json
import logging

from .agent import LeadAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Research one company")
    parser.add_argument("company")
    parser.add_argument("--hints", default="")
    parser.add_argument("--trace", action="store_true", help="also print the tool-call trace")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    agent = LeadAgent()
    profile = agent.run(args.company, args.hints)
    print(json.dumps(profile.model_dump(), indent=2))
    if args.trace:
        print(json.dumps(agent.trace, indent=2))


if __name__ == "__main__":
    main()
