# Validation Windows

Le job Windows du workflow `.github/workflows/release.yml` exécute :

1. les tests Python et les contrôles de version ;
2. le parcours fonctionnel dans Chrome, Edge et Firefox ;
3. la compilation native de JoyConDSU avec SDL3 ;
4. la création PyInstaller et Inno Setup ;
5. une installation silencieuse réelle dans un dossier propre ;
6. l’auto-test du paquet, le démarrage du serveur sans Python dans le `PATH`, puis la désinstallation.

Les commits et pull requests exécutent uniquement les tests. Un tag `v*` construit une release seulement si les jobs Windows et macOS réussissent. Le workflow installe d’abord la version définie dans `packaging/UPGRADE_BASELINE`, applique la mise à niveau et vérifie les raccourcis ainsi que les données persistantes. Une validation matérielle sur Windows 10/11 reste recommandée pour les Joy-Con et l’intégration avec les émulateurs.
