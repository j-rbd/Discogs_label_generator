# Vignettes Discogs

Lit une collection Discogs et génère un PDF de vignettes autocollantes (titre - artiste, label,
pays + année, style, pochette) à imprimer sur planches A4 et coller sur les pochettes.

## Utilisation
1. Créer un token : discogs.com > Settings > Developers > *Generate new token*.
2. Double-cliquer sur `lancer.bat` (ou `python -m streamlit run app.py`).
3. Saisir pseudo + token (ou les mettre dans `.streamlit/secrets.toml`, modèle : `secrets.toml.example`).
4. « Lire ma collection » → décocher les disques inutiles → choisir le format de planche → « Générer le PDF ».
5. Imprimer en **100 % / taille réelle**. Faire d'abord un essai sur papier normal avec « Tracer le contour ».

## Notes
- Le pays n'est pas dans la liste de collection : 1 appel API par disque (limite 60/min). Premier chargement
  de 500 disques ≈ 10 min ; ensuite tout est en cache (`cache/`).
- Formats de planches dans `labels_pdf.py` (`SHEETS`) : ajouter le vôtre en mesurant la planche.
- Tests : `python tests/test_pdf.py <dossier>` et `python tests/test_client.py <dossier>`.
