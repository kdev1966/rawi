# ADR 0007 — Parallaxe par calques : premier plan par la profondeur, décor rebâti par MI-GAN

- **Statut** : accepté, désactivé par défaut (`--calques oui` pour l'essayer) en attendant le détourage MobileSAM
- **Date** : 14 novembre 2026
- **Décideur** : porteur du projet (ordre de la v0.3 ; étape 1 jugée « ça va »)

## Contexte

L'étape 1 de la v0.3 fait glisser chaque pixel selon sa profondeur (déformation douce). L'effet reste discret, et au-delà de 6 % de la largeur les formes s'étirent. Pour un vrai relief, le premier plan doit bouger d'un bloc devant un décor qu'il faut reconstituer là où il le cachait.

## Décision

- **Premier plan** : partie de la case plus proche que le seuil d'Otsu de sa carte de profondeur (Depth Anything V2 Small), bulles exclues. Pas de calques si ce premier plan couvre moins de 3 % ou plus de 85 % de la case.
- **Décor** : la zone du premier plan, élargie de 7 px, est reconstituée par **MI-GAN** (`migan-512`, pipeline ONNX publié par l'auteur, `andraniksargsyan/migan`, code et poids sous MIT). Mesuré sur la machine de référence : 0,6 à 1,1 s par case, 850 Mo de RAM au pic.
- **Rendu** : pendant le plan, le premier plan glisse (jusqu'à 3 % de la largeur), le décor glisse de 30 % de cela dans l'autre sens, aller-retour sans à-coup ; les bulles ne bougent pas.
- **Cache** : masque du premier plan et décor reconstitué sont écrits dans `calques/`, avec une empreinte de la case, de sa profondeur, de ses bulles et du modèle. Format de projet 5 (`front`, `back` par case).
- **Repli** : sans MI-GAN (hors ligne, jamais téléchargé) ou sans premier plan net, la déformation de l'étape 1 est gardée. Le niveau 0 d'embedkit (`cv2.inpaint`) n'est pas utilisé pour les calques : il étale les couleurs sur les grandes zones.

## Constats

- Sur de grandes zones, MI-GAN invente un décor absurde (entraîné sur des photos de paysages, Places2). En parallaxe, seule une bande étroite le long de la silhouette se découvre, là où le remplissage prolonge le vrai décor : le résultat vu est propre.
- Sur les 8 planches Qahwati : 45 cases sur 48 ont des calques ; analyse complète (cases, bulles, texte, profondeur, calques) en 14 s par planche.

## Conséquences

- Le premier plan est un seul bloc : plusieurs personnages à des profondeurs différentes glissent ensemble. Le détourage précis (étape 3, MobileSAM, clics) permettra plusieurs calques.
- Reste à vérifier : les conditions du jeu Places2 ayant servi à entraîner MI-GAN.

## Retour du porteur (14 novembre 2026)

Sur les vidéos, les personnages sont déformés et déchirés. Cause vue sur les cases : le seuil d'Otsu sur la profondeur coupe les personnages en deux (tête devant, buste derrière ; main séparée du bras). La tête glisse seule et découvre le remplissage absurde de MI-GAN. Ce n'est pas réglable par un paramètre : il faut la silhouette entière d'un personnage.

Décision : les calques passent derrière l'option `--calques oui` ; la déformation de l'étape 1 redevient le rendu par défaut. Les calques seront réévalués avec les masques MobileSAM (étape 3), qui donnent des objets entiers.
