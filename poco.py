#!/usr/bin/env python3
"""poco entrypoint."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from pathlib import Path


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "poco.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _emergency_deadend_watchdog() -> None:
    import time
    import subprocess
    import os
    # 5 hours 15 minutes deadend timer to beat 5h55m absolute timeout
    time.sleep(5.25 * 3600)
    print("\n[CRITICAL] 5h15m0s DEADEND REACHED. FORCING EMERGENCY REBIRTH AND TERMINATION.\n")
    try:
        # Force a push to trigger the next lifecycle immediately regardless of hung locks
        subprocess.run(["python", "final_push.py"], timeout=300)
        subprocess.run(["python", "ultimate_push.py"], timeout=300)
    except Exception as e:
        print(f"Emergency deadend push failed: {e}")
    finally:
        # Guarantee absolute death of the hung organism
        os._exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="poco v1 runner")
    default_hours = (
        os.environ.get("poco_RUN_HOURS_OVERRIDE", "").strip()
        or os.environ.get("RUN_HOURS", "").strip()
        or os.environ.get("poco_RUN_HOURS", "").strip()
        or "5.0"
    )
    parser.add_argument("--run-hours", type=float, default=float(default_hours))
    parser.add_argument("--data-path", default="data")
    parser.add_argument("--profile-path", default=None)
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--boot-validation-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    import threading
    threading.Thread(target=_emergency_deadend_watchdog, daemon=True).start()
    args = parse_args()
    data_dir = Path(args.data_path).resolve()

    try:
        from src import headderfill
        from src.runtime_paths import PROJECT_ROOT, ensure_runtime_paths, resolve_profile_dir

        runtime_paths = ensure_runtime_paths()
        setup_logging(runtime_paths.logs_root)
        log = logging.getLogger("poco")
        log.info("Using local editable headderfill bootstrap from %s", Path(headderfill.__file__).resolve())
        from src.ai_engine import PocoAI

        data_arg = Path(args.data_path)
        data_dir = data_arg if data_arg.is_absolute() else (PROJECT_ROOT / data_arg)
        data_dir = data_dir.resolve()
        profile_dir = resolve_profile_dir(args.profile_path)
        engine = PocoAI(
            data_dir=data_dir,
            profile_dir=profile_dir,
            headless=not args.no_headless,
            dry_run=args.dry_run,
        )
        if args.boot_validation_only:
            os.environ["poco_BOOT_SEQUENCE_ONLY"] = "1"
        result = engine.run_forever(hours_per_run=args.run_hours)
        with open(data_dir / "rebirth_data.json", "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        log.info("Run complete")
        return 0
    except Exception as exc:
        log.exception("Fatal error: %s", exc)
        try:
            from src.self_heal import SelfHealer

            healer = SelfHealer(data_dir / "self_heal_log.jsonl")
            healer.record_failure(exc, traceback.format_exc())
        except Exception:
            log.exception("Self-heal logging failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
