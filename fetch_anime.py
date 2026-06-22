import requests
import json
import asyncio
from googletrans import Translator
import time
import os
from datetime import date
from urllib.parse import urlparse
from dotenv import load_dotenv

# =========================
# CONFIG
# =========================
load_dotenv()  # Charger les variables d'environnement depuis le fichier .env
MAL_CLIENT_ID = os.getenv("MAL_CLIENT_ID")

MAL_BASE_URL = "https://api.myanimelist.net/v2/anime/season"

# Champs renvoyés par l'API officielle MAL.
# (l'API officielle ne renvoie que id+title par défaut, donc on précise tout)
MAL_FIELDS = "id,title,main_picture,mean,broadcast,start_date"

CDN_PREFIX = "https://cdn.myanimelist.net/images/anime/"
MAX_EMPTY_FIELDS = 5

# Traduction des jours
JOUR_FR = {
    "monday": "Lu",
    "tuesday": "Ma",
    "wednesday": "Me",
    "thursday": "Je",
    "friday": "Ve",
    "saturday": "Sa",
    "sunday": "Di",
    None: "~"
}

SEASONS_ORDER = ["winter", "spring", "summer", "fall"]


# =========================
# SAISON COURANTE / SUIVANTE
# =========================

def get_current_season():

    today = date.today()
    month = today.month

    if month in (1, 2, 3):
        season = "winter"
    elif month in (4, 5, 6):
        season = "spring"
    elif month in (7, 8, 9):
        season = "summer"
    else:
        season = "fall"

    return today.year, season


def get_next_season(year, season):

    idx = SEASONS_ORDER.index(season)

    if idx == len(SEASONS_ORDER) - 1:
        return year + 1, SEASONS_ORDER[0]

    return year, SEASONS_ORDER[idx + 1]


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
# API (MyAnimeList officielle)
# =========================

def fetch_season_anime(year, season):

    all_anime = []

    url = (
        f"{MAL_BASE_URL}/{year}/{season}"
        f"?limit=100&fields={MAL_FIELDS}"
    )

    headers = {
        "X-MAL-CLIENT-ID": MAL_CLIENT_ID
    }

    while url:

        try:
            resp = requests.get(url, headers=headers, timeout=20)

        except requests.RequestException as e:
            raise RuntimeError(
                f"Erreur réseau pour {season} {year}: {e}"
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Erreur API {resp.status_code} pour {season} {year}: "
                f"{resp.text[:200]}"
            )

        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(
                f"JSON invalide pour {season} {year}"
            )

        all_anime += [
            item.get("node", {})
            for item in data.get("data", [])
        ]

        url = data.get("paging", {}).get("next")

        if url:
            time.sleep(1)

    if not all_anime:
        raise RuntimeError(
            f"Aucun anime récupéré pour {season} {year}"
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
            anime.get("id"),
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

    # L'API officielle renvoie broadcast.day_of_the_week (ex: "monday")
    jour_en = (
        anime.get("broadcast", {})
        .get("day_of_the_week")
    )

    jour = JOUR_FR.get(jour_en, "~")

    # L'API officielle ne fournit que main_picture.large / main_picture.medium
    full_url = (
        anime.get("main_picture", {})
        .get("large")

        or

        anime.get("main_picture", {})
        .get("medium")
    )

    compressed_cover = compress_cover(full_url)

    return [
        anime.get("id"),
        anime.get("title"),
        compressed_cover,
        anime.get("mean")
        if anime.get("mean") is not None
        else "~",
        jour
    ]


# =========================
# PROCESS
# =========================

async def process(label, year, season, translator):

    print(f"Récupération {label} ({season} {year}) ...")

    raw = fetch_season_anime(year, season)

    unique = remove_duplicates(raw)

    if not unique:
        raise RuntimeError(
            f"Aucun anime unique pour {label}"
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
            f"Aucune donnée valide pour {label}"
        )

    return final


# =========================
# MAIN
# =========================

async def main():

    if not MAL_CLIENT_ID or MAL_CLIENT_ID == "TON_CLIENT_ID_ICI":
        raise RuntimeError(
            "MAL_CLIENT_ID manquant. "
            "Définis la variable d'environnement MAL_CLIENT_ID."
        )

    current_year, current_season = get_current_season()
    next_year, next_season = get_next_season(current_year, current_season)

    async with Translator() as translator:

        now, upcoming = await asyncio.gather(
            process("now", current_year, current_season, translator),
            process("upcoming", next_year, next_season, translator)
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
