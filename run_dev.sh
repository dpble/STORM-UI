#!/bin/bash
# Recreates the lab PC's Python path so the original bare imports resolve.
# Temporary: Phase 2 replaces these with proper package imports.
HERE="$(cd "$(dirname "$0")" && pwd)"
SA="$HERE/../storm-analysis/storm_analysis"
export PYTHONPATH="$SA:$SA/sa_library:$HERE/analysis_scripts:$HERE"
exec "$HERE/.venv/bin/python" "$@"
