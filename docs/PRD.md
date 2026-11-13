# PRD — bdanim & embedkit

**Projet** : bdanim — redonner vie aux bandes dessinées par l'animation automatique
**Socle partagé** : embedkit — boîte à outils d'IA embarquée réutilisable entre projets *(nom de travail)*
**Porteur** : Kaabaoui Othman — TPLUS INNOVATION
**Version du document** : 1.0 — 13 novembre 2026
**État du code** : bdanim v0.1 fonctionnel (analyse + rendu motion comic, OpenCV/FFmpeg)

---

## 1. Vision

Transformer n'importe quelle planche de BD — scan ancien ou création récente — en **vidéo animée** (motion comic) prête pour Reels, TikTok et YouTube, avec un outil :

- **100 % open source**, sous licence permissive (Apache 2.0) ;
- **100 % local et hors ligne** après le premier téléchargement des modèles ;
- **sans API payante, sans abonnement, sans serveur tiers** (pas d'Ollama, pas de LM Studio, pas de service cloud) ;
- **à IA embarquée** : les moteurs d'inférence sont des bibliothèques chargées dans le processus de l'application, et les modèles de simples fichiers livrés ou téléchargés ;
- **utilisable sur une machine modeste** : la machine de référence est un MacBook 2015 sans GPU.

Le code d'IA embarquée n'est **pas propre à bdanim**. Le porteur mène plusieurs projets à IA embarquée : tout ce qui est générique (gestion des modèles, moteurs d'inférence, détection du matériel, licences) vit dans une bibliothèque séparée, **embedkit**, que bdanim et les autres projets réutilisent.

---

## 2. Objectifs et non-objectifs

### Objectifs

1. **O1 — Automatiser environ 80 % du travail** d'un monteur motion comic : découpage, ordre de lecture, mise en scène, rendu.
2. **O2 — Garder l'humain dans la boucle** : chaque étape produit un résultat vérifiable (images de contrôle) et corrigeable (projet JSON, masques en images), puis le rendu est relancé.
3. **O3 — Tourner sur la machine de référence** (voir §5) pour les niveaux 0 et 1.
4. **O4 — Réutilisabilité** : embedkit est indépendant de bdanim, documenté et testé séparément.
5. **O5 — Conformité des licences** : tout composant livré par défaut autorise l'usage commercial.

### Non-objectifs (pour l'instant)

- Pas d'application mobile, ni de cible embarquée matérielle (Raspberry Pi, smartphone). L'architecture doit toutefois ne pas l'empêcher.
- Pas de génération de BD à partir de rien : on anime des planches existantes.
- Pas de service en ligne, pas de compte utilisateur, pas de télémétrie.
- Pas de vidéo générative dans le parcours par défaut (niveau 2 optionnel uniquement).

---

## 3. Utilisateurs et cas d'usage

| Profil | Besoin |
|---|---|
| **Créateur de contenu** (ex. série « Qahwati ») | Publier un épisode par planche, en 9:16, rapidement, avec sa propre voix |
| **Ayant droit / passionné de BD ancienne** | Numériser de vieux albums et leur donner une seconde vie en vidéo |
| **Éducateur** | Transformer des BD pédagogiques en vidéos courtes |
| **Développeur** (porteur, contributeurs) | Réutiliser embedkit dans d'autres projets à IA embarquée |

**Parcours principal :**

1. L'utilisateur dépose des planches (JPG/PNG/PDF scanné).
2. `bdanim analyser` produit `projet.json` et des images de contrôle.
3. L'utilisateur vérifie et corrige si besoin (JSON aujourd'hui, éditeur web plus tard).
4. `bdanim rendre` produit une vidéo par planche (ou une vidéo globale).
5. Optionnel : il ajoute voix, musique et sous-titres, puis relance le rendu.

---

## 4. Principes de conception

1. **Le classique d'abord, l'IA seulement où elle apporte.** Exemple : l'intérieur d'une bulle est uni, on le remplit en blanc au lieu de lancer un modèle d'inpainting.
2. **Niveaux interchangeables par tâche** :
   - **Niveau 0, classique** : OpenCV/NumPy seuls, tourne partout ;
   - **Niveau 1, léger** (par défaut) : petits modèles ONNX/GGUF quantifiés, sur CPU ;
   - **Niveau 2, lourd** (optionnel) : gros modèles, GPU ou machine distante de l'utilisateur.

   Le niveau est choisi automatiquement selon le matériel, et forçable par option.
3. **Tout est fichier, tout est rejouable.** Chaque étape écrit ses sorties dans le dossier projet (`cache/`, masques PNG, JSON). Une étape ne recalcule que si ses entrées ont changé (hash).
4. **Embarqué, pas client-serveur.** Inférence en processus via des bibliothèques (ONNX Runtime, OpenCV DNN, llama.cpp, whisper.cpp, stable-diffusion.cpp). Aucun démon à lancer.
5. **Licences vérifiées par le code.** Chaque modèle déclare sa licence dans un manifeste. Par défaut, embedkit refuse de charger un modèle non commercial, sauf option explicite.
6. **Messages utilisateur en français**, code et identifiants en anglais.

---

## 5. Contraintes techniques

### Machine de référence (doit fonctionner)

| Élément | Valeur |
|---|---|
| Machine | MacBook Pro 2015, Intel (x86_64, AVX2), sans GPU NVIDIA |
| RAM | 16 Go |
| OS | macOS 12.7.6 Monterey |
| Python | 3.11 via **Miniforge / conda-forge** (Homebrew est mal supporté sur macOS 12) |

### Conséquences

- **PyTorch est exclu à l'exécution** : il n'est plus distribué pour macOS Intel depuis la version 2.3. Tous les modèles de vision sont convertis en **ONNX** (la conversion se fait ailleurs, une fois, et les fichiers sont publiés).
- **ONNX Runtime** : vérifier la disponibilité pour osx-64 (conda-forge ou pip). Repli : **OpenCV DNN**, déjà présent.
- **llama.cpp** via `llama-cpp-python`, compilé à l'installation (Xcode Command Line Tools requis). Fallback : binaire `llama-mtmd-cli` appelé en sous-processus, toujours sans serveur.
- **FFmpeg** : choix automatique de l'encodeur (libx264, sinon `h264_videotoolbox`, sinon OpenH264), déjà implémenté.
- **Budgets** :
  - modèles de niveau 1 hors modèle de langage : **≤ 150 Mo au total** ;
  - modèle vision-langage par défaut : **≤ 2,5 Go** (Q4) ;
  - pic de RAM : **≤ 8 Go**.

### Autres plateformes

Linux x86_64 et Windows doivent fonctionner (CI). Apple Silicon et GPU NVIDIA sont des bonus (accélération automatique si disponible).

---

## 6. Architecture

### 6.1 Organisation du dépôt (monorepo)

```
bdanim-workspace/
├── CLAUDE.md                  # règles de travail pour Claude Code
├── docs/
│   ├── PRD.md                 # ce document
│   └── adr/                   # décisions d'architecture (ADR)
├── packages/
│   └── embedkit/              # socle IA embarquée — RÉUTILISABLE
│       ├── embedkit/
│       │   ├── hardware.py        # détection CPU/RAM/GPU, AVX2, choix du niveau
│       │   ├── registry.py        # lecture des manifestes de modèles
│       │   ├── store.py           # téléchargement HF, cache, sha256, reprise
│       │   ├── licenses.py        # politique de licences (allow/deny)
│       │   ├── runtimes/
│       │   │   ├── onnx.py            # ONNX Runtime (+ repli OpenCV DNN)
│       │   │   ├── opencv_dnn.py
│       │   │   ├── llamacpp.py        # LLM / VLM GGUF (llama-cpp-python)
│       │   │   ├── whispercpp.py      # ASR (v0.4)
│       │   │   └── sdcpp.py           # stable-diffusion.cpp (v0.5, optionnel)
│       │   ├── tasks/             # interfaces haut niveau, indépendantes du modèle
│       │   │   ├── segment.py         # détourage
│       │   │   ├── inpaint.py         # effacement / reconstruction
│       │   │   ├── depth.py           # profondeur
│       │   │   ├── detect.py          # détection d'objets (bulles, texte…)
│       │   │   ├── ocr.py
│       │   │   ├── vlm.py             # image + texte → texte / JSON
│       │   │   └── asr.py
│       │   ├── bench.py           # micro-benchmarks (temps, RAM) par modèle
│       │   └── cli.py             # `embedkit models list|pull|verify|bench`
│       ├── models/                # manifestes YAML (un par modèle)
│       └── tests/
├── apps/
│   └── bdanim/
│       ├── bdanim/
│       │   ├── project.py         # schéma projet, versions, migrations
│       │   ├── analyze/           # cases, ordre, bulles (v0.1 existant)
│       │   ├── restore/           # restauration des scans (v0.3)
│       │   ├── layers/            # calques : texte, personnages, fond, profondeur (v0.2)
│       │   ├── direct/            # mise en scène automatique (v0.3, VLM)
│       │   ├── render/            # moteur de rendu, effets, parallaxe
│       │   ├── audio/             # voix, bruitages, musique, sous-titres (v0.4)
│       │   ├── ui/                # éditeur web local (v0.3)
│       │   └── cli.py
│       └── tests/
│           └── fixtures/qahwati/  # 8 planches de référence
└── tools/
    └── convert/               # scripts de conversion PyTorch → ONNX (hors machine de référence)
```

**Règle de dépendance** : `bdanim` dépend d'`embedkit`, **jamais l'inverse**. embedkit ne connaît pas la BD.

### 6.2 embedkit — spécification

#### Manifeste de modèle (`models/<id>.yaml`)

```yaml
id: migan-512
task: inpaint
tier: 1
runtime: onnx            # onnx | opencv_dnn | llamacpp | whispercpp | sdcpp
source:
  repo: <org>/<repo>     # Hugging Face
  file: migan_pipeline_v2.onnx
  revision: <commit-sha> # épinglé
sha256: <hash>
size_mb: 28
license:
  code: MIT
  weights: <à vérifier>
  commercial: unknown    # true | false | unknown
io:
  input: {image: rgb_uint8, mask: gray_uint8}
  output: {image: rgb_uint8}
  resolution: 512
notes: "Conçu pour mobile."
```

#### API Python (contrat stable)

```python
from embedkit import hardware, tasks

profile = hardware.probe()             # CPU, RAM, AVX2, GPU, niveau recommandé
seg = tasks.Segmenter.load(tier="auto")  # choisit le meilleur modèle autorisé
mask = seg(image, box=(x, y, w, h))    # numpy in → numpy out

vlm = tasks.VLM.load("smolvlm2-2.2b")
data = vlm.ask(image, prompt, schema=MyPydanticModel)  # sortie JSON validée
```

#### Exigences embedkit

- **EK-1** : téléchargement depuis Hugging Face (HTTP simple, pas de dépendance lourde), avec reprise, vérification sha256 et révision épinglée. Cache dans `~/.cache/embedkit` (configurable).
- **EK-2** : mode **hors ligne** strict (`EMBEDKIT_OFFLINE=1`) : aucune requête réseau.
- **EK-3** : politique de licences, par défaut `commercial: true` requis. `--allow-noncommercial` pour lever la restriction, avec avertissement.
- **EK-4** : sélection automatique du niveau selon `hardware.probe()` et les budgets RAM. Repli gracieux (niveau 1 → 0) avec message clair.
- **EK-5** : chaque tâche expose la même interface quel que soit le modèle (images NumPy `HxWx3 uint8` en entrée et en sortie).
- **EK-6** : `embedkit bench` mesure le temps et le pic de RAM de chaque modèle installé sur la machine courante.
- **EK-7** : chargement paresseux et libération explicite (`close()` / gestionnaire de contexte) pour tenir dans 16 Go.
- **EK-8** : sortie structurée des VLM, avec grammaire GBNF ou schéma JSON côté llama.cpp et validation pydantic.
- **EK-9** : aucune dépendance à PyTorch ni à transformers à l'exécution.

### 6.3 bdanim — pipeline

```
planches ─► [1 Restaurer] ─► [2 Analyser] ─► [3 Calques] ─► [4 Mettre en scène] ─► [5 Audio] ─► [6 Rendre] ─► MP4
               v0.3            v0.1 ✅          v0.2              v0.3                 v0.4         v0.1 ✅ → v0.2
```

Chaque étape lit et écrit dans le **dossier projet** :

```
mon_projet/
├── projet.json            # source de vérité, éditable
├── pages/                 # planches originales
├── cache/<hash>/…         # sorties intermédiaires (recalculables)
├── layers/page01/panel03/ # background.png, char_01.png, char_01_mask.png, depth.png…
├── controle/              # images de contrôle
├── audio/
└── videos/
```

---

## 7. État actuel : v0.1 (livré)

**Code** : `bdanim/analyze.py`, `bdanim/render.py`, `bdanim/__main__.py` (~400 lignes), dépendances NumPy, OpenCV et FFmpeg.

| Fonction | Implémentation |
|---|---|
| Détection des cases | Masque blanc (HSV), gouttières = composantes blanches touchant le bord et traversant au moins 40 % de la page ; prolongement des gouttières interrompues (Hough, accepté si ≥ 60 % du trajet passe sous du blanc) ; fusion des fragments (chevauchement > 45 %) |
| Ordre de lecture | Regroupement en rangées (recouvrement vertical > 50 %), puis gauche → droite par défaut, `--rtl` en option |
| Bulles | Zones blanches fermées, solidité > 0,75, 3 à 45 % de pixels sombres |
| Durée par case | `clamp(1.8 + pixels_texte / 2600, 2.2, 7.5)` secondes |
| Rendu | Plan d'ensemble, puis transitions cubiques entre cases, zoom Ken Burns de 5 %, assombrissement des autres cases à 60 %, rebond des bulles, fond flouté ; cadre caméra minimal (50 % largeur, 20 % hauteur) |
| Sortie | 9:16, 16:9, 1:1 ; 30 i/s ; `--apercu` en demi-résolution ; `--musique` |
| CLI | `bdanim analyser`, `bdanim rendre`, `bdanim auto` |

**Résultats sur les 8 planches Qahwati** : épisodes de 25 à 43 s, environ 30 à 50 s de rendu par planche sur une machine Linux. Sur la machine de référence, l'estimation est de 1 à 2 min (**non mesuré** à ce jour).

**Limites connues :**

- planche 5 : deux cases de la 2e rangée fusionnées (gouttière en biais cachée) ;
- planche 6 : dernière case coupée en deux (prolongement de gouttière à travers une bulle) ;
- les bulles restent visibles en permanence (le « pop » n'est qu'un rebond) ;
- masque de bulle approximé par une ellipse (bbox) ;
- aucun test automatisé ;
- le script `installer_mac.sh` n'a pas été testé sur macOS 12.

---

## 8. Feuille de route et critères d'acceptation

### M0 — Fondations (prérequis à tout le reste)

- Restructurer en monorepo (§6.1), en déplaçant la v0.1 dans `apps/bdanim` sans régression.
- Créer `embedkit` : `hardware`, `registry`, `store`, `licenses`, runtime `onnx` (+ repli OpenCV DNN), CLI `models`.
- Mettre en place pytest, ruff, les types (mypy en mode souple) et une CI GitHub Actions (Linux et macOS).
- Introduire un schéma de projet versionné (`"version": 2`) avec migration depuis la v1.
- Écrire des tests « golden » sur les 8 planches : nombre de cases et ordre attendus (fichier `expected.json` écrit à la main).

**Critères d'acceptation :**
- `bdanim auto` produit les mêmes vidéos qu'en v0.1 ;
- `embedkit models list` fonctionne hors ligne ;
- la CI est verte ;
- l'installation est vérifiée sur la machine de référence.

### v0.2 — Calques et parallaxe 2.5D

| Tâche | Niveau 0 | Niveau 1 (par défaut) | Niveau 2 |
|---|---|---|---|
| Masque précis des bulles | contour réel (déjà calculé) | détecteur RT-DETR comic text/bubble quantifié (Apache 2.0) | — |
| Effacer le texte dans les bulles | remplissage blanc | — | — |
| Effacer bulles et texte hors bulles | `cv2.inpaint` (Telea) | MI-GAN ONNX (*licence des poids à confirmer*) | LaMa |
| Détourage des personnages | — | MobileSAM ONNX (prompt = bbox), ou U²-Net-p | BiRefNet |
| Reconstruction du fond derrière les personnages | Telea | MI-GAN | LaMa |
| Profondeur | ordre des calques | Depth Anything V2 Small, ONNX INT8 (Apache 2.0) | — |

Comportements attendus :

- **Bulles réelles** : chaque bulle est un calque PNG (alpha) qui apparaît au bon moment (scale 0,85 → 1,0 avec rebond, ou fondu).
- **Parallaxe** : le fond, les personnages et les bulles se déplacent à des vitesses différentes, avec une option de déformation légère guidée par la profondeur.
- **Corrections manuelles** : si `char_01_mask.png` a été modifié par l'utilisateur (hash différent), il est conservé et réutilisé.
- **Images de contrôle** : vue en calques séparés.

**Critères d'acceptation :**
- sur les 8 planches, ≥ 90 % des bulles sont correctement effacées et réapparaissent ;
- détourage jugé « utilisable » sur ≥ 80 % des cases ;
- analyse de niveau 1 ≤ 5 min par planche sur la machine de référence ;
- rendu ≤ 2 min par planche en 1080×1920 ;
- tous les modèles par défaut ont `commercial: true`.

### v0.3 — Comprendre, restaurer, éditer

- **Restauration des scans** : redressement, correction du jaunissement, débruitage (niveau 0), agrandissement Real-ESRGAN ONNX (niveau 1, BSD).
- **OCR** des bulles (Tesseract ou PaddleOCR ONNX, arabe et français) : texte modifiable, traduction possible, base des sous-titres.
- **Mise en scène par VLM** (llama.cpp, par défaut SmolVLM2 2.2B ou équivalent sous Apache 2.0). Pour chaque case, un JSON validé : `{speaker, emotion, action, camera: {move, target, intensity}, sfx[], pause_after}`.
- **Éditeur web local** (FastAPI + front statique, servi par bdanim lui-même) : visualiser et corriger cases, ordre, calques, durées, timeline, puis prévisualiser.

**Critères d'acceptation :**
- OCR correct sur ≥ 85 % des mots des planches Qahwati ;
- les propositions du VLM sont jugées pertinentes sur ≥ 70 % des cases ;
- l'éditeur permet de corriger une case mal détectée en moins de 30 s.

### v0.4 — Audio

- Import de voix enregistrées (une piste par bulle ou une piste globale découpée).
- Calage automatique des sous-titres avec whisper.cpp.
- Bruitages depuis une bibliothèque CC0 locale, sélectionnés à partir des étiquettes `sfx` du VLM.
- Musique avec ducking automatique sous les voix, mixage FFmpeg.
- Synthèse vocale **optionnelle**, avec uniquement des modèles à licence permissive. La derja tunisienne n'est pas couverte : la voix enregistrée reste la voie recommandée.

### v0.5 — Animation avancée (optionnelle)

- Visages : clignement des yeux et mouvement de bouche synchronisé (modèle ONNX permissif à identifier).
- Plans génératifs ponctuels via stable-diffusion.cpp (famille Wan), réservés au niveau 2 ou à une machine avec GPU.

---

## 9. Exigences non fonctionnelles

| Domaine | Exigence |
|---|---|
| Performance | Voir les critères par jalon. Toute étape > 10 s affiche une barre de progression. |
| Mémoire | Pic ≤ 8 Go sur la machine de référence ; un seul gros modèle chargé à la fois. |
| Reproductibilité | Mêmes entrées et même projet = même vidéo (graines fixées, versions de modèles épinglées). |
| Robustesse | Une planche en échec n'arrête pas le lot ; erreur claire en français et suggestion de correction. |
| Hors ligne | Après `embedkit models pull`, aucune connexion n'est requise. |
| Qualité du code | Python 3.11, annotations de types, ruff, docstrings ; aucune fonction de plus de 60 lignes sans raison. |
| Tests | Unitaires (embedkit), golden (bdanim), smoke test de rendu en `--apercu` en CI. |
| Licences | `embedkit licenses audit` liste code et modèles ; la CI échoue si un modèle par défaut n'est pas commercial. |
| Documentation | README par paquet, ADR pour chaque choix structurant (runtime, modèle par défaut, format projet). |

---

## 10. Risques et parades

| Risque | Impact | Parade |
|---|---|---|
| ONNX Runtime indisponible sur macOS 12 Intel | Bloquant v0.2 | Repli OpenCV DNN ; vérification en M0 ; ADR |
| Opérateurs ONNX non supportés par OpenCV DNN | Modèle inutilisable | Tester chaque modèle dans `embedkit bench` ; modèle alternatif dans le manifeste |
| Compilation de `llama-cpp-python` sur Monterey | Bloquant v0.3 | Repli sur le binaire `llama-mtmd-cli` en sous-processus |
| Licences de poids ambiguës (MI-GAN, isnet-anime…) | Juridique | `commercial: unknown` = refusé par défaut ; demander aux auteurs ; alternatives prêtes |
| Qualité insuffisante des petits modèles sur le dessin | Résultat moyen | Niveau 0 robuste ; corrections manuelles faciles ; niveau 2 optionnel |
| Vieux scans (bruit, jaunissement, trame) | Détection dégradée | Étape de restauration avant analyse ; jeu de test dédié |
| Lenteur sur la machine de référence | Expérience | Cache par hash, `--apercu`, traitement par lot de nuit |

---

## 11. Questions ouvertes

1. Nom définitif des deux projets (bdanim, embedkit) et organisation GitHub (publique dès M0 ?).
2. Jeu de test de vieilles BD : quelles planches, et avec quels droits (domaine public, accord des ayants droit) ?
3. embedkit doit-il viser dès maintenant d'autres langages (bindings) ou rester en Python ?
4. Liste des autres projets à IA embarquée du porteur, pour valider les interfaces de `tasks/` (quelles tâches seront partagées ?).
5. Faut-il une interface graphique de bureau (Tauri, etc.) en plus de l'éditeur web local ?

---

## 12. Glossaire

- **Motion comic** : BD animée par mouvements de caméra, calques et effets, sans réanimer entièrement les dessins.
- **Gouttière** : espace blanc entre deux cases.
- **Parallaxe 2.5D** : calques plats déplacés à des vitesses différentes pour simuler la profondeur.
- **Inpainting** : reconstruction d'une zone effacée d'une image.
- **VLM** : modèle vision-langage (image + texte → texte).
- **GGUF / ONNX** : formats de fichiers de modèles, pour llama.cpp et ONNX Runtime respectivement.
- **Niveau 0/1/2** : classique / léger embarqué / lourd optionnel.
