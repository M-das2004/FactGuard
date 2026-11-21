"""Estimate how often built-in templates match real prompts.

Usage:  python measure_template_match.py prompts.txt     (one requirement per line)
        python measure_template_match.py prompts.jsonl   (objects with a "prompt" or "text" field)
Use prompts from a public benchmark (e.g. HumanEval/MBPP) you did not write.
"""
import json
import sys

from modules.test_generator import generate_from_requirement


def load(path):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if path.endswith(".jsonl"):
                item = json.loads(line)
                line = item.get("prompt") or item.get("text") or ""
            yield line


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    prompts = list(load(sys.argv[1]))
    hits = sum(1 for p in prompts if generate_from_requirement(p))
    print(f"{hits}/{len(prompts)} prompts ({100 * hits / max(len(prompts), 1):.0f}%) match a template")


if __name__ == "__main__":
    main()
