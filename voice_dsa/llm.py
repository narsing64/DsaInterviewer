"""Thin Sarvam wrappers: chat, JSON chat, speech-to-text, text-to-speech."""
import base64
import json
import os
import re
from pathlib import Path

from sarvamai import SarvamAI

_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())

if not os.environ.get("SARVAM_API_KEY"):
    raise SystemExit("SARVAM_API_KEY is not set. Add it to .env.")

client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])

CHAT_MODEL = "sarvam-105b-conversations"
STT_MODEL = "saaras:v3"
TTS_MODEL = "bulbul:v3"
LANG = "en-IN"
DEFAULT_VOICE = "shubh"


def chat(system: str, user: str, history: list | None = None, json_mode: bool = False,
         temperature: float | None = None) -> str:
    messages = [{"role": "system", "content": system}] + (history or []) + [{"role": "user", "content": user}]
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if temperature is not None:
        kwargs["temperature"] = temperature
    text = client.chat.completions(model=CHAT_MODEL, messages=messages, **kwargs).choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def chat_json(system: str, user: str, default: dict) -> dict:
    """JSON-mode chat; falls back to `default` if the model returns something unparseable."""
    try:
        raw = chat(system, user, json_mode=True, temperature=0)
        return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception as e:
        print("json agent failed:", repr(e))
        return default


def transcribe(audio: bytes, mime: str) -> str:
    return client.speech_to_text.transcribe(
        file=("answer", audio, mime), model=STT_MODEL, mode="transcribe", language_code=LANG
    ).transcript.strip()


def speak(text: str, voice: str = DEFAULT_VOICE) -> str:
    """Returns base64 wav, or '' if TTS fails (the interview continues as text)."""
    clean = re.sub(r"[*#`_]", "", text)[:2400]
    if not clean.strip():
        return ""
    try:
        return client.text_to_speech.convert(
            text=clean, language_code=LANG, speaker=voice, model=TTS_MODEL
        ).audios[0]
    except Exception as e:
        print("tts failed:", repr(e))
        return ""
