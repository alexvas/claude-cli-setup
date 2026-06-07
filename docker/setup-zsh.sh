#!/bin/bash
# Install oh-my-zsh at a pinned git ref and set up minimal zsh config for user dev.
set -euo pipefail

HOME="${HOME:-/home/dev}"
ZSH="${HOME}/.oh-my-zsh"
ZSHRC="${HOME}/.zshrc"
PROMPT_FILE="${HOME}/.claude-cli-zsh-prompt"
OH_MY_ZSH_VERSION="${OH_MY_ZSH_VERSION:?OH_MY_ZSH_VERSION required}"
OH_MY_ZSH_REPO="${OH_MY_ZSH_REPO:-https://github.com/ohmyzsh/ohmyzsh.git}"

install_oh_my_zsh() {
  if [ -d "${ZSH}" ]; then
    return 0
  fi

  umask g-w,o-w

  git init --quiet "${ZSH}"
  cd "${ZSH}"
  git config core.eol lf
  git config core.autocrlf false
  git config fsck.zeroPaddedFilemode ignore
  git config fetch.fsck.zeroPaddedFilemode ignore
  git config receive.fsck.zeroPaddedFilemode ignore
  git config oh-my-zsh.remote origin
  git config oh-my-zsh.branch master
  git remote add origin "${OH_MY_ZSH_REPO}"
  git fetch --depth 1 origin "${OH_MY_ZSH_VERSION}"
  git checkout -q FETCH_HEAD
  git config oh-my-zsh.lastVersion "${OH_MY_ZSH_VERSION}"
  cd - >/dev/null
}

install_oh_my_zsh

# Write minimal .zshrc: oh-my-zsh base + user fragment
cat > "${ZSHRC}" <<'ZSHRC_EOF'
export ZSH="${HOME}/.oh-my-zsh"
ZSH_DISABLE_COMPFIX=true
ZSH_THEME=""
plugins=(git)
source "$ZSH/oh-my-zsh.sh"

# claude-cli zsh prompt
[[ -f "${HOME}/.claude-cli-zsh-prompt" ]] && source "${HOME}/.claude-cli-zsh-prompt"
ZSHRC_EOF

# Copy prompt/alias fragment
if [ -f /tmp/zshrc.fragment ]; then
  cp /tmp/zshrc.fragment "${PROMPT_FILE}"
fi
