# Développer BOTW Companion

Ce guide concerne le clone Git. Les joueurs doivent utiliser les installateurs
décrits dans [`INSTALLATION.md`](INSTALLATION.md).

## Prérequis communs

- Git ;
- Python 3.10 ou ultérieur, Python 3.12 recommandé ;
- Node.js et npm uniquement pour les tests navigateur.

Cloner le projet :

```bash
git clone https://github.com/Oxnight/botw-companion.git
cd botw-companion
```

Créer l'environnement avec `uv` :

```bash
uv sync
```

Ou avec Python :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

Sous Windows PowerShell :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

## Lancer depuis les sources

```bash
.venv/bin/python -m botw_companion interface
```

Avec une sauvegarde précise :

```bash
.venv/bin/python -m botw_companion interface "/chemin/vers/le/slot"
```

Commandes disponibles :

```bash
.venv/bin/python -m botw_companion analyse
.venv/bin/python -m botw_companion reste --categorie sanctuaires
.venv/bin/python -m botw_companion surveille --intervalle 3
.venv/bin/python -m botw_companion --help
```

## Tests Python et audits

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python tools/audit_distribution.py
.venv/bin/python tools/check_version_consistency.py
```

Les tests utilisent des données synthétiques. Aucune sauvegarde personnelle ne
doit être ajoutée au dépôt.

## Tests navigateur

```bash
npm ci --ignore-scripts
npx playwright install chromium firefox webkit
python3 tools/browser_test_server.py --port 18765
```

Dans un autre terminal :

```bash
node tools/browser_smoke.js http://127.0.0.1:18765 chromium
node tools/browser_smoke.js http://127.0.0.1:18765 firefox
node tools/browser_smoke.js http://127.0.0.1:18765 webkit
```

Sous Windows, le script `tools/run_browser_smoke.ps1` utilise Chrome, Edge et
Firefox installés ou préparés par le workflow. L'audit axe-core couvre les
critères WCAG automatisables ; une vérification humaine reste nécessaire.

## Construction Windows x64

Installer Visual Studio 2022 Build Tools avec C++ et CMake, Python 3.12 x64 et
Inno Setup 6, puis lancer :

```powershell
.\tools\build_windows_app.ps1
```

Le script compile JoyConDSU et SDL3, construit l'application PyInstaller,
exécute son auto-test et crée le `Setup.exe` dans `dist\installer`.

## Construction macOS Apple Silicon

La construction nécessite un Mac Apple Silicon, macOS 14 ou ultérieur, les
Command Line Tools Xcode, CMake et Python 3.12 arm64 :

```bash
xcode-select --install
brew install cmake
./tools/build_macos_app.sh
```

Le script compile JoyConDSU et SDL3 en arm64, vérifie les dépendances Mach-O,
signe l'application localement et crée le DMG dans `dist/`.

## Données générées

Les fichiers compilés du dossier `botw_companion/data` accélèrent le démarrage
hors ligne et font partie du produit. Lorsqu'une source de données change,
utiliser le script `tools/build_*.py` correspondant, vérifier le diff et lancer
tous les tests avant de committer le résultat.

Toute nouvelle bibliothèque, police, image ou source de données doit également
être déclarée dans `THIRD_PARTY_NOTICES.md`, `DATA_SOURCES.md` ou `licenses/`
selon le cas, puis ajoutée à `tools/audit_distribution.py`.

## Publier une version

Seul le mainteneur prépare une version. La procédure complète se trouve dans
[`RELEASING.md`](../RELEASING.md).
