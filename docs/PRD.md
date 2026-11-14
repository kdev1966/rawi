# PRD — Rawi & embedkit

**Projet** : Rawi — redonner vie aux bandes dessinées par l'animation automatique (anciennement *bdanim*)
**Socle partagé** : embedkit — boîte à outils d'IA embarquée réutilisable entre projets *(nom de travail)*
**Porteur** : Kaabaoui Othman — TPLUS INNOVATION
**Version du document** : 1.1 — 13 novembre 2026
**État du code** : v0.1 fonctionnelle (analyse + rendu motion comic, OpenCV/FFmpeg), M0 en cours

### Historique

| Version | Changements |
|---|---|
| 1.0 | Première version. |
| 1.1 | Renommage en **Rawi** (code compris, en M0 — ADR 0001). Planches de **tout style et toute langue**, Qahwati n'étant qu'un exemple. Texte **arabe (derja) mêlé de français**. Feuille de route réordonnée : bulles vivantes, OCR et sous-titres passent en v0.2 ; calques et éditeur en v0.3 ; VLM en v0.4 (Qwen3-VL-2B, ADR 0002) ; audio en v0.5 ; restauration en v0.6. Détourage **automatique et manuel**. Texte OCR stocké prêt pour la traduction. LivePortrait et la vidéo générative (Wan) sont retirés de la feuille de route (§13 Pistes futures). |

---

## 1. Vision

Transformer n'importe quelle planche de BD — scan ancien ou création récente, quels que soient son style, sa langue et son sens de lecture — en **vidéo animée** (motion comic) prête pour Reels, TikTok et YouTube, avec un outil :

- **100 % open source**, sous licence permissive (Apache 2.0) ;
- **100 % local et hors ligne** après le premier téléchargement des modèles ;
- **sans API payante, sans abonnement, sans serveur tiers** (pas d'Ollama, pas de LM Studio, pas de service cloud) ;
- **à IA embarquée** : les moteurs d'inférence sont des bibliothèques chargées dans le processus de l'application, et les modèles de simples fichiers livrés ou téléchargés ;
- **utilisable sur une machine modeste** : la machine de référence est un MacBook 2015 sans GPU.

Le code d'IA embarquée n'est **pas propre à Rawi**. Le porteur mène plusieurs projets à IA embarquée : tout ce qui est générique (gestion des modèles, moteurs d'inférence, détection du matériel, licences) vit dans une bibliothèque séparée, **embedkit**, que Rawi et les autres projets réutilisent.

---

## 2. Objectifs et non-objectifs

### Objectifs

1. **O1 — Automatiser environ 80 % du travail** d'un monteur motion comic : découpage, ordre de lecture, lecture du texte, mise en scène, rendu.
2. **O2 — Garder l'humain dans la boucle** : chaque étape produit un résultat vérifiable (images de contrôle) et corrigeable (projet JSON, masques en images, clics dans l'éditeur), puis le rendu est relancé.
3. **O3 — Tourner sur la machine de référence** (voir §5) pour les niveaux 0 et 1.
4. **O4 — Réutilisabilité** : embedkit est indépendant de Rawi, documenté et testé séparément.
5. **O5 — Conformité des licences** : tout composant livré par défaut autorise l'usage commercial.
6. **O6 — Généralité** : la détection ne doit pas être ajustée à une seule série. Les planches Qahwati servent de référence, pas de cible unique ; un second jeu de planches de styles différents sert de contrôle.

### Non-objectifs (pour l'instant)

- Pas d'application mobile, ni de cible embarquée matérielle (Raspberry Pi, smartphone). L'architecture doit toutefois ne pas l'empêcher.
- Pas de génération de BD à partir de rien : on anime des planches existantes.
- Pas de service en ligne, pas de compte utilisateur, pas de télémétrie.
- Pas de vidéo générative ni de réanimation des visages (voir §13).
- Pas de traduction automatique dans la feuille de route actuelle ; le format de données la prépare (voir §6.4).

---

## 3. Utilisateurs et cas d'usage

| Profil | Besoin |
|---|---|
| **Créateur de contenu** (ex. série « Qahwati ») | Publier un épisode par planche, en 9:16, rapidement, avec sous-titres et sa propre voix |
| **Ayant droit / passionné de BD ancienne** | Numériser de vieux albums et leur donner une seconde vie en vidéo |
| **Éducateur** | Transformer des BD pédagogiques en vidéos courtes |
| **Développeur** (porteur, contributeurs) | Réutiliser embedkit dans d'autres projets à IA embarquée |

**Planches visées :** tout style (ligne claire, manga, comics, scans anciens), toute disposition de cases, gouttières blanches ou non, sens de lecture gauche → droite ou droite → gauche. Texte des bulles : en priorité **arabe (dont la derja tunisienne écrite en lettres arabes) mêlé de français** dans une même bulle, puis toute langue en écriture latine.

**Parcours principal :**

1. L'utilisateur dépose des planches (JPG/PNG/PDF scanné).
2. `rawi analyser` produit `projet.json` et des images de contrôle (cases, ordre, bulles, texte lu).
3. L'utilisateur vérifie et corrige si besoin (JSON aujourd'hui, éditeur web local en v0.3).
4. `rawi rendre` produit une vidéo par planche (ou une vidéo globale), avec sous-titres incrustés et/ou fichier `.srt`.
5. Optionnel : il ajoute voix, musique et bruitages, puis relance le rendu.

