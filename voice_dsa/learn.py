"""Learn + Quiz agents. Generated content is cached in the database, so each topic is generated once
and then served instantly to every user (this is what makes the content side cheap to scale)."""
import random

from . import catalog, db
from .llm import chat_json

POOL_SIZE = 4  # distinct quiz sets cached per (topic, difficulty) before we start reusing them


def note(subject: str, topic: str) -> dict:
    if not catalog.valid(subject, topic):
        raise ValueError("Unknown topic.")
    key = f"note:{subject}:{topic}"
    cached = db.kv_get(key)
    if cached:
        return cached
    system = (
        "You are a senior engineer writing a concise interview study note. Return JSON only with keys: "
        '"summary" (3-4 plain sentences), "key_points" (6-8 short strings), '
        '"interview_questions" (5 objects, each {"q": string, "a": 2-3 sentence model answer}), '
        '"pitfalls" (3-4 common mistakes candidates make), "cheat_sheet" (4-6 one-line facts or formulas to memorise). '
        "Be accurate and specific. No markdown."
    )
    out = chat_json(system, f"Subject: {catalog.SUBJECTS[subject]['title']}\nTopic: {topic}", {})
    if not out.get("key_points") or not out.get("interview_questions"):
        raise ValueError("Could not generate this note right now. Please try again.")
    out["topic"], out["subject"] = topic, subject
    db.kv_set(key, out)
    return out


def _valid_question(q: dict) -> bool:
    opts = q.get("options")
    return (isinstance(q.get("q"), str) and isinstance(opts, list) and len(opts) == 4 and len(set(map(str, opts))) == 4
            and isinstance(q.get("answer"), int) and 0 <= q["answer"] < 4 and bool(q.get("explanation")))


def _generate_quiz(subject: str, topic: str, difficulty: str, n: int) -> list:
    system = (
        f"You write {difficulty}-level multiple choice questions for software engineering interviews. Return JSON only: "
        '{"questions": [{"q": string, "options": [4 distinct strings], "answer": integer 0-3 index of the correct option, '
        '"explanation": 1-2 sentences on why it is correct}]}. Exactly one option must be correct. Vary the position of the '
        "correct answer. Test understanding, not trivia. No markdown."
    )
    for _ in range(2):
        out = chat_json(system, f"Subject: {catalog.SUBJECTS[subject]['title']}\nTopic: {topic}\nNumber of questions: {n}", {})
        qs = [q for q in out.get("questions", []) if isinstance(q, dict) and _valid_question(q)]
        if len(qs) >= max(3, n - 1):
            return qs[:n]
    raise ValueError("Could not generate a quiz right now. Please try again.")


def quiz(subject: str, topic: str, difficulty: str = "medium", n: int = 5) -> dict:
    if not catalog.valid(subject, topic) or difficulty not in ("easy", "medium", "hard"):
        raise ValueError("Unknown topic or difficulty.")
    n = max(3, min(int(n), 10))
    key = f"quiz:{subject}:{topic}:{difficulty}:{n}"
    pool = db.kv_get(key) or []
    if len(pool) >= POOL_SIZE:
        questions = random.choice(pool)
    else:
        questions = _generate_quiz(subject, topic, difficulty, n)
        db.kv_set(key, pool + [questions])
    return {"subject": subject, "topic": topic, "difficulty": difficulty, "questions": questions}
