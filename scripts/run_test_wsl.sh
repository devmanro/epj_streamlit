#!/bin/bash
source ~/.bashrc 2>/dev/null || true
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PYENV_ROOT/shims:$PATH"
eval "$(pyenv init -)" 2>/dev/null || true
eval "$(pyenv virtualenv-init -)" 2>/dev/null || true
pyenv activate epj 2>/dev/null || true
python scripts/test_sort_group.py
