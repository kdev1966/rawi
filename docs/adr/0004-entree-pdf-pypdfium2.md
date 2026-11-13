# ADR 0004 — Lire les albums PDF avec pypdfium2

- **Statut** : accepté
- **Date** : 14 novembre 2026

## Contexte

Le PRD (§3) prévoit des planches en PDF scanné, mais la v0.1 ne lit que des images (`cv2.imread`). Beaucoup de BD, anciennes ou numériques, circulent en PDF. L'entrée PDF permet aussi de constituer le jeu de contrôle (PRD §11) sans conversion à la main.

Contraintes : licence compatible avec un usage commercial, rien de lourd, hors ligne, fonctionnement sur la machine de référence.

## Options

| Option | Licence | Verdict |
|---|---|---|
| **pypdfium2** (PDFium, le moteur PDF de Chrome) | Apache 2.0 / BSD-3 | retenu |
| PyMuPDF | AGPL ou licence commerciale | écarté (AGPL) |
| pdf2image + Poppler | MIT + GPL | écarté (GPL, binaire externe) |
| Exporter à la main (Aperçu) | — | reste un contournement possible |

## Décision

- Ajouter la dépendance **pypdfium2** (conda-forge, version 4.30.1 pour Python 3.11 sur osx-64, environ 3 Mo).
- Nouveau module `rawi/sources.py` : les images passent telles quelles. Chaque page des PDF est dessinée en PNG dans `pages/<nom>-<empreinte>/pNNN.png`, et réutilisée tant que le PDF ne change pas (empreinte sha256).
- **Résolution** : une page couverte par une image (un scan) est dessinée à la résolution native de cette image, ce qui en conserve les pixels. Une page numérique est dessinée à 300 dpi. Le côté le plus long est plafonné à 3000 px. Option `--dpi` pour forcer une valeur.
- On dessine la page plutôt que d'extraire l'image brute : un PDF peut porter du texte vectoriel (le lettrage des bulles) par-dessus l'image, que l'extraction perdrait.
- CLI : `analyser` et `auto` acceptent des PDF, avec `--pages 3-10,12` et `--dossier-pages`.

## Vérifications

- Les 8 planches Qahwati, mises dans un PDF avec leurs octets JPEG d'origine, ressortent **identiques au pixel près**, et l'analyse donne les mêmes cases.
- `rawi auto album.pdf --pages 2-3 --apercu` produit des vidéos identiques image par image à celles faites depuis les JPEG.
- Défaut trouvé et corrigé : pypdfium2 arrondit la taille de l'image au pixel supérieur. Sans correction, l'erreur de calcul transformait 1 499 px en 1 500 et étirait le scan d'une ligne.
- 27 tests (`apps/rawi/tests/test_sources.py`). Ils fabriquent leurs propres PDF ; les tests sur Qahwati ne tournent qu'en local.

## Conséquences

- Le dossier projet gagne un dossier `pages/` (déjà prévu au PRD §6.3).
- Constat annexe : la détection des cases v0.1 est **sensible à la recompression JPEG**. Une planche réencodée en qualité 95 (écart moyen d'environ 1 niveau de gris) peut voir ses cases bouger de plusieurs dizaines de pixels, ou en perdre une. Ce point est ajouté aux risques du PRD.
