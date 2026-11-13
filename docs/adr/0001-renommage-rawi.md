# ADR 0001 — Renommer l'application en Rawi

- **Statut** : accepté
- **Date** : 13 novembre 2026
- **Décideur** : porteur du projet

## Contexte

L'application s'appelait `bdanim` (nom de travail). Le porteur a choisi le nom **Rawi** (« le conteur » en arabe). Le dossier du dépôt a déjà été renommé en `rawi`, et le dépôt GitHub s'appelle `rawi`. Le code (paquet, module Python, commande CLI) porte encore l'ancien nom.

## Décision

Tout renommer en `rawi` : documentation, paquet `apps/rawi`, module Python `rawi`, commande CLI `rawi`, README et `CLAUDE.md`.

- Le PRD passe à Rawi dès la v1.1.
- Le code est renommé au début de M0, en même temps que la restructuration en monorepo, tant qu'il y a peu de code et aucun utilisateur externe.
- Aucun alias `bdanim` n'est conservé : il n'existe pas d'installation à préserver.
- `embedkit` garde son nom de travail (question ouverte du PRD §11).

## Conséquences

- Un seul nom partout, donc pas de confusion entre nom produit et nom technique.
- Les projets `projet.json` existants n'ont pas de champ de nom de l'application : aucune migration de données n'est nécessaire.
- L'ancien chemin `bdanim-workspace` peut encore apparaître dans des notes ou des mémoires antérieures.
- Critère de M0 : `rawi auto` produit les mêmes vidéos que `bdanim auto` en v0.1.