---

## 4. Principes de conception

1. **Le classique d'abord, l'IA seulement où elle apporte.** Exemple : l'intérieur d'une bulle est uni, on le remplit en blanc au lieu de lancer un modèle d'inpainting.
2. **Niveaux interchangeables par tâche** :
   - **Niveau 0, classique** : OpenCV/NumPy seuls, tourne partout ;
   - **Niveau 1, léger** (par défaut) : petits modèles ONNX/GGUF quantifiés, sur CPU ;
   - **Niveau 2, lourd** (optionnel) : gros modèles, GPU ou machine distante de l'utilisateur.

   Le niveau est choisi automatiquement selon le matériel, et forçable par option. **Chaque tâche IA a un repli de niveau 0**, éventuellement manuel (saisie, clics).
3. **Automatique et manuel côte à côte.** Pour les tâches où l'IA se trompe souvent (détourage, texte), l'utilisateur peut corriger ou faire à la main, case par case. Une correction manuelle n'est jamais écrasée par un recalcul.
4. **Tout est fichier, tout est rejouable.** Chaque étape écrit ses sorties dans le dossier projet (`cache/`, masques PNG, JSON). Une étape ne recalcule que si ses entrées ont changé (hash).
5. **Embarqué, pas client-serveur.** Inférence en processus via des bibliothèques (ONNX Runtime, OpenCV DNN, llama.cpp, whisper.cpp). Aucun démon à lancer.
6. **Licences vérifiées par le code.** Chaque modèle déclare sa licence dans un manifeste. Par défaut, embedkit refuse de charger un modèle non commercial, sauf option explicite.
7. **Messages utilisateur en français**, code et identifiants en anglais.

---

## 5. Contraintes techniques

### Machine de référence (doit fonctionner)

C'est aussi la machine de travail du porteur : tout ce qui est annoncé comme fonctionnel y est mesuré.

| Élément | Valeur |
|---|---|
| Machine | MacBook Pro 2015, Intel Core i7-4870HQ (x86_64, AVX2), sans GPU utile à l'inférence |
| RAM | 16 Go |
| OS | macOS 12.7.6 Monterey |
| Python | 3.11 via **conda, canal conda-forge uniquement** (Miniforge, ou le Miniconda déjà installé ; jamais le canal `defaults` d'Anaconda). Environnement `rawi`. Voir ADR 0003 |

### Conséquences

- **PyTorch est exclu à l'exécution** : il n'est plus distribué pour macOS Intel depuis la version 2.3. Tous les modèles de vision sont convertis en **ONNX** (la conversion se fait ailleurs, une fois, et les fichiers sont publiés).
- **ONNX Runtime** : disponibilité sur osx-64 à vérifier **en premier** en M0 (conda-forge ou pip). Repli : **OpenCV DNN**, déjà présent.
- **llama.cpp** via `llama-cpp-python`, compilé à l'installation (Xcode Command Line Tools requis). Repli : binaire `llama-mtmd-cli` appelé en sous-processus, toujours sans serveur.
- **FFmpeg** : choix automatique de l'encodeur (libx264, sinon `h264_videotoolbox`, sinon OpenH264), déjà implémenté. Les sous-titres incrustés passent par libass (mise en forme de l'arabe), à vérifier dans le FFmpeg de conda-forge.
- **Budgets** :
  - modèles de niveau 1 hors modèle de langage : **≤ 150 Mo au total** ;
  - modèle vision-langage par défaut : **≤ 2,5 Go** (Q4, projecteur compris) ;
  - pic de RAM : **≤ 8 Go** ;
  - analyse IA : **quelques minutes par planche** (≤ 5 min), faite une fois puis mise en cache ;
  - rendu : **≤ 2 min par planche** en 1080×1920.

### Autres plateformes

Linux x86_64 et Windows doivent fonctionner (CI). Apple Silicon et GPU NVIDIA sont des bonus (accélération automatique si disponible).

