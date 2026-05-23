import re
from downloader import clean_hashtags

def escape_md(text: str) -> str:
    """Escapa caracteres que rompen el ParseMode.MARKDOWN clásico de Telegram."""
    if not text:
        return ""
    # Evita que _, *, [, ] rompan el formato
    escape_chars = r"_*[`"
    for c in escape_chars:
        text = text.replace(c, f"\\{c}")
    return text

def format_instagram(info: dict, clean_url: str) -> str:
    caption = info.get("description", "") or ""
    hashtags = clean_hashtags(caption)
    body = caption.replace(hashtags, "").strip()
    msg = f"📸 *Instagram*\n\n🔗 [Ver contenido]({clean_url})\n\n"
    if body:
        msg += f"📝 *Caption:*\n{escape_md(body)}\n\n"
    if hashtags:
        msg += f"*#️⃣ Hashtags:*\n{escape_md(hashtags)}"
    return msg.strip()

def format_tiktok(info: dict, clean_url: str) -> str:
    caption = info.get("description", "") or ""
    hashtags = clean_hashtags(caption)
    body = caption.replace(hashtags, "").strip()
    msg = f"🎵 *TikTok*\n\n🔗 [Ver contenido]({clean_url})\n\n"
    if body:
        msg += f"📝 *Caption:*\n{escape_md(body)}\n\n"
    if hashtags:
        msg += f"*#️⃣ Hashtags:*\n{escape_md(hashtags)}"
    return msg.strip()

def format_facebook(info: dict, clean_url: str) -> str:
    caption = info.get("description", "") or info.get("title", "") or ""
    hashtags = clean_hashtags(caption)
    body = caption.replace(hashtags, "").strip()
    msg = f"📘 *Facebook*\n\n🔗 [Ver contenido]({clean_url})\n\n"
    if body:
        msg += f"📝 *Caption:*\n{escape_md(body)}\n\n"
    if hashtags:
        msg += f"*#️⃣ Hashtags:*\n{escape_md(hashtags)}"
    return msg.strip()

def format_youtube_short(info: dict, clean_url: str) -> str:
    caption = info.get("description", "") or ""
    hashtags = clean_hashtags(caption)
    body = caption.replace(hashtags, "").strip()
    msg = f"▶️ *YouTube Short*\n\n🔗 [Ver contenido]({clean_url})\n\n"
    if body:
        msg += f"📝 *Caption:*\n{escape_md(body)}\n\n"
    if hashtags:
        msg += f"*#️⃣ Hashtags:*\n{escape_md(hashtags)}"
    return msg.strip()

def format_youtube_long(info: dict, clean_url: str) -> str:
    title = info.get("title", "Sin título")
    description = info.get("description", "") or ""
    if len(description) > 800:
        description = description[:800] + "..."
    msg = f"▶️ *YouTube*\n\n📌 *Título:* {escape_md(title)}\n\n🔗 [Ver video]({clean_url})\n\n"
    if description:
        msg += f"📄 *Descripción:*\n{escape_md(description)}"
    return msg.strip()

def format_reddit(info: dict, clean_url: str) -> str:
    title = info.get("title", "Sin título")
    post_url = info.get("webpage_url", clean_url)
    ext = info.get("ext", "")
    is_gallery = info.get("is_gallery", False)
    
    if ext in ("gif", "gifv"):
        tipo = "🎞️ GIF"
    elif is_gallery:
        tipo = "🖼️ Galería"
    elif ext in ("jpg", "jpeg", "png", "webp"):
        tipo = "🖼️ Foto"
    else:
        tipo = "🎬 Video"
        
    msg = f"👽 *Reddit*\n\n{tipo}\n\n📌 *Título:* {escape_md(title)}\n\n🔗 [Ver post]({post_url})"
    return msg.strip()

def format_twitter(info: dict, clean_url: str) -> str:
    caption = info.get("description", "") or info.get("title", "") or ""
    hashtags = clean_hashtags(caption)
    body = caption.replace(hashtags, "").strip()
    msg = f"🐦 *Twitter / X*\n\n🔗 [Ver tweet]({clean_url})\n\n"
    if body:
        msg += f"📝 *Tweet:*\n{escape_md(body)}\n\n"
    if hashtags:
        msg += f"*#️⃣ Hashtags:*\n{escape_md(hashtags)}"
    return msg.strip()

def format_threads(info: dict, clean_url: str) -> str:
    caption = info.get("description", "") or ""
    hashtags = clean_hashtags(caption)
    body = caption.replace(hashtags, "").strip()
    msg = f"🧵 *Threads*\n\n🔗 [Ver post]({clean_url})\n\n"
    if body:
        msg += f"📝 *Caption:*\n{escape_md(body)}\n\n"
    if hashtags:
        msg += f"*#️⃣ Hashtags:*\n{escape_md(hashtags)}"
    return msg.strip()

def format_message(platform: str, info: dict, clean_url: str) -> str:
    formatters = {
        "instagram": format_instagram,
        "tiktok": format_tiktok,
        "facebook": format_facebook,
        "youtube_short": format_youtube_short,
        "youtube_long": format_youtube_long,
        "reddit": format_reddit,
        "twitter": format_twitter,
        "threads": format_threads,
    }
    fn = formatters.get(platform)
    if fn:
        return fn(info, clean_url)
    return f"✅ Contenido descargado\n🔗 {clean_url}"
