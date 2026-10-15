#!/bin/bash
# Instala las dependencias del agente de pisos en las sesiones de Claude Code en la nube.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt -r requirements-dev.txt
echo "export PYTHONPATH=\"${CLAUDE_PROJECT_DIR}\${PYTHONPATH:+:\$PYTHONPATH}\"" >> "$CLAUDE_ENV_FILE"
