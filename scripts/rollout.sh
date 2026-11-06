#!/bin/sh
# Put agent-email on the other machines: copy the grants and config, bring the Google CLI and Herdr up to what this
# machine has, install everything from the public repo, and point the gws commands at it. Safe to run again.
# Usage: scripts/rollout.sh <name=ssh-route> ...   Each name is the machine's fixed name, such as studio=me@studio.
set -u
grants=$(python3 -c 'import json,os;print(os.path.expanduser(json.load(open(os.path.expanduser("~/.agent-email/config.json")))["grants_dir"]))')
real_gws=$(python3 -c 'import json,os;print(os.path.realpath(json.load(open(os.path.expanduser("~/.agent-email/machine.json")))["gws_bin"]))')
herdr_bin=$(command -v herdr)
here=$(uname -sm)
want=$("$real_gws" --version | head -1)
ssh_opts="-o BatchMode=yes -o ConnectTimeout=10"
tools='PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"; for d in "$HOME"/.nvm/versions/node/*/bin; do [ -d "$d" ] && PATH="$PATH:$d"; done'
fail=0

for pair in "$@"; do
  name=${pair%%=*}; route=${pair#*=}
  echo "== $name ($route)"
  ssh $ssh_opts "$route" true || { echo "unreachable"; fail=1; continue; }
  remote_grants=$(python3 -c "import os,sys;print(sys.argv[1].replace(os.path.expanduser('~') + '/', '', 1))" "$grants")
  there=$(ssh $ssh_opts "$route" 'uname -sm')

  # Logins and config.
  ssh $ssh_opts "$route" "mkdir -p ~/$remote_grants ~/.agent-email ~/.local/bin ~/.local/share/agent-email && chmod 700 ~/$remote_grants ~/.agent-email" || { fail=1; continue; }
  rsync -a -e "ssh $ssh_opts" --include='gws-*-credentials.json' --exclude='*' "$grants/" "$route:$remote_grants/" || { echo "grants failed"; fail=1; continue; }
  rsync -a -e "ssh $ssh_opts" "$HOME/.agent-email/config.json" "$route:.agent-email/config.json" || { fail=1; continue; }

  # The Google CLI, unless this machine already has the right version. An older one lacks what the commands use.
  gws_bin=$(ssh $ssh_opts "$route" "$tools"'; python3 - <<PY 2>/dev/null
import json, os
p = os.path.expanduser("~/.agent-email/machine.json")
print(json.load(open(p))["gws_bin"] if os.path.exists(p) else "")
PY')
  if [ -z "$gws_bin" ]; then
    gws_bin=$(ssh $ssh_opts "$route" "$tools"'; for c in /opt/homebrew/bin/gws /usr/local/bin/gws "$HOME"/.nvm/versions/node/*/bin/gws; do [ -x "$c" ] && echo "$c"; done' | while read -r c; do
      [ "$(ssh $ssh_opts "$route" "\"$c\" --version 2>/dev/null | head -1" </dev/null)" = "$want" ] && { echo "$c"; break; }
    done)
    if [ -z "$gws_bin" ] && [ "$there" = "$here" ]; then
      scp -q $ssh_opts "$real_gws" "$route:.local/share/agent-email/gws-real" && gws_bin=".local/share/agent-email/gws-real" && echo "Google CLI copied"
      gws_bin="\$HOME/$gws_bin"
    fi
    [ -n "$gws_bin" ] || { echo "no usable Google CLI"; fail=1; continue; }
  fi

  # Herdr, needed to reach and resume sessions.
  if ! ssh $ssh_opts "$route" "$tools"'; command -v herdr >/dev/null'; then
    if [ "$there" = "$here" ]; then
      scp -q $ssh_opts "$herdr_bin" "$route:.local/bin/herdr" && echo "Herdr copied"
    else
      echo "no Herdr, and it can't be copied from here"; fail=1; continue
    fi
  fi

  # Everything else, from the public repo.
  ssh $ssh_opts "$route" "$tools"'
    mkdir -p "$HOME/workspace" && cd "$HOME/workspace" || exit 1
    if [ -d agent-email/.git ]; then git -C agent-email pull -q --ff-only || exit 1; else git clone -q https://github.com/aelaguiz/agent-email.git || exit 1; fi
    cd agent-email || exit 1
    make install MACHINE='"$name"' GWS_BIN="'"$gws_bin"'" && make links || exit 1
    # Homebrew or Node may come first in login shells, and bare gws has to reach this script.
    line="export PATH=\"\$HOME/.local/bin:\$PATH\"  # agent-email: the gws command before any raw one"
    grep -qF "agent-email: the gws command" "$HOME/.zprofile" 2>/dev/null || printf "%s\n" "$line" >> "$HOME/.zprofile"
    make verify_install' || { echo "install failed"; fail=1; continue; }
done
exit $fail
