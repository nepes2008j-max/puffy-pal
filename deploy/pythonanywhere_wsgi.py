# PythonAnywhere WSGI file for Puffy Pal.
# Paste this whole file into: Web tab -> "WSGI configuration file" link, replacing everything there.
# Then replace the two things marked  <<<  below and click the green "Reload" button.
import os
import sys

USERNAME = "your-pythonanywhere-username"            # <<< your PythonAnywhere username
os.environ["LLM_KEY"] = "paste-your-groq-key-here"   # <<< from console.groq.com -> API Keys (keep it secret)

# AI brain: Groq (OpenAI-compatible). Qwen3 needs REASONING_EFFORT "none" (no slow "thinking").
os.environ["LLM_URL"] = "https://api.groq.com/openai/v1/chat/completions"
os.environ["LLM_MODEL"] = "qwen/qwen3-32b"
os.environ["REASONING_EFFORT"] = "none"
# If Groq says that model doesn't exist, use a fast Llama instead:
# os.environ["LLM_MODEL"] = "llama-3.1-8b-instant"; os.environ["REASONING_EFFORT"] = ""

# Ears: Groq's cloud Whisper (same key). Voice: the phone's own voice (no GPU here for Kokoro).
os.environ["STT_URL"] = "https://api.groq.com/openai/v1/audio/transcriptions"

# Optional access code: uncomment, pick any word, and type the same word once in the app's
# Settings -> Connection -> Access code. Stops strangers who find the address from using your Groq quota.
# os.environ["APP_TOKEN"] = "pick-a-secret-word"

# Browsers on other websites are blocked, and each visitor gets at most 40 AI requests a minute.
# Scripts can still call the API directly: set APP_TOKEN above if you need it fully private.
os.environ["ALLOWED_HOSTS"] = f"{USERNAME.lower()}.pythonanywhere.com"  # web addresses are lowercase
os.environ["TRUSTED_IP_HEADER"] = "X-Real-IP"  # set by PythonAnywhere's proxy, used for the rate limit
os.environ["ALLOWED_ORIGINS"] = f"https://{USERNAME.lower()}.pythonanywhere.com,https://nepes2008j-max.github.io"

sys.path.insert(0, f"/home/{USERNAME}/puffy_pal/server")
from app import app as application  # noqa: E402
