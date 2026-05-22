import yt_dlp
import os
import re
import tempfile
import logging
import requests

logger = logging.getLogger(__name__)

COOKIES_FILE = os.environ.get("COOKIES_FILE", None)
INSTAGRAM_COOKIES = os.environ.get("INSTAGRAM_COOKIES", None)  # base64 cookies.txt


def _get_cookies_file(platform: str = None) -> str | None:
    """Return path to cookies file if available."""
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        return COOKIES_FILE

    # Instagram-specific cookies from env var (base64 encoded)
    if platform == "instagram" and INSTAGRAM_COOKIES:
        import base64
        path = "/tmp/instagram_cookies.txt"
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(base64.b64decode(INSTAGRAM_COOKIES))
        return path

    return None


def _base_ydl_opts(output_dir: str, platform: str = None) -> dict:
    opts = {
        "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        # Primary: merged HD. Fallbacks avoid ffmpeg requirement.
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "noplaylist": True,
        "socket_timeout": 30,
    }
    cookies = _get_cookies_file(platform)
    if cookies:
        opts["cookiefile"] = cookies
    return opts


def download_media(url: str, platform: str = None) -> tuple[str | None, dict | None]:
    """Download media. Returns (file_path, info_dict) or (None, None)."""
    # Convert threads.com → threads.net for yt-dlp compatibility
    if "threads.com" in url:
        url = url.replace("threads.com", "threads.net")

    tmp_dir = tempfile.mkdtemp()
    ydl_opts = _base_ydl_opts(tmp_dir, platform)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            for f in os.listdir(tmp_dir):
                full_path = os.path.join(tmp_dir, f)
                if os.path.isfile(full_path):
                    return full_path, info
        return None, None
    except Exception as e:
        logger.error(f"download_media error: {e}")
        return None, None


def download_reddit_image(url: str) -> tuple[str | None, dict | None]:
    """Fallback for Reddit images/gifs using the Reddit JSON API."""
    try:
        clean = url.split("?")[0].rstrip("/")
        json_url = clean + ".json"
        headers = {"User-Agent": "mediabot/1.0 (by /u/mediabot_app)"}
        resp = requests.get(json_url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        post = data[0]["data"]["children"][0]["data"]
        title = post.get("title", "Reddit post")
        img_url = post.get("url_overridden_by_dest", "")

        # Download if it's a direct image
        if img_url and any(
            img_url.lower().endswith(ext)
            for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]
        ):
            ext = img_url.split(".")[-1].split("?")[0].lower()
            img_resp = requests.get(img_url, headers=headers, timeout=30)
            img_resp.raise_for_status()
            tmp_path = os.path.join(tempfile.mkdtemp(), f"reddit_img.{ext}")
            with open(tmp_path, "wb") as f:
                f.write(img_resp.content)
            info = {
                "title": title,
                "webpage_url": url,
                "ext": ext,
                "extractor_key": "Reddit",
            }
            return tmp_path, info

        # Try gallery (multiple images — return first)
        if post.get("is_gallery") and post.get("media_metadata"):
            for media_id, media in post["media_metadata"].items():
                if media.get("status") == "valid":
                    img_url = media.get("s", {}).get("u", "").replace("&amp;", "&")
                    if img_url:
                        ext = "jpg"
                        img_resp = requests.get(img_url, headers=headers, timeout=30)
                        tmp_path = os.path.join(tempfile.mkdtemp(), f"reddit_img.{ext}")
                        with open(tmp_path, "wb") as f:
                            f.write(img_resp.content)
                        info = {
                            "title": title,
                            "webpage_url": url,
                            "ext": ext,
                            "extractor_key": "Reddit",
                        }
                        return tmp_path, info

    except Exception as e:
        logger.error(f"download_reddit_image error: {e}")

    return None, None


def clean_hashtags(text: str) -> str:
    if not text:
        return ""
    tags = re.findall(r"#\w+", text)
    return " ".join(tags)


def get_clean_url(info: dict) -> str:
    webpage = info.get("webpage_url", "")
    video_id = info.get("id", "")
    uploader_id = info.get("uploader_id", "")
    platform = info.get("extractor_key", "").lower()

    if "youtube" in platform:
        return f"https://www.youtube.com/watch?v={video_id}"
    elif "instagram" in platform:
        return f"https://www.instagram.com/p/{video_id}/"
    elif "tiktok" in platform:
        return f"https://www.tiktok.com/@{uploader_id}/video/{video_id}"
    elif "twitter" in platform or "x.com" in platform:
        return f"https://x.com/i/status/{video_id}"
    elif "reddit" in platform:
        return webpage
    elif "facebook" in platform:
        return f"https://www.facebook.com/watch/?v={video_id}" if video_id else webpage
    elif "threads" in platform:
        return webpage
    else:
        return webpage
