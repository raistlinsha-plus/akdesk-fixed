#!/bin/zsh

ROOT="$(cd "$(dirname "$0")" && pwd)"
export AKDESK_DEMO=1
exec "$ROOT/start-macos.command"
