"""Agent 2's model calls: what is sent, and how long each call takes.

- keep_recent_images: before every model call, only the images of the last N tool results stay in the input;
  older ones become a short text note. Every image stays in the history and on disk as evidence (the judge
  reads the files); only what the model re-reads on each turn shrinks. Without it each turn re-sent every
  screenshot so far and the think time grew during the run (run 20261022-160813: 18 images, 25 s per turn
  after a screenshot).
- ModelCallTrace: one `model_call` trace event per call, with its seconds, the images sent and the token usage,
  so a long idle stretch can be told apart from a slow tool.
"""

import copy
import time

from agents import RunHooks
from agents.run_config import CallModelData, ModelInputData

from mpagent.runlog import Trace, log

DROPPED_IMAGE_NOTE = ("[image no longer shown to save time: an older screenshot; it is kept as evidence under the "
                      "file name given in this result]")
SLOW_CALL_S = 30  # model calls at least this long also go to run.log


def _image_parts(item) -> list[dict]:
    if not isinstance(item, dict) or item.get("type") != "function_call_output":
        return []
    output = item.get("output")
    return [p for p in output if isinstance(p, dict) and p.get("type") == "input_image"] if isinstance(output, list) else []


def count_images(items) -> int:
    return sum(len(_image_parts(i)) for i in items or [])


def keep_recent_images(keep: int):
    """A call_model_input_filter: the images of the last `keep` tool results with images stay, older images are
    replaced by DROPPED_IMAGE_NOTE. keep <= 0: everything is sent, as before."""

    def apply(data: CallModelData) -> ModelInputData:
        items = data.model_data.input
        if keep <= 0 or not isinstance(items, list):
            return data.model_data
        with_images = [i for i, item in enumerate(items) if _image_parts(item)]
        older = set(with_images[:-keep])
        if not older:
            return data.model_data
        trimmed = []
        for i, item in enumerate(items):
            if i in older:  # a copy: the run's own history keeps the images
                item = copy.copy(item)
                item["output"] = [{"type": "input_text", "text": DROPPED_IMAGE_NOTE}
                                  if isinstance(p, dict) and p.get("type") == "input_image" else p
                                  for p in item["output"]]
            trimmed.append(item)
        return ModelInputData(input=trimmed, instructions=data.model_data.instructions)

    return apply


class ModelCallTrace(RunHooks):
    """Writes a `model_call` trace event after every model call (Agent 2 makes one call at a time)."""

    def __init__(self, trace: Trace):
        self.trace = trace
        self.n = 0
        self._started = 0.0
        self._images = 0

    async def on_llm_start(self, context, agent, system_prompt, input_items) -> None:
        self._started = time.monotonic()
        self._images = count_images(input_items)

    async def on_llm_end(self, context, agent, response) -> None:
        self.n += 1
        seconds = round(time.monotonic() - self._started, 1)
        usage = getattr(response, "usage", None)
        details = getattr(usage, "output_tokens_details", None)
        self.trace.write("model_call", n=self.n, seconds=seconds, images_sent=self._images,
                         input_tokens=getattr(usage, "input_tokens", None),
                         output_tokens=getattr(usage, "output_tokens", None),
                         reasoning_tokens=getattr(details, "reasoning_tokens", None))
        if seconds >= SLOW_CALL_S:
            log.info("  model call %d took %.0f s (%d images sent)", self.n, seconds, self._images)
