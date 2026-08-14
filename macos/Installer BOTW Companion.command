#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
SOURCE="$SCRIPT_DIR/BOTW Companion.app"
DESTINATION_DIR="$HOME/Applications"
DESTINATION="$DESTINATION_DIR/BOTW Companion.app"

mkdir -p "$DESTINATION_DIR"
/usr/bin/ditto "$SOURCE" "$DESTINATION"
/bin/chmod +x "$DESTINATION/Contents/MacOS/BOTW Companion"
/usr/bin/open "$DESTINATION_DIR"
/usr/bin/osascript -e 'display notification "Glisse BOTW Companion dans le Dock, puis double-clique dessus pour ouvrir le site local." with title "Installation terminée"'

print "BOTW Companion a été installé dans :"
print "$DESTINATION"
print "Tu peux maintenant le faire glisser dans le Dock."