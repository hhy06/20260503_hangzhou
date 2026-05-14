#!/usr/bin/env python3
"""Run a simulation scenario and get an LLM commentary on what happened.

Usage:
    python3 commentator.py scenario_hangzhou0
    python3 commentator.py scenario1
"""

import sys
import subprocess
import json
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Config - tweak these
# ---------------------------------------------------------------------------
OLLAMA_MODEL = "qwen3-coder:480b-cloud" #"kimi-k2:1t-cloud" #"kimi-k2.5:cloud"
OLLAMA_URL = "http://localhost:11434/api/generate"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tee_run(args: list[str]) -> str:
    """Run a command, print stdout/stderr in real time, return full stdout."""
    full_output: list[str] = []
    with subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            full_output.append(line)
    return "".join(full_output)


def ask_ollama(model: str, prompt: str, url: str = OLLAMA_URL) -> str:
    """Send a prompt to Ollama and return the response text."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
        },
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return f"[Ollama HTTP {e.code}] {e.read().decode()}"
    except urllib.error.URLError as e:
        return f"[Ollama connection failed] {e.reason}. Is `ollama serve` running?"
    except json.JSONDecodeError as e:
        return f"[Ollama bad response] {e}"

    return data.get("response", str(data))


# ---------------------------------------------------------------------------
# Commentary prompt
# ---------------------------------------------------------------------------

COMMENTARY_PROMPT = """\
Below is the full output of a warehouse-simulation run.

Please analyse it and produce a short commentary covering:

1. **Workflow sketch** — what is the flow of materials (source → warehouse → production → sink)?
2. **Jobs** — what transport jobs and production jobs were defined, and did they complete?
3. **Execution quality** — did everything run satisfactorily? Any jobs that failed, materials that got stuck, or orders that never shipped?
4. **Phenomena / bugs / unexpectedness** — anything odd in the timing, inventory left behind, bottlenecks, or anomalies?

Be concise but specific. Reference actual SKU names, node names, quantities and timings from the output.

--- begin simulation output ---
{output}
--- end simulation output ---
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <scenario_name>", file=sys.stderr)
        sys.exit(1)

    scenario = sys.argv[1]

    print("=" * 70)
    print(f"COMMENTATOR: running main.py {scenario}")
    print(f"             model = {OLLAMA_MODEL}")
    print("=" * 70)
    print()

    # -- run simulation and capture output --
    try:
        output = tee_run(["python3", "main.py", scenario])
    except FileNotFoundError:
        print(f"[ERROR] main.py not found — are you in the project root?", file=sys.stderr)
        sys.exit(1)

    print()
    print("=" * 70)
    print("COMMENTATOR: sending to Ollama for commentary ...")
    print("=" * 70)
    print()

    prompt = COMMENTARY_PROMPT.format(output=output)
    commentary = ask_ollama(OLLAMA_MODEL, prompt)

    print("=" * 70)
    print("LLM COMMENTARY")
    print("=" * 70)
    print(commentary)
    print("=" * 70)


if __name__ == "__main__":
    main()
