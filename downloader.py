import yt_dlp
import os
import re
import tempfile
import logging
import requests

logger = logging.getLogger(__name__)

INSTAGRAM_COOKIES = os.environ.get("INSTAGRAM_COOKIES", None)
YOUTUBE_COOKIES   = os.environ.get("YOUTUBE_COOKIES",   None)
REDDIT_COOKIES    = os.environ.get("REDDIT_COOKIES",    None)
REDGIFS_COOKIES   = os.environ.get("REDGIFS_COOKIES",   None)
COOKIES_FILE      = os.environ.get("COOKIES_FILE",      None)

_PATHS = {
    "instagram": "/tmp/ig_cookies.txt",
    "youtube":   "/tmp/yt_cookies.txt",
    "reddit":    "/tmp/rd_cookies.txt",
    "redgifs":   "/tmp/rg_cookies.txt",
}


def _write_cookies(content: str, path: str) -> str | None:
    if not content:
        return None
    if os.path.exists(path):
        os.remove(path)
    lines = ["# Netscape HTTP Cookie File"]
    for line in content.strip().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _cookies(platform: str) -> str | None:
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        return COOKIES_FILE
    mapping = {
        "instagram":     (INSTAGRAM_COOKIES, "instagram"),
        "youtube_short": (YOUTUBE_COOKIES,   "youtube"),
        "youtube_long":  (YOUTUBE_COOKIES,   "youtube"),
        "reddit":        (REDDIT_COOKIES,    "reddit"),
        "redgifs":       (REDGIFS_COOKIES,   "redgifs"),
    }
    if platform in mapping:
        content, key = mapping[platform]
        if content:
            return _write_cookies(content, _PATHS[key])
    return None


def _extract_video_id(url: str) -> str | None:
    for pat in [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"shorts/([a-zA-Z0-9_-]{11})",
        r"embed/([a-zA-Z0-9_-]{11})",
        r"live/([a-zA-Z0-9_-]{11})",
    ]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


# ─── YouTube: descarga con yt-dlp + cookies ───────────────────────────────────

def download_youtube(url: str, platform: str) -> tuple[str | None, dict | None]:
    """
    Descarga YouTube usando yt-dlp con las cookies del usuario.
    Las cookies son la clave: con ellas YouTube no bloquea aunque
    la IP sea de un servidor cloud.

    Probamos varios clientes en orden — cada uno tiene distintas
    restricciones de formato y bot-detection:
      - android_vr   : sin SABIS, acepta descarga directa
      - ios          : cliente móvil, permisivo
      - tv_simply    : cliente TV, sin bot detection
      - tv_downgraded: cliente TV legacy
      - web          : cliente web estándar (requiere cookies sí o sí)
    """
    # Escribir cookies PRIMERO antes de cualquier otra cosa
    cookies = _cookies(platform)
    if not cookies:
        logger.warning("⚠️ No hay YOUTUBE_COOKIES configuradas — YouTube probablemente bloqueará")

    # Formato flexible: acepta cualquier contenedor disponible, no solo mp4
    # Esto evita el error "Requested format is not available"
    FORMAT = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"

    clients_order = [
        "android_vr",
        "ios",
        "tv_simply",
        "tv_downgraded",
        "web",
    ]

    base_opts = {
        "quiet":               True,
        "no_warnings":         True,
        "merge_output_format": "mp4",
        "noplaylist":          True,
        "socket_timeout":      60,
        "nocheckcertificate":  True,
        "format":              FORMAT,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1"
            ),
        },
    }

    if cookies:
        base_opts["cookiefile"] = cookies

    for client in clients_order:
        tmp_dir = tempfile.mkdtemp()
        opts = {
            **base_opts,
            "outtmpl": os.path.join(tmp_dir, "%(id)s.%(ext)s"),
            "extractor_args": {"youtube": {"player_client": [client]}},
        }
        try:
            logger.info(f"→ yt-dlp cliente [{client}]...")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                for f in os.listdir(tmp_dir):
                    fp = os.path.join(tmp_dir, f)
                    if os.path.isfile(fp) and os.path.getsize(fp) > 10_000:
                        logger.info(f"✅ YouTube OK con cliente [{client}]")
                        return fp, info
        except Exception as e:
            err = str(e)
            if "Sign in" in err or "sign in" in err:
                logger.error(
                    f"❌ [{client}] YouTube pide login — las cookies pueden estar "
                    f"vencidas o mal formateadas en YOUTUBE_COOKIES"
                )
            elif "403" in err:
                logger.warning(f"[{client}] 403 Forbidden — IP bloqueada para este cliente")
            elif "Requested format" in err:
                logger.warning(f"[{client}] Formato no disponible, probando siguiente cliente")
            else:
                logger.warning(f"[{client}] Error: {err[:120]}")

            if "DRM" in err:
                return None, None
            continue

    logger.error(f"❌ Todos los clientes fallaron para: {url}")
    return None, None


