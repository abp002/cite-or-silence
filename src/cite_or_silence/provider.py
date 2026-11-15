"""LLM providers behind one interface: a prompt and a JSON Schema in, a dict of that shape out.

Every number in the README names the provider and model that produced it, so each provider
carries a `name` such as "codex:gpt-6-astra".
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

import httpx


class Provider(Protocol):
    name: str

    def complete(self, prompt: str, schema: dict) -> dict: ...


class Codex:
    """ChatGPT through the Codex CLI and the user's ChatGPT login (OAuth), no API key.

    Runs in an empty temporary directory, read-only and without the user's config, so the model
    sees nothing but the prompt. stdin is closed: with it open, `codex exec` waits for more input.
    """

    def __init__(self, model: str = "gpt-6-luna", effort: str = "low", timeout: int = 300):
        self.model, self.effort, self.timeout = model, effort, timeout
        self.name = f"codex:{model}:{effort}"

    def complete(self, prompt: str, schema: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            schema_path, out = Path(tmp) / "schema.json", Path(tmp) / "out.json"
            schema_path.write_text(json.dumps(schema))
            run = subprocess.run(
                ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config",
                 "-s", "read-only", "-C", tmp, "-m", self.model,
                 "-c", f'model_reasoning_effort="{self.effort}"',
                 "--output-schema", str(schema_path), "-o", str(out), prompt],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=self.timeout,
            )  # fmt: skip
            if run.returncode != 0 or not out.exists():
                raise RuntimeError(f"codex exited {run.returncode}: {run.stderr[-500:]}")
            return json.loads(out.read_text())


class Ollama:
    """A local model through Ollama; the fallback that costs nothing and needs no login.

    Ollama's default window is 4,096 tokens and it cuts longer prompts without saying so; judge
    prompts run to ~7k, some bench judge prompts to ~18k. The window is set explicitly and
    `truncate: false` makes Ollama refuse a prompt that does not fit instead of cutting it.

    The model is unloaded after every call (`keep_alive: 0`): over a day-long bench the runner
    grew from 11 to 19 GB, the Mac ran out of memory and panicked (2026-10-09). Reloading
    costs ~7 s per call.
    """

    def __init__(self, model: str = "qwen3:14b", url: str = "http://localhost:11434", timeout: int = 900, num_ctx: int = 24576):
        self.model, self.url, self.timeout, self.num_ctx = model, url, timeout, num_ctx
        self.name = f"ollama:{model}"

    def complete(self, prompt: str, schema: dict) -> dict:
        r = httpx.post(
            f"{self.url}/api/chat",
            json={"model": self.model, "messages": [{"role": "user", "content": prompt}],
                  "format": schema, "stream": False, "think": False, "truncate": False, "keep_alive": 0,
                  "options": {"temperature": 0, "num_ctx": self.num_ctx}},
            timeout=self.timeout,
        )  # fmt: skip
        if r.is_error:
            raise RuntimeError(f"ollama {r.status_code}: {r.text[:300]}")
        return json.loads(r.json()["message"]["content"])


class Claude:
    """Claude through the Claude Code CLI and the user's login, no API key.

    Used as the independent bench judge: a model family that neither answering model belongs to.
    No tools, no user or project settings, no MCP servers and an empty working directory, so the
    model sees nothing but the prompt, which goes in through stdin.
    """

    SYSTEM = "You are a careful grader. Answer only through the structured output."

    def __init__(self, model: str = "claude-sonnet-5-5", timeout: int = 600):
        self.model, self.timeout = model, timeout
        self.name = f"claude:{model}"

    def complete(self, prompt: str, schema: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            run = subprocess.run(
                ["claude", "-p", "--model", self.model, "--output-format", "json",
                 "--json-schema", json.dumps(schema), "--tools", "", "--setting-sources", "",
                 "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
                 "--system-prompt", self.SYSTEM],
                input=prompt, capture_output=True, text=True, timeout=self.timeout, cwd=tmp,
            )  # fmt: skip
        if run.returncode != 0:
            raise RuntimeError(f"claude exited {run.returncode}: {(run.stderr or run.stdout)[-500:]}")
        reply = json.loads(run.stdout)
        if reply.get("is_error") or "structured_output" not in reply:
            raise RuntimeError(f"claude gave no structured output: {str(reply.get('result'))[:300]}")
        return reply["structured_output"]


PROVIDERS = {"codex": Codex, "ollama": Ollama, "claude": Claude}


def get(name: str) -> Provider:
    return PROVIDERS[name]()
