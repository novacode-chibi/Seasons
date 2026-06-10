import requests
import json
import asyncio
from googletrans import Translator
import time
import os
from urllib.parse import urlparse

# =========================
# CONFIG
# =========================

CDN_PREFIX = "https://cdn.myanimelist.net/images/anime/"
MAX_EMPTY_FIELDS = 5

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

    if not compressed or compressed == "~":
        return None

    return CDN_PREFIX + compressed


# =========================
# VALIDATION
# =========================

def validate_dataset(data, name):

    if not data:
        print(f"[ERREUR] Dataset {name} vide")
        return False

    empty_id = 0
    empty_title = 0
    empty_cover = 0

    for anime in data:

        if not anime[0]:
            empty_id += 1

        if not anime[1]:
            empty_title += 1

        if anime[2] == "~":
            empty_cover += 1

    print(
        f"{name} -> "
        f"id:{empty_id} "
        f"title:{empty_title} "
        f"cover:{empty_cover}"
    )

    if empty_id > MAX_EMPTY_FIELDS:
        print(f"[ERREUR] Trop d'ID manquants dans {name}")
        return False

    if empty_title > MAX_EMPTY_FIELDS:
        print(f"[ERREUR] Trop de titres manquants dans {name}")
        return False

    if empty_cover > MAX_EMPTY_FIELDS:
        print(f"[ERREUR] Trop de covers manquantes dans {name}")
        return False

    return True


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
            raise RuntimeError(
                f"Erreur réseau pour {season_type}: {e}"
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Erreur API {resp.status_code} pour {season_type}"
            )

        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(
                f"JSON invalide pour {season_type}"
            )

        all_anime += data.get("data", [])

        has_next = (
            data.get("pagination", {})
            .get("has_next_page", False)
        )

        if not has_next:
            break

        page += 1

        time.sleep(1)

    if not all_anime:
        raise RuntimeError(
            f"Aucun anime récupéré pour {season_type}"
        )

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

    if synopsis:
        try:
            await translator.translate(
                synopsis,
                src="en",
                dest="fr"
            )
        except Exception:
            pass

    jour_en = (
        anime.get("broadcast", {})
        .get("day")
    )

    jour = JOUR_FR.get(jour_en, "~")

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

    if not unique:
        raise RuntimeError(
            f"Aucun anime unique pour {season_type}"
        )

    tasks = [
        extract_info(anime, translator)
        for anime in unique
    ]

    results = await asyncio.gather(
        *tasks,
        return_exceptions=True
    )

    final = []

    for result in results:

        if isinstance(result, Exception):
            print("Erreur extraction:", result)
            continue

        final.append(result)

    if not final:
        raise RuntimeError(
            f"Aucune donnée valide pour {season_type}"
        )

    return final


# =========================
# MAIN
# =========================

async def main():

    async with Translator() as translator:

        now, upcoming = await asyncio.gather(
            process("now", translator),
            process("upcoming", translator)
        )

    if not validate_dataset(now, "now"):
        raise RuntimeError(
            "Validation échouée pour now"
        )

    if not validate_dataset(upcoming, "upcoming"):
        raise RuntimeError(
            "Validation échouée pour upcoming"
        )

    data = {
        "h": ["i", "t", "c", "s", "d"],
        "n": now,
        "u": upcoming
    }

    tmp_file = "seasonal_animes.tmp"

    with open(
        tmp_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            separators=(',', ':')
        )

    os.replace(
        tmp_file,
        "seasonal_animes.json"
    )

    print(
        "\nFichier seasonal_animes.json généré avec succès"
    )


# =========================
# START
# =========================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print("\nProgramme arrêté proprement")

    except Exception as e:

        print("\n==============================")
        print("ERREUR CRITIQUE")
        print("==============================")
        print(e)
        print(
            "\nLe fichier seasonal_animes.json "
            "n'a PAS été modifié."
        )
