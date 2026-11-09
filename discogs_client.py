"""Client minimal pour l'API Discogs : lecture de la collection + détail des releases.

- La liste de la collection (`basic_information`) donne titre, artiste, label, style,
  année et pochette, mais PAS le pays : il faut un appel `/releases/{id}` par disque.
- Limite Discogs : 60 requêtes/minute (authentifié). Le client attend sur les 429.
- Tout est mis en cache sur disque (JSON + images) : les relances sont quasi instantanées.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

import requests

API = "https://api.discogs.com"
USER_AGENT = "DiscogsLabelPrinter/1.0"
CACHE_DIR = Path(__file__).parent / "cache"
IMG_DIR = CACHE_DIR / "images"

_SUFFIX_NUM = re.compile(r"\s*\(\d+\)\s*$")  # « Artist (2) » -> « Artist »


def clean_name(name: str) -> str:
    """Retire le suffixe d'homonymie Discogs : « Prince (2) » -> « Prince »."""
    return _SUFFIX_NUM.sub("", name or "").strip()


@dataclass
class Release:
    release_id: int
    title: str
    artist: str
    label: str
    country: str
    year: int
    styles: str
    cover_url: str
    cat_no: str = ""
    fmt: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class DiscogsError(RuntimeError):
    pass


class DiscogsClient:
    def __init__(self, token: str, username: str):
        if not token or not username:
            raise DiscogsError("Nom d'utilisateur et token Discogs requis.")
        self.username = username
        self.s = requests.Session()
        self.s.headers.update(
            {"User-Agent": USER_AGENT, "Authorization": f"Discogs token={token}"}
        )

    # ------------------------------------------------------------------ HTTP
    def _get(self, url: str, params: dict | None = None, stream: bool = False):
        for attempt in range(6):
            r = self.s.get(url, params=params, timeout=30, stream=stream)
            if r.status_code == 429:  # rate limit : on patiente puis on réessaie
                time.sleep(min(65, 5 * (attempt + 1)))
                continue
            if r.status_code == 401:
                raise DiscogsError("Token Discogs invalide (401).")
            if r.status_code == 404:
                raise DiscogsError(f"Introuvable (404) : {url}")
            r.raise_for_status()
            return r
        raise DiscogsError("Trop de requêtes (429) : réessayez dans une minute.")

    # ------------------------------------------------------------ collection
    def fetch_collection(
        self, progress: Callable[[str, int, int], None] | None = None
    ) -> list[Release]:
        """Lit toute la collection (dossier 0 = « All ») puis complète le pays."""
        CACHE_DIR.mkdir(exist_ok=True)
        details = self._load_details_cache()

        items: list[dict] = []
        page, pages = 1, 1
        while page <= pages:
            r = self._get(
                f"{API}/users/{self.username}/collection/folders/0/releases",
                params={"per_page": 100, "page": page, "sort": "artist"},
            ).json()
            pages = r["pagination"]["pages"]
            items.extend(r["releases"])
            if progress:
                progress("Lecture de la collection", len(items), r["pagination"]["items"])
            page += 1

        releases: list[Release] = []
        seen: set[int] = set()
        todo = [i for i in items if str(i["basic_information"]["id"]) not in details]
        done = 0
        for it in items:
            bi = it["basic_information"]
            rid = int(bi["id"])
            if rid in seen:  # même release en double dans la collection
                continue
            seen.add(rid)
            d = details.get(str(rid))
            if d is None:
                d = self._fetch_release_detail(rid)
                details[str(rid)] = d
                done += 1
                if done % 10 == 0:
                    self._save_details_cache(details)
                if progress:
                    progress("Détails (pays)", done, len(todo))
            releases.append(self._build(bi, d))
        self._save_details_cache(details)
        return releases

    def _fetch_release_detail(self, rid: int) -> dict:
        r = self._get(f"{API}/releases/{rid}").json()
        return {"country": r.get("country", ""), "year": r.get("year", 0)}

    @staticmethod
    def _build(bi: dict, detail: dict) -> Release:
        labels = bi.get("labels") or [{}]
        styles = bi.get("styles") or bi.get("genres") or []
        fmts = bi.get("formats") or [{}]
        return Release(
            release_id=int(bi["id"]),
            title=(bi.get("title") or "").strip(),
            artist=" / ".join(clean_name(a["name"]) for a in bi.get("artists", [])),
            label=clean_name(labels[0].get("name", "")),
            cat_no=labels[0].get("catno", "") or "",
            country=detail.get("country", "") or "",
            year=int(detail.get("year") or bi.get("year") or 0),
            styles=", ".join(styles),
            cover_url=bi.get("cover_image") or bi.get("thumb") or "",
            fmt=fmts[0].get("name", ""),
        )

    # ---------------------------------------------------------------- images
    def get_image(self, rid: int, url: str) -> Path | None:
        """Télécharge (une seule fois) la pochette et renvoie le chemin local."""
        if not url or "spacer.gif" in url:
            return None
        IMG_DIR.mkdir(parents=True, exist_ok=True)
        path = IMG_DIR / f"{rid}.jpg"
        if path.exists() and path.stat().st_size > 0:
            return path
        try:
            r = self._get(url)
            path.write_bytes(r.content)
            return path
        except Exception:
            return None

    # ----------------------------------------------------------------- cache
    @staticmethod
    def _details_path() -> Path:
        return CACHE_DIR / "release_details.json"

    def _load_details_cache(self) -> dict:
        p = self._details_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_details_cache(self, d: dict) -> None:
        CACHE_DIR.mkdir(exist_ok=True)
        self._details_path().write_text(json.dumps(d), encoding="utf-8")
