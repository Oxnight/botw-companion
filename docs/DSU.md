# Configurer le gyroscope DSU

BOTW Companion intègre un serveur compatible avec le protocole
Cemuhook/DSU. Il transmet localement les capteurs d'une manette compatible vers
Ryujinx ou Cemu sur `127.0.0.1:26760`.

## Manettes

Le moteur utilise SDL3 et n'affiche comme activables que les sources fournissant
à la fois un gyroscope et un accéléromètre. Une paire de Joy-Con est regroupée
comme une seule source en mode grip. La détection réelle dépend du matériel, de
sa connexion et de sa prise en charge par SDL3 sur le système utilisé.

## Dans BOTW Companion

1. Connecter la manette en Bluetooth ou en USB.
2. Ouvrir la section **Gyroscope universel**.
3. Choisir la source proposée.
4. Cliquer sur **Activer**.
5. Laisser la manette immobile pendant la calibration.
6. Attendre l'état **Gyroscope prêt**.

Le diagnostic affiche notamment la cadence, le jitter, l'âge des échantillons,
la qualité de la calibration, les anomalies et l'état réseau.

## Dans l'émulateur

Configurer une source de mouvement Cemuhook/DSU avec :

```text
Hôte : 127.0.0.1
Port : 26760
Slot : 1
```

Les noms exacts des menus changent selon la version de l'émulateur. Dans Cemu,
la source se trouve dans les paramètres d'entrée ou de mouvement du Wii U
GamePad. Dans les versions de Ryujinx qui acceptent Cemuhook, elle se trouve
dans la configuration du mouvement de la manette.

Le serveur transporte uniquement le mouvement. Les boutons et sticks restent
configurés normalement dans l'émulateur.

## Arrêt et données locales

Le moteur DSU est désactivé par défaut et ne démarre qu'après une action dans
l'interface. Son journal est enregistré sous `joycon-dsu.log` dans le dossier
de données de BOTW Companion. L'interface indique son chemin exact.

En cas de problème de détection ou de port, suivre la section
[Dépannage du gyroscope](TROUBLESHOOTING.md#le-gyroscope-ne-fonctionne-pas).
