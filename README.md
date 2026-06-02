# Budget Web

Application web locale pour gérer un budget par périodes, comptes et intitulés.

Le projet est volontairement simple: un serveur Python, une base SQLite locale, du HTML rendu côté serveur, et un peu de JavaScript pour l'édition directe des tableaux.

## But de l'application

L'application sert à remplacer un suivi de budget dans un tableur par une interface web générique.

Elle permet de:

- créer et consulter des périodes budgétaires;
- gérer les comptes;
- gérer les intitulés;
- encoder les mouvements compte par compte;
- éditer les tableaux directement, avec validation ou annulation comme dans une feuille Excel;
- consulter une synthèse des soldes, entrées, sorties et transferts;
- définir un budget mensuel type dans les paramètres;
- créer automatiquement un onglet `Budget` par période à partir du budget mensuel;
- importer des transactions CSV dans un compte.

## Données

La base de données est SQLite et se trouve dans:

```text
data/budget.sqlite3
```

Au démarrage, l'application vérifie que la base existe. Si elle n'existe pas, elle crée le schéma et initialise les données depuis:

```text
initial-data.yaml
```

Ce fichier contient les comptes et intitulés par défaut, par exemple:

- `Compte courant`;
- `Compte epargne`;
- quelques intitulés usuels comme `Salaire`, `Courses`, `Loyer`, `Internet`.

L'application ne dépend plus du fichier Excel initial.

## Démarrer l'application

Depuis le dossier du projet:

```bash
python3 app.py
```

Puis ouvrir:

```text
http://127.0.0.1:8000
```

Si la base n'existe pas encore, elle est créée automatiquement au premier démarrage.

## Pages principales

- `/`: liste les périodes et permet d'en créer.
- `/parameters`: gère les comptes, les intitulés et le budget mensuel.
- `/period/<id>`: affiche une période avec la synthèse, l'onglet `Budget`, puis un onglet par compte.
- `/period/<id>/import?account=<id>`: importe des transactions CSV pour un compte.
- `/transactions`: affiche une vue filtrable des transactions.

## Structure des fichiers

```text
.
├── app.py                  # Serveur HTTP et routage principal
├── database.py             # Connexion SQLite, schéma, migrations, données initiales
├── initial-data.yaml       # Comptes et intitulés créés dans une base neuve
├── web_helpers.py          # Helpers HTML communs
├── data/
│   └── budget.sqlite3      # Base SQLite locale
├── endpoints/
│   ├── api.py              # Endpoints JSON pour édition, suppression, drag/drop, budget
│   ├── imports.py          # Page et logique d'import CSV
│   ├── parameters.py       # Page des paramètres
│   ├── period.py           # Vue d'une période, synthèse, comptes, budget
│   ├── periods.py          # Liste et création des périodes
│   ├── static_files.py     # Service des fichiers statiques
│   └── transactions.py     # Vue globale des transactions
└── static/
    ├── app.js              # Interactions navigateur
    └── style.css           # Styles de l'application
```

## Notes d'utilisation

Une période a toujours une date de début. Sa date de fin est connue seulement quand la période suivante est créée.

Dans les comptes, les lignes sont triées par date puis par numéro. Le numéro `#` est géré par l'application et peut changer après un ajout, une suppression ou un drag and drop.

L'onglet `Budget` est spécial: il affiche les entrées planifiées issues du budget mensuel. Il n'est pas éditable comme un compte classique. Une ligne planifiée peut être annulée ou instanciée dans un compte réel.
