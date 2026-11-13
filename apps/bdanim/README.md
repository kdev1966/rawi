# bdanim — redonner vie aux bandes dessinées

Outil **100 % open source** (Apache 2.0) qui transforme des planches de BD (scans ou images) en **motion comic** prêt pour Reels / TikTok / YouTube.
Aucune API payante, aucun abonnement : tout tourne en local, même sur un **MacBook 2015** (sans GPU).

## Ce que fait la v0.1

1. **Analyse** de chaque planche (OpenCV, sans IA lourde) :
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
cd bdanim
./installer_mac.sh
```

Le script installe Miniforge (Python open source), puis OpenCV et FFmpeg dans un environnement isolé `bdanim`. Il ne touche pas au reste du système.

À chaque nouvelle fenêtre du Terminal :

```bash
source ~/miniforge3/bin/activate && conda activate bdanim
```

*(Linux / Windows : `pip install -e .` + FFmpeg installé.)*

## Utilisation

```bash
# Tout en une commande : analyse + une vidéo par planche
bdanim auto pages/*.jpg

# Aperçu rapide (demi-résolution) pour tester le rythme
bdanim auto pages/*.jpg --apercu

# En deux temps, avec vérification
bdanim analyser pages/*.jpg -o projet.json      # → images dans controle/
#   … ouvrir controle/*.jpg, corriger projet.json si besoin …
bdanim rendre projet.json --format 9:16 --musique fond.mp3

# Une seule vidéo pour toutes les planches
bdanim rendre projet.json --tout

# BD lue de droite à gauche (manga, certaines BD arabes)
bdanim auto pages/*.jpg --rtl
```

Les vidéos sont dans `videos/` : `episode_01_9x16.mp4`, `episode_02_9x16.mp4`, …

### Corriger un projet

Dans `projet.json`, chaque case ressemble à :

```json
{ "id": 2, "x": 0, "y": 457, "w": 562, "h": 286, "duration": 5.13, "bubbles": [ … ] }
```

- **`duration`** : durée d'affichage en secondes ;
- **ordre** : l'ordre des cases dans la liste = l'ordre de la caméra (déplacez un bloc pour le changer) ;
- **`x, y, w, h`** : cadre de la case en pixels (à ajuster si une case est mal détectée).

## Performances (MacBook 2015, CPU uniquement)

Rendu en 1080×1920 : environ 1 à 2 minutes par planche. Avec `--apercu`, environ 4 fois plus rapide.

## Feuille de route

| Version | Contenu | Briques open source |
|---|---|---|
| **0.1** ✅ | Cases, ordre, bulles, caméra, rendu vidéo | OpenCV, FFmpeg |
| 0.2 | Calques : effacement du texte, détourage, parallaxe 2.5D | LaMa, SAM 2 / BiRefNet, Depth Anything V2 Small |
| 0.3 | Restauration des vieux scans, OCR, éditeur web de timeline | Real-ESRGAN, Tesseract / PaddleOCR |
| 0.4 | Audio : voix importées, bruitages, sous-titres | FFmpeg, Whisper, sons CC0 |
| 0.5 | Visages animés, plans génératifs (sur GPU externe) | LivePortrait, Wan 2.x |

## Licence

Apache 2.0 : utilisation, modification et usage commercial autorisés.
