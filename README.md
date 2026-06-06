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
- consulter une synthèse globale multi-périodes par intitulé;
- créer automatiquement un onglet `Budget` par période à partir du budget mensuel;
- instancier une entrée planifiée du budget dans un compte réel;
- importer des transactions CSV dans un compte;
- filtrer les transactions par périodes, comptes et intitulés avec rafraîchissement réactif;
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

- `users`
- `period`
- `accounts`
- `transaction_labels`
- `transactions`
- `account_balances`
- `monthly_budget`
- `budget_schedule`

L'application ne dépend plus du fichier Excel initial.
Le schéma courant est créé directement pour les bases neuves. Une migration légère conserve les données existantes en ajoutant `user_id` aux tables métier.

## Utilisateurs

L'application est multi-user via FastAPI Users avec une authentification par cookie HTTP-only.

- `/register`: registration rapide par email et mot de passe;
- `/login`: connexion;
- `/logout`: suppression du cookie de session.
- `/admin`: interface réservée aux admins pour lister les utilisateurs, créer un utilisateur, changer un mot de passe, activer/désactiver un compte et attribuer/retirer le rôle admin.

Chaque table métier contient `user_id` et toutes les lectures/écritures filtrent sur l'utilisateur connecté. Les données historiques sans utilisateur sont marquées temporairement avec un identifiant legacy, puis adoptées par le premier utilisateur qui s'enregistre.

La table `users` contient aussi `last_login`, mis à jour quand un utilisateur authentifié accède à l'application.

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

Configuration auth:

```bash
BUDGET_AUTH_SECRET=change-me
BUDGET_AUTH_COOKIE_MAX_AGE=2592000
BUDGET_AUTH_COOKIE_SECURE=0
BUDGET_AUTH_LIFETIME=2592000
```

En production, `BUDGET_AUTH_SECRET` doit être une valeur longue et privée. Mets `BUDGET_AUTH_COOKIE_SECURE=1` derrière HTTPS.

Si `BUDGET_AUTH_SECRET` n'est pas défini, l'application génère un secret aléatoire non prédictible au démarrage. C'est plus sûr qu'une valeur par défaut hardcodée, mais les cookies existants deviennent invalides après un redémarrage. Pour conserver les sessions entre redémarrages, configure une valeur stable dans l'environnement.

Pour créer la base et l'utilisateur MySQL avec le CLI:

```bash
BUDGET_DB_BACKEND=mysql \
BUDGET_MYSQL_ROOT_USER=root \
BUDGET_MYSQL_ROOT_PASSWORD=... \
BUDGET_MYSQL_DATABASE=budget \
BUDGET_MYSQL_USER=budget \
BUDGET_MYSQL_PASSWORD=... \
python3 budget_cli.py --db-backend mysql db create
```

Pour lancer l'application sur MySQL:

```bash
BUDGET_DB_BACKEND=mysql \
BUDGET_MYSQL_HOST=127.0.0.1 \
BUDGET_MYSQL_PORT=3306 \
BUDGET_MYSQL_DATABASE=budget \
BUDGET_MYSQL_USER=budget \
BUDGET_MYSQL_PASSWORD=... \
python3 app.py
```

Avec un Docker local classique, `BUDGET_MYSQL_HOST=127.0.0.1` fonctionne si le port MySQL est publié sur l'hôte. Avec Docker via Minikube (`eval $(minikube docker-env)`), le port est publié sur la VM Minikube; utilise alors:

```bash
export BUDGET_MYSQL_HOST="$(minikube ip)"
```

La base MySQL est créée/ajustée avec `CHARACTER SET utf8mb4 COLLATE utf8mb4_bin`; les tables héritent de ce défaut. Le schéma ne force pas le moteur des tables et laisse MySQL utiliser son moteur par défaut, InnoDB. Cela reste compatible avec SQLite: deux noms qui diffèrent seulement par la casse, par exemple `CASH` et `Cash`, restent distincts.

## Pages principales

- `/`: liste les périodes et permet d'en créer.
- `/parameters`: gère les comptes, les intitulés et le budget mensuel.
- `/period/<id>`: affiche une période avec synthèse, onglet `Budget`, puis les comptes visibles.
- `/period/<id>/import?account=<id>`: importe des transactions CSV pour un compte.
- `/transactions`: affiche une vue filtrable des transactions.
- `/summary`: affiche une synthèse globale multi-périodes des entrées/sorties par intitulé.

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
- le groupage des intitulés se fait sur la partie avant le séparateur `-`; les placeholders le rappellent dans les champs concernés.

Dans les transactions globales:

- les périodes et comptes utilisent un sélecteur à tags avec dropdown à checkboxes;
- une sélection vide signifie toutes les périodes ou tous les comptes;
- les sélections sont appliquées quand le dropdown est fermé, ce qui permet de cocher plusieurs valeurs sans refresh intermédiaire;
- le filtre d'intitulé utilise le même dropdown que les transactions de compte;
- changer compte ou intitulé rafraîchit la table;
- la ligne de total affiche débit, crédit et total net.

Dans la synthèse globale:

