# Distribution macOS

La version macOS cible uniquement les Mac Apple Silicon sous macOS 14 ou plus récent.

Les joueurs téléchargent `BOTW_Companion_0.40.0-alpha.24_macOS_arm64.dmg`, ouvrent l’image disque et glissent **BOTW Companion** dans **Applications**. Le paquet contient Python, toutes les ressources hors ligne, JoyConDSU arm64 et `libSDL3.0.dylib`. Il ne dépend ni du clone, ni de `.venv`, Homebrew ou Xcode.

## Construction

La construction officielle s’exécute sur un runner GitHub Actions Apple Silicon :

```bash
./tools/build_macos_app.sh
./tools/test_macos_installation.sh
```

Le premier script compile JoyConDSU et SDL3 pour arm64, construit l’application PyInstaller, applique une signature ad hoc puis crée le DMG. Le second monte le DMG, copie l’application comme le ferait un joueur, vérifie les architectures et dépendances, lance l’auto-test, JoyConDSU et le serveur avec un `PATH` sans outil de développement.

Cette alpha n’est ni Developer ID signée ni notariée. Au premier lancement, macOS peut demander d’autoriser l’application dans **Réglages Système > Confidentialité et sécurité > Ouvrir quand même**.
