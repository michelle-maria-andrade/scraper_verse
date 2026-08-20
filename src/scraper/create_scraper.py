import argparse
import json
import logging
from pathlib import Path
from typing import Optional

from config.settings import settings
from src.scraper.bdata_client import bdata_client

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = (
    "Extract product detail page fields: product_url (current URL), "
    "product_name (title or h1), sku (product SKU number or code), "
    "list_price (original/strikethrough price as float), "
    "discount_price (current/discounted price as float), "
    "discount_pct (discount percentage as float), "
    "in_stock (boolean true if in stock)."
)


def create_pdp_scraper(
    target_url: str,
    prompt: Optional[str] = None,
    name: str = "indianrobo-pdp-scraper",
    output_file: Optional[Path] = None,
) -> dict:
    """
    Creates a new Bright Data scraper via AI flow.
    """
    description = prompt or DEFAULT_PROMPT
    logger.info(f"Initiating scraper creation for: {target_url}")
    result = bdata_client.create_scraper(
        url=target_url,
        description=description,
        name=name,
    )

    collector_id = result.get("collector_id")
    logger.info(f"Successfully created scraper! Collector ID: {collector_id}")

    # Save to create_result.json
    out_path = output_file or (settings.BASE_DIR / "create_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # If .env exists, update or append BRIGHTDATA_COLLECTOR_ID
    env_path = settings.BASE_DIR / ".env"
    if collector_id:
        if env_path.exists():
            env_content = env_path.read_text(encoding="utf-8")
            if "BRIGHTDATA_COLLECTOR_ID=" in env_content:
                lines = [
                    f"BRIGHTDATA_COLLECTOR_ID={collector_id}" if l.startswith("BRIGHTDATA_COLLECTOR_ID=") else l
                    for l in env_content.splitlines()
                ]
                env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            else:
                env_path.write_text(env_content.rstrip() + f"\nBRIGHTDATA_COLLECTOR_ID={collector_id}\n", encoding="utf-8")
        else:
            env_path.write_text(f"BRIGHTDATA_COLLECTOR_ID={collector_id}\n", encoding="utf-8")

    return result


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Create a Bright Data PDP scraper using AI generation.")
    parser.add_argument(
        "--url", "-u",
        type=str,
        default="https://indianrobostore.com/product/male-dupont-electrical-terminal-plug-reed-connector-254mm-5-pins",
        help="Sample product URL to generate scraper against",
    )
    parser.add_argument("--prompt", "-p", type=str, default=DEFAULT_PROMPT, help="Natural language extraction prompt")
    parser.add_argument("--name", "-n", type=str, default="indianrobo-pdp-scraper", help="Scraper template name")

    args = parser.parse_args()
    res = create_pdp_scraper(target_url=args.url, prompt=args.prompt, name=args.name)
    print("\nCollector creation result:")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
