import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    CONFIG_DIR: Path = BASE_DIR / "config"
    FIXTURES_DIR: Path = BASE_DIR / "fixtures"

    # Database configuration
    DB_PATH: Path = Path(os.getenv("DB_PATH", str(DATA_DIR / "scraper.db")))

    # Bright Data configuration
    BRIGHTDATA_API_KEY: str = os.getenv("BRIGHTDATA_API_KEY", os.getenv("BRIGHTDATA_API_TOKEN", ""))
    BRIGHTDATA_COLLECTOR_ID: str = os.getenv("BRIGHTDATA_COLLECTOR_ID", "")
    BRIGHTDATA_API_URL: str = os.getenv("BRIGHTDATA_API_URL", "https://api.brightdata.com")

    # Discord configuration (for downstream pipeline)
    DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")

    # Target URLs configuration
    TARGET_URLS_FILE: Path = CONFIG_DIR / "target_urls.json"

    # Scraper settings
    DEFAULT_TIMEOUT_SECONDS: int = int(os.getenv("SCRAPER_TIMEOUT", "600"))

    @classmethod
    def ensure_directories(cls):
        """Ensure necessary directories exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cls.FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_directories()
