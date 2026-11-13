#!/bin/bash
# Installation de Rawi sur macOS 12 (Monterey), Mac Intel.
# Réutilise un conda existant (Miniforge, Miniconda…) ; sinon installe Miniforge.
# Les paquets viennent uniquement de conda-forge (pas du canal « defaults » d'Anaconda).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

if command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base)"
  echo "→ conda trouvé : $CONDA_BASE"
else
  CONDA_BASE="$HOME/miniforge3"
  if [ ! -x "$CONDA_BASE/bin/conda" ]; then
    echo "→ Téléchargement de Miniforge (Python open source)…"
    curl -L -o /tmp/miniforge.sh \
      https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-x86_64.sh
    bash /tmp/miniforge.sh -b -p "$CONDA_BASE"
  fi
fi
source "$CONDA_BASE/etc/profile.d/conda.sh"

if conda env list | grep -qE '^rawi[[:space:]]'; then
  echo "→ L'environnement « rawi » existe déjà."
else
  echo "→ Création de l'environnement « rawi » (Python, OpenCV, FFmpeg, lecture des PDF)…"
  conda create -y -n rawi --override-channels -c conda-forge python=3.11 numpy opencv ffmpeg pypdfium2
fi
conda activate rawi
conda install -y -q -n rawi --override-channels -c conda-forge pypdfium2  # ajouté après la v0.1
pip install --no-deps -e "$DIR"

echo
echo "✅ Installation terminée."
echo "   À chaque nouvelle session du Terminal :"
echo "     source \"$CONDA_BASE/etc/profile.d/conda.sh\" && conda activate rawi"
echo "   Puis par exemple :"
echo "     rawi auto pages/*.jpg --apercu"