# ─── Descargador genérico (non-YouTube) ───────────────────────────────────────

def download_media(url: str, platform: str = None) -> tuple[str | None, dict | None]:
    if "threads.com" in url:
        url = url.replace("threads.com", "threads.net")

    if platform in ("youtube_short", "youtube_long"):
        return download_youtube(url, platform)

    tmp_dir = tempfile.mkdtemp()
    opts = {
        "outtmpl":             os.path.join(tmp_dir, "%(id)s.%(ext)s"),
        "quiet":               True,
        "no_warnings":         True,
        "merge_output_format": "mp4",
        "noplaylist":          True,
        "socket_timeout":      30,
        "nocheckcertificate":  True,
        "format":              "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    }
    cookies = _cookies(platform)
    if cookies:
        opts["cookiefile"] = cookies

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            for f in os.listdir(tmp_dir):
                fp = os.path.join(tmp_dir, f)
                if os.path.isfile(fp):
                    return fp, info
    except Exception as e:
        logger.error(f"download_media error: {e}")

    return None, None


# ─── Reddit image fallback ────────────────────────────────────────────────────

def download_reddit_image(url: str) -> tuple[str | None, dict | None]:
    try:
        clean = url.split("?")[0].rstrip("/")
        headers = {"User-Agent": "mediabot/1.0"}
        resp = requests.get(clean + ".json", headers=headers, timeout=15)
        resp.raise_for_status()
        post = resp.json()[0]["data"]["children"][0]["data"]
        title = post.get("title", "Reddit post")
        img_url = post.get("url_overridden_by_dest", "")

        if img_url and any(img_url.lower().endswith(e) for e in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
            ext = img_url.split(".")[-1].split("?")[0].lower()
            r = requests.get(img_url, headers=headers, timeout=30)
            r.raise_for_status()
            tmp = os.path.join(tempfile.mkdtemp(), f"reddit.{ext}")
            with open(tmp, "wb") as f:
                f.write(r.content)
            return tmp, {"title": title, "webpage_url": url, "ext": ext, "extractor_key": "Reddit"}

        if post.get("is_gallery") and post.get("media_metadata"):
            for _, media in post["media_metadata"].items():
                if media.get("status") == "valid":
                    img_url = media.get("s", {}).get("u", "").replace("&amp;", "&")
                    if img_url:
                        r = requests.get(img_url, headers=headers, timeout=30)
                        tmp = os.path.join(tempfile.mkdtemp(), "reddit.jpg")
                        with open(tmp, "wb") as f:
                            f.write(r.content)
                        return tmp, {"title": title, "webpage_url": url, "ext": "jpg", "extractor_key": "Reddit"}
    except Exception as e:
        logger.error(f"download_reddit_image error: {e}")
    return None, None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def clean_hashtags(text: str) -> str:
    if not text:
        return ""
    return " ".join(re.findall(r"#\w+", text))


def get_clean_url(info: dict) -> str:
    webpage     = info.get("webpage_url", "")
    video_id    = info.get("id", "")
    uploader_id = info.get("uploader_id", "")
    platform    = info.get("extractor_key", "").lower()

    if "youtube"   in platform: return f"https://www.youtube.com/watch?v={video_id}"
    if "instagram" in platform: return f"https://www.instagram.com/p/{video_id}/"
    if "tiktok"    in platform: return f"https://www.tiktok.com/@{uploader_id}/video/{video_id}"
    if "twitter"   in platform or "x.com" in platform: return f"https://x.com/i/status/{video_id}"
    if "facebook"  in platform: return f"https://www.facebook.com/watch/?v={video_id}" if video_id else webpage
    return webpage
