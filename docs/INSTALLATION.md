# Installer et mettre à jour BOTW Companion

Les joueurs doivent utiliser les fichiers publiés sur la page
[Releases](https://github.com/Oxnight/botw-companion/releases). Aucun clone du
dépôt et aucun environnement de développement ne sont nécessaires.

## Compatibilité

| Système | Paquet | Configuration prise en charge |
| --- | --- | --- |
| Windows | `_Setup.exe` | Windows 10 version 1809 ou ultérieure, Windows 11, processeur x64 |
| macOS | `_macOS_arm64.dmg` | macOS 14 ou ultérieur, Mac Apple Silicon uniquement |

Les paquets incluent le runtime Python, les données hors ligne, la carte,
JoyConDSU, SDL3, les licences, les icônes et le lanceur. Python, Git, Node.js,
CMake, Homebrew, Xcode, Visual Studio et PyCharm ne sont pas nécessaires.

## Windows

1. Télécharger le fichier se terminant par `_Setup.exe`.
2. Lancer l'installateur et conserver l'option de raccourci Bureau si souhaité.
3. Ouvrir **BOTW Companion** depuis le Bureau ou le menu Démarrer.

L'installation se fait sans privilèges administrateur dans :

```text
%LOCALAPPDATA%\Programs\BOTW Companion
```

La préversion n'est pas signée avec un certificat commercial. SmartScreen peut
afficher un avertissement : vérifier que le fichier vient bien de
`github.com/Oxnight/botw-companion/releases` avant de choisir les informations
complémentaires permettant de l'exécuter.

## macOS Apple Silicon

1. Télécharger le fichier se terminant par `_macOS_arm64.dmg`.
2. Ouvrir le DMG.
3. Glisser **BOTW Companion** dans le raccourci **Applications** affiché dans la
   fenêtre.
4. Lancer l'application depuis Applications.

La préversion utilise une signature ad hoc et n'est pas notariée. Si macOS la
bloque, tenter une première ouverture, puis utiliser **Réglages Système >
Confidentialité et sécurité > Ouvrir quand même** après avoir vérifié la
provenance du DMG.

## Premier lancement

Le lanceur ouvre l'interface locale dans le navigateur. Le guide initial
confirme la sauvegarde détectée et présente le gyroscope facultatif. Le bouton
**Aide** permet de rouvrir ce guide.

Si aucune sauvegarde n'est détectée, consulter le
[guide de dépannage](TROUBLESHOOTING.md#aucune-sauvegarde-détectée).

## Mise à jour

BOTW Companion consulte brièvement les Releases GitHub au démarrage. Si une
version plus récente et compatible est publiée, un bandeau propose directement
le bon paquet. Le bouton **Vérifier les mises à jour** permet de recommencer la
vérification manuellement.

Sans connexion, cette vérification expire rapidement et silencieusement :
l'analyse, la carte, les guides, le suivi et le gyroscope restent entièrement
fonctionnels hors ligne. Aucun téléchargement ne démarre sans clic.

Installer ensuite le nouveau paquet par-dessus la version existante :

- sous Windows, relancer le nouveau `Setup.exe` ;
- sous macOS, remplacer l'application présente dans Applications par celle du
  nouveau DMG.

Il n'est pas nécessaire de désinstaller la version précédente. Il reste aussi
possible de télécharger manuellement le paquet depuis Releases.

Le suivi manuel, les itinéraires, les préférences et les sauvegardes de sécurité
restent dans un dossier utilisateur séparé :

```text
Windows : %LOCALAPPDATA%\BOTW Companion
macOS   : ~/Library/Application Support/BOTW Companion
```

Le workflow teste automatiquement une installation propre et une mise à niveau
depuis la version de référence avant toute publication.

## Désinstallation

- Windows : utiliser **Applications installées > BOTW Companion >
  Désinstaller**.
- macOS : déplacer **BOTW Companion.app** de Applications vers la Corbeille.

Les données personnelles sont volontairement conservées. Elles peuvent être
supprimées séparément dans le dossier indiqué ci-dessus après avoir réalisé un
export si elles doivent être gardées.
