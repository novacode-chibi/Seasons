import requests
import json
import asyncio
from googletrans import Translator
import time

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

URL_PREFIX = "https://cdn.myanimelist.net/images/anime/"


def compress_cover(url):
    if not url:
        return "~"

    if url.startswith(URL_PREFIX):
        path = url[len(URL_PREFIX):]
        return path.rsplit(".", 1)[0]  # retire extension

    return "~"


def fetch_season_anime(season_type):
    all_anime = []
    page = 1

    while True:
        url = f"https://api.jikan.moe/v4/seasons/{season_type}?sfw=true&page={page}"
        resp = requests.get(url)

        if resp.status_code != 200:
            print(f"Erreur {resp.status_code} pour {season_type} page {page}")
            break

        data = resp.json()
        all_anime += data.get("data", [])

        if not data.get("pagination", {}).get("has_next_page", False):
            break

        page += 1
        time.sleep(1)

    return all_anime


def remove_duplicates(anime_list):
    seen = set()
    unique = []

    for a in anime_list:
        ident = (a.get("mal_id"), a.get("title"))

        if ident not in seen:
            seen.add(ident)
            unique.append(a)

    return unique


async def extract_info(anime, translator):

    synopsis = anime.get("synopsis") or ""
    if synopsis:
        try:
            res = await translator.translate(synopsis, src="en", dest="fr")
            synopsis_fr = res.text
        except:
            synopsis_fr = ""
    else:
        synopsis_fr = ""

    jour_en = anime.get("broadcast", {}).get("day")
    jour = JOUR_FR.get(jour_en, "~")

    # récupération cover avec fallback
    full_url = (
        anime.get("images", {}).get("jpg", {}).get("large_image_url")
        or anime.get("images", {}).get("jpg", {}).get("image_url")
        or anime.get("images", {}).get("webp", {}).get("large_image_url")
    )

    compressed_url = compress_cover(full_url)

    return [
        anime.get("mal_id"),
        anime.get("title"),
        compressed_url,
        anime.get("score") if anime.get("score") is not None else "~",
        jour
    ]


async def process(season_type, translator):

    print(f"Récupération {season_type} ...")

    raw = fetch_season_anime(season_type)

    uniq = remove_duplicates(raw)

    tasks = [extract_info(a, translator) for a in uniq]

    return await asyncio.gather(*tasks)


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

    with open("seasonal_animes.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    print("Fichier seasonal_animes.json généré")


if __name__ == "__main__":
    asyncio.run(main())
