# Confidentialité

BOTW Companion fonctionne localement et ne contient ni compte, ni publicité, ni
télémétrie, ni outil d'analyse d'audience.

## Données lues

L'application cherche les sauvegardes locales de Ryujinx ou Cemu, puis lit le
slot BOTW sélectionné et sa vignette. Le moteur gyroscopique lit les capteurs de
la manette choisie uniquement lorsqu'il est activé.

## Données écrites

Le suivi manuel, les itinéraires, les préférences et les journaux restent dans :

* Windows : `%LOCALAPPDATA%\BOTW Companion\` ;
* macOS : `~/Library/Application Support/BOTW Companion/`.

La désinstallation conserve volontairement ce dossier. Pour effacer toutes les
données du Companion, fermer l'application puis supprimer manuellement ce
dossier. Cette suppression ne touche pas aux sauvegardes de l'émulateur.

## Réseau

Le serveur écoute uniquement sur `127.0.0.1`. L'analyse de la sauvegarde, la
carte, les guides et le suivi ne déclenchent aucune requête Internet. Une
connexion n'est utilisée que si l'utilisateur ouvre lui-même un lien externe.
Le téléchargement initial et les mises à jour passent par GitHub Releases, en
dehors de l'application.
