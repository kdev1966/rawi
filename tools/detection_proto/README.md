# Prototypes de détection des cases (v0.2, en cours)

Scripts d'exploration, hors du paquet `rawi`. À lancer depuis la racine du dépôt :

```bash
python tools/detection_proto/p3_gutters_any_angle.py 40 0.6   # nouvelle détection seule
python tools/detection_proto/p4_union.py                      # union avec les gouttières v0.1
```

Mesures (rappel / précision, outil `python -m rawi.evaluate`) au 14 novembre 2026 :

| Variante | Qahwati | Goldorak |
|---|---|---|
| v0.1 (actuelle) | 93 % / 91 % | 39 % / 74 % |
| p3 seule, 2000 px | 84 % / 83 % | 80 % / 86 % |
| p4 « D » : union v0.1 + p3, filtre à fragments | 89 % / 82 % | 86 % / 90 % |

Idées : papier estimé sur toute la page ; gouttières = papier relié au bord, à tout angle ;
prolongement depuis les culs-de-sac du squelette, seulement à travers du clair (bulles) ;
cases = composantes après ouverture morphologique ; travail à 2000 px (à 1000 px les gouttières fines disparaissent).
