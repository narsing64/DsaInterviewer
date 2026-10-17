"""The specialist agents. Each one owns a single job and a single prompt.

Presenter     - opens the interview and states the problem (no LLM, instant)
Analyst       - classifies what the candidate just said and extracts signals
Clarifier     - answers clarifying questions without leaking the solution
Prober        - asks ONE targeted follow-up on the candidate's last answer
Hinter        - gives progressively stronger hints on request
CodeReviewer  - reviews submitted code for correctness, bugs and complexity
Evaluator     - scores the whole interview on a rubric
Coach         - turns the evaluation into a study plan
"""
import json
import random

from .llm import chat, chat_json

SPOKEN = ("Your reply is spoken aloud: plain text only, no markdown, no lists, no code. "
          "Natural interviewer tone.")


def _tail(state: dict, n: int = 14) -> str:
    return "\n".join(f"{t['role'].capitalize()}: {t['content']}" for t in state["transcript"][-n:])


def _said(state: dict, n: int = 12) -> list:
    """The candidate's own spoken/typed statements (code submissions excluded)."""
    return [t["content"] for t in state["transcript"]
            if t["role"] == "candidate" and not t["content"].startswith("[submitted code]")][-n:]


def _numbered(items: list) -> str:
    return "\n".join(f"{i + 1}. {x}" for i, x in enumerate(items)) or "(nothing yet)"


# ── Presenter ───────────────────────────────────────────────────────────────
def presenter(state: dict) -> str:
    p = state["problem"]
    article = "an" if p["difficulty"][0] in "aeiou" else "a"
    return (f"Hello, welcome to your mock interview. Today's problem is {p['title']}, {article} {p['difficulty']} "
            f"{p['topic'].replace('_', ' ')} problem. {p['description']} "
            "Feel free to ask clarifying questions, or tell me your approach when you're ready.")


# ── Analyst ─────────────────────────────────────────────────────────────────
ANALYST_DEFAULT = {"intent": "probe_answer", "algorithm": "", "complexity": "", "edge_cases": [], "confidence": "medium"}


def analyst(state: dict, text: str) -> dict:
    last_q = next((t["content"] for t in reversed(state["transcript"]) if t["role"] == "interviewer"), "")
    system = (
        "You analyse a candidate in a spoken coding interview. Return JSON only with keys: "
        '"intent" (of the LATEST utterance only; one of: clarifying_question, approach, probe_answer, hint_request, wants_to_end, skip_code, other), '
        '"algorithm" (technique they have named ANYWHERE in their statements, else ""), '
        '"complexity" (time/space complexity they have stated ANYWHERE, e.g. "O(n) time, O(n) space", else ""), '
        '"edge_cases" (every specific edge case they have named ANYWHERE, else []), "confidence" (high, medium or low).\n'
        "Signals are CUMULATIVE: read all their statements, and keep anything they said earlier. "
        "intent rules: if the latest utterance explains how they would solve the problem (names a technique or gives steps) "
        "it is approach, even if it also contains a question; clarifying_question = ONLY asking the interviewer about the "
        "problem's inputs, outputs or constraints; probe_answer = answering the interviewer's last question; hint_request = "
        "asks for a hint or says they are stuck; wants_to_end = wants to stop; skip_code = does not want to write code."
    )
    user = (f"Problem: {state['problem']['description']}\nInterview stage: {state['stage']}\n"
            f"Interviewer's last message: {last_q}\n\nAll candidate statements so far (oldest first):\n"
            f"{_numbered(_said(state))}\n\nLATEST utterance: \"{text}\"")
    out = chat_json(system, user, ANALYST_DEFAULT)
    return {**ANALYST_DEFAULT, **out}


