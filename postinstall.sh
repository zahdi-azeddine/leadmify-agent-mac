#!/usr/bin/env bash
set -e
# Install Firefox + Geckodriver on the macOS runner
brew update
brew install --cask firefox
brew install geckodriver