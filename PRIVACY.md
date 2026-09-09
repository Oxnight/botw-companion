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
carte, les guides et le suivi ne sont jamais envoyés sur Internet.

Au démarrage, l'application peut consulter la liste publique des Releases de
`github.com/Oxnight/botw-companion`. Cette requête ne contient ni sauvegarde,
ni progression, ni préférence personnelle. Elle expire rapidement si la
connexion est absente et n'empêche aucune fonction hors ligne. Une nouvelle
tentative peut être demandée avec **Vérifier les mises à jour**.

Le téléchargement ne commence qu'après un clic de l'utilisateur et cible
directement le Setup Windows ou le DMG Apple Silicon publié sur GitHub.
