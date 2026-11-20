"""Flow steps that do work (branching steps - If and Switch - are handled by the engine)."""

import time

from .base import Field, NodeContext, NodeError, node


@node(
    "wait",
    "Wait",
    "Flow",
    "Pause before continuing (up to the administrator's limit).",
    "timer",
    [Field("seconds", "Seconds", "number", required=True, default=5)],
    output_hint="{ waited_seconds }",
)
def wait(cfg: dict, ctx: NodeContext):
    try:
        seconds = float(cfg["seconds"])
    except (TypeError, ValueError):
        raise NodeError("Seconds must be a number") from None
    limit = float(ctx.settings.get("max_wait_seconds", 300))
    if seconds < 0 or seconds > limit:
        raise NodeError(f"Wait must be between 0 and {int(limit)} seconds")
    time.sleep(seconds)
    return {"waited_seconds": seconds}


@node(
    "stop_with_error",
    "Stop with error",
    "Flow",
    "Stop the workflow and mark the run as failed with your message.",
    "octagon-x",
    [Field("message", "Error message", "text", required=True)],
)
def stop_with_error(cfg: dict, ctx: NodeContext):
    raise NodeError(str(cfg["message"]))
