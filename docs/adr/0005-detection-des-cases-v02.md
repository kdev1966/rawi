# ADR 0005 — Nouvelle détection des cases par défaut (v0.2)

- **Statut** : accepté
- **Date** : 14 novembre 2026
- **Décideur** : porteur du projet (option 1 parmi trois proposées)

## Contexte

La détection v0.1 cherche des gouttières blanches longues (au moins 40 % de la page), presque horizontales ou verticales, puis découpe des rectangles. Elle est juste sur Qahwati, mais échoue sur un scan de magazine de 1979 (Goldorak, *TELEjunior* n° 16) : cases en biais, dessins qui débordent, ombre de reliure. L'objectif O6 du PRD (toute BD) n'était pas tenu.

Mesures faites avec `python -m rawi.evaluate`, sur une vérité écrite à la main et validée par le porteur : 8 pages Qahwati et 9 pages Goldorak. Une case est retrouvée si son cadre recouvre la vraie case à au moins 60 % (IoU).

## Décision

La détection `nouvelle` (`rawi/panels.py`, niveau 0, OpenCV et NumPy seuls) devient la détection par défaut. La v0.1 reste disponible avec `--detection v01`.

Principe : les gouttières sont l'union de deux indices.
1. Les gouttières v0.1.
2. Les gouttières « papier », sous n'importe quel angle :
   - la couleur du papier est le pic d'histogramme clair et peu saturé le plus clair, ce qui marche sur papier blanc, crème ou jauni ;
   - les gouttières sont les zones de cette couleur reliées au bord de la page ;
   - une gouttière n'est prolongée que depuis un vrai cul-de-sac de son squelette, dans sa direction, et seulement à travers du clair (une bulle qui la chevauche).

Les cases sont les composantes du reste après une ouverture morphologique. Les petits fragments creux ou blancs sont écartés. Le travail se fait à 2000 px de côté : à 1000 px, les gouttières fines disparaissent.

## Résultats

| Détection | Qahwati (rappel / précision) | Goldorak (rappel / précision) |
|---|---|---|
| `v01` | 93 % / 91 % | 39 % / 74 % |
| `nouvelle` | 91 % / 85 % | 86 % / 90 % |

Environ 4 à 5 s d'analyse par page sur la machine de référence.

## Conséquences

- Léger recul sur deux planches Qahwati (une case à fond blanc ; une case coupée en trop), accepté contre le gain sur une BD que la méthode ne connaissait pas.
- L'objectif v0.2 de 90 % sur le jeu de contrôle n'est pas encore atteint (86 % sur Goldorak). Restent difficiles : les cases sans cadre qui débordent (« TRANSFER », « FULGUROPOING ») et les cartouches qui traversent une gouttière.
- Les cases restent des rectangles ; les polygones (format de projet 3) ne seront ajoutés que si le rendu l'exige.
- Les tests `test_golden.py` fixent des planchers de rappel et de précision par jeu et par détection ; `test_panels.py` vérifie en CI les cas en biais, la bulle sur la gouttière et le papier jauni sur des pages fabriquées.
- Avec seulement deux BD de contrôle, le risque de surajustement demeure : il faudra d'autres styles (manga, comics, BD sans gouttières).
