# Publier une version

Trois fichiers sont à modifier pour préparer une version :

1. `botw_companion/VERSION`, qui contient la version unique du projet ;
2. `RELEASE_NOTES.md`, qui décrit clairement les changements pour les joueurs ;
3. `CHANGELOG.md`, où la section **À venir** est déplacée sous la nouvelle
   version avec la date au format `AAAA-MM-JJ`.

Les formats acceptés sont `X.Y.Z`, `X.Y.Z-alpha.N`, `X.Y.Z-beta.N` et `X.Y.Z-rc.N`. Les versions Python, Windows et macOS, les noms des installateurs et le titre GitHub sont tous calculés à partir de cette valeur.

Après le commit et le push, les jobs Windows et macOS exécutent les tests sans construire ni publier d’installateur. Pour valider aussi les deux paquets avant le tag, lancer manuellement le workflow avec l’option **Construire et tester les installateurs** ; cette vérification ne publie rien. Lorsque tout est vert, créer puis pousser le tag correspondant.

Avant le commit, lancer l'audit local :

```bash
python tools/audit_distribution.py
python tools/check_version_consistency.py
python -m unittest discover -s tests
```

Créer ensuite le tag :

```bash
git tag -a vX.Y.Z-alpha.N -m "BOTW Companion X.Y.Z alpha N"
git push origin vX.Y.Z-alpha.N
```

Le tag déclenche la construction native, les tests d’installation propre et de mise à niveau, puis la publication. Une version alpha, beta ou RC est marquée comme préversion. Une version sans suffixe, comme `v1.0.0`, est publiée comme version stable et devient la version la plus récente.

La release contient uniquement l’installateur Windows et le DMG Apple Silicon, en plus des archives de code source ajoutées automatiquement par GitHub.

Tout ajout ou changement de runtime, bibliothèque native, source de données,
image, police ou outil inclus impose de mettre à jour les avis, le dossier
`licenses/` et l'audit avant de créer le tag.

Après la publication, vérifier le titre, le statut préversion/stable, les deux
installateurs et les liens du journal des versions. Un tag publié ne doit pas
être déplacé : toute correction passe par une nouvelle version.
