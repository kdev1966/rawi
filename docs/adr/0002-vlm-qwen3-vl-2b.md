# ADR 0002 — VLM par défaut pour la mise en scène : Qwen3-VL-2B

- **Statut** : proposé — à confirmer par mesure sur la machine de référence avant l'intégration (v0.4)
- **Date** : 13 novembre 2026

## Contexte

La mise en scène automatique (v0.4) demande, pour chaque case, un JSON structuré : locuteur, émotion, action, mouvement de caméra, bruitages, pause. Contraintes (PRD §5) :

- inférence en processus via llama.cpp, sans serveur ;
- CPU seul (MacBook Pro 2015, AVX2, 16 Go) ;
- ≤ 2,5 Go en Q4, projecteur compris ; pic de RAM ≤ 8 Go ;
- ≤ 5 min d'analyse par planche, mise en cache ;
- licence compatible avec un usage commercial ;
- planches avec du texte arabe et français : le modèle doit comprendre un minimum les deux langues.

Le PRD 1.0 proposait SmolVLM2 2.2B.

## Décision

Retenir **Qwen3-VL-2B** (GGUF Q4 + projecteur, via llama.cpp) comme modèle par défaut, et garder SmolVLM2 2.2B comme alternative déclarée dans un second manifeste.

Raisons :
- meilleure compréhension multilingue, arabe compris, que SmolVLM2, entraîné surtout en anglais ;
- taille compatible avec le budget de 2,5 Go en Q4 ;
- licence annoncée Apache 2.0, **à vérifier sur la révision épinglée** et à déclarer dans le manifeste (`commercial: unknown` tant que ce n'est pas fait).

## Conditions de confirmation

Avant l'intégration, `embedkit bench` doit établir sur la machine de référence :
1. le chargement par `llama-cpp-python` (ou par le binaire `llama-mtmd-cli`) ;
2. le temps par case et le pic de RAM, dans les budgets ;
3. la validité de la sortie JSON avec la grammaire GBNF (EK-8) sur les 8 planches Qahwati.

Si une condition échoue : essayer SmolVLM2 2.2B ou une quantification plus forte. Sinon, rester sur les règles de niveau 0 de la v0.1.

## Conséquences

- Le texte OCR (v0.2) est passé au VLM en contexte : la qualité de la mise en scène dépend aussi de l'OCR.
- Le statut passera à « accepté » ou « rejeté » une fois les mesures faites.