---

## 6. Architecture

### 6.1 Organisation du dépôt (monorepo)

```
rawi/
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
│       │   │   ├── llamacpp.py        # LLM / VLM GGUF (llama-cpp-python) — v0.4
│       │   │   └── whispercpp.py      # ASR — v0.5
│       │   ├── tasks/             # interfaces haut niveau, indépendantes du modèle
│       │   │   ├── detect.py          # détection d'objets (bulles, texte…) — v0.2
│       │   │   ├── ocr.py             # v0.2
│       │   │   ├── inpaint.py         # effacement / reconstruction — v0.2
│       │   │   ├── segment.py         # détourage — v0.3
│       │   │   ├── depth.py           # profondeur — v0.3
│       │   │   ├── vlm.py             # image + texte → texte / JSON — v0.4
│       │   │   └── asr.py             # v0.5
│       │   ├── bench.py           # micro-benchmarks (temps, RAM) par modèle
│       │   ├── cli.py             # `embedkit hardware`, `models list|pull|verify|bench`, `licenses audit`
│       │   └── models/            # manifestes YAML livrés (un par modèle), installés avec le paquet
│       └── tests/
├── apps/
│   └── rawi/
│       ├── rawi/
│       │   ├── project.py         # schéma projet, versions, migrations
│       │   ├── analyze/           # cases, ordre, bulles (v0.1 existant)
│       │   ├── text/              # OCR, sens de lecture, sous-titres (v0.2)
│       │   ├── layers/            # calques : bulles (v0.2), personnages, fond, profondeur (v0.3)
│       │   ├── render/            # moteur de rendu, effets, parallaxe
│       │   ├── ui/                # éditeur web local (v0.3)
│       │   ├── direct/            # mise en scène automatique (v0.4, VLM)
│       │   ├── audio/             # voix, bruitages, musique (v0.5)
│       │   ├── restore/           # restauration des scans (v0.6)
│       │   └── cli.py
│       └── tests/
│           └── fixtures/
│               ├── qahwati/       # 8 planches de référence
│               └── controle/      # planches d'autres styles (voir §11)
└── tools/
    └── convert/               # scripts de conversion PyTorch → ONNX (hors machine de référence)
```

**Règle de dépendance** : `rawi` dépend d'`embedkit`, **jamais l'inverse**. embedkit ne connaît pas la BD.

### 6.2 embedkit — spécification

#### Manifeste de modèle (`embedkit/models/<id>.yaml`)

```yaml
id: migan-512
task: inpaint
tier: 1
runtime: onnx            # onnx | opencv_dnn | llamacpp | whispercpp
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

profile = hardware.probe()               # CPU, RAM, AVX2, GPU, niveau recommandé
seg = tasks.Segmenter.load(tier="auto")  # choisit le meilleur modèle autorisé
mask = seg(image, box=(x, y, w, h))      # numpy in → numpy out
mask = seg(image, points=[(x, y, 1), (x2, y2, 0)])  # clics positifs / négatifs

ocr = tasks.OCR.load(tier="auto", scripts=["arabic", "latin"])
lines = ocr(image)                       # [{text, script, box, confidence}]

vlm = tasks.VLM.load("qwen3-vl-2b")
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
- **EK-10** : la tâche `segment` accepte une boîte **ou** des clics (positifs/négatifs), pour le détourage manuel assisté.

### 6.3 Rawi — pipeline

```
planches ─► [Restaurer] ─► [Analyser] ─► [Texte] ─► [Calques] ─► [Mettre en scène] ─► [Audio] ─► [Rendre] ─► MP4 + .srt
               v0.6         v0.1 ✅       v0.2       v0.2/v0.3        v0.4             v0.5      v0.1 ✅ → v0.3
