"""Settings for one pipeline run, read from CodeBase/.env and the environment.

Every value has a default except the OpenAI key, which is only checked when an agent needs it.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# CodeBase/ (this file is CodeBase/src/mpagent/config.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(Exception):
    """A required setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str | None
    agent2_max_turns: int
    agent2_tool_timeout_s: int
    agent2_timeout_min: int
    windows_mcp_command: str
    runs_dir: Path
    judge_max_images: int = 6  # screenshots per judged claim (FUNC_TESTS_PLAN.md F17)
    judge_file_excerpt_chars: int | None = None  # all output files of one claim together; None: no limit (F17)
    agent2_func_min_per_test: int = 10  # time allowance per FUNC test, added to agent2_timeout_min (F15)
    agent2_func_turns_per_test: int = 40  # turn allowance per FUNC test, added to agent2_max_turns (F15)
    agent2_reasoning_effort: str | None = None  # Agent 2's reasoning effort; None = the model's default
    agent2_ui_find_tools: bool = True  # find/click/type UI elements by name, Windows-MCP as fallback (UI_FIND_TOOLS_PLAN.md)
    samples_dir: Path | None = None  # TEMPORARY (POC): the one sample, a file or a folder (F18, Q14)
    # TEMPORARY (until the OpenAI key arrives): Gemini through Google's OpenAI-compatible endpoint.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-lite-latest"

    @property
    def uses_temporary_gemini(self) -> bool:
        return not self.openai_api_key and bool(self.gemini_api_key)

    def require_openai(self) -> None:
        """Fail with a clear message before the first LLM call if the key or model is missing."""
        if self.uses_temporary_gemini:
            return
        missing = [n for n, v in (("OPENAI_API_KEY", self.openai_api_key), ("OPENAI_MODEL", self.openai_model)) if not v]
        if missing:
            raise ConfigError(f"missing in {PROJECT_ROOT / '.env'}: {', '.join(missing)} (see .env.example)")

    def agent_model(self):
        """The `model` argument for an Agents SDK Agent: the OpenAI model name, or (temporary) a Gemini model."""
        self.require_openai()
        if not self.uses_temporary_gemini:
            return self.openai_model
        from agents import OpenAIChatCompletionsModel
        from openai import AsyncOpenAI

        # a slow free-tier request must not block F5 for the client's default 10 min; the free tier's
        # per-minute token quota (HTTP 429, "retry in ~11 s") is ridden out by the client's backoff retries
        client = AsyncOpenAI(base_url=GEMINI_OPENAI_URL, api_key=self.gemini_api_key, timeout=180, max_retries=6)
        return OpenAIChatCompletionsModel(model=self.gemini_model, openai_client=client)


    def fresh_model(self):
        """Like agent_model(), but always with its own new OpenAI client. Needed for a call made after another
        agent ran in an asyncio.run() loop: the SDK's shared client stays tied to that closed loop
        (run 20261014-153924: 'Event loop is closed' in the judge)."""
        self.require_openai()
        if self.uses_temporary_gemini:
            return self.agent_model()  # builds a new client every time already
        from agents import OpenAIResponsesModel
        from openai import AsyncOpenAI

        return OpenAIResponsesModel(model=self.openai_model, openai_client=AsyncOpenAI(api_key=self.openai_api_key))


GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from None


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def _effort(name: str) -> str | None:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return None
    if raw not in REASONING_EFFORTS:
        raise ConfigError(f"{name} must be one of {', '.join(REASONING_EFFORTS)} (or empty), got {raw!r}")
    return raw


def load_settings() -> Settings:
    """Load CodeBase/.env (if present) without overriding variables already set in the environment."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    # Traces stay local (ARCHITECTURE.md D11); the Agents SDK reads this variable.
    os.environ.setdefault("OPENAI_AGENTS_DISABLE_TRACING", "1")
    return Settings(
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        openai_model=os.environ.get("OPENAI_MODEL") or None,
        agent2_max_turns=_int("AGENT2_MAX_TURNS", 150),
        agent2_tool_timeout_s=_int("AGENT2_TOOL_TIMEOUT_S", 120),
        agent2_timeout_min=_int("AGENT2_TIMEOUT_MIN", 40),
        windows_mcp_command=os.environ.get("WINDOWS_MCP_COMMAND") or "windows-mcp",
        runs_dir=PROJECT_ROOT / "runs",
        judge_max_images=_int("JUDGE_MAX_IMAGES", 6),
        agent2_ui_find_tools=_bool("AGENT2_UI_FIND_TOOLS", True),
        agent2_reasoning_effort=_effort("AGENT2_REASONING_EFFORT"),
        judge_file_excerpt_chars=_int("JUDGE_FILE_EXCERPT_CHARS", 0) or None,  # 0 or unset: no limit
        agent2_func_min_per_test=_int("AGENT2_FUNC_MIN_PER_TEST", 10),
        agent2_func_turns_per_test=_int("AGENT2_FUNC_TURNS_PER_TEST", 40),
        samples_dir=Path(os.environ["SAMPLES_DIR"].strip().strip('"')) if os.environ.get("SAMPLES_DIR", "").strip() else None,
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        gemini_model=os.environ.get("GEMINI_MODEL") or "gemini-flash-lite-latest",
    )
