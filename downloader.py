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

# YouTube: 3 strategies in order
_YT_STRATEGIES = [
    # (client_list, format_str)
    (["web"],              "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"),
    (["tv"],               "best"),
    (["tv_embedded","ios"],"best"),
]

def _ydl_opts(output_dir: str, platform: str, attempt: int = 0) -> dict:
    opts = {
        "outtmpl":             os.path.join(output_dir, "%(id)s.%(ext)s"),
        "quiet":               True,
        "no_warnings":         True,
        "merge_output_format": "mp4",
        "noplaylist":          True,
        "socket_timeout":      30,
        "format":              "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    }
    cookies = _cookies(platform)
    if cookies:
        opts["cookiefile"] = cookies

    if platform in ("youtube_short", "youtube_long"):
        clients, fmt = _YT_STRATEGIES[attempt]
        opts["format"] = fmt
        opts["extractor_args"] = {"youtube": {"player_client": clients}}

    return opts

def download_media(url: str, platform: str = None) -> tuple[str | None, dict | None]:
    if "threads.com" in url:
        url = url.replace("threads.com", "threads.net")

    n_attempts = len(_YT_STRATEGIES) if platform in ("youtube_short","youtube_long") else 2

    for attempt in range(n_attempts):
        tmp_dir = tempfile.mkdtemp()
        try:
            with yt_dlp.YoutubeDL(_ydl_opts(tmp_dir, platform, attempt)) as ydl:
                info = ydl.extract_info(url, download=True)
                for f in os.listdir(tmp_dir):
                    fp = os.path.join(tmp_dir, f)
                    if os.path.isfile(fp):
                        return fp, info
        except Exception as e:
            err = str(e)
            logger.error(f"download attempt {attempt+1} error: {err}")
            if "DRM" in err:
                return None, None   # undownloadable, stop immediately
            if attempt == n_attempts - 1:
                return None, None

    return None, None

def download_reddit_image(url: str) -> tuple[str | None, dict | None]:
    try:
        clean = url.split("?")[0].rstrip("/")
        headers = {"User-Agent": "mediabot/1.0"}
        resp = requests.get(clean + ".json", headers=headers, timeout=15)
        resp.raise_for_status()
        post = resp.json()[0]["data"]["children"][0]["data"]
        title = post.get("title", "Reddit post")
        img_url = post.get("url_overridden_by_dest", "")

        if img_url and any(img_url.lower().endswith(e) for e in [".jpg",".jpeg",".png",".gif",".webp"]):
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