```

Chaque étape lit et écrit dans le **dossier projet** :

```
mon_projet/
├── projet.json            # source de vérité, éditable
├── pages/                 # planches originales
├── cache/<hash>/…         # sorties intermédiaires (recalculables)
├── layers/page01/panel03/ # background.png, bubble_01.png, char_01.png, char_01_mask.png, depth.png…
├── controle/              # images de contrôle
├── audio/
├── sous-titres/           # .srt (et .ass pour l'incrustation)
└── videos/
```

### 6.4 Texte des bulles dans `projet.json`

Le texte lu est stocké **par bulle**, avec sa langue et son sens d'écriture, et un emplacement réservé aux traductions. Les sous-titres et la future traduction lisent cette même structure.

```json
{
  "id": "p01-c03-b02",
  "polygon": [[412, 88], [530, 90], "…"],
  "order": 2,
  "source": "ocr",
  "text": "صباح الخير، ça va ?",
  "segments": [
    {"text": "صباح الخير،", "script": "arabic", "direction": "rtl"},
    {"text": "ça va ?", "script": "latin", "direction": "ltr"}
  ],
  "lang": ["ar-TN", "fr"],
  "confidence": 0.81,
  "translations": {}
}
```

- `source` vaut `ocr` ou `manual`. Un texte `manual` n'est jamais écrasé par un nouvel OCR.
- `translations` est une table `langue → texte`, vide tant que la traduction n'existe pas.

---

## 7. État actuel : v0.1 (livré)

**Code** : `rawi/analyze.py`, `rawi/render.py`, `rawi/__main__.py` (~400 lignes), dépendances NumPy, OpenCV et FFmpeg. Renommé de `bdanim` en `rawi` en M0, sans changement de résultat (vidéos identiques image par image).

| Fonction | Implémentation |
|---|---|
| Détection des cases | Masque blanc (HSV), gouttières = composantes blanches touchant le bord et traversant au moins 40 % de la page ; prolongement des gouttières interrompues (Hough, accepté si ≥ 60 % du trajet passe sous du blanc) ; fusion des fragments (chevauchement > 45 %) |
| Ordre de lecture | Regroupement en rangées (recouvrement vertical > 50 %), puis gauche → droite par défaut, `--rtl` en option |
| Bulles | Zones blanches fermées, solidité > 0,75, 3 à 45 % de pixels sombres |
| Durée par case | `clamp(1.8 + pixels_texte / 2600, 2.2, 7.5)` secondes |
| Rendu | Plan d'ensemble, puis transitions cubiques entre cases, zoom Ken Burns de 5 %, assombrissement des autres cases à 60 %, rebond des bulles, fond flouté ; cadre caméra minimal (50 % largeur, 20 % hauteur) |
| Sortie | 9:16, 16:9, 1:1 ; 30 i/s ; `--apercu` en demi-résolution ; `--musique` |
| CLI | `rawi analyser`, `rawi rendre`, `rawi auto` |

**Résultats sur les 8 planches Qahwati** : épisodes de 25 à 43 s. Mesuré sur la machine de référence : **25 à 43 s de rendu par planche** en 1080×1920 (4 min 44 s pour les 8, analyse comprise, pic de RAM < 800 Mo) ; 6 à 13 s par planche en `--apercu`.

**Limites connues :**

- planche 5 : deux cases de la 2e rangée fusionnées (gouttière en biais cachée) ;
- planche 6 : dernière case coupée en deux (prolongement de gouttière à travers une bulle) ;
- planche 7 : dernière rangée (deux cases séparées en biais) découpée en trois, dont une tranche de 130 px ;
- les bulles restent visibles en permanence (le « pop » n'est qu'un rebond) ;
- masque de bulle approximé par une ellipse (bbox) ;
- détection des cases dépendante de gouttières blanches ; non testée hors Qahwati ;
- tests automatisés ajoutés en M0 (85 tests, dont les tests golden Qahwati : planches 5, 6 et 7 en échec connu) ;
- le script `installer_mac.sh` n'a pas été testé sur macOS 12.

---

## 8. Feuille de route et critères d'acceptation

| Jalon | Contenu | Valeur pour l'utilisateur |
|---|---|---|
| **M0** | Fondations, renommage, tests | Base saine et mesurée |
| **v0.2** | Détection universelle des cases, bulles vivantes, OCR ar/fr, sous-titres | Toute BD, vidéo publiable sous-titrée |
| **v0.3** | Calques, parallaxe, détourage auto + manuel, éditeur | Vrai effet motion comic, corrections faciles |
| **v0.4** | Mise en scène par VLM | Caméra et rythme pensés case par case |
| **v0.5** | Audio | Épisode complet avec voix et ambiance |
| **v0.6** | Restauration des scans | Vieilles BD exploitables |
| *Option* | Format webtoon (défilement vertical) | Non planifié ; à placer selon la demande |

### M0 — Fondations (prérequis à tout le reste)

1. **Vérifier ONNX Runtime sur la machine de référence** (installation conda-forge/pip, chargement d'un petit modèle ONNX, comparaison avec OpenCV DNN). Conclusion consignée dans un ADR. ✅ (ADR 0003)
2. **Renommer `bdanim` en `rawi`** : paquet, module Python, commande CLI, README et `CLAUDE.md` (ADR 0001). ✅
3. Restructurer en monorepo (§6.1), en déplaçant la v0.1 dans `apps/rawi` sans régression. ✅
4. Créer `embedkit` : `hardware`, `registry`, `store`, `licenses`, runtime `onnx` (+ repli OpenCV DNN), CLI `models`. ✅ (+ `bench`, tâche `depth`, premier modèle Depth Anything V2 Small)
5. Mettre en place pytest, ruff, les types (mypy en mode souple) et une CI GitHub Actions (Linux et macOS). ✅ (CI macOS sur Apple Silicon : GitHub n'a plus de Mac Intel)
6. Introduire un schéma de projet versionné (`"version": 2`, avec la structure de texte §6.4) et une migration depuis la v1. ✅
7. Écrire des tests « golden » sur les 8 planches Qahwati : nombre de cases et ordre attendus (fichier `expected.json` écrit à la main). ✅ (5 planches justes ; 5, 6 et 7 en échec connu, voir §7)
8. **Entrée PDF** : `rawi analyser|auto album.pdf --pages 3-10`, pages extraites à la résolution du scan (pypdfium2, ADR 0004). ✅

**Critères d'acceptation :**
- `rawi auto` produit les mêmes vidéos que `bdanim auto` en v0.1 ;
- `embedkit models list` fonctionne hors ligne ;
- la CI est verte (tests golden Qahwati verts en local, la CI ne disposant pas de ces planches) ;
- l'installation et le temps de rendu v0.1 sont mesurés sur la machine de référence.

### v0.2 — Détection universelle, bulles vivantes, OCR arabe/français, sous-titres

**Priorité : une détection des cases qui marche sur toutes les BD** (objectif O6). Constat du 14 novembre 2026 sur un scan de magazine de 1979 (Goldorak, *TELEjunior* n° 16, 9 pages) : la lecture du PDF est parfaite, mais la détection v0.1 échoue sur la plupart des pages :

- **cases en biais** et compositions éclatées (pages 7 et 8 vues comme une seule case alors qu'elles en ont 8 à 10) : la v0.1 ne cherche que des gouttières qui traversent la page de bord à bord ;
- **dessins qui débordent** dans les gouttières ou sortent du cadre (cadres qui chevauchent plusieurs cases) ;
- **défauts de scan** : ombre de reliure, marges irrégulières ;
- bulles manquées en nombre ;
- s'y ajoute la sensibilité à la recompression JPEG (ADR 0004).

**Avancement (14 novembre 2026, ADR 0005)** : vérité Goldorak écrite et validée ; outil de mesure `python -m rawi.evaluate` ; nouvelle détection par défaut (`rawi/panels.py`) : Goldorak de 39 % à **86 %** de cases retrouvées (précision 74 % → 90 %), Qahwati 93 % → 91 %. L'ancienne reste disponible (`--detection v01`). Reste à faire pour atteindre 90 % : cases sans cadre qui débordent, cartouches qui traversent une gouttière.

**Bulles vivantes (14 novembre 2026)** : format de projet 3 (contour réel de chaque bulle) ; les bulles sont montrées **vides** (leur texte repeint avec la couleur de fond de la bulle, niveau 0, principe n° 1) et le texte de chacune apparaît à sa lecture, en fondu, puis reste visible. Effacer la bulle entière et reconstituer le dessin dessous (cv2.inpaint, puis flou) a été essayé puis écarté par le porteur : les taches floues donnaient une image abîmée. Détection des bulles refaite sur toute la page (`rawi/bubbles.py`) : sur Qahwati, 89 % des bulles trouvées et 91 % de détections justes (avant : 85 % / 68 %), mesuré contre une vérité de 51 bulles (`qahwati_bubbles_expected.json`, validée par le porteur). Sur Goldorak, environ la moitié des bulles seulement (estimation visuelle : bulles ouvertes, collées au bord des cases) ; à mesurer.

**Lecture du texte (14 novembre 2026, ADR 0006)** : PaddleOCR arabe v5 en ONNX, lignes trouvées sans modèle ; texte, segments arabe/latin, langues et confiance enregistrés par bulle. Sur la chaîne complète Qahwati : 21 % d'erreurs par caractère, 67 % des mots retrouvés (transcription de référence de 46 bulles validée par le porteur ; les bulles non détectées comptent comme fausses). Langues réelles de Qahwati : arabe, français **et anglais**.

Pistes à évaluer, du classique au modèle : cadres de cases détectés comme polygones (contours, segments de droite) plutôt que gouttières horizontales ou verticales ; cases non rectangulaires ; détecteur de cases léger en niveau 1 ; correction manuelle facile en repli. Le format de projet doit accepter des cases polygonales.


| Tâche | Niveau 0 | Niveau 1 (par défaut) |
|---|---|---|
| Masque précis des bulles | contour réel (déjà calculé) | détecteur de bulles/texte pour BD (RT-DETR quantifié ; licence à vérifier) |
| Effacer les bulles du fond | `cv2.inpaint` (Telea) ; remplissage blanc à l'intérieur | MI-GAN ONNX (*licence des poids à confirmer*) |
| Lecture du texte (OCR) | saisie manuelle dans le projet | PaddleOCR ONNX (Apache 2.0), modèles arabe et latin, choix par ligne ; alternative Tesseract `ara+fra` (Apache 2.0) — à départager par bench |
| Sens de lecture | `--rtl` | ~~déduit de l'écriture dominante~~ : abandonné, Qahwati est en arabe mais se lit de gauche à droite (ADR 0006) |

Comportements attendus :

- **Bulles vivantes** : chaque bulle est un calque PNG (alpha) découpé selon son contour réel ; elle **apparaît au bon moment**, dans l'ordre de lecture de la case (scale 0,85 → 1,0 avec rebond, ou fondu), le fond étant reconstitué dessous.
- **Durée par bulle** calculée à partir de la longueur du texte lu (repli : pixels de texte, comme en v0.1). ✅ `rawi/pacing.py` : 14 caractères par seconde, 1,2 s minimum ; chaque bulle attend que la précédente soit lue ; durée de la case = somme, entre 2,2 et 12 s.
- **Texte mixte** : une même bulle peut contenir de l'arabe et du français ; chaque segment garde son sens d'écriture (§6.4).
- **Sous-titres** : fichier `.srt` exporté et/ou sous-titres incrustés (arabe correctement mis en forme et lié), synchronisés sur l'apparition des bulles. Option `--sous-titres {aucun,srt,incrustes,les-deux}`. ✅ `srt` par défaut (le texte lu n'est juste qu'aux deux tiers : rien n'est gravé dans l'image sans le demander) ; calage sur les images rendues (même déroulé que le rendu) ; nom de celui qui parle retiré (« Nom: », ou nom seul en tête de plusieurs bulles quand l'OCR a perdu le deux-points), `--garder-noms` pour le garder ; incrustation libass vérifiée sur la machine de référence.
- **Corrections** : texte et ordre des bulles modifiables dans `projet.json` ; une correction manuelle est conservée.
- **Images de contrôle** : bulles détectées numérotées, texte lu en regard.

**Critères d'acceptation :**
- détection des cases correcte sur ≥ 90 % des cases du jeu de contrôle (dont les 9 pages Goldorak), sans régression sur Qahwati ;
- sur les 8 planches Qahwati, ≥ 90 % des bulles sont correctement détourées, effacées et réapparaissent ;
- OCR correct sur ≥ 85 % des mots des planches Qahwati (arabe et français), mesuré contre une transcription écrite à la main ;
- le jeu de contrôle (§11) ne présente pas de régression grossière (bulles manquées en masse, ordre inversé) ;
- analyse de niveau 1 ≤ 5 min par planche et rendu ≤ 2 min par planche, mesurés sur la machine de référence ;
- tous les modèles par défaut ont `commercial: true`.

### v0.3 — Calques, parallaxe 2.5D, éditeur

**Avancement (14 novembre 2026)** — ordre validé par le porteur : 1) parallaxe par la profondeur, 2) reconstitution du décor (MI-GAN), 3) détourage (MobileSAM, clics), 4) éditeur local (serveur Python intégré, sans dépendance). Étape 1 faite : carte de profondeur par case (Depth Anything V2 Small, mise en cache par empreinte dans `calques/`), format de projet 4 ; pendant le plan, chaque pixel glisse selon sa profondeur (déformation douce, 6 % de la largeur au plus, aller-retour sans à-coup), bulles immobiles. `--profondeur non` pour s'en passer.

| Tâche | Niveau 0 | Niveau 1 (par défaut) | Niveau 2 |
|---|---|---|---|
| Détourage des personnages | tracé manuel (polygone) | MobileSAM ONNX, prompt = boîte ou clics ; repli U²-Net-p | BiRefNet |
| Reconstruction du fond derrière les personnages | Telea | MI-GAN | LaMa |
| Profondeur | ordre des calques | Depth Anything V2 Small, ONNX INT8 (Apache 2.0) | — |

- **Détourage au choix, case par case** : automatique (boîte détectée), assisté (clics positifs/négatifs) ou entièrement manuel.
- **Parallaxe** : le fond, les personnages et les bulles se déplacent à des vitesses différentes, avec une option de déformation légère guidée par la profondeur.
- **Corrections manuelles** : si `char_01_mask.png` a été modifié par l'utilisateur (hash différent), il est conservé et réutilisé.
- **Éditeur web local** (FastAPI + front statique, servi par Rawi lui-même, sans service externe) : visualiser et corriger cases, ordre, bulles, texte, masques (clics), durées et timeline, puis prévisualiser.
- **Images de contrôle** : vue en calques séparés.

**Critères d'acceptation :**
- détourage automatique jugé « utilisable » sur ≥ 80 % des cases Qahwati ; les autres se corrigent par clics en moins d'une minute par personnage ;
- l'éditeur permet de corriger une case mal détectée en moins de 30 s ;
- temps d'analyse et de rendu toujours dans les budgets du §5.

### v0.4 — Mise en scène par VLM

- **VLM par défaut : Qwen3-VL-2B** en GGUF Q4 via llama.cpp (ADR 0002 ; licence à confirmer dans le manifeste). Repli : règles de niveau 0 de la v0.1 (durées, zoom, transitions).
- Pour chaque case, un JSON validé : `{speaker, emotion, action, camera: {move, target, intensity}, sfx[], pause_after}`. Le texte OCR de la v0.2 est fourni au VLM en contexte.
- Les propositions sont écrites dans `projet.json`, modifiables dans l'éditeur, et jamais appliquées par-dessus une valeur fixée à la main.

**Critères d'acceptation :**
- les propositions du VLM sont jugées pertinentes sur ≥ 70 % des cases ;
- analyse VLM ≤ 5 min par planche sur la machine de référence, mise en cache ;
- pic de RAM ≤ 8 Go.

### v0.5 — Audio

- Import de voix enregistrées (une piste par bulle ou une piste globale découpée).
- Calage automatique des sous-titres et des bulles sur la voix avec whisper.cpp.
- Bruitages depuis une bibliothèque CC0 locale, sélectionnés à partir des étiquettes `sfx` du VLM.
- Musique avec ducking automatique sous les voix, mixage FFmpeg.
- Synthèse vocale **optionnelle**, avec uniquement des modèles à licence permissive. La derja tunisienne n'est pas couverte : la voix enregistrée reste la voie recommandée.

### v0.6 — Restauration des scans

- Redressement, correction du jaunissement, débruitage et atténuation de la trame (niveau 0).
- Agrandissement Real-ESRGAN ONNX (niveau 1, BSD).
- Placée avant l'analyse dans le pipeline ; activable par planche.

**Critère d'acceptation :** sur un jeu de vieux scans (§11), la détection des cases et l'OCR après restauration sont meilleurs qu'avant.

---

## 9. Exigences non fonctionnelles

| Domaine | Exigence |
|---|---|
| Performance | Voir les budgets (§5) et les critères par jalon. Toute étape > 10 s affiche une barre de progression. |
| Mémoire | Pic ≤ 8 Go sur la machine de référence ; un seul gros modèle chargé à la fois. |
| Reproductibilité | Mêmes entrées et même projet = même vidéo (graines fixées, versions de modèles épinglées). |
| Robustesse | Une planche en échec n'arrête pas le lot ; erreur claire en français et suggestion de correction. |
| Hors ligne | Après `embedkit models pull`, aucune connexion n'est requise. |
| Texte | Arabe et français rendus correctement (mise en forme, ligatures, sens bidirectionnel) dans les images de contrôle, l'éditeur et les sous-titres. |
| Qualité du code | Python 3.11, annotations de types, ruff, docstrings ; aucune fonction de plus de 60 lignes sans raison. |
| Tests | Unitaires (embedkit), golden (Rawi, Qahwati + jeu de contrôle), smoke test de rendu en `--apercu` en CI. Les planches Qahwati ne sont **pas publiées** (hors git, `.gitignore`) : leurs tests golden tournent en local et sont marqués « données absentes » en CI ; la CI utilise des planches libres de droits. |
| Licences | `embedkit licenses audit` liste code et modèles ; la CI échoue si un modèle par défaut n'est pas commercial. |
| Documentation | README par paquet, ADR pour chaque choix structurant (runtime, modèle par défaut, format projet). |

---

## 10. Risques et parades

| Risque | Impact | Parade |
|---|---|---|
| ONNX Runtime indisponible sur macOS 12 Intel | Bloquant v0.2 | Vérifié en premier en M0 ; repli OpenCV DNN ; ADR |
| Opérateurs ONNX non supportés par OpenCV DNN | Modèle inutilisable | Tester chaque modèle dans `embedkit bench` ; modèle alternatif dans le manifeste |
| OCR médiocre sur la derja manuscrite ou le lettrage BD, surtout en arabe | Sous-titres faux | Bench PaddleOCR / Tesseract en début de v0.2 ; correction manuelle facile ; texte `manual` protégé |
| Bulles mêlant arabe et français (sens bidirectionnel) | Texte mal ordonné | Segments par écriture (§6.4) ; tests dédiés |
| Mise en forme de l'arabe à l'incrustation (OpenCV ne la gère pas) | Sous-titres illisibles | Incrustation via libass (FFmpeg) ou Pillow + raqm ; vérifié en v0.2 |
| Détection ajustée à Qahwati | Échec sur d'autres BD | Jeu de contrôle d'autres styles dans les tests golden (O6) |
| Compilation de `llama-cpp-python` sur Monterey | Bloquant v0.4 | Repli sur le binaire `llama-mtmd-cli` en sous-processus |
| Qwen3-VL-2B trop lent ou trop gros sur la machine de référence | v0.4 dégradée | Bench avant intégration ; quantification plus forte ; repli règles de niveau 0 |
| Licences de poids ambiguës (détecteur de bulles…). MI-GAN : code **et poids sous MIT** (fichiers LICENSE et LICENSE-WEIGHTS du dépôt officiel, vérifiés le 14 novembre 2026) ; reste à vérifier les conditions du jeu Places2 ayant servi à l'entraînement | Juridique | `commercial: unknown` = refusé par défaut ; demander aux auteurs ; alternatives prêtes |
| Qualité insuffisante des petits modèles sur le dessin | Résultat moyen | Niveau 0 robuste ; corrections manuelles faciles ; niveau 2 optionnel |
| Détection des cases sensible à la recompression JPEG (mesuré : cases déplacées de plusieurs dizaines de pixels après réencodage en qualité 95) | Résultats instables d'une source à l'autre | Tests golden aussi sur des versions réencodées ; durcir la détection en v0.2 ; ADR 0004 |
| Vieux scans (bruit, jaunissement, trame) | Détection dégradée | Restauration (v0.6) ; jeu de test dédié |
| Lenteur sur la machine de référence | Expérience | Cache par hash, `--apercu`, traitement par lot de nuit |

---

## 11. Questions ouvertes

1. Nom définitif d'embedkit. (Les planches Qahwati restent privées, hors git.)
2. **Jeu de contrôle** : quelles planches d'autres styles (manga, comics, ligne claire, BD sans gouttières blanches) et quels vieux scans, avec quels droits (domaine public, accord des ayants droit) ? Premier élément : Goldorak, *TELEjunior* n° 16 (1979), 9 pages, gardé en local comme Qahwati (droits non libres).
3. embedkit doit-il viser dès maintenant d'autres langages (bindings) ou rester en Python ?
4. Liste des autres projets à IA embarquée du porteur, pour valider les interfaces de `tasks/` (quelles tâches seront partagées ?).
5. Faut-il une interface graphique de bureau (Tauri, etc.) en plus de l'éditeur web local ?
6. Format webtoon : à quel jalon le rattacher, si la demande se confirme ?

---

## 12. Glossaire

- **Motion comic** : BD animée par mouvements de caméra, calques et effets, sans réanimer entièrement les dessins.
- **Gouttière** : espace blanc entre deux cases.
- **Bulle vivante** : bulle détourée qui apparaît à l'écran au moment où elle est lue, au lieu d'être visible en permanence.
- **Parallaxe 2.5D** : calques plats déplacés à des vitesses différentes pour simuler la profondeur.
- **Inpainting** : reconstruction d'une zone effacée d'une image.
- **OCR** : reconnaissance du texte dans une image.
- **Derja** : arabe dialectal tunisien, écrit ici en lettres arabes.
- **VLM** : modèle vision-langage (image + texte → texte).
- **GGUF / ONNX** : formats de fichiers de modèles, pour llama.cpp et ONNX Runtime respectivement.
- **Niveau 0/1/2** : classique / léger embarqué / lourd optionnel.
- **Webtoon** : BD verticale lue en défilement continu.

---

## 13. Pistes futures (hors périmètre)

Ces idées ne sont pas planifiées. Elles sont notées pour ne pas être perdues et pour que l'architecture ne les empêche pas.

- **Traduction des bulles** (ex. derja → français ou anglais), en local avec un petit modèle de langage ; le format §6.4 la prépare déjà. Remplacement du texte dans les bulles traduites.
- **Réanimation des visages** (clignement des yeux, bouche synchronisée), type LivePortrait : retirée pour des raisons de licence et de coût sur CPU. À reconsidérer si un modèle permissif et léger apparaît.
- **Plans génératifs** (famille Wan via stable-diffusion.cpp) : retirés, trop lourds pour la machine de référence. Le runtime `sdcpp` d'embedkit est abandonné tant que cette piste n'est pas reprise.
- **Synthèse vocale en derja**, si un modèle à licence permissive apparaît.
- **Application de bureau** ou mobile (voir §11, question 5).
