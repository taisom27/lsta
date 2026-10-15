#!/bin/bash
# Bloquea cualquier intento de instalar el plugin claude-mem (thedotmack). Decisión del usuario.
cmd=$(jq -r '.tool_input.command // ""')
if printf '%s' "$cmd" | grep -qiE 'claude-mem|thedotmack|cmem\.ai'; then
  if printf '%s' "$cmd" | grep -qiE 'install|marketplace +add|npx|bunx|npm +(i|add)|bun +add|git +clone|curl|wget|enable'; then
    jq -n '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:"Bloqueado: el usuario prohibió instalar claude-mem (ver CLAUDE.md)."}}'
  fi
fi
exit 0
