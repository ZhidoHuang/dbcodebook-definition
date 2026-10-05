"""Offline lifecycle tests for delayed download reception across CLI calls."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
subprocess.run(['node', str(root / 'tests/download_capture_cases.js')], check=True)
