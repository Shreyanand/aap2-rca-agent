"""Surface MLflow trace cost for a legacy batch Claude invocation.

The Stop hook (mlflow.claude_code.hooks.stop_hook_handler) already logs a
trace for each headless `claude -p` run, and MLflow computes cost onto
trace.info.cost from the recorded token usage. That cost isn't logged
anywhere visible outside the trace detail view, so this script fetches the
trace just created for this invocation and re-logs its cost as a metric on
a tagged MLflow run, making it show up in run/metric views too.
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager

from rca.config import Config

_MLFLOW_ENV_KEYS = (
    "MLFLOW_TRACKING_URI",
    "MLFLOW_TRACKING_USERNAME",
    "MLFLOW_TRACKING_PASSWORD",
    "MLFLOW_TRACKING_TOKEN",
    "MLFLOW_EXPERIMENT_NAME",
)


@contextmanager
def _tracking_environment(environment: dict[str, str]):
    """Temporarily expose settings to the MLflow client; always restore the process env."""
    previous = {key: os.environ.get(key) for key in _MLFLOW_ENV_KEYS}
    try:
        for key in _MLFLOW_ENV_KEYS:
            if environment.get(key):
                os.environ[key] = environment[key]
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Log the most recent Claude trace's cost to MLflow"
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args(argv)

    try:
        import mlflow
    except ImportError:
        print("[WARN] mlflow not installed, skipping cost logging", file=sys.stderr)
        return 0

    config = Config.from_env()
    environment = config.environment
    tracking_uri = environment.get("MLFLOW_TRACKING_URI", "")
    experiment_name = environment.get("MLFLOW_EXPERIMENT_NAME", "")
    if not tracking_uri or not experiment_name:
        print("[WARN] MLflow tracking URI/experiment is not configured, skipping", file=sys.stderr)
        return 0

    with _tracking_environment(environment):
        mlflow.set_tracking_uri(tracking_uri)
        client = mlflow.MlflowClient()
        exp = mlflow.get_experiment_by_name(experiment_name)
        if exp is None:
            print(
                "[WARN] MLflow experiment not found, skipping",
                file=sys.stderr,
            )
            return 0

        traces = client.search_traces(
            experiment_ids=[exp.experiment_id], order_by=["timestamp_ms DESC"], max_results=1
        )
        if not traces:
            print("[WARN] No traces found for this experiment, skipping cost logging", file=sys.stderr)
            return 0

        trace = traces[0]
        cost = getattr(trace.info, "cost", None)
        token_usage = getattr(trace.info, "token_usage", None) or {}

        if cost is None:
            print(f"[WARN] trace {trace.info.trace_id} has no cost recorded, skipping", file=sys.stderr)
            return 0

        with mlflow.start_run(run_name=args.batch_id):
            mlflow.set_tags(
                {
                    "batch_id": args.batch_id,
                    "model": args.model,
                    "trace_id": trace.info.trace_id,
                }
            )
            mlflow.log_metric("cost_usd", float(cost))
            for key, value in token_usage.items():
                try:
                    mlflow.log_metric(key, float(value))
                except (TypeError, ValueError):
                    continue

    print(f"[INFO] Logged cost_usd={cost} for trace {trace.info.trace_id} to MLflow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
