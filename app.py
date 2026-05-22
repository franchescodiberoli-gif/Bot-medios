import streamlit as st
import os
import sys
import subprocess

st.set_page_config(page_title="MediaBot", page_icon="🤖", layout="centered")

st.title("🤖 MediaBot - Telegram")
st.markdown("""
Este es el panel de control del **MediaBot**.  
El bot está corriendo en segundo plano y escuchando mensajes en Telegram.

---

### ¿Cómo usarlo?
1. Abre Telegram y busca tu bot
2. Envía cualquier link de:
   - 📸 Instagram
   - 🎵 TikTok
   - 📘 Facebook
   - ▶️ YouTube (corto o largo)
   - 👽 Reddit (video, gif, foto, redgif)
   - 🐦 Twitter / X
   - 🧵 Threads

3. El bot te responde con el contenido descargado + info

---
""")

token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if token:
    st.success("✅ Bot token detectado — el bot está activo.")
else:
    st.error("❌ TELEGRAM_BOT_TOKEN no configurado. Agrégalo en Secrets de Streamlit Cloud.")

st.markdown("---")
st.caption("Powered by yt-dlp · python-telegram-bot · Streamlit")


def is_bot_running() -> bool:
    """Check if bot.py is already running using a PID file."""
    pid_file = "/tmp/mediabot.pid"
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            # Check if that process is still alive
            os.kill(pid, 0)
            return True  # Process exists
        except (OSError, ValueError):
            # Process is dead — remove stale PID file
            os.remove(pid_file)
    return False


def start_bot():
    """Start bot.py as a subprocess and save its PID."""
    pid_file = "/tmp/mediabot.pid"
    proc = subprocess.Popen([sys.executable, "bot.py"])
    with open(pid_file, "w") as f:
        f.write(str(proc.pid))


if not is_bot_running():
    start_bot()
