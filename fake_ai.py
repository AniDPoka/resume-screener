"""A stand-in for the real AI, used by tests.py and make_example.py. It never contacts Groq.

It answers in exactly the shape the real AI is asked for, so the real loop code can be run and
tested without a key. Nothing made with it is ever shown as a real result: make_example.py marks
its output "simulated".
"""

import json


def reply(must, nice, quote="Wrote SQL queries"):
    """A reply with the given verdicts, e.g. reply(["met"] * 4, ["not met"] * 5).
    Every "met" or "partly" verdict gets the given quote as evidence."""
    item = lambda v: {"requirement": "ignored", "verdict": v, "quotes": [quote] if v != "not met" else [], "reason": "Simulated reason."}
    return json.dumps({"must_have": [item(v) for v in must], "nice_to_have": [item(v) for v in nice]})


def queue(replies):
    """A fake AI that gives back the replies in order. call.prompts records what it was sent."""
    waiting = list(replies)

    def call(prompt):
        call.prompts.append(prompt)
        return waiting.pop(0), {"prompt_tokens": 100, "reply_tokens": 50, "seconds": 0.1}
    call.prompts = []
    return call


def by_prompt(choose):
    """A fake AI whose reply depends on the prompt: choose(prompt, number of calls so far) -> reply."""
    def call(prompt):
        call.prompts.append(prompt)
        return choose(prompt, len(call.prompts)), {"prompt_tokens": 100, "reply_tokens": 50, "seconds": 0.1}
    call.prompts = []
    return call
