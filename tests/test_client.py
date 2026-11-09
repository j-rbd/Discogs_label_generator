"""Teste le client Discogs avec des réponses simulées (aucun appel réseau)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import discogs_client as dc

class R:
    def __init__(s, j, code=200): s._j, s.status_code, s.content = j, code, b"img"
    def json(s): return s._j
    def raise_for_status(s): pass

def fake_get(self, url, params=None, stream=False):
    if "collection/folders/0/releases" in url:
        bi = lambda i: {"basic_information": {"id": i, "title": f"T{i}", "year": 1990,
            "artists": [{"name": "Prince (2)"}], "labels": [{"name": "Warp (3)", "catno": "W1"}],
            "styles": ["Techno"], "genres": ["Electronic"], "cover_image": "http://x/y.jpg",
            "formats": [{"name": "Vinyl"}]}}
        return R({"pagination": {"pages": 1, "items": 2}, "releases": [bi(1), bi(2), bi(1)]})
    return R({"country": "UK", "year": 1995})

dc.CACHE_DIR = pathlib.Path(sys.argv[1]); dc.IMG_DIR = dc.CACHE_DIR / "images"
dc.DiscogsClient._get = fake_get
rs = dc.DiscogsClient("tok", "me").fetch_collection()
assert len(rs) == 2, rs                       # doublon supprimé
assert rs[0].artist == "Prince" and rs[0].label == "Warp"
assert rs[0].country == "UK" and rs[0].year == 1995 and rs[0].styles == "Techno"
print("client OK", rs[0])
