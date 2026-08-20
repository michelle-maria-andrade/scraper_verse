import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


def clean_price_value(value: Any) -> Optional[float]:
    """
    Parse float price from numbers or formatted strings like:
    '₹29', '$39.99', '₹ 1,499.00', '29(Inc GST)', ' 129.50 '
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    
    if isinstance(value, str):
        # Remove currency symbols, commas, whitespace, trailing text
        cleaned = value.strip()
        if not cleaned:
            return None
        # Extract first numeric sequence (including optional decimals)
        match = re.search(r'[\d,]+(?:\.\d+)?', cleaned)
        if match:
            num_str = match.group(0).replace(',', '')
            try:
                return float(num_str)
            except ValueError:
                return None
    return None


def clean_discount_pct(
    value: Any, 
    list_price: Optional[float] = None, 
    discount_price: Optional[float] = None
) -> Optional[float]:
    """
    Clean discount percentage or calculate from list_price & discount_price.
    Handles '26% OFF', '26%', 26, 25.64, etc.
    """
    if value is not None:
        if isinstance(value, (int, float)):
            pct = float(value)
            if 0 <= pct <= 100:
                return round(pct, 2)
        elif isinstance(value, str):
            match = re.search(r'(\d+(?:\.\d+)?)', value)
            if match:
                try:
                    pct = float(match.group(1))
                    if 0 <= pct <= 100:
                        return round(pct, 2)
                except ValueError:
                    pass

    # Fallback calculation if list_price and discount_price are available
    if (
        list_price is not None 
        and discount_price is not None 
        and list_price > 0 
        and list_price > discount_price
    ):
        calc_pct = ((list_price - discount_price) / list_price) * 100.0
        return round(calc_pct, 2)

    return None


def clean_in_stock(value: Any) -> bool:
    """Parse stock boolean from boolean or strings like 'In Stock', 'Out of Stock', 'Available'."""
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    if isinstance(value, (int, float)):
        return bool(value)
    
    val_str = str(value).strip().lower()
    if val_str in ("in stock", "instock", "available", "yes", "true", "1"):
        return True
    if val_str in ("out of stock", "outofstock", "unavailable", "sold out", "no", "false", "0"):
        return False
    return True


class ProductSnapshot(BaseModel):
    """
    Normalized data model representing a single product's state at a point in time.
    Conforms to .agents/rules/projects.md requirements.
    """
    id: Optional[int] = None
    run_id: str
    product_url: str
    product_name: Optional[str] = None
    sku: Optional[str] = None
    list_price: Optional[float] = None
    discount_price: Optional[float] = None
    discount_pct: Optional[float] = None
    in_stock: bool = True
    scraped_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_data: Optional[Dict[str, Any]] = None

    @field_validator('scraped_at', mode='before')
    @classmethod
    def validate_scraped_at(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, str) and v.strip():
            return v.strip()
        return datetime.now(timezone.utc).isoformat()

    def is_valid(self) -> bool:
        """
        A snapshot is considered valid/healthy if it has a product_name
        and at least one price field (list_price or discount_price).
        """
        has_name = bool(self.product_name and self.product_name.strip())
        has_price = (self.list_price is not None) or (self.discount_price is not None)
        return has_name and has_price

    def missing_fields(self) -> List[str]:
        """Returns list of essential fields that are missing or null."""
        missing = []
        if not self.product_name or not self.product_name.strip():
            missing.append("product_name")
        if self.list_price is None and self.discount_price is None:
            missing.append("price (both list_price & discount_price)")
        if self.list_price is None:
            missing.append("list_price")
        if self.discount_price is None:
            missing.append("discount_price")
        return missing

    @classmethod
    def from_raw_dict(cls, raw: Dict[str, Any], run_id: str, default_url: str = "") -> "ProductSnapshot":
        """
        Constructs and normalizes a ProductSnapshot from raw Bright Data collector output.
        Tolerates flexible key naming and messy data types.
        """
        # Resolve product URL
        product_url = (
            raw.get("product_url")
            or raw.get("url")
            or raw.get("link")
            or raw.get("input_url")
            or default_url
        )
        if not product_url:
            product_url = default_url

        # Resolve product name
        name = (
            raw.get("product_name")
            or raw.get("title")
            or raw.get("name")
            or raw.get("h1")
        )
        product_name = str(name).strip() if name else None

        # Resolve SKU
        sku_val = raw.get("sku") or raw.get("product_sku") or raw.get("item_sku")
        if sku_val is not None:
            sku_str = str(sku_val).strip()
            # Clean "SKU " prefix if present
            sku_clean = re.sub(r'^sku\s*[:#-]?\s*', '', sku_str, flags=re.I).strip()
            # Take only the first token if extra text is appended (e.g. '2401250015 No reviews found...')
            tokens = sku_clean.split()
            sku = tokens[0] if tokens else None
        else:
            sku = None

        # Resolve prices
        raw_list_price = raw.get("list_price") or raw.get("original_price") or raw.get("mrp") or raw.get("was_price")
        raw_discount_price = raw.get("discount_price") or raw.get("current_price") or raw.get("price") or raw.get("now_price")

        list_price = clean_price_value(raw_list_price)
        discount_price = clean_price_value(raw_discount_price)

        # If only one price was extracted into list_price and no discount_price, check context
        if list_price is not None and discount_price is None and "discount" not in str(raw).lower():
            # Standard single price scenario
            discount_price = list_price

        # Resolve discount percentage
        raw_discount_pct = raw.get("discount_pct") or raw.get("discount_percentage") or raw.get("discount")
        discount_pct = clean_discount_pct(raw_discount_pct, list_price=list_price, discount_price=discount_price)

        # Resolve stock status
        raw_stock = raw.get("in_stock") if "in_stock" in raw else raw.get("stock_status") or raw.get("availability")
        in_stock = clean_in_stock(raw_stock)

        # Resolve scraped_at timestamp
        scraped_at_val = raw.get("scraped_at") or datetime.now(timezone.utc).isoformat()

        return cls(
            run_id=run_id,
            product_url=str(product_url).strip(),
            product_name=product_name,
            sku=sku,
            list_price=list_price,
            discount_price=discount_price,
            discount_pct=discount_pct,
            in_stock=in_stock,
            scraped_at=scraped_at_val,
            raw_data=raw,
        )


class ScrapeRun(BaseModel):
    """
    Tracks metadata and health metrics for each execution run of the scraper.
    """
    run_id: str
    collector_id: Optional[str] = None
    status: str = "SUCCESS"  # SUCCESS, FAILED, PARTIAL
    total_products: int = 0
    valid_products: int = 0
    broken_products: int = 0
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def breakage_rate(self) -> float:
        """Returns the ratio (0.0 - 1.0) of broken products in this run."""
        if self.total_products == 0:
            return 0.0
        return self.broken_products / self.total_products
