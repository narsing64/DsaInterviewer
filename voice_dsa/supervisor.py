"""Supervisor: owns interview state and routes every candidate turn to the right agent.

Stages:  clarify -> probe -> coding -> done
  clarify  candidate may ask questions; first real approach moves us to probe
  probe    Prober asks follow-ups until complexity + edge cases are covered (min 2, max 5)
  coding   candidate writes code in the editor; CodeReviewer reviews it, then Evaluator closes
Hints, code submissions and "end" can happen at any stage.
"""
import json
import random
import time
import uuid
from pathlib import Path

from . import agents, db
from .llm import speak

PROBLEMS = json.loads((Path(__file__).parent / "problems.json").read_text(encoding="utf-8"))["problems"]
STAGES = ["clarify", "probe", "coding", "done"]
MIN_PROBES, MAX_PROBES = 2, 5

SESSIONS: dict = {}


def topics() -> dict:
    return {"topics": sorted({p["topic"] for p in PROBLEMS}), "difficulties": ["easy", "medium", "hard"]}


def _log(state: dict, role: str, content: str, agent: str | None = None) -> None:
    state["transcript"].append({"role": role, "content": content, **({"agent": agent} if agent else {})})


def _snapshot(state: dict) -> dict:
    return {
        "stage": state["stage"], "algorithm": state["algorithm"], "complexity": state["complexity"],
        "edge_cases": state["edge_cases"], "probes": state["probes"], "hints": state["hints"],
        "clarifying_questions": state["clarifying_questions"],
    }


def _respond(state: dict, text: str, agent: str, voice: str, **extra) -> dict:
    _log(state, "interviewer", text, agent)
    return {"reply": text, "agent": agent, "audio": speak(text, voice), "state": _snapshot(state), **extra}


def start(topic: str | None, difficulty: str | None) -> dict:
    pool = [p for p in PROBLEMS if (not topic or p["topic"] == topic) and (not difficulty or p["difficulty"] == difficulty)]
    if not pool:
        raise ValueError("No problems match that topic/difficulty.")
    problem = random.choice(pool)
    state = {
        "id": uuid.uuid4().hex, "problem": problem, "stage": "clarify", "transcript": [], "algorithm": "",
        "complexity": "", "edge_cases": [], "confidence": "", "clarifying_questions": 0, "probes": 0, "hints": 0,
        "code_reviews": [], "scores": None, "report": None, "started": time.time(), "duration_sec": 0, "voice": "shubh",
    }
    SESSIONS[state["id"]] = state
    out = _respond(state, agents.presenter(state), "presenter", state["voice"])
    return {"session_id": state["id"], "problem": {k: problem[k] for k in ("title", "difficulty", "topic", "description", "constraints")}, **out}


def _merge_signals(state: dict, a: dict) -> None:
    if a.get("algorithm"):
        state["algorithm"] = a["algorithm"]
    if a.get("complexity"):
        state["complexity"] = a["complexity"]
    if a.get("confidence"):
        state["confidence"] = a["confidence"]
    for e in a.get("edge_cases") or []:
        if e not in state["edge_cases"]:
            state["edge_cases"].append(e)


def _gaps_covered(state: dict) -> bool:
    if state["probes"] >= MAX_PROBES:
        return True
    return state["probes"] >= MIN_PROBES and bool(state["complexity"]) and bool(state["edge_cases"])


def finish(state: dict, lead: str = "") -> dict:
    """Evaluator + Coach agents close the interview and the result is saved."""
    state["scores"] = agents.evaluator(state)
    state["report"] = agents.coach(state, PROBLEMS)
    state["stage"] = "done"
    state["duration_sec"] = int(time.time() - state["started"])
    db.save_session(state)
    ev = state["scores"]
    spoken = (f"{lead} That's the end of the interview. Your score is {ev['total']} out of 10, verdict {ev['verdict']}. "
              + (f"You did well on: {ev['strengths'][0]}. " if ev["strengths"] else "")
              + (f"Next, work on: {ev['improvements'][0]}. " if ev["improvements"] else "")
              + "Your full scorecard and study plan are on screen.").strip()
    return _respond(state, spoken, "evaluator", state["voice"], result={
        "scores": ev, "report": state["report"], "problem": state["problem"]["title"],
        "duration_sec": state["duration_sec"], "hints": state["hints"], "session_id": state["id"]})


def turn(session_id: str, text: str, code: str = "", end: bool = False) -> dict:
    state = SESSIONS.get(session_id)
    if state is None:
        raise ValueError("This interview session expired (the server restarted). Please start a new interview.")
    if state["stage"] == "done":
        return {"reply": "", "state": _snapshot(state)}
    voice = state["voice"]
    text = (text or "").strip()
    if text:
        _log(state, "candidate", text)

    if end:
        return finish(state, "Alright, let's wrap up.")

    # code submitted from the editor -> CodeReviewer
    if code.strip() and code != state.get("last_code"):
        state["last_code"] = code
        _log(state, "candidate", "[submitted code]\n" + code)
        review = agents.code_reviewer(state, code)
        state["code_reviews"].append(review)
        if state["stage"] == "coding" or _gaps_covered(state):
            return finish(state, review.get("spoken", ""))
        return _respond(state, review.get("spoken", ""), "code_reviewer", voice, review=review)

    a = agents.analyst(state, text)
    _merge_signals(state, a)
    intent = a["intent"]

    if intent == "wants_to_end":
        return finish(state, "Alright, let's wrap up.")

    if intent == "hint_request":
        hint = agents.hinter(state)
        state["hints"] += 1
        return _respond(state, hint, "hinter", voice)

    if state["stage"] == "coding":
        if intent == "skip_code":
            return finish(state, "No problem, we'll skip the code.")
        return _respond(state, "Take your time. Write your solution in the editor and press Submit code, or say skip.",
                        "supervisor", voice)

    if state["stage"] == "clarify":
        if intent == "clarifying_question":
            state["clarifying_questions"] += 1
            return _respond(state, agents.clarifier(state, text), "clarifier", voice)
        state["stage"] = "probe"  # candidate started solving
    else:
        if intent == "clarifying_question":  # a question mid-probe is not an answer
            return _respond(state, agents.clarifier(state, text), "clarifier", voice)
        state["probes"] += 1  # the candidate just answered a probe

    if _gaps_covered(state):
        state["stage"] = "coding"
        return _respond(state, "Good discussion. Now please implement your solution in the editor and press Submit code, "
                        "or say skip if you'd rather not.", "supervisor", voice)

    return _respond(state, agents.prober(state), "prober", voice)
