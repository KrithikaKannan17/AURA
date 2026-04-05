#!/bin/zsh
set -e
cd /Users/krithikakannan/Desktop/PROJECTSS/AURA

echo "=== git init ==="
git init

echo "=== Adding README ==="
git add README.md
git commit -m "first commit"

echo "=== Renaming branch to main ==="
git branch -M main

echo "=== Adding remote ==="
git remote add origin https://github.com/KrithikaKannan17/AURA.git

echo "=== Staging all files ==="
git add .

echo "=== Final commit ==="
git commit -m "feat: initial AURA multi-agent RAG system"

echo "=== Pushing to GitHub ==="
git push -u origin main

echo "=== DONE ==="
