#!/bin/bash
# Installation de bdanim sur macOS 12 (Monterey), Mac Intel.
# Utilise Miniforge (conda-forge) : fonctionne sur les anciens macOS, sans Homebrew.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
MF="$HOME/miniforge3"

if [ ! -x "$MF/bin/conda" ]; then
  echo "→ Téléchargement de Miniforge (Python open source)…"
  curl -L -o /tmp/miniforge.sh \
    https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-x86_64.sh
  bash /tmp/miniforge.sh -b -p "$MF"
fi
source "$MF/bin/activate"

echo "→ Création de l'environnement « bdanim » (Python, OpenCV, FFmpeg)…"
conda create -y -n bdanim -c conda-forge python=3.11 numpy opencv ffmpeg
conda activate bdanim
pip install --no-deps -e "$DIR"

echo
echo "✅ Installation terminée."
echo "   À chaque nouvelle session du Terminal :"
echo "     source ~/miniforge3/bin/activate && conda activate bdanim"
echo "   Puis par exemple :"
echo "     bdanim auto pages/*.jpg --apercu"
