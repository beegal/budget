# Budget Web

Application web locale pour gérer un budget par périodes, comptes et intitulés.

Le projet est volontairement simple: un serveur Python standard library, une base SQLite locale, du HTML rendu côté serveur, et du JavaScript/CSS vanilla pour l'édition directe des tableaux.

## Fonctionnalités

- créer et consulter des périodes budgétaires;
- gérer les comptes, les intitulés et un budget mensuel type;
- encoder les mouvements compte par compte;
- éditer les tableaux directement avec `Enter` pour valider et `Esc` pour annuler;
- réordonner les comptes et transactions par drag and drop;
- consulter une synthèse des soldes, entrées, sorties et transferts;
- créer automatiquement un onglet `Budget` par période à partir du budget mensuel;
- instancier une entrée planifiée du budget dans un compte réel;
- importer des transactions CSV dans un compte;
- masquer les comptes vides dans les périodes, avec ajout ponctuel via le bouton `+` des tabs.

## Données

La base SQLite locale se trouve dans:

```text
data/budget.sqlite3
```

La base n'est pas suivie par Git. À la première exécution, l'application crée le schéma et initialise les données depuis:

```text
initial-data.yaml
```

Tables actives:

- `months`
- `accounts`
- `transaction_labels`
- `transactions`
- `account_balances`
- `monthly_budget`
- `budget_schedule`

L'application ne dépend plus du fichier Excel initial.
Le code de migration/backfill legacy a été retiré: une base neuve est créée directement avec le schéma courant.

## Démarrer l'application

Depuis le dossier du projet:

```bash
python3 app.py
```

Puis ouvrir:

```text
http://127.0.0.1:8000
```

## Pages principales

- `/`: liste les périodes et permet d'en créer.
- `/parameters`: gère les comptes, les intitulés et le budget mensuel.
- `/period/<id>`: affiche une période avec synthèse, onglet `Budget`, puis les comptes visibles.
- `/period/<id>/import?account=<id>`: importe des transactions CSV pour un compte.
- `/transactions`: affiche une vue filtrable des transactions.

## Notes UI

Dans les paramètres:

- les comptes ont `Synthèse` et `Visible si vide`;
- si `Visible si vide` est décoché, le compte n'apparaît plus comme tab dans une période tant qu'il est vide;
- le tab `+` d'une période liste les comptes masqués et permet d'en ouvrir un pour encoder;
- les listes longues de comptes, intitulés et budget mensuel sont scrollables;
- le budget mensuel utilise le même sélecteur d'intitulés que les transactions;
- les lignes positives/négatives sont colorées en vert/rouge;
- les boutons d'action des lignes sont alignés dans une colonne dédiée.

Dans les comptes:

- les lignes sont triées par date puis par numéro;
- le numéro `#` est géré par l'application;
- les transactions peuvent être ajoutées, validées, annulées, supprimées ou réordonnées;
- le bouton de suppression globale retire toutes les lignes du compte pour la période affichée;
- le sélecteur d'intitulés est partagé avec le budget mensuel et propose la création d'un intitulé manquant.

L'onglet `Budget` est spécial:

- il affiche les entrées planifiées depuis `monthly_budget`;
- il n'est pas éditable comme un compte classique;
- une entrée planifiée peut être annulée ou instanciée dans un compte réel;
- une transaction classique sauvegardée avec même période, intitulé et montant marque une entrée planifiée comme `found`.

## Import CSV

Format attendu:

```text
Date,Intitulé,Montant,commentaire
```

Validation:

- date obligatoire et dans la période;
- montant numérique;
- intitulé obligatoire;
- les intitulés inconnus peuvent être créés automatiquement à l'import.

## Développement récent

- ajout de `Visible si vide` sur les comptes;
- ajout d'un tab `+` dans les périodes pour ouvrir un compte masqué et encoder dessus;
- scroll vertical sur les longues tables des paramètres;
- largeur minimale sur la table des comptes pour garder le nom lisible;
- coloration vert/rouge du budget mensuel;
- factorisation du picker d'intitulés et des boutons d'action;
- nettoyage des tables et colonnes non utilisées;
- suppression du code de migration historique;
- ajout d'un build Docker Alpine Python et d'un workflow GitHub Actions.

## Structure

```text
.
├── app.py
├── database.py
├── initial-data.yaml
├── README.md
├── web_helpers.py
├── .dockerignore
├── .github/
│   └── workflows/
│       └── docker-image.yml
├── build/
│   └── Dockerfile
├── data/
│   └── budget.sqlite3
├── endpoints/
│   ├── __init__.py
│   ├── api.py
│   ├── imports.py
│   ├── parameters.py
│   ├── period.py
│   ├── periods.py
│   ├── static_files.py
│   └── transactions.py
└── static/
    ├── app.js
    └── style.css
```

## Docker

Une image Docker peut être construite avec:

```bash
docker build -f build/Dockerfile -t beegal/budget:local .
```

Avec minikube:

```bash
eval $(minikube docker-env) && docker build -f build/Dockerfile -t beegal/budget:local .
```

Le conteneur écoute sur le port `8000` et utilise `/app/data` pour la base SQLite.

Exemple d'exécution:

```bash
docker run --rm -p 8000:8000 -v "$(pwd)/data:/app/data" beegal/budget:local
```

## GitHub Actions

Le workflow `.github/workflows/docker-image.yml` construit et publie l'image Docker sur Docker Hub lors d'un push sur la branche `release`.

Image publiée:

```text
beegal/budget:latest
```

Secrets requis:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`
