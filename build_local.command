#!/usr/bin/env bash
# macOS double-click vao file .command; logic that su nam trong build_local.sh,
# dung chung voi Linux.
exec "$(dirname "$0")/build_local.sh" "$@"
