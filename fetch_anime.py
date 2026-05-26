import requests
import json
import asyncio
from googletrans import Translator
import time
from urllib.parse import urlparse

# =========================
# CONFIG
# =========================

CDN_PREFIX = "https://cdn.myanimelist.net/images/anime/"

# Traduction des jours
JOUR_FR = {
    "Mondays": "Lu",
    "Tuesdays": "Ma",
    "Wednesdays": "Me",
    "Thursdays": "Je",
    "Fridays": "Ve",
    "Saturdays": "Sa",
    "Sundays": "Di",
    None: "~"
}


# =========================
# COVER
# =========================

def compress_cover(url):
    """
    Convertit :
    https://cdn.myanimelist.net/images/anime/1015/138006.jpg

    en :
    1015/138006.jpg
    """

    if not url:
        return "~"

    try:
        parsed = urlparse(url)

        if "/images/anime/" in parsed.path:
            return parsed.path.split("/images/anime/")[1]

    except Exception:
        pass

    return "~"


def build_cover_url(compressed):
    """
    Reconstruit l'URL complète
    """

    if not compressed or compressed == "~":
        return None

    return CDN_PREFIX + compressed


# =========================
# API
# =========================

def fetch_season_anime(season_type):

    all_anime = []
    page = 1

    while True:

        url = (
            f"https://api.jikan.moe/v4/seasons/"
            f"{season_type}?sfw=true&page={page}"
        )

        try:
            resp = requests.get(url, timeout=20)

        except requests.RequestException as e:
            print(f"Erreur réseau : {e}")
            break

        if resp.status_code != 200:
            print(f"Erreur {resp.status_code} pour {season_type} page {page}")
            break

        data = resp.json()

        all_anime += data.get("data", [])

        has_next = (
            data.get("pagination", {})
            .get("has_next_page", False)
        )

        if not has_next:
            break

        page += 1

        # évite le rate limit
        time.sleep(1)

    return all_anime


# =========================
# DUPLICATES
# =========================

def remove_duplicates(anime_list):

    seen = set()
    unique = []

    for anime in anime_list:

        ident = (
            anime.get("mal_id"),
            anime.get("title")
        )

        if ident not in seen:
            seen.add(ident)
            unique.append(anime)

    return unique


# =========================
# EXTRACTION
# =========================

async def extract_info(anime, translator):

    synopsis = anime.get("synopsis") or ""

    synopsis_fr = ""

    if synopsis:
        try:
            translated = await translator.translate(
                synopsis,
                src="en",
                dest="fr"
            )

            synopsis_fr = translated.text

        except Exception:
            synopsis_fr = ""

    jour_en = (
        anime.get("broadcast", {})
        .get("day")
    )

    jour = JOUR_FR.get(jour_en, "~")

    # =========================
    # COVER
    # =========================

    full_url = (
        anime.get("images", {})
        .get("jpg", {})
        .get("large_image_url")

        or

        anime.get("images", {})
        .get("jpg", {})
        .get("image_url")

        or

        anime.get("images", {})
        .get("webp", {})
        .get("large_image_url")

        or

        anime.get("images", {})
        .get("webp", {})
        .get("image_url")
    )

    compressed_cover = compress_cover(full_url)

    print("FULL :", full_url)
    print("COMP :", compressed_cover)
    print("FINAL:", build_cover_url(compressed_cover))
    print("-" * 60)

    return [
        anime.get("mal_id"),
        anime.get("title"),
        compressed_cover,
        anime.get("score")
        if anime.get("score") is not None
        else "~",
        jour
    ]


# =========================
# PROCESS
# =========================

async def process(season_type, translator):

    print(f"Récupération {season_type} ...")

    raw = fetch_season_anime(season_type)

    unique = remove_duplicates(raw)

    tasks = [
        extract_info(anime, translator)
        for anime in unique
    ]

    return await asyncio.gather(*tasks)


# =========================
# MAIN
# =========================

async def main():

    async with Translator() as translator:

        now, upcoming = await asyncio.gather(
            process("now", translator),
            process("upcoming", translator)
        )

    data = {
        "h": ["i", "t", "c", "s", "d"],
        "n": now,
        "u": upcoming
    }

    with open(
        "seasonal_animes.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            separators=(',', ':')
        )

    print("\nFichier seasonal_animes.json généré")


# =========================
# START
# =========================

if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("\nProgramme arrêté proprement")
