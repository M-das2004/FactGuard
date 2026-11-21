"""Optional LLM repair hook for code the built-in recipes cannot fix.

make_anthropic_llm() returns a function `llm_fn(prompt) -> text` for analyze(llm_fn=...).
Uses only the standard library. The key is read from the ANTHROPIC_API_KEY environment
variable (or passed in) and is never stored. Whatever the LLM returns is just a candidate:
it is accepted only if it passes FactGuard's own verification.
NOTE: your code and requirement are sent to the provider when this is used.
"""
import json
import os
import urllib.request

DEFAULT_MODEL = "claude-sonnet-5-5"


def make_anthropic_llm(api_key=None, model=DEFAULT_MODEL, timeout=60):
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None

    def llm_fn(prompt):
        body = json.dumps({"model": model, "max_tokens": 2000,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body, method="POST",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode())
        return "".join(part.get("text", "") for part in data.get("content", []))

    return llm_fn
