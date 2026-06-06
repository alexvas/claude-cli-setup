#!/bin/bash
# Install oh-my-zsh at a pinned git ref and append project zshenv for user dev.
set -euo pipefail

HOME="${HOME:-/home/dev}"
ZSH="${HOME}/.oh-my-zsh"
ZSH_ENV_MARKER='# claude-cli zshenv'
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

  if [ ! -f "${HOME}/.zshrc" ]; then
    sed "s|^export ZSH=.*$|export ZSH=\"\${HOME}/.oh-my-zsh\"|" \
      "${ZSH}/templates/zshrc.zsh-template" > "${HOME}/.zshrc"
  fi
}

install_oh_my_zsh

if [ -f /tmp/zshenv.fragment ]; then
  touch "${HOME}/.zshenv"
  if ! grep -qF "${ZSH_ENV_MARKER}" "${HOME}/.zshenv"; then
    {
      echo
      echo "${ZSH_ENV_MARKER}"
      cat /tmp/zshenv.fragment
    } >> "${HOME}/.zshenv"
  fi
fi
