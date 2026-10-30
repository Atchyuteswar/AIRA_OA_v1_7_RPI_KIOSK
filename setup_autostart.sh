#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/aira-oa.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=AIRA-OA
Comment=AIRA-OA v1.4 Raspberry Pi screening console
Exec=$ROOT/start_rpi.sh
Path=$ROOT
Terminal=false
X-GNOME-Autostart-enabled=true
DESKTOP

echo "Autostart installed: $HOME/.config/autostart/aira-oa.desktop"
echo "AIRA-OA will launch after the Raspberry Pi desktop session starts."
