#!/usr/bin/env bash
set -euo pipefail

rsync -av --delete \
  --exclude '.git' \
  --exclude '.cursor' \
  --exclude '.vscode' \
  --exclude '.venv' \
  --exclude '.venv-editor' \
  --exclude 'vendor' \
  --exclude 'dist' \
  --exclude 'build' \
  --exclude 'docs' \
  --exclude 'manual' \
  --exclude 'example_projects' \
  /home/joshua/Documents/ChoreBoyCodeStudio/ \
  /home/joshua/Documents/ChoreBoyCodeStudio_safe/