"""Re-exports the default loaded curriculum for use by main.py and tests."""

from .curriculum_loader import load_default_curriculum

CURRICULUM = load_default_curriculum()