- les périodes utilisent le même sélecteur à tags que les transactions;
- cliquer sur un intitulé ouvre `/transactions` avec les périodes et l'intitulé préfiltrés.

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
- ajout d'une migration de schéma pour isoler les données par utilisateur;
- ajout d'un build Docker Alpine Python et d'un workflow GitHub Actions;
- ajout d'une page Synthèse globale;
- ajout de filtres réactifs multi-périodes/multi-comptes dans Transactions;
- ajout de la création inline d'utilisateurs dans l'administration;
- secret d'authentification aléatoire au démarrage si `BUDGET_AUTH_SECRET` est absent.

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
│   ├── admin.py
│   ├── api.py
│   ├── filters.py
│   ├── imports.py
│   ├── parameters.py
│   ├── period.py
│   ├── periods.py
│   ├── static_files.py
│   ├── summary.py
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
    ├── summary.html
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
python3 budget_cli.py db create
python3 budget_cli.py workbook import Personnal-Budget.xls --user user@example.com
```

Par défaut, la base utilisée est `data/budget.sqlite3`. Pour tester dans une autre base:

```bash
python3 budget_cli.py --db /tmp/budget-test.sqlite3 db create
python3 budget_cli.py --db /tmp/budget-test.sqlite3 users create user@example.com
python3 budget_cli.py --db /tmp/budget-test.sqlite3 workbook import Personnal-Budget.xlsx --user user@example.com
```

La commande `db create` recrée une base vide. L'import accepte directement `.xlsx`; si `Personnal-Budget.xls` est demandé mais que `Personnal-Budget.xlsx` existe, le fichier `.xlsx` est utilisé. L'option `--user` cible l'utilisateur de destination par email ou UUID. Si cet utilisateur ne contient que les données initiales vides, elles sont retirées avant l'import.

Les dates de début/fin sont inférées depuis le texte de période visible dans le classeur. Les transactions sont importées même si leur date tombe hors de cette plage; le CLI affiche ces incohérences en `Incohérence importée` sans les filtrer, puis logge séparément les lignes réellement non importables.

La feuille Excel `Budget` est ignorée par le CLI.

Les comptes et intitulés importés sont normalisés en casse titre pour éviter les doublons de saisie (`CASH`, `cash` et `Cash` deviennent `Cash`): première lettre en majuscule, le reste en minuscule.

## Export/import complet

Le CLI peut exporter toute la base dans un classeur `.xlsx` simple, avec un onglet par table et un onglet `_meta`:

```bash
python3 budget_cli.py export full backup-budget.xlsx
```

Pour restaurer cet export dans une base vide:

```bash
python3 budget_cli.py db create
python3 budget_cli.py import full backup-budget.xlsx
```

Les onglets exportés sont:

- `users`
- `period`
- `accounts`
- `transaction_labels`
- `monthly_budget`
- `account_balances`
- `budget_schedule`
- `transactions`

L'import complet conserve les `id` et les `user_id`, ce qui permet de reconstruire les relations entre utilisateurs, périodes, comptes, soldes, budgets et transactions.

## Migration SQLite vers MySQL

Exemple avec un MySQL Docker de test:

```bash
eval "$(minikube docker-env)" # seulement si tu utilises le Docker de Minikube
docker run --name budget-mysql-test \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=budget_test \
  -e MYSQL_USER=budget \
  -e MYSQL_PASSWORD=budgetpass \
  -p 3307:3306 \
  -d mysql:8.0
```

Si Docker est local:

```bash
export BUDGET_MYSQL_HOST=127.0.0.1
```

Si Docker pointe vers Minikube:

```bash
export BUDGET_MYSQL_HOST="$(minikube ip)"
```

Puis:

```bash
export BUDGET_MYSQL_PORT=3307
export BUDGET_MYSQL_DATABASE=budget_test
export BUDGET_MYSQL_USER=budget
export BUDGET_MYSQL_PASSWORD=budgetpass
export BUDGET_MYSQL_ROOT_USER=root
export BUDGET_MYSQL_ROOT_PASSWORD=rootpass

cp data/budget.sqlite3 /tmp/budget-source.sqlite3
python3 budget_cli.py --db /tmp/budget-source.sqlite3 export full /tmp/budget-full.xlsx
python3 budget_cli.py --db-backend mysql db create
python3 budget_cli.py --db-backend mysql import full /tmp/budget-full.xlsx
python3 budget_cli.py --db-backend mysql export full /tmp/budget-mysql-check.xlsx
```

La dernière commande permet de réexporter MySQL et de comparer les onglets avec l'export source si nécessaire.

## Export/import utilisateur

Depuis l'écran `Paramètres`, un utilisateur connecté peut exporter ses propres données dans un `.xlsx`, puis les réimporter plus tard. Cet import remplace uniquement ses données métier; il ne touche pas aux autres utilisateurs ni aux comptes d'authentification.

Le CLI expose la même fonction pour un utilisateur donné, identifié par email ou UUID:

```bash
python3 budget_cli.py export user user@example.com budget-user.xlsx
python3 budget_cli.py import user user@example.com budget-user.xlsx
```

Contrairement à `export full`, cet export ne contient pas la table `users` et ne conserve pas les `user_id`; à l'import, les périodes et comptes sont recréés pour l'utilisateur cible.

## Administration CLI

Le CLI est basé sur Typer et Rich. Il peut administrer les utilisateurs avec une aide moderne et des tables lisibles:

```bash
python3 budget_cli.py users list
python3 budget_cli.py users create user@example.com --password Password123!
python3 budget_cli.py users set-password user@example.com --password NewPassword123!
python3 budget_cli.py users enable user@example.com
python3 budget_cli.py users disable user@example.com
python3 budget_cli.py users make-admin user@example.com
python3 budget_cli.py users revoke-admin user@example.com
```

`users list` affiche une table ASCII avec l'UUID, l'email, la dernière connexion, le nombre de comptes, le nombre de transactions, le statut actif/inactif et le rôle admin.
