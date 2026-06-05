# Budget Web

Application web locale pour gérer un budget par périodes, comptes et intitulés.

Le projet reste volontairement simple: une application FastAPI locale, une base SQLite ou MySQL, du HTML rendu côté serveur avec Jinja, et du JavaScript/CSS vanilla pour l'édition directe des tableaux.

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

Le chemin peut être changé avec:

```bash
BUDGET_SQLITE_PATH=/chemin/budget.sqlite3 python3 app.py
```

La base n'est pas suivie par Git. À la première exécution, l'application crée le schéma et initialise les données depuis:

```text
initial-data.yaml
```

Tables actives:

- `period`
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
python3 -m pip install -r requirements.txt
python3 app.py
```

Équivalent Uvicorn:

```bash
uvicorn app:application --host 127.0.0.1 --port 8000
```

Puis ouvrir:

```text
http://127.0.0.1:8000
```

## Configuration

Le fichier `config.yaml` contient les préférences d'affichage:

```yaml
i18n:
  default-locale: fr_FR.UTF-8
  date-format: jj/mm/yy
display:
  number-decimals: 2
```

`date-format` accepte `jj/mm/yy`, `mm/jj/yy` ou `yy-mm-jj`. Ce format sert notamment de valeur par défaut dans l'import CSV.

La base de données peut aussi être configurée par variables d'environnement:

```bash
BUDGET_DB_BACKEND=sqlite
BUDGET_SQLITE_PATH=data/budget.sqlite3
```

Pour MySQL:

```bash
BUDGET_DB_BACKEND=mysql
BUDGET_MYSQL_HOST=127.0.0.1
BUDGET_MYSQL_PORT=3306
BUDGET_MYSQL_DATABASE=budget
BUDGET_MYSQL_USER=budget
BUDGET_MYSQL_PASSWORD=...
```

Pour créer la base et l'utilisateur MySQL avec le CLI:

```bash
BUDGET_DB_BACKEND=mysql \
BUDGET_MYSQL_ROOT_USER=root \
BUDGET_MYSQL_ROOT_PASSWORD=... \
BUDGET_MYSQL_DATABASE=budget \
BUDGET_MYSQL_USER=budget \
BUDGET_MYSQL_PASSWORD=... \
python3 budget_cli.py --db-backend mysql --create
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

L'écran permet de choisir:

- le format de date: `jj/mm/yy`, `mm/jj/yy` ou `yy-mm-jj`;
- le format de fichier: CSV/TSV, avec ou sans en-tête.

Les années sur deux ou quatre chiffres sont acceptées. Le format de date sélectionné par défaut vient de `i18n.date-format` dans `config.yaml`.

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
├── budget_cli.py
├── config.py
├── config.yaml
├── components/
│   ├── common.py
│   ├── imports.py
│   ├── parameters.py
│   ├── period.py
│   ├── periods.py
│   └── transactions.py
├── database.py
├── initial-data.yaml
├── README.md
├── requirements.txt
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
├── static/
    ├── app.js
    └── style.css
└── templates/
    ├── imports.html
    ├── layout.html
    ├── parameters.html
    ├── period.html
    ├── periods.html
    └── transactions.html
```

Les endpoints préparent les données et délèguent le rendu HTML réutilisable au répertoire `components/`. Les templates dans `templates/` gardent les squelettes de pages, tandis que `components/` contient les composants dynamiques comme tabs, lignes de tables, boutons d'action, icônes et sélecteurs d'intitulés.

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

### Docker avec MySQL géré

Un fichier compose démarre l'application et une base MySQL:

```bash
BUDGET_MYSQL_ROOT_PASSWORD=... \
BUDGET_MYSQL_PASSWORD=... \
docker compose -f build/docker-compose.mysql.yml up --build
```

Volumes utilisés:

- `budget-mysql-data`: données MySQL (`/var/lib/mysql`);
- `budget-db-config`: copie des informations de connexion (`/app/config/db.env`);
- `budget-app-data`: données locales de l'application.

Au premier démarrage, le conteneur applicatif écrit `/app/config/db.env` si le fichier n'existe pas encore. Si les volumes existent déjà, le fichier est relu et la base MySQL garde ses données.

Variables principales:

- `BUDGET_HTTP_PORT`: port HTTP publié, par défaut `8000`;
- `BUDGET_DB_BACKEND`: `sqlite` ou `mysql`;
- `BUDGET_MYSQL_CREATE_DATABASE`: `1` pour créer/assurer la DB au démarrage, `0` sinon;
- `BUDGET_MYSQL_HOST`, `BUDGET_MYSQL_PORT`;
- `BUDGET_MYSQL_DATABASE`;
- `BUDGET_MYSQL_USER`, `BUDGET_MYSQL_PASSWORD`;
- `BUDGET_MYSQL_ROOT_USER`, `BUDGET_MYSQL_ROOT_PASSWORD`;
- `BUDGET_DB_CONFIG_DIR`: dossier où écrire/lire `db.env`, par défaut `/app/config`.

### Docker avec MySQL externe

Pour utiliser une base existante:

```bash
BUDGET_MYSQL_HOST=mysql.example.local \
BUDGET_MYSQL_DATABASE=budget \
BUDGET_MYSQL_USER=budget \
BUDGET_MYSQL_PASSWORD=... \
docker compose -f build/docker-compose.external-mysql.yml up --build
```

Dans ce mode, `BUDGET_MYSQL_CREATE_DATABASE` vaut `0` par défaut. Mets-le à `1` seulement si l'utilisateur root est fourni et peut créer la base.

## GitHub Actions

Le workflow `.github/workflows/docker-image.yml` construit et publie l'image Docker sur Docker Hub lors d'un push sur la branche `release`.

Image publiée:

```text
beegal/budget:latest
```

Secrets requis:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

## Import Personnal-Budget

Un utilitaire CLI permet de recréer la base et d'importer le classeur `Personnal-Budget`:

```bash
python3 budget_cli.py --create --import Personnal-Budget.xls
```

Par défaut, la base utilisée est `data/budget.sqlite3`. Pour tester dans une autre base:

```bash
python3 budget_cli.py --db /tmp/budget-test.sqlite3 --create --import Personnal-Budget.xlsx
```

Le flag `--create` recrée une base vide. L'import accepte directement `.xlsx`; si `Personnal-Budget.xls` est demandé mais que `Personnal-Budget.xlsx` existe, le fichier `.xlsx` est utilisé.

Les dates de début/fin sont inférées depuis le texte de période visible dans le classeur. Les transactions sont importées même si leur date tombe hors de cette plage; le CLI affiche ces incohérences en `Incohérence importée` sans les filtrer, puis logge séparément les lignes réellement non importables.

La feuille Excel `Budget` est ignorée par le CLI.

## Export/import complet

Le CLI peut exporter toute la base dans un classeur `.xlsx` simple, avec un onglet par table et un onglet `_meta`:

```bash
python3 budget_cli.py --export-full backup-budget.xlsx
```

Pour restaurer cet export dans une base vide:

```bash
python3 budget_cli.py --create --import-full backup-budget.xlsx
```

Les onglets exportés sont:

- `period`
- `accounts`
- `transaction_labels`
- `monthly_budget`
- `account_balances`
- `budget_schedule`
- `transactions`

L'import complet conserve les `id`, ce qui permet de reconstruire les relations entre périodes, comptes, soldes, budgets et transactions.
