import os
import sys
from pathlib import Path

# Base SQLite isolée pour les tests (définie AVANT l'import des modèles).
_DB = Path(__file__).parent / "test.db"
if _DB.exists():
    _DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-bytes-long!!"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
