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


# ─── Obtener metadata de YouTube ─────────────────────────────────────────────

def _get_yt_meta(url: str, cookies: str | None = None) -> dict:
    opts = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "extractor_args": {"youtube": {"player_client": ["ios"]}},
        "http_headers": {
            "User-Agent": "com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iPhone OS 17_5_1 like Mac OS X;)",
        },
    }
    if cookies:
        opts["cookiefile"] = cookies
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False) or {}
    except Exception as e:
        logger.warning(f"_get_yt_meta error: {e}")
    return {}


# ─── Método 1: cobalt.tools ───────────────────────────────────────────────────

def _cobalt_download(url: str) -> tuple[str | None, dict | None]:
    instances = [
        "https://api.cobalt.tools/",
        "https://cobalt.synapstion.com/",
        "https://co.wuk.sh/",
        "https://cobalt.ggtyler.dev/",
    ]
    payload = {"url": url, "videoQuality": "720", "filenameStyle": "basic"}
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    for instance in instances:
        try:
            resp = requests.post(instance, json=payload, headers=headers, timeout=20, verify=False)
            if resp.status_code not in (200, 201):
                logger.info(f"cobalt {instance} → HTTP {resp.status_code}")
                continue
            data = resp.json()
            status = data.get("status", "")
            logger.info(f"cobalt {instance} status: {status}")
            if "error" in status.lower():
                logger.warning(f"cobalt error: {data.get('error', {})}")
                continue
            download_url = None
            if status in ("stream", "redirect", "tunnel"):
                download_url = data.get("url")
            elif status == "picker":
                for item in data.get("picker", []):
                    if item.get("type") == "video":
                        download_url = item.get("url")
                        break
                if not download_url and data.get("picker"):
                    download_url = data["picker"][0].get("url")
            if not download_url:
                logger.warning(f"cobalt {instance}: sin download_url")
                continue
            r = requests.get(download_url, timeout=180, stream=True, verify=False)
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            ext = "mp4"
            if "webm" in ct:
                ext = "webm"
            elif "audio" in ct:
                ext = "m4a"
            tmp = os.path.join(tempfile.mkdtemp(), f"yt_video.{ext}")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    f.write(chunk)
            if os.path.getsize(tmp) < 1000:
                logger.warning(f"cobalt {instance}: archivo demasiado pequeño")
                continue
            info = {
                "id":            _extract_video_id(url) or url.split("/")[-1],
                "title":         data.get("filename", "YouTube video"),
                "description":   "",
                "webpage_url":   url,
                "extractor_key": "Youtube",
            }
            logger.info(f"✅ cobalt OK via {instance}")
            return tmp, info
        except Exception as e:
            logger.warning(f"cobalt {instance}: {type(e).__name__}: {str(e)[:80]}")
            continue

    return None, None


# ─── Método 2: Invidious ──────────────────────────────────────────────────────

def _invidious_download(url: str) -> tuple[str | None, dict | None]:
    vid_id = _extract_video_id(url)
    if not vid_id:
        return None, None

    instances = [
        "https://invidious.flokinet.to",
        "https://yt.artemislena.eu",
        "https://invidious.projectsegfau.lt",
        "https://inv.tux.pizza",
        "https://invidious.privacydev.net",
        "https://iv.melmac.space",
        "https://invidious.fdn.fr",
        "https://invidious.perennialte.ch",
    ]

    for instance in instances:
        try:
            resp = requests.get(f"{instance}/api/v1/videos/{vid_id}", timeout=10, verify=False)
            if resp.status_code != 200:
                continue
            data = resp.json()
            title = data.get("title", "YouTube video")
            description = data.get("description", "")
            best_stream = None
            for fmt in data.get("formatStreams", []):
                if "mp4" in fmt.get("type", ""):
                    best_stream = fmt
                    break
            if not best_stream:
                for fmt in data.get("adaptiveFormats", []):
                    if "video/mp4" in fmt.get("type", "") and not fmt.get("audioTrackId"):
                        best_stream = fmt
                        break
            if not best_stream:
                logger.info(f"invidious {instance}: sin streams MP4")
                continue
            stream_url = best_stream.get("url", "")
            if not stream_url:
                continue
            r = requests.get(stream_url, timeout=180, stream=True, verify=False)
            r.raise_for_status()
            tmp = os.path.join(tempfile.mkdtemp(), f"{vid_id}.mp4")
            size = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    f.write(chunk)
                    size += len(chunk)
            if size < 10_000:
                logger.warning(f"invidious {instance}: archivo demasiado pequeño ({size} bytes)")
                continue
            info = {
                "id":            vid_id,
                "title":         title,
                "description":   description,
                "webpage_url":   f"https://www.youtube.com/watch?v={vid_id}",
                "extractor_key": "Youtube",
            }
            logger.info(f"✅ invidious OK via {instance} ({size/1024:.0f}KB)")
            return tmp, info
        except Exception as e:
            logger.warning(f"invidious {instance}: {type(e).__name__}: {str(e)[:80]}")
            continue

    return None, None


