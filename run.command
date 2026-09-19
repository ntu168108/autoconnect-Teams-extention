#!/usr/bin/env bash
# macOS double-click vao file .command; logic that su nam trong run.sh, dung
# chung voi Linux.
exec "$(dirname "$0")/run.sh" "$@"
