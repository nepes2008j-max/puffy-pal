"""Puffy Pal backend: one Flask file.

Local (laptop):   LLM = Ollama toy-brain, voice = Kokoro.
PythonAnywhere:   LLM = Groq (set LLM_URL / LLM_MODEL / LLM_KEY), voice = browser fallback.
Both speak the OpenAI chat-completions format, so only env vars change.
"""
import hmac
import io
import json
import math
import os
import re
import time
import urllib.request
import uuid
import wave
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request

LLM_URL = os.environ.get("LLM_URL", "http://localhost:11434/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "toy-brain")
LLM_KEY = os.environ.get("LLM_KEY", "")
REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "none")  # set to "" for models without reasoning (e.g. Llama)
APP_TOKEN = os.environ.get("APP_TOKEN", "")  # if set, the web app must send it (stops strangers burning your API credit)
# Only these web pages may call the API (stops any random site you visit from using your laptop's AI/mic transcription).
ALLOWED_ORIGINS = set(os.environ.get(
    "ALLOWED_ORIGINS", "https://nepes2008j-max.github.io,http://localhost:5000,http://127.0.0.1:5000").split(","))
KOKORO_DIR = Path(os.environ.get("KOKORO_DIR", Path.home() / "Desktop/ai/kokoro"))
VOICE = os.environ.get("VOICE", "af_heart")

WEB_DIR = Path(__file__).resolve().parent.parent / "docs"
app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 5_000_000  # rejects huge uploads before reading them
MAX_AUDIO_SECONDS = 20

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


ROOT = Path(__file__).resolve().parent.parent
ALLOWED_HOSTS = set(os.environ.get("ALLOWED_HOSTS", "localhost:5000,127.0.0.1:5000").split(","))


def tunnel_origin():
    """The exact public tunnel address start.sh wrote (empty if no tunnel). Re-read each time: the tunnel can restart."""
    try:
        return (ROOT / "public_url.txt").read_text().strip()
    except OSError:
        return ""


def origin_ok(origin):
    """Only explicitly listed pages: the allowlist plus this laptop's own tunnel address. Never 'Origin == Host'
    (a DNS-rebinding site controls both)."""
    return bool(origin) and (origin in ALLOWED_ORIGINS or origin == tunnel_origin())


def host_ok():
    """Blocks DNS rebinding: a random domain pointed at 127.0.0.1 arrives with its own Host header."""
    return request.host in ALLOWED_HOSTS or request.host == urlparse(tunnel_origin()).netloc


@app.after_request
def cors(resp):
    origin = request.headers.get("Origin", "")
    if origin_ok(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-App-Token"
        resp.headers["Access-Control-Allow-Private-Network"] = "true"  # lets the GitHub Pages site reach this laptop's localhost
        resp.headers["Vary"] = "Origin"
    return resp


# ponytail: in-memory per-IP limit, fine for one server process; use Redis or the host's limiter if it ever scales out.
RATE_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "40"))  # a chatting child uses well under 10
LIMITED = {"/api/chat", "/api/talk", "/api/stt", "/api/tts"}
_hits = defaultdict(deque)


TRUSTED_IP_HEADER = os.environ.get("TRUSTED_IP_HEADER", "")  # PythonAnywhere: X-Real-IP (its proxy overwrites it)


def client_ip():
    """Visitor address for rate limiting, only from headers a trusted proxy sets (clients can fake any header)."""
    if TRUSTED_IP_HEADER and request.headers.get(TRUSTED_IP_HEADER):
        return request.headers[TRUSTED_IP_HEADER]
    tunnel = urlparse(tunnel_origin()).netloc
    if tunnel and request.host == tunnel and request.remote_addr == "127.0.0.1":
        return request.headers.get("CF-Connecting-IP") or "tunnel"  # cloudflared: Cloudflare overwrites this header
    return request.remote_addr or "?"


