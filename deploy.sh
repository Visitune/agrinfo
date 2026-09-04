#!/bin/bash
# deploy.sh — Push the AGRINFO scraper to GitHub
# Usage: ./deploy.sh [message]

cd "$(dirname "$0")"

MESSAGE="${1:-Auto-commit: AGRINFO scraper update}"

git add -A
git commit -m "$MESSAGE"
git push origin master

echo "✅ Pushed to https://github.com/Visitune/agrinfo"
