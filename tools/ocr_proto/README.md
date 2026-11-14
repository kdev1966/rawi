# Banc d'essai OCR (v0.2, exploration)

`ocr_bench.py` lit les 46 bulles de référence de Qahwati (`apps/rawi/tests/fixtures/qahwati/qahwati_text_expected.json`, privée, hors git)
avec plusieurs moteurs et mesure le taux d'erreur par caractère (CER, après normalisation : voyelles courtes,
ponctuation, variantes d'alef) et la part de mots retrouvés. Les chemins des modèles pointent vers un dossier
temporaire : les télécharger d'abord (voir ci-dessous).

Mesures du 14 novembre 2026 (MacBook Pro 2015), sur le texte isolé de chaque bulle (encre noire sur blanc) :

| Moteur | CER | Mots retrouvés | Temps / bulle |
|---|---|---|---|
| Tesseract 5 `ara+fra+eng` (best), image brute | 47 % | 57 % | 0,7 s |
| Tesseract 5 (fast), texte isolé | 28 % | 64 % | 0,4 s |
| PaddleOCR arabe v3 (ONNX), ligne par ligne | **9 %** | 61 % | 0,06 s |
| PaddleOCR arabe v5 (ONNX), ligne par ligne | 11 % | **76 %** | 0,08 s |
| Arbitrage arabe / latin par confiance (v3 ou v5) | 13–14 % | 60–75 % | 0,15 s |

Constats : isoler le texte de la bulle divise les erreurs de Tesseract par deux ; PaddleOCR est 5 à 10 fois plus
rapide et bien plus juste ; la v3 lit mieux les mots latins et les chiffres mais colle les mots arabes (espaces
manquantes) ; la v5 place bien les espaces mais abîme les mots latins et les chiffres. Lignes : découpage classique
(bandes d'encre, bandes de diacritiques rattachées à la ligne voisine). L'ordre de sortie du modèle arabe est
retourné par passages (règle de PaddleOCR : les passages latins et chiffres restent à l'endroit).

Modèles (Apache 2.0) : `monkt/paddleocr-onnx` (rév. 7b02d0a3) `languages/arabic`, `languages/latin` ;
v5 arabe : publication v0.3.0 de GreatV/oar-ocr (`arabic_pp-ocrv5_mobile_rec.onnx`, `ppocrv5_arabic_dict.txt`) ;
Tesseract : `tessdata_best` / `tessdata_fast` (`ara`, `fra`, `eng`).
