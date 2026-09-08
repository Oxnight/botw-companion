# Dépannage

Commencer par vérifier que BOTW Companion et l'installateur proviennent de la
page [Releases officielle](https://github.com/Oxnight/botw-companion/releases).

## L'application ne s'ouvre pas

### Windows

- Relancer BOTW Companion depuis le menu Démarrer.
- Si SmartScreen apparaît, vérifier la provenance du fichier avant de choisir
  **Informations complémentaires**.
- Consulter `%LOCALAPPDATA%\BOTW Companion\launcher.log`.
- Réinstaller la même version par-dessus l'installation existante. Cette
  opération ne supprime pas les données personnelles.

### macOS

- Vérifier que l'application se trouve dans Applications et non dans le DMG.
- Après le premier blocage, ouvrir **Réglages Système > Confidentialité et
  sécurité** et utiliser **Ouvrir quand même**.
- Consulter `~/Library/Application Support/BOTW Companion/launcher.log`.
- Remplacer l'application par une nouvelle copie issue du DMG.

## L'interface ne s'affiche pas

L'interface utilise normalement `http://127.0.0.1:8765`. Un double lancement
réutilise le serveur déjà ouvert. Si le navigateur n'apparaît pas :

1. ouvrir manuellement cette adresse ;
2. fermer toute ancienne instance de BOTW Companion ;
3. relancer l'application ;
4. vérifier `launcher.log` si le port est occupé ou si le serveur s'arrête.

Ne pas exposer ce port sur le réseau et ne pas remplacer `127.0.0.1` par une
adresse distante.

## Aucune sauvegarde détectée

1. Lancer BOTW dans Ryujinx ou Cemu et créer une sauvegarde récente.
2. Vérifier que l'émulateur utilise bien son dossier habituel ou un emplacement
   portable accessible au compte courant.
3. Dans Ryujinx, utiliser l'action permettant d'ouvrir le dossier de sauvegarde
   utilisateur du jeu pour confirmer qu'il existe.
4. Pour Cemu, vérifier le `mlc_path` défini dans `settings.xml` lorsqu'un chemin
   personnalisé est utilisé.

Un clone de développement peut imposer un chemin en le passant à la commande
`interface`. L'application installée conserve la détection automatique afin
d'éviter d'enregistrer un chemin de sauvegarde fragile.

## La progression semble ancienne

- Effectuer une sauvegarde dans le jeu, pas seulement un état instantané de
  l'émulateur.
- Vérifier le slot, le mode normal/Expert, l'émulateur et le chemin affichés
  dans l'aperçu de la sauvegarde.
- Si plusieurs émulateurs sont installés, la source la plus récente et valide
  est sélectionnée.
- Ne pas modifier directement les fichiers `.sav`.

## Le gyroscope ne fonctionne pas

- Vérifier que la source choisie affiche bien gyroscope **et** accéléromètre.
- Laisser la manette immobile jusqu'à la fin de la calibration.
- Utiliser exactement `127.0.0.1` et `26760` dans l'émulateur.
- Fermer les autres serveurs DSU susceptibles d'occuper le port 26760, par
  exemple une autre instance ou un outil de manette.
- Reconnecter la manette en USB ou Bluetooth puis actualiser les sources.
- Vérifier le diagnostic et le fichier `joycon-dsu.log` indiqué par l'interface.

Un contrôleur reconnu pour ses boutons n'expose pas nécessairement ses capteurs
à SDL3. Dans ce cas, le Companion ne doit pas le présenter comme une source de
mouvement compatible.

## Préparer un rapport de bug

Indiquer :

- la version exacte de BOTW Companion ;
- Windows ou macOS et sa version ;
- Ryujinx ou Cemu ;
- les étapes permettant de reproduire le problème ;
- le message affiché et les dernières lignes pertinentes du journal.

Retirer le nom d'utilisateur et les chemins personnels. Ne jamais publier une
sauvegarde ou un rapport de vulnérabilité. Les problèmes de sécurité suivent
[`SECURITY.md`](../SECURITY.md).
