# Contribuer à BOTW Companion

Les corrections, tests, améliorations de documentation et retours sur des
sauvegardes réelles sont bienvenus.

## Avant de commencer

- Rechercher d'abord si une issue traite déjà du même problème.
- Utiliser une issue distincte par problème et fournir des étapes de
  reproduction minimales.
- Ne jamais joindre une sauvegarde personnelle, un journal contenant un chemin
  privé ou une donnée provenant du jeu. Préférer un exemple synthétique.
- Signaler une vulnérabilité selon [`SECURITY.md`](SECURITY.md), jamais dans une
  issue publique.
- Pour un changement important, ouvrir une issue avant d'écrire beaucoup de
  code afin de valider le périmètre.

## Préparer le projet

Les prérequis, commandes et constructions natives se trouvent dans le
[guide de développement](docs/DEVELOPMENT.md).

Créer une branche courte depuis `master` :

```bash
git switch -c type/description-courte
```

Exemples : `fix/detection-cemu`, `docs/installation-windows` ou
`test/sauvegarde-dlc`.

## Règles de modification

- Ne pas modifier `botw_companion/VERSION` ni `RELEASE_NOTES.md` dans une pull
  request ordinaire : ces fichiers sont préparés au moment d'une release.
- Ajouter ou adapter les tests avec tout changement de comportement.
- Ne pas ajouter de dépendance d'exécution sans expliquer son utilité et mettre
  à jour les licences et `THIRD_PARTY_NOTICES.md`.
- Garder toutes les fonctions principales utilisables hors ligne.
- Ne pas committer de dossier `build`, `dist`, `.venv`, `node_modules`, de
  sauvegarde, de journal ou d'archive locale.
- Conserver les données utilisateur hors du dossier de l'application.
- Mettre à jour le présent journal lorsqu'un changement est notable pour les
  joueurs, sous la section **À venir** de `CHANGELOG.md`.

## Vérifier la contribution

Contrôles rapides obligatoires :

```bash
python3 tools/audit_distribution.py
python3 tools/check_version_consistency.py
python3 -m unittest discover -s tests
```

Pour une modification de l'interface, exécuter également les parcours décrits
dans le [guide de développement](docs/DEVELOPMENT.md#tests-navigateur).

Une modification Windows doit rester compatible Windows 10/11 x64. Une
modification macOS doit cibler macOS 14 ou ultérieur sur Apple Silicon. Les
installateurs natifs sont construits et testés par le workflow GitHub.

## Pull request

La description doit expliquer le problème, la solution et les vérifications
effectuées. Avant l'envoi, contrôler que :

- les tests passent ;
- aucun fichier généré ou personnel n'est présent ;
- la documentation correspond au comportement réel ;
- les changements Windows et macOS ont été envisagés ;
- les licences ont été vérifiées si une ressource ou un outil a été ajouté.

En proposant une contribution, son auteur confirme avoir le droit de la fournir
au projet sous la licence MIT présente dans [`LICENSE`](LICENSE).