# ─── Método 3: yt-dlp con clientes alternativos ───────────────────────────────

def _ytdlp_download(url: str, cookies: str | None = None) -> tuple[str | None, dict | None]:
    clients_order = [
        ["ios"],
        ["tv_simply"],
        ["tv_downgraded"],
        ["mweb"],
        ["android"],
        ["web_creator"],
    ]
    base_opts = {
        "quiet":               True,
        "no_warnings":         True,
        "merge_output_format": "mp4",
        "noplaylist":          True,
        "socket_timeout":      30,
        "nocheckcertificate":  True,
        "format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]/best",
        "http_headers": {
            "User-Agent": "com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iPhone OS 17_5_1 like Mac OS X;)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    if cookies:
        base_opts["cookiefile"] = cookies

    for clients in clients_order:
        tmp_dir = tempfile.mkdtemp()
        opts = {
            **base_opts,
            "outtmpl": os.path.join(tmp_dir, "%(id)s.%(ext)s"),
            "extractor_args": {"youtube": {"player_client": clients}},
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                for f in os.listdir(tmp_dir):
                    fp = os.path.join(tmp_dir, f)
                    if os.path.isfile(fp) and os.path.getsize(fp) > 10_000:
                        logger.info(f"✅ yt-dlp OK con cliente {clients}")
                        return fp, info
        except Exception as e:
            err = str(e)
            logger.warning(f"yt-dlp {clients}: {err[:100]}")
            if "DRM" in err:
                return None, None
            continue

    return None, None


# ─── Método 4: Piped API ──────────────────────────────────────────────────────

def _piped_download(url: str) -> tuple[str | None, dict | None]:
    vid_id = _extract_video_id(url)
    if not vid_id:
        return None, None

    instances = [
        "https://pipedapi.kavin.rocks",
        "https://pipedapi.adminforge.de",
        "https://piped-api.privacy.com.de",
        "https://api.piped.yt",
    ]

    for instance in instances:
        try:
            resp = requests.get(f"{instance}/streams/{vid_id}", timeout=10, verify=False)
            if resp.status_code != 200:
                continue
            data = resp.json()
            title = data.get("title", "YouTube video")
            description = data.get("description", "")
            best_stream = None
            for s in data.get("videoStreams", []):
                if not s.get("videoOnly", True) and "mp4" in s.get("mimeType", ""):
                    best_stream = s
                    break
            if not best_stream:
                for s in data.get("videoStreams", []):
                    if "mp4" in s.get("mimeType", ""):
                        best_stream = s
                        break
            if not best_stream:
                continue
            stream_url = best_stream.get("url", "")
            if not stream_url:
                continue
            r = requests.get(stream_url, timeout=180, stream=True, verify=False)
            r.raise_for_status()
            tmp = os.path.join(tempfile.mkdtemp(), f"{vid_id}.mp4")
            size = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    f.write(chunk)
                    size += len(chunk)
            if size < 10_000:
                continue
            info = {
                "id":            vid_id,
                "title":         title,
                "description":   description,
                "webpage_url":   f"https://www.youtube.com/watch?v={vid_id}",
                "extractor_key": "Youtube",
            }
            logger.info(f"✅ piped OK via {instance}")
            return tmp, info
        except Exception as e:
            logger.warning(f"piped {instance}: {str(e)[:80]}")
            continue

    return None, None


# ─── Orquestador principal de YouTube ────────────────────────────────────────

def download_youtube(url: str, platform: str) -> tuple[str | None, dict | None]:
    logger.info(f"▶️ YouTube download: {url}")
    cookies = _cookies(platform)
    meta = _get_yt_meta(url, cookies)

    def _enrich(fp: str, info: dict) -> tuple[str, dict]:
        if meta:
            info["title"]       = meta.get("title", info.get("title", ""))
            info["description"] = meta.get("description", info.get("description", ""))
            info["id"]          = meta.get("id", info.get("id", ""))
            info["webpage_url"] = meta.get("webpage_url", info.get("webpage_url", url))
            info["tags"]        = meta.get("tags", [])
        return fp, info

    logger.info("→ [1/4] Probando cobalt.tools...")
    fp, info = _cobalt_download(url)
    if fp:
        return _enrich(fp, info)

    logger.info("→ [2/4] Probando Invidious...")
    fp, info = _invidious_download(url)
    if fp:
        return _enrich(fp, info)

    logger.info("→ [3/4] Probando Piped...")
    fp, info = _piped_download(url)
    if fp:
        return _enrich(fp, info)

    logger.info("→ [4/4] Probando yt-dlp con clientes alternativos...")
    fp, info = _ytdlp_download(url, cookies)
    if fp:
        return _enrich(fp, info)

    logger.error(f"❌ Todos los métodos fallaron para: {url}")
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
