# ADR 0006 — Lecture du texte des bulles : PaddleOCR arabe v5 (ONNX)

- **Statut** : accepté
- **Date** : 14 novembre 2026
- **Décideur** : porteur du projet (choix de la v5 parmi v3 et v5)

## Contexte

La v0.2 doit lire le texte des bulles pour les sous-titres, puis pour la traduction. Les bulles Qahwati mêlent arabe (derja), français et anglais dans une même bulle, parfois sur une même ligne. Contraintes : local, CPU, licence commerciale.

Mesure faite sur une transcription de référence des 46 bulles Qahwati, écrite à la main et validée par le porteur (`tests/fixtures/qahwati/qahwati_text_expected.json`, privée comme les planches : elle reproduit les dialogues). Banc d'essai : `tools/ocr_proto`.

| Moteur | Erreurs par caractère | Mots retrouvés | Temps / bulle |
|---|---|---|---|
| Tesseract 5 `ara+fra+eng`, image brute | 47 % | 57 % | 0,7 s |
| Tesseract 5, texte isolé | 28 % | 64 % | 0,4 s |
| PaddleOCR arabe v3 (ONNX), ligne par ligne | 9 % | 61 % | 0,06 s |
| PaddleOCR arabe v5 (ONNX), ligne par ligne | 11 % | 76 % | 0,08 s |

## Décision

- **PaddleOCR arabe v5** (`arabic_PP-OCRv5_mobile_rec`, ONNX converti par le projet oar-ocr, Apache 2.0, 7,7 Mo) est le modèle par défaut (`paddleocr-arabic-v5-rec`). Il place bien les espaces entre les mots arabes, ce qui compte à la lecture d'un sous-titre ; il est plus faible que la v3 sur les mots latins et les chiffres.
- **Les lignes sont trouvées sans modèle** (niveau 0) : texte de la bulle isolé en noir sur blanc (même extraction que les bulles vides), bandes d'encre, bandes de diacritiques rattachées à la ligne voisine. Le modèle de détection de PaddleOCR (88 Mo) n'est pas utilisé.
- L'ordre de sortie du modèle arabe est rétabli par passages (règle de PaddleOCR), sauf pour les lignes sans aucun caractère arabe.
- Les lignes lues avec une confiance inférieure à 0,5 sont ignorées : pour un sous-titre, mieux vaut pas de texte qu'un texte absurde.
- embedkit gagne les sources par adresse fixe (publication GitHub) et les fichiers annexes (le dictionnaire du modèle), avec sha256 pour chacun.

## Résultats sur la chaîne complète

Détection des bulles puis lecture, sur les 8 planches Qahwati : **21 % d'erreurs par caractère, 67 % des mots retrouvés**. Les 5 bulles non détectées comptent comme entièrement fausses (environ 11 points) ; sur les bulles détectées, la lecture rejoint le banc d'essai. Environ 4 s par planche, analyse comprise.

## Conséquences

- Le texte est enregistré par bulle (`text`, `segments` arabe et latin avec leur sens, `lang` : `ar` et `und-Latn`, `confidence`, `source: "ocr"`). Un texte saisi à la main (`source: "manual"`) n'est jamais écrasé.
- Le niveau 0 de l'OCR est la saisie manuelle : sans modèle (hors ligne, jamais téléchargé), l'analyse continue sans texte.
- Le français et l'anglais ne sont pas distingués (`und-Latn`).
- Le sens de lecture n'est **pas** déduit de l'écriture : Qahwati est en arabe mais se lit de gauche à droite (numéros des bulles).
- Pistes : combiner v5 (passages arabes) et un modèle latin (passages latins) ; améliorer la détection des bulles, qui pèse la moitié des erreurs.
