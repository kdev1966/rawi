# Rawi — redonner vie aux bandes dessinées

Outil **100 % open source** (Apache 2.0) qui transforme des planches de BD (scans ou images) en **motion comic** prêt pour Reels / TikTok / YouTube.
Aucune API payante, aucun abonnement : tout tourne en local, même sur un **MacBook 2015** (sans GPU).

## Ce que fait la v0.1

1. **Analyse** de chaque planche, image ou page de PDF (OpenCV, sans IA lourde) :
   - détection des cases (y compris gouttières en biais et bulles qui débordent) ;
   - ordre de lecture gauche → droite (ou droite → gauche avec `--rtl`) ;
   - détection des bulles et estimation du temps de lecture ;
   - image de **contrôle** pour vérifier le résultat en un coup d'œil.
2. **Rendu vidéo** :
   - plan d'ensemble de la planche, puis caméra qui voyage de case en case (mouvements adoucis) ;
   - léger zoom avant (effet Ken Burns) et « projecteur » qui assombrit les autres cases ;
   - petit rebond des bulles dans l'ordre de lecture ;
   - fond flouté, formats 9:16, 16:9 ou 1:1, musique de fond optionnelle.
3. **Projet modifiable** : tout est enregistré dans `projet.json` (cases, ordre, durées). On corrige à la main, on relance le rendu.

## Installation (macOS 12 Monterey, Mac Intel)

```bash
cd apps/rawi
./installer_mac.sh
```

Le script réutilise le conda déjà installé (Miniforge ou Miniconda), ou installe Miniforge s'il n'y en a pas. Il crée un environnement isolé `rawi` avec Python 3.11, OpenCV, FFmpeg et pypdfium2 (lecture des PDF), en prenant les paquets **uniquement sur conda-forge**. Il ne touche pas au reste du système.

À chaque nouvelle fenêtre du Terminal :

```bash
conda activate rawi
```

*(Linux / Windows : `pip install -e .` + FFmpeg installé.)*

## Utilisation

```bash
# Tout en une commande : analyse + une vidéo par planche
rawi auto pages/*.jpg

# Aperçu rapide (demi-résolution) pour tester le rythme
rawi auto pages/*.jpg --apercu

# En deux temps, avec vérification
rawi analyser pages/*.jpg -o projet.json      # → images dans controle/
#   … ouvrir controle/*.jpg, corriger projet.json si besoin …
rawi rendre projet.json --format 9:16 --musique fond.mp3

# Une seule vidéo pour toutes les planches
rawi rendre projet.json --tout

# BD lue de droite à gauche (manga, certaines BD arabes)
rawi auto pages/*.jpg --rtl

# Album PDF : toutes les pages, ou une sélection
rawi auto album.pdf
rawi auto album.pdf --pages 3-10,12
```

Les vidéos sont dans `videos/` : `episode_01_9x16.mp4`, `episode_02_9x16.mp4`, …

Les pages d'un PDF sont d'abord extraites en PNG dans `pages/` (réutilisées tant que le PDF ne change pas). Un PDF scanné est lu à la résolution d'origine du scan, un PDF numérique à 300 dpi (`--dpi` pour changer).

### Corriger un projet

Dans `projet.json`, chaque case ressemble à :

```json
{ "id": 2, "x": 0, "y": 457, "w": 562, "h": 286, "duration": 5.13, "bubbles": [ … ] }
```

- **`duration`** : durée d'affichage en secondes ;
- **ordre** : l'ordre des cases dans la liste = l'ordre de la caméra (déplacez un bloc pour le changer) ;
- **`x, y, w, h`** : cadre de la case en pixels (à ajuster si une case est mal détectée).

## Performances mesurées

MacBook Pro 2015 (i7-4870HQ, 16 Go, macOS 12.7.6), CPU uniquement, 8 planches Qahwati (épisodes de 25 à 43 s) :

| Mode | Rendu par planche | Total (analyse + rendu) | Pic de RAM |
|---|---|---|---|
| 1080×1920 | 25 à 43 s | 4 min 44 s | < 800 Mo |
| `--apercu` (540×960) | 6 à 13 s | 1 min 21 s | — |

## Feuille de route

Détails et critères d'acceptation : `docs/PRD.md` §8.

| Version | Contenu |
|---|---|
| **0.1** ✅ | Cases, ordre, bulles, caméra, rendu vidéo |
| M0 | Fondations : renommage, embedkit, tests, CI, format de projet v2 |
| 0.2 | Bulles qui apparaissent quand on les lit, lecture du texte arabe et français, sous-titres |
| 0.3 | Calques, parallaxe 2.5D, détourage automatique ou par clics, éditeur web local |
| 0.4 | Mise en scène par un modèle vision-langage local |
| 0.5 | Audio : voix importées, bruitages, musique |
| 0.6 | Restauration des vieux scans |

## Licence

Apache 2.0 : utilisation, modification et usage commercial autorisés.
