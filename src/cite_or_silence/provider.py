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
    """A local model through Ollama; the fallback that costs nothing and needs no login."""

    def __init__(self, model: str = "qwen3:14b", url: str = "http://localhost:11434", timeout: int = 600):
        self.model, self.url, self.timeout = model, url, timeout
        self.name = f"ollama:{model}"

    def complete(self, prompt: str, schema: dict) -> dict:
        r = httpx.post(
            f"{self.url}/api/chat",
            json={"model": self.model, "messages": [{"role": "user", "content": prompt}],
                  "format": schema, "stream": False, "think": False, "options": {"temperature": 0}},
            timeout=self.timeout,
        )  # fmt: skip
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])


def get(name: str) -> Provider:
    return {"codex": Codex, "ollama": Ollama}[name]()
