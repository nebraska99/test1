from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "telaio_strategie.db"
RAW_UPLOADS_DIR = DATA_DIR / "raw_uploads"
SIGNAL_SNAPSHOTS_DIR = DATA_DIR / "signal_snapshots"
CONFIG_DIR = DATA_DIR / "config"
PORTFOLIOS_DIR = DATA_DIR / "portfolios"

for folder in [DATA_DIR, RAW_UPLOADS_DIR, SIGNAL_SNAPSHOTS_DIR, CONFIG_DIR, PORTFOLIOS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)
