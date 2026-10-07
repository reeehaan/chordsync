from __future__ import annotations

import argparse

from backend.api.app.services.analysis_job_dispatcher import DispatchReconciler
from backend.api.app.services.cloud_runtime import (
    CloudRuntimeConfig,
    compose_cloud_runtime,
)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retry durable ChordSync queue dispatches"
    )
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--limit", type=int, default=100)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    arguments = parse_arguments(argv)
    config = CloudRuntimeConfig.from_env()
    runtime = compose_cloud_runtime(config)
    if runtime.queue is None:
        raise RuntimeError("Dispatch reconciliation requires queue mode")
    DispatchReconciler(runtime.repository, runtime.queue).reconcile(
        limit=arguments.limit
    )


if __name__ == "__main__":
    main()
