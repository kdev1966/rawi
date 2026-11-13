# CLAUDE.md — règles de travail

Lis d'abord `docs/PRD.md` : c'est la source de vérité du projet. En cas de doute, le PRD gagne. Si le PRD est ambigu, pose la question plutôt que de deviner.

## Le projet en une phrase

**bdanim** transforme des planches de BD en vidéos motion comic. Il s'appuie sur **embedkit**, une bibliothèque d'IA embarquée réutilisable par d'autres projets. Tout est open source, local et hors ligne, sans API payante ni serveur tiers.

## Contraintes non négociables

1. **Pas de service externe** : ni API payante, ni Ollama, ni LM Studio, ni cloud. L'inférence se fait en processus (ONNX Runtime, OpenCV DNN, llama.cpp, whisper.cpp, stable-diffusion.cpp).
2. **Pas de PyTorch ni de transformers à l'exécution.** Ils sont autorisés uniquement dans `tools/convert/` pour convertir des modèles en ONNX.
3. **Machine de référence** : MacBook Pro 2015, Intel x86_64, 16 Go de RAM, macOS 12.7.6, sans GPU, Python 3.11 via Miniforge/conda-forge. Tout ce qui est par défaut doit y tourner.
4. **Licences** : toute nouvelle dépendance ou tout nouveau modèle doit avoir une licence compatible avec un usage commercial (Apache 2.0, MIT, BSD…). Déclare-la dans le manifeste du modèle. En cas de doute : `commercial: unknown`, et signale-le.
5. **Dépendances** : `embedkit` ne dépend jamais de `bdanim`. N'ajoute aucune dépendance Python lourde sans justification dans un ADR (`docs/adr/`).
6. **Le classique d'abord** : propose une solution OpenCV/NumPy (niveau 0) avant un modèle. Chaque tâche IA doit avoir un repli de niveau 0.

## Conventions

- Code, identifiants et commentaires techniques en **anglais**. Messages utilisateur (CLI, erreurs, UI) en **français**.
- Python 3.11, annotations de types, `ruff` (lint et format), docstrings courtes.
- Images en NumPy `HxWx3 uint8` (BGR côté OpenCV, à convertir explicitement aux frontières des modèles).
- Toute étape longue affiche une progression et écrit ses sorties dans le dossier projet (cache par hash des entrées).
- Le format `projet.json` est versionné. Toute modification passe par une migration dans `bdanim/project.py`.

## Commandes utiles

```bash
source ~/miniforge3/bin/activate && conda activate bdanim
pytest -q                                   # tests
ruff check . && ruff format --check .       # qualité
bdanim auto apps/bdanim/tests/fixtures/qahwati/*.jpg --apercu   # test de bout en bout rapide
embedkit models list | pull | verify | bench        # (à partir de M0)
```

## Façon de travailler

- Avance **jalon par jalon** (M0, puis v0.2, etc.) en suivant le PRD §8. Commence toujours par M0.
- Avant de coder une tâche : rappelle en 3 à 5 lignes le plan et les fichiers touchés.
- Après chaque changement de la détection ou du rendu : relance les tests golden sur les 8 planches Qahwati et regarde les images de contrôle.
- Ne dis jamais qu'une chose « marche sur la machine de référence » sans qu'elle y ait été testée. Indique « non vérifié sur macOS 12 Intel » quand c'est le cas.
- Pour un nouveau modèle : manifeste YAML, test de chargement, `embedkit bench`, puis seulement l'intégration.
- Commits petits et explicites. Pas de fichiers de modèles (`.onnx`, `.gguf`) dans git.
