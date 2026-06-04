# Azul - Jeu à 2 Joueurs en ligne

Implémentation du jeu de société Azul pour deux joueurs en peer-to-peer.

## Installation

```bash
pip install -r requirements.txt
python generate_assets.py
```

## Comment jouer

### Option A: Deux ordis sur le même réseau

1. **Joueur 1 (Hôte)**: Lance `python main.py`, clique sur "Héberger la partie".
   - Notez l'adresse IP affichée.
2. **Joueur 2 (Client)**: Lance `python main.py`, clique sur "Rejoindre une partie".
   - Entrez l'IP du Joueur 1.

### Option B: Un seul ordi (les deux joueurs partagent l'écran)

Lancez `python main.py` en mode hôte. Les deux joueurs jouent sur le même écran
en se passant la souris.

## Règles

### But du jeu
Marquez le plus de points en plaçant des tuiles sur votre mur.

### Déroulement
- 5 fabriques sont disposées au centre, chacune avec 4 tuiles aléatoires.
- À tour de rôle, les joueurs prennent toutes les tuiles d'une couleur
  depuis une fabrique (les tuiles restantes vont au centre), ou depuis le centre.
- Les tuiles sont placées sur les lignes de motif (5 lignes, de 1 à 5 cases).
- Une ligne de motif remplie permet de placer une tuile sur le mur et de marquer des points.
- Les tuiles en excès vont sur la ligne de plancher (pénalité).
- La partie se termine quand un joueur complète une ligne horizontale du mur.

### Score final
- Ligne horizontale complète: +2 points
- Colonne verticale complète: +7 points
- Cinq tuiles d'une même couleur sur le mur: +10 points

## Personnalisation des tuiles
Remplacez les fichiers dans `assets/` par vos propres images (PNG, 64x64):
- `blue.png`, `yellow.png`, `red.png`, `black.png`, `white.png`

## Touches
- `ÉCHAP`: Quitter
- `ESPACE`: Quitter après la fin de partie
