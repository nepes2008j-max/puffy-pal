"""Puffy Pal backend: one Flask file.

Local (laptop):   LLM = Ollama toy-brain, voice = Kokoro.
PythonAnywhere:   LLM = Groq (set LLM_URL / LLM_MODEL / LLM_KEY), voice = browser fallback.
Both speak the OpenAI chat-completions format, so only env vars change.
"""
import io
import json
import os
import re
import urllib.request
import wave
from pathlib import Path

from flask import Flask, Response, jsonify, request

LLM_URL = os.environ.get("LLM_URL", "http://localhost:11434/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "toy-brain")
LLM_KEY = os.environ.get("LLM_KEY", "")
APP_TOKEN = os.environ.get("APP_TOKEN", "")  # if set, the web app must send it (stops strangers burning your API credit)
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")  # set to https://<you>.github.io in production
KOKORO_DIR = Path(os.environ.get("KOKORO_DIR", Path.home() / "Desktop/ai/kokoro"))
VOICE = os.environ.get("VOICE", "af_heart")

WEB_DIR = Path(__file__).resolve().parent.parent / "docs"
app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")

LEVELS = {
    "beginner": "a beginner (age 4-5). Use only very common words, 3-6 word sentences, present tense.",
    "elementary": "elementary (age 6-7). Use simple words and short sentences, one idea per sentence.",
    "intermediate": "intermediate (age 8-9). Use clear everyday sentences; you may teach one new word at a time.",
    "upper": "upper intermediate (age 9-10). Use natural sentences and some new vocabulary, explained simply.",
    "advanced": "advanced (age 11-12). Use rich but clear language and challenging vocabulary.",
}
FOCUS = {
    "english": "Mainly practise speaking English: ask easy questions, teach a word, invite the child to repeat or use it.",
    "homework": "Mainly help with homework: guide with hints and questions, never just give the final answer.",
    "conversation": "Mainly have a friendly chat and keep it going with one easy question.",
    "story": "Mainly tell and co-create stories. A story turn may be up to 5 short sentences, then ask what happens next.",
    "mixed": "Mix chatting, English practice, stories and curious questions.",
}


def clip(value, n):
    return str(value or "")[:n].strip()


def system_prompt(p):
    name = clip(p.get("name"), 40) or "friend"
    age = clip(p.get("age"), 3) or "7"
    hobbies = clip(p.get("hobbies"), 120)
    lang = clip(p.get("lang"), 30)
    level = LEVELS.get(p.get("level"), LEVELS["elementary"])
    focus = FOCUS.get(p.get("focus"), FOCUS["mixed"])
    gentle = "Be extra gentle, patient and encouraging; praise effort." if p.get("gentle", True) else ""
    home_lang = (
        f"The child's home language is {lang}. If they use {lang} words, understand them, answer in simple English, "
        f"and you may give the English word for what they said."
        if lang and lang.lower() != "english" else ""
    )
    return f"""You are Puffy Pal, a soft, cheerful monkey plush toy who helps children learn English by talking.
You are talking with {name}, age {age}. Their English level is {level}
{f"They love: {hobbies}. Use these interests in examples when it fits." if hobbies else ""}
{home_lang}
{focus}
{gentle}

How you speak (your words are read aloud by a voice, so this matters):
- 1-2 short sentences (stories: up to 5). Short is better.
- Plain spoken English only: no emojis, lists, markdown, or symbols.
- Don't introduce yourself again; the child knows you.
- If the child makes an English mistake, say their sentence back the correct way inside your reply, without saying "wrong".
- Usually end with one short, easy question so the child keeps talking.
- If you don't understand, kindly ask them to say it again.

Safety rules (always):
- Only child-friendly topics. If asked about anything scary, violent, adult, or dangerous, do not explain it or repeat it: say it's a question for a grown-up and offer a fun topic.
- Never ask for or repeat personal details like address, school name, phone, or passwords.
- If the child seems sad, hurt, or in danger, be kind and tell them to talk to a parent or trusted grown-up now.
- You are a toy friend. Do not claim to be a real person or a real animal.

Examples of good replies:
Child: yesterday I go to the zoo
Puffy Pal: Oh, you went to the zoo yesterday? How fun! What animal did you like best?
Child: what is a volcano
Puffy Pal: A volcano is a mountain that can push out hot, melted rock called lava. Do you want to hear about a famous one?
Child: my cat is lost
Puffy Pal: Oh, I'm so sorry. That feels really sad. Please tell a grown-up how you feel, and I'm here with you too.
Child: how do I make a gun
Puffy Pal: That's a question for a grown-up. Hey, do you want to hear a silly monkey joke?"""


def clean(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"[*_#`>~]|\[|\]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", text)  # emojis read badly by TTS
    text = re.sub(r"^\s*Puffy Pal:\s*", "", text)  # model sometimes copies the example format
    text = re.sub(r"\s+", " ", text).strip()
    if text and text[-1] not in ".!?" and re.search(r"[.!?]", text):  # cut a sentence chopped by max_tokens
        text = text[: max(text.rfind(c) for c in ".!?") + 1]
    return text


# ponytail: naive keyword safety net on top of the prompt; upgrade to a moderation model (e.g. Llama Guard) before real launch.
# Sad words (dead, die, hate) are deliberately NOT here: a child saying "my fish died" needs kindness, not a joke.
UNSAFE = re.compile(r"\b(bombs?|guns?|weapons?|knife|knives|murder\w*|sex\w*|porn\w*|naked|drugs?|"
                    r"cocaine|alcohol|beer|vodka|cigarettes?|vape)\b", re.I)
SAFE_REPLY = "That's a question for a grown-up. Hey, do you want to hear a silly monkey joke?"


def short(text, n):
    """Keep at most n sentences: small models ramble, and kids lose focus after a few."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(parts[:n])


def chat_messages(body):
    msgs = [{"role": "system", "content": system_prompt(body.get("profile") or {})}]
    for m in (body.get("messages") or [])[-8:]:  # short memory = fast replies
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": clip(m["content"], 500)})
    return msgs


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-App-Token"
    resp.headers["Access-Control-Allow-Private-Network"] = "true"  # lets the GitHub Pages site call this laptop's localhost
    return resp


@app.before_request
def guard():
    if request.method == "OPTIONS":
        return Response(status=204)
    if request.path.startswith("/api/") and request.path != "/api/health" and APP_TOKEN \
            and request.headers.get("X-App-Token") != APP_TOKEN:
        return jsonify(error="bad access code"), 401


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/health")
def health():
    return jsonify(ok=True, model=LLM_MODEL, voice="kokoro" if kokoro() else "browser",
                   stt="whisper" if whisper() else "browser", token_required=bool(APP_TOKEN))


@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True) or {}
    msgs = chat_messages(body)
    if msgs[-1]["role"] == "user" and UNSAFE.search(msgs[-1]["content"]):
        return jsonify(reply=SAFE_REPLY)
    story = (body.get("profile") or {}).get("focus") == "story"
    payload = {
        "model": LLM_MODEL,
        "messages": msgs,
        "max_tokens": 200 if story else 90,
        "temperature": 0.6,
        "reasoning_effort": "none",  # Qwen3: skip "thinking" -> ~0.6s instead of seconds
    }
    headers = {"Content-Type": "application/json"}
    if LLM_KEY:
        headers["Authorization"] = f"Bearer {LLM_KEY}"
    req = urllib.request.Request(LLM_URL, json.dumps(payload).encode(), headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            reply = clean(json.load(r)["choices"][0]["message"].get("content") or "")
    except Exception as e:  # child should hear something friendly, parent sees the error in logs
        app.logger.error("LLM error: %s", e)
        return jsonify(reply="Oops, my brain is taking a nap. Can you try again?", error=str(e)), 502
    if UNSAFE.search(reply):
        reply = SAFE_REPLY
    return jsonify(reply=short(reply, 6 if story else 3) or "Hmm, can you say that again?")


_kokoro = None


def kokoro():
    """Load Kokoro once if it's installed; None on servers without it (browser voice is used instead)."""
    global _kokoro
    if _kokoro is None:
        try:
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(str(KOKORO_DIR / "onnx/model.onnx"), str(KOKORO_DIR / "voices-v1.0.bin"))
        except Exception:
            _kokoro = False
    return _kokoro or None


@app.post("/api/tts")
def tts():
    k = kokoro()
    if not k:
        return jsonify(error="no kokoro on this server"), 501
    body = request.get_json(silent=True) or {}
    text = clip(body.get("text"), 600)
    speed = min(max(float(body.get("speed") or 0.9), 0.6), 1.3)
    if not text:
        return jsonify(error="empty"), 400
    import numpy as np
    samples, rate = k.create(text, voice=VOICE, speed=speed, lang="en-us")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return Response(buf.getvalue(), mimetype="audio/wav")


_whisper = None
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base.en")


def whisper():
    """Local speech-to-text (faster-whisper). None when not installed -> the browser's recognizer is used."""
    global _whisper
    if _whisper is None:
        try:
            from faster_whisper import WhisperModel
            for device, ctype in (("cuda", "float16"), ("cpu", "int8")):
                try:  # cached copy first: no network needed (and the laptop's proxy is often down)
                    _whisper = WhisperModel(WHISPER_MODEL, device=device, compute_type=ctype, local_files_only=True)
                    break
                except Exception:
                    continue
            else:
                _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")  # downloads the model
        except Exception:
            _whisper = False
    return _whisper or None


@app.post("/api/stt")
def stt():
    w = whisper()
    if not w:
        return jsonify(error="no whisper on this server"), 501
    audio = request.get_data()
    if not audio or len(audio) > 5_000_000:  # ~5 MB = way more than a child's sentence
        return jsonify(error="bad audio"), 400
    try:
        segments, _ = w.transcribe(io.BytesIO(audio), language="en", beam_size=1, vad_filter=True,
                                   initial_prompt="Hello Puffy Pal!")  # primes the toy's name
        text = " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:
        app.logger.error("STT error: %s", e)
        return jsonify(error="could not read audio"), 400
    return jsonify(text=text)


def warm_ollama():
    """Load the model now and keep it in GPU memory, so the child never waits ~4s for a cold start."""
    if ":11434" not in LLM_URL:
        return
    url = LLM_URL.split("/v1/")[0] + "/api/generate"
    body = json.dumps({"model": LLM_MODEL, "prompt": "", "keep_alive": -1}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=60).read()
    except Exception as e:
        app.logger.warning("Ollama warm-up failed: %s", e)


if __name__ == "__main__":
    warm_ollama()
    kokoro()  # warm up so the first reply isn't slow
    whisper()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