# ── Clarifier ───────────────────────────────────────────────────────────────
def clarifier(state: dict, question: str) -> str:
    p = state["problem"]
    system = ("You are a technical interviewer answering a candidate's clarifying question. " + SPOKEN +
              " Answer in one or two sentences using the problem data. Hint if useful but never reveal the solution.")
    user = (f"Problem: {p['description']}\nConstraints: {p['constraints']}\nReference approach (secret): "
            f"{p['optimal_approach']}\nCandidate asked: \"{question}\"")
    return chat(system, user)


# ── Prober ──────────────────────────────────────────────────────────────────
def prober(state: dict) -> str:
    p = state["problem"]
    said = _said(state)
    latest = said[-1] if said else ""
    system = ("You are a technical interviewer. " + SPOKEN + " The candidate just answered. First react to ONE specific thing "
              "they actually said (paraphrase it briefly), then ask exactly ONE follow-up that builds on their answer. "
              "Never re-ask anything already answered or covered, and never ask something their own words already answer. "
              "Two or three sentences total. Return only what you will say.")
    covered = (f"algorithm={state['algorithm'] or 'none'}; complexity={state['complexity'] or 'none'}; "
               f"edge cases={', '.join(state['edge_cases']) or 'none'}")
    user = (
        f"Problem: {p['description']}\nReference approach (secret): {p['optimal_approach']}\n"
        f"Known edge cases (secret): {', '.join(p['edge_cases'])}\n\n"
        f"Everything the candidate has said (oldest first):\n{_numbered(said)}\n\n"
        f"Conversation so far:\n{_tail(state)}\n\n"
        f"ALREADY COVERED by the candidate (do not ask again): {covered}\n"
        f"Their LATEST answer: \"{latest}\"\nThis is follow-up {state['probes'] + 1}.\n"
        "Choose what to probe next, skipping anything covered: complexity not yet stated; then a specific edge case; "
        "then a gap, wrong claim or assumption in what they said; then a better approach; then trace a small example."
    )
    return chat(system, user)


# ── Hinter ──────────────────────────────────────────────────────────────────
HINT_LEVELS = {
    1: "a gentle nudge toward the right way of thinking, without naming the technique",
    2: "name the technique or data structure that applies and why, without the steps",
    3: "an outline of the key steps in words, but no code and no full solution",
}


def hinter(state: dict) -> str:
    level = min(state["hints"] + 1, 3)
    p = state["problem"]
    system = ("You are a supportive interviewer giving a hint. " + SPOKEN + f" Give {HINT_LEVELS[level]}. "
              "At most two sentences.")
    user = f"Problem: {p['description']}\nReference approach (secret): {p['optimal_approach']}\nConversation:\n{_tail(state)}"
    return chat(system, user)


# ── CodeReviewer ────────────────────────────────────────────────────────────
def code_reviewer(state: dict, code: str) -> dict:
    p = state["problem"]
    system = (
        "You review a candidate's solution in a coding interview. Return JSON only with keys: "
        '"correct" (true, false), "bugs" (list of short strings), "time_complexity" (string), "space_complexity" (string), '
        '"quality" (integer 0-2: 2 = correct and clean, 1 = mostly right or messy, 0 = wrong or incomplete), '
        '"spoken" (one or two plain sentences of feedback to say aloud, no code).'
    )
    user = (f"Problem: {p['description']}\nReference approach: {p['optimal_approach']}\n"
            f"Candidate code:\n{code}")
    return chat_json(system, user, {"correct": False, "bugs": [], "time_complexity": "?", "space_complexity": "?",
                                    "quality": 1, "spoken": "I could not fully review that code, but thanks for submitting it."})


# ── Evaluator ───────────────────────────────────────────────────────────────
CRITERIA = ["clarification", "communication", "complexity", "edge_cases", "adaptability"]

RUBRIC = """Score each criterion 0-2 strictly from transcript evidence. Be fair; credit correct answers given when asked.
clarification: 2 = asked a meaningful clarifying question, OR the problem was unambiguous and they proceeded confidently; 1 = vague or skipped questions on an ambiguous problem; 0 = ignored real ambiguity.
communication: 2 = named the algorithm AND explained key steps; 1 = vague or only after prompting; 0 = never explained.
complexity: 2 = stated or clearly implied correct time complexity; 1 = partly wrong or vague; 0 = could not state any.
edge_cases: 2 = named at least one specific edge case at any point; 1 = only acknowledged they exist; 0 = never engaged.
adaptability: 2 = built on or corrected their thinking after follow-ups; 1 = incomplete or confused; 0 = could not respond."""


