# ADR 0003 — Runtime d'inférence : ONNX Runtime par défaut

- **Statut** : accepté
- **Date** : 13 novembre 2026
- **Mesuré sur** : machine de référence (MacBook Pro 2015, i7-4870HQ, AVX2, 16 Go, macOS 12.7.6)

## Contexte

Le PRD (§5, §10) faisait de la disponibilité d'ONNX Runtime sur macOS 12 Intel le premier risque à lever en M0, avec OpenCV DNN comme repli.

## Mesures

Environnement conda `rawi`, canal conda-forge seul (`--override-channels`) : Python 3.11.14, `onnxruntime` 1.22.2 (build CPU), `opencv` 4.11.0 (headless), NumPy 2.4.2, FFmpeg 7.1.1.

- ONNX Runtime s'installe depuis conda-forge pour osx-64 et se charge sur macOS 12.7.6 (binaire compilé pour macOS ≥ 10.15). Fournisseur disponible : `CPUExecutionProvider`.
- Entrée : une planche Qahwati redimensionnée. Médiane de 10 inférences après une passe d'échauffement. Un processus par mesure.

| Modèle | Moteur | Chargement | Inférence | Pic RAM | Résultat |
|---|---|---|---|---|---|
| MobileNetV2 (CNN, 224²) | ONNX Runtime | 0,14 s | 3,4 ms | 101 Mo | OK |
| MobileNetV2 (CNN, 224²) | OpenCV DNN | 0,04 s | 8,1 ms | 110 Mo | OK, écart max 6·10⁻⁶ |
| Depth Anything V2 Small FP32 (ViT, 518²) | ONNX Runtime | 0,58 s | 598 ms | 417 Mo | OK |
| Depth Anything V2 Small FP32 | OpenCV DNN | — | — | — | **échec** au chargement (nœuds `Shape` / `Reshape` dynamiques) |
| Depth Anything V2 Small INT8 | ONNX Runtime | 0,53 s | 694 ms | 432 Mo | OK, corrélation 0,99 avec FP32 |
| Depth Anything V2 Small INT8 | OpenCV DNN | — | — | — | **échec** au chargement |

## Décision

1. **ONNX Runtime est le runtime par défaut** d'embedkit pour les modèles de vision (`runtime: onnx`).
2. **OpenCV DNN n'est qu'un repli partiel** : il convient aux réseaux convolutifs simples à formes fixes, pas aux modèles de type transformer exportés avec des formes dynamiques. Un manifeste ne déclare `opencv_dnn` comme alternative que si `embedkit bench` a validé ce modèle sous OpenCV DNN.
3. Si ONNX Runtime manque ou échoue, une tâche dont le modèle ne passe pas sous OpenCV DNN **retombe au niveau 0** (PRD §4), avec un message clair en français.
4. **Quantification** : sur ce processeur (Haswell, sans instructions VNNI), l'INT8 dynamique n'accélère pas l'inférence ; il est même un peu plus lent (694 ms contre 598 ms). Il ne réduit que la taille sur disque (27 Mo contre 99 Mo). Chaque manifeste choisit sa variante (FP32, FP16, INT8) d'après `embedkit bench` sur la machine de référence, pas par principe.

## Conséquences

- Le risque « ONNX Runtime indisponible sur macOS 12 Intel » (PRD §10) est levé.
- Le budget de 150 Mo pour les modèles de niveau 1 doit arbitrer entre taille (INT8) et vitesse (FP32). La profondeur coûte environ 0,6 s par case à 518², ce qui reste compatible avec le budget de 5 min d'analyse par planche.
- **FFmpeg de conda-forge** : il inclut libass, HarfBuzz et FreeType, donc l'incrustation de sous-titres arabes est possible (risque v0.2 en partie levé, à confirmer par un essai réel). C'est la variante **GPL** (libx264) : sans effet pour un usage local, mais à revoir si Rawi distribue un jour FFmpeg avec l'application. La variante LGPL et l'encodeur OpenH264 restent possibles.
- **Installation** : la machine de référence n'a pas Miniforge mais un Miniconda installé par Homebrew. L'environnement `rawi` a été créé avec `--override-channels -c conda-forge`, sans passer par le canal `defaults` d'Anaconda, dont les conditions d'utilisation posent problème pour un usage commercial. `installer_mac.sh` (qui suppose `~/miniforge3`) et les commandes de `CLAUDE.md` seront mis à jour lors du renommage en M0.
- Mesures à refaire avec `embedkit bench` une fois ce dernier écrit, pour qu'elles soient reproductibles.
