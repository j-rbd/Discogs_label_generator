"""Vignettes Discogs : lit une collection et génère un PDF de vignettes autocollantes."""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from discogs_client import DiscogsClient, DiscogsError, Release
from labels_pdf import SHEETS, build_pdf

st.set_page_config(page_title="Vignettes Discogs", page_icon="💿", layout="wide")
st.title("💿 Vignettes pour pochettes Discogs")


def _secret(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, os.environ.get(key.upper(), default))
    except Exception:  # pas de secrets.toml
        return os.environ.get(key.upper(), default)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Compte Discogs")
    username = st.text_input("Nom d'utilisateur", value=_secret("discogs_username"))
    token = st.text_input(
        "Token personnel", value=_secret("discogs_token"), type="password",
        help="Discogs > Settings > Developers > Generate new token. "
             "Peut aussi être mis dans .streamlit/secrets.toml.",
    )
    load = st.button("Lire ma collection", type="primary", use_container_width=True)

    st.header("Planche d'autocollants")
    sheet_name = st.selectbox("Format", list(SHEETS))
    sheet = SHEETS[sheet_name]
    per_page = sheet.cols * sheet.rows
    start = st.number_input("Commencer à l'emplacement n°", 1, per_page, 1,
                            help="Pour réutiliser une planche déjà entamée.")
    border = st.checkbox("Tracer le contour des vignettes", value=False,
                         help="Utile pour un essai sur papier normal avant d'imprimer sur les autocollants.")
    use_img = st.checkbox("Inclure la pochette", value=True)

# --------------------------------------------------------------- collection
if load:
    try:
        client = DiscogsClient(token.strip(), username.strip())
        bar = st.progress(0.0, text="Connexion à Discogs…")

        def on_progress(label: str, n: int, total: int):
            bar.progress(min(1.0, n / max(total, 1)), text=f"{label} : {n}/{total}")

        st.session_state["releases"] = client.fetch_collection(on_progress)
        st.session_state["client"] = client
        bar.empty()
    except DiscogsError as e:
        st.error(str(e))
    except Exception as e:  # réseau, JSON inattendu...
        st.error(f"Erreur : {e}")

releases: list[Release] | None = st.session_state.get("releases")
if not releases:
    st.info("Renseignez votre nom d'utilisateur et votre token Discogs, puis cliquez sur "
            "« Lire ma collection ». Le pays de chaque disque nécessite un appel par release "
            "(~1 s chacun la première fois, ensuite mis en cache).")
    st.stop()

# ----------------------------------------------------------------- sélection
df = pd.DataFrame([r.to_dict() for r in releases])
df.insert(0, "Imprimer", True)

q = st.text_input("Filtrer (titre, artiste, label, style…)", "")
view = df
if q:
    mask = df[["title", "artist", "label", "styles", "country"]].astype(str).apply(
        lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)
    view = df[mask]

st.caption(f"{len(releases)} disques dans la collection — {len(view)} affichés")
c1, c2, _ = st.columns([1, 1, 6])
if c1.button("Tout cocher"):
    st.session_state["sel_version"] = st.session_state.get("sel_version", 0) + 1
    st.session_state["sel_default"] = True
if c2.button("Tout décocher"):
    st.session_state["sel_version"] = st.session_state.get("sel_version", 0) + 1
    st.session_state["sel_default"] = False
view = view.copy()
view["Imprimer"] = st.session_state.get("sel_default", True)

edited = st.data_editor(
    view,
    key=f"editor_{st.session_state.get('sel_version', 0)}_{q}",
    hide_index=True, use_container_width=True, height=450,
    disabled=[c for c in view.columns if c != "Imprimer"],
    column_config={
        "title": "Titre", "artist": "Artiste", "label": "Label", "country": "Pays",
        "year": st.column_config.NumberColumn("Année", format="%d"),
        "styles": "Style", "cat_no": "Réf.", "fmt": "Format",
        "release_id": None, "cover_url": None,
    },
)
chosen_ids = edited.loc[edited["Imprimer"], "release_id"].tolist()
chosen = [r for r in releases if r.release_id in set(chosen_ids)]
pages = -(-(len(chosen) + int(start) - 1) // per_page) if chosen else 0
st.write(f"**{len(chosen)}** vignette(s) sélectionnée(s) → **{pages}** planche(s) A4.")

# ----------------------------------------------------------------------- PDF
if st.button("Générer le PDF", disabled=not chosen, type="primary"):
    client: DiscogsClient | None = st.session_state.get("client")
    bar = st.progress(0.0, text="Téléchargement des pochettes…")
    paths = {}
    if use_img and client:
        for i, r in enumerate(chosen, 1):
            paths[r.release_id] = client.get_image(r.release_id, r.cover_url)
            bar.progress(i / len(chosen), text=f"Pochettes : {i}/{len(chosen)}")
    bar.empty()
    st.session_state["pdf"] = build_pdf(
        chosen, sheet, lambda r: paths.get(r.release_id),
        start_position=int(start), show_border=border,
    )

if st.session_state.get("pdf"):
    st.success("PDF prêt. À l'impression : échelle 100 % (« taille réelle »), pas « ajuster à la page ».")
    st.download_button("⬇️ Télécharger le PDF", st.session_state["pdf"],
                       file_name="vignettes_discogs.pdf", mime="application/pdf")
    try:  # aperçu de la 1re planche
        import pymupdf
        doc = pymupdf.open(stream=st.session_state["pdf"], filetype="pdf")
        st.image(doc[0].get_pixmap(dpi=100).tobytes("png"), caption=f"Aperçu planche 1/{len(doc)}", width=600)
    except Exception:
        pass
