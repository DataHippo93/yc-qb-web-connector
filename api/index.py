"""
Vercel serverless entry point.
Exports the FastAPI app for Vercel's Python runtime.
"""
import sys
from pathlib import Path

# Ensure project root is on the path so `src.*` imports resolve
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.main import app
