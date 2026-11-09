"""Génère un PDF d'essai avec des données factices (sans appel Discogs)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from PIL import Image
from discogs_client import Release, clean_name
from labels_pdf import SHEETS, build_pdf

assert clean_name("Prince (2)") == "Prince"
assert clean_name("Daft Punk") == "Daft Punk"

out = pathlib.Path(sys.argv[1])
out.mkdir(exist_ok=True)
img = out / "cover.jpg"
Image.new("RGB", (300, 300), (200, 60, 40)).save(img)
rs = [
    Release(1, "Strings Of Life", "Rhythim Is Rhythim", "Transmat", "US", 1987, "Detroit Techno, House", "", fmt="12\""),
    Release(2, "Un titre très très long pour tester le retour à la ligne automatique de la vignette", "Artiste Avec Un Nom Interminable / Et Un Autre", "Un Label Au Nom Assez Long Records", "Germany", 1999, "Minimal, Tech House, Deep House, Ambient", ""),
    Release(3, "Été", "Zoë", "Café Müller", "France", 0, "", ""),
] * 6
for key, sheet in SHEETS.items():
    pdf = build_pdf(rs, sheet, lambda r: img, start_position=2, show_border=True)
    (out / f"test_{sheet.name}.pdf").write_bytes(pdf)
    print(sheet.name, len(pdf))