def evaluator(state: dict) -> dict:
    system = ("You evaluate a mock coding interview. Return JSON only with keys: "
              '"scores" (object with integer keys clarification, communication, complexity, edge_cases, adaptability, each 0-2), '
              '"strengths" (2-3 short specific strings), "improvements" (2-3 short specific strings). ' + RUBRIC)
    reviews = state["code_reviews"]
    code_note = (f"Code review results: {json.dumps(reviews[-1])}" if reviews else "No code was submitted.")
    said = _said(state, 40)
    user = (f"Problem: {state['problem']['title']} - {state['problem']['description']}\n"
            f"Hints requested: {state['hints']}\n{code_note}\n\n"
            f"THE CANDIDATE'S OWN WORDS, verbatim (this is the evidence; credit anything stated here, even if brief "
            f"or said early):\n{_numbered(said)}\n\n"
            f"Signals already detected: algorithm={state['algorithm'] or 'none'}; complexity={state['complexity'] or 'none'}; "
            f"edge cases={', '.join(state['edge_cases']) or 'none'}; "
            f"clarifying questions asked={state['clarifying_questions']}.\n\n"
            f"Full transcript:\n{_tail(state, 60)}")
    raw = chat_json(system, user, {})
    s = raw.get("scores", {}) if isinstance(raw.get("scores"), dict) else {}
    scores = {k: max(0, min(2, int(s.get(k, 1) or 0))) for k in CRITERIA}
    # floors from signals the Analyst already caught, so a model slip can't erase evidence
    if state["complexity"]:
        scores["complexity"] = max(scores["complexity"], 1)
    if state["edge_cases"]:
        scores["edge_cases"] = max(scores["edge_cases"], 1 if len(state["edge_cases"]) == 1 else 2)
    if state["algorithm"]:
        scores["communication"] = max(scores["communication"], 1)
    if state["clarifying_questions"]:
        scores["clarification"] = max(scores["clarification"], 1)
    if state["probes"] >= 1 and said:
        scores["adaptability"] = max(scores["adaptability"], 1)
    total = sum(scores.values())
    penalty = 1 if state["hints"] >= 3 else 0
    total = max(0, total - penalty)
    code_quality = max(0, min(2, int(reviews[-1].get("quality", 0)))) if reviews else None
    verdict = "Strong" if total >= 8 else "Average" if total >= 5 else "Needs Work"
    return {
        "scores": scores, "code_quality": code_quality, "hint_penalty": penalty, "total": total, "verdict": verdict,
        "strengths": raw.get("strengths", [])[:3], "improvements": raw.get("improvements", [])[:3],
    }


# ── Coach ───────────────────────────────────────────────────────────────────
def coach(state: dict, problems: list) -> dict:
    p, ev = state["problem"], state["scores"]
    system = ("You are a DSA coach. Return JSON only with keys: "
              '"study_plan" (exactly 3 short, concrete next steps tailored to the weaknesses), '
              '"model_approach" (3-4 plain sentences explaining the ideal solution and its complexity).')
    user = (f"Problem: {p['title']}\nReference approach: {p['optimal_approach']}\n"
            f"Scores: {json.dumps(ev['scores'])}\nImprovements: {ev['improvements']}")
    out = chat_json(system, user, {"study_plan": ev["improvements"], "model_approach": p["optimal_approach"]})
    related = [x for x in problems if x["topic"] == p["topic"] and x["id"] != p["id"]]
    out["related"] = [{"title": x["title"], "difficulty": x["difficulty"]} for x in random.sample(related, min(3, len(related)))]
    return out