def too_many(ip):
    now = time.monotonic()
    if len(_hits) > 5000:  # cap memory: drop visitors with nothing in the last minute, then everyone if still huge
        for k in [k for k, q in _hits.items() if not q or now - q[-1] > 60]:
            del _hits[k]
        if len(_hits) > 5000:
            _hits.clear()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_PER_MIN:
        return True
    q.append(now)
    return False


@app.before_request
def guard():
    if not host_ok():
        return jsonify(error="unknown host"), 403
    if request.method == "OPTIONS":
        return Response(status=204)
    origin = request.headers.get("Origin")
    if origin and not origin_ok(origin) and request.path.startswith("/api/"):
        return jsonify(error="origin not allowed"), 403  # browsers send Origin; curl/scripts on this machine don't
    if request.path.startswith("/api/") and request.path != "/api/health" and APP_TOKEN \
            and not hmac.compare_digest(request.headers.get("X-App-Token", ""), APP_TOKEN):
        return jsonify(error="bad access code"), 401  # checked first: strangers can't use up a visitor's quota
    if request.path in LIMITED and too_many(client_ip()):
        return jsonify(error="slow down"), 429


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/health")
def health():
    return jsonify(ok=True, model=LLM_MODEL, voice="kokoro" if kokoro() else "browser",
                   stt="whisper" if has_stt() else "browser", token_required=bool(APP_TOKEN))


def llm_request(body):
    """(payload, headers, max_sentences) for the model, or None when the child's message trips the safety filter."""
    msgs = chat_messages(body)
    if msgs[-1]["role"] == "user" and UNSAFE.search(msgs[-1]["content"]):
        return None
    story = (body.get("profile") or {}).get("focus") == "story"
    payload = {
        "model": LLM_MODEL,
        "messages": msgs,
        "max_tokens": 200 if story else 90,
        "temperature": 0.6,
    }
    if REASONING_EFFORT:  # Qwen3: "none" skips "thinking" (~0.6s instead of seconds); other models may reject it
        payload["reasoning_effort"] = REASONING_EFFORT
    headers = {"Content-Type": "application/json"}
    if LLM_KEY:
        headers["Authorization"] = f"Bearer {LLM_KEY}"
    return payload, headers, 6 if story else 3


