# elexon-typical-battery-behaviour

Comportement typique d'une batterie du réseau britannique, reconstitué à partir
des données publiques d'[Elexon Insights (BMRS)](https://developer.data.elexon.co.uk/).

L'API est publique et ne demande aucune clef. Les données sont soumises à la
[licence d'utilisation Elexon](https://www.elexon.co.uk/bsc/data/balancing-mechanism-reporting-agent/copyright-licence-use-bmrs-api/),
qui impose de citer la source.

## Ce que produit le dépôt

Une figure carrée 1200 × 1200 à trois panneaux :

1. **Une journée** — le profil de puissance d'une batterie nommée, pas demi-horaire
   (décharge au-dessus de zéro, charge en dessous).
2. **La même journée** — le prix de déséquilibre du système.
3. **Douze mois** — le profil médian par heure de la journée, avec l'intervalle
   interquartile.

Les deux échelles (MW et £/MWh) occupent deux panneaux distincts plutôt qu'un
double axe : superposer deux unités sur un même axe y laisse choisir au lecteur
la corrélation qu'il veut voir.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Utilisation

### 1. Trouver une batterie

Elexon ne publie pas de `fuelType = BATTERY` fiable. Le script repère les unités
bidirectionnelles — capables à la fois d'importer et d'exporter — et écarte le
pompage-turbinage connu.

```bash
python src/discover_batteries.py --min-mw 50
```

La liste complète est écrite dans `data/battery_bmus.csv`. Retenir un
identifiant `bmUnit` (par exemple `T_XXXXX-1`).

### 2. Télécharger les données

```bash
python src/fetch.py --bmu T_XXXXX-1 --day 2026-06-18 --months 12
```

L'historique de douze mois est récupéré par tranches de sept jours ; comptez
quelques minutes. Pour un essai rapide, `--months 0` ne prend que la journée.

### 3. Construire la figure

```bash
python src/make_figure.py --bmu T_XXXXX-1 --day 2026-06-18 --name "Nom du site"
```

Résultat dans `figures/`.

## Choisir une bonne journée

Une journée intéressante est une journée où le prix bouge : pointe du soir
marquée, épisode de prix négatifs, ou tension sur le système. Les journées
plates donnent une figure plate.

## Structure

```
src/elexon.py              client API (aucune clef requise)
src/discover_batteries.py  identification des batteries
src/fetch.py               téléchargement et cache CSV
src/make_figure.py         figure
data/                      cache local (les gros fichiers ne sont pas versionnés)
figures/                   sorties
```

## Note sur le pas de temps

Le marché britannique fonctionne en périodes de règlement d'une demi-heure. Le
marché belge, comme la plupart des marchés continentaux, raisonne au quart
d'heure. La granularité de la figure est donc celle de GB, pas celle d'Elia.