@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True) or {}
    req_parts = llm_request(body)
    if req_parts is None:
        return Response(SAFE_REPLY + "\n", mimetype="text/plain") if body.get("stream") else jsonify(reply=SAFE_REPLY)
    payload, headers, max_sentences = req_parts
    if body.get("stream"):
        return Response(stream_sentences(payload, headers, max_sentences), mimetype="text/plain")
    req = urllib.request.Request(LLM_URL, json.dumps(payload).encode(), headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            reply = clean(json.load(r)["choices"][0]["message"].get("content") or "")
    except Exception as e:  # child should hear something friendly, parent sees the error in logs
        app.logger.error("LLM error: %s", e)
        return jsonify(reply="Oops, my brain is taking a nap. Can you try again?", error=str(e)), 502
    if UNSAFE.search(reply):
        reply = SAFE_REPLY
    return jsonify(reply=short(reply, max_sentences) or "Hmm, can you say that again?")


def stream_sentences(payload, headers, max_sentences):
    """Yield the reply one finished sentence per line, so the voice can start on sentence 1
    while the model is still writing sentence 2. Same cleaning + safety filter as /api/chat."""
    req = urllib.request.Request(LLM_URL, json.dumps({**payload, "stream": True}).encode(), headers)
    buf, sent = "", 0

    def emit(sentence):
        s = clean(sentence)
        if not s:
            return None
        return SAFE_REPLY if UNSAFE.search(s) else s

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            for line in r:
                line = line.decode("utf-8", "ignore").strip()
                if not line.startswith("data:") or line.endswith("[DONE]"):
                    continue
                delta = (json.loads(line[5:])["choices"][0].get("delta") or {}).get("content") or ""
                buf += delta
                while m := re.search(r"[.!?]+\s", buf):  # sentence is finished once the next space arrives
                    sentence, buf = buf[: m.end()], buf[m.end():]
                    s = emit(sentence)
                    if s:
                        yield s + "\n"
                        sent += 1
                        if s == SAFE_REPLY or sent >= max_sentences:
                            return
            s = emit(buf)
            if s and sent < max_sentences:
                yield s + "\n"
            elif not sent:
                yield "Hmm, can you say that again?\n"
    except Exception as e:
        app.logger.error("LLM stream error: %s", e)
        if not sent:
            yield "Oops, my brain is taking a nap. Can you try again?\n"


_kokoro = None


def kokoro():
    """Load Kokoro once if it's installed; None on servers without it (browser voice is used instead)."""
    global _kokoro
    if _kokoro is None:
        try:
            import onnxruntime
            try:  # GPU voice: ~0.14s per sentence vs ~0.6s on CPU. onnxruntime falls back to CPU by itself if CUDA is missing.
                onnxruntime.preload_dlls()  # loads CUDA/cuDNN from the nvidia-* pip packages
                os.environ.setdefault("ONNX_PROVIDER", "CUDAExecutionProvider")
            except Exception:
                pass
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(str(KOKORO_DIR / "onnx/model.onnx"), str(KOKORO_DIR / "voices-v1.0.bin"))
            _kokoro.create("Ready.", voice=VOICE, speed=1.0, lang="en-us")  # warm-up: first run is slow
        except Exception:
            _kokoro = False
    return _kokoro or None


def safe_speed(value):
    """Voice speed from the client: any junk (text, NaN, inf) becomes the default 0.9, then clamped to 0.6-1.3."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.9
    return min(max(v, 0.6), 1.3) if math.isfinite(v) else 0.9


def wav_bytes(k, text, speed):
    import numpy as np
    samples, rate = k.create(text, voice=VOICE, speed=safe_speed(speed), lang="en-us")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def mp3_bytes(k, text, speed):
    """Voice as 48 kbps MP3: ~8x smaller than WAV (matters on phones), plays in every browser, ~15 ms to encode."""
    import av
    import numpy as np
    samples, rate = k.create(text, voice=VOICE, speed=safe_speed(speed), lang="en-us")
    buf = io.BytesIO()
    with av.open(buf, "w", format="mp3") as out:
        st = out.add_stream("libmp3lame", rate=rate)
        st.bit_rate, st.layout = 48000, "mono"
        frame = av.AudioFrame.from_ndarray(np.clip(samples, -1, 1).astype(np.float32).reshape(1, -1), format="flt", layout="mono")
        frame.sample_rate = rate
        for packet in [*st.encode(frame), *st.encode(None)]:
            out.mux(packet)
    return buf.getvalue()


@app.post("/api/tts")
def tts():
    k = kokoro()
    if not k:
        return jsonify(error="no kokoro on this server"), 501
    body = request.get_json(silent=True) or {}
    text = clip(body.get("text"), 600)
    if not text:
        return jsonify(error="empty"), 400
    return Response(wav_bytes(k, text, body.get("speed")), mimetype="audio/wav")


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


def decode_capped(data, max_seconds):
    """Decode to 16 kHz mono float32, giving up (None) as soon as it runs past max_seconds.
    Stops early instead of decoding everything first: a tiny compressed file can hold hours of audio."""
    import av
    import numpy as np
    limit, chunks, n = max_seconds * 16000, [], 0
    with av.open(io.BytesIO(data)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        frames = (f for fr in container.decode(audio=0) for f in resampler.resample(fr))
        for f in frames:
            a = f.to_ndarray().reshape(-1)
            n += len(a)
            if n > limit:
                return None
            chunks.append(a)
        chunks += [f.to_ndarray().reshape(-1) for f in resampler.resample(None)]  # flush the tail
    return (np.concatenate(chunks).astype(np.float32) / 32768.0) if chunks else np.zeros(0, np.float32)


STT_URL = os.environ.get("STT_URL", "")  # cloud Whisper for servers without a GPU, e.g. Groq:
#                                        https://api.groq.com/openai/v1/audio/transcriptions
STT_MODEL = os.environ.get("STT_MODEL", "whisper-large-v3-turbo")
STT_KEY = os.environ.get("STT_KEY", LLM_KEY)


def has_stt():
    return bool(whisper() or STT_URL)


def cloud_transcribe(audio, ctype):
    """OpenAI-compatible /audio/transcriptions (Groq, OpenAI...). Size-capped: no decoder on small servers."""
    if len(audio) > 1_000_000:  # ~20s of phone mic audio is well under 200 KB
        raise ValueError("too long")
    ext = "m4a" if "mp4" in ctype else "ogg" if "ogg" in ctype else "webm"
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
             for k, v in (("model", STT_MODEL), ("language", "en"), ("prompt", "Hello Puffy Pal!"), ("response_format", "json"))]
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="speech.{ext}"\r\n'
                 f'Content-Type: {ctype or "audio/webm"}\r\n\r\n'.encode() + audio + b"\r\n")
    req = urllib.request.Request(STT_URL, b"".join(parts) + f"--{b}--\r\n".encode(),
                                 {"Content-Type": f"multipart/form-data; boundary={b}", "Authorization": f"Bearer {STT_KEY}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return (json.load(r).get("text") or "").strip()


def transcribe(audio, ctype=""):
    """Audio bytes -> text, with local Whisper (GPU laptop) or cloud Whisper (STT_URL).
    Raises ValueError for empty / too long / unreadable audio."""
    if not audio:
        raise ValueError("empty")
    if not whisper():
        return cloud_transcribe(audio, ctype)
    samples = decode_capped(audio, MAX_AUDIO_SECONDS)
    if samples is None:
        raise ValueError("too long")
    segments, _ = whisper().transcribe(samples, language="en", beam_size=1, vad_filter=True,
                                       initial_prompt="Hello Puffy Pal!")  # primes the toy's name
    return " ".join(seg.text.strip() for seg in segments).strip()


@app.post("/api/stt")
def stt():
    if not has_stt():
        return jsonify(error="no whisper on this server"), 501
    try:
        return jsonify(text=transcribe(request.get_data(), request.content_type or ""))  # MAX_CONTENT_LENGTH already capped the size
    except Exception as e:
        app.logger.warning("STT rejected: %s", e)
        return jsonify(error="could not read audio"), 400


@app.post("/api/talk")
def talk():
    """One round trip for the whole turn (matters over the internet: ~0.3s per trip saved):
    audio or typed text in -> NDJSON stream out: {"heard": ...}, then {"text": sentence, "audio": base64 mp3} each."""
    import base64
    try:
        meta = json.loads(request.form.get("meta") or "{}")
    except ValueError:
        return jsonify(error="bad meta"), 400
    text = clip(meta.get("text"), 500)
    audio = request.files.get("audio")
    if audio and has_stt():
        try:
            text = transcribe(audio.read(), audio.mimetype or "")
        except Exception as e:
            app.logger.warning("STT rejected: %s", e)
            return jsonify(error="could not read audio"), 400
    history = [m for m in (meta.get("messages") or []) if isinstance(m, dict)][-7:]
    body = {"profile": meta.get("profile") or {}, "messages": history + [{"role": "user", "content": text}]}
    speed, k = meta.get("speed"), kokoro()

    def turn():
        yield json.dumps({"heard": text}) + "\n"
        if not text:
            return
        parts = llm_request(body)
        sentences = [SAFE_REPLY + "\n"] if parts is None else stream_sentences(*parts)
        for line in sentences:
            item = {"text": line.strip()}
            if k:
                item["audio"] = base64.b64encode(mp3_bytes(k, item["text"], speed)).decode()
            yield json.dumps(item) + "\n"

    return Response(turn(), mimetype="application/x-ndjson")


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
    # 127.0.0.1 = only this laptop can connect. Set HOST=0.0.0.0 to let phones on your Wi-Fi in.
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)), threaded=True)
