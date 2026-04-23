import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.extract.spreadsheet_localization import CHEDRAUI_EXPORT_COLUMN_MAP, rename_columns

BASE_URL = "https://www.chedraui.com.mx"
CATEGORY_URL = f"{BASE_URL}/supermercado"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

TARGET_SEARCH_TERMS = {
    "aguacate": ["aguacate"],
    "tomate": ["tomate"],
    "elote": ["elote"],
    "zanahoria": ["zanahoria"],
    "cebolla": ["cebolla"],
    "chile_jalapeno": ["jalapeno", "chile jalapeno"],
    "limon": ["limon"],
    "platano": ["platano"],
    "mango": ["mango"],
    "papa": ["papa"],
}
TARGET_CROPS = list(TARGET_SEARCH_TERMS.keys())


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ñ": "n",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = "".join(
        character for character in unicodedata.normalize("NFKD", text) if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", text)


def _contains_term_as_word(text: str, term: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_term = normalize_text(term)
    if not normalized_term:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def build_search_urls(query: str) -> List[str]:
    encoded_query = urlencode({"q": query})
    encoded_search = urlencode({"s": query})
    encoded_api_query = urlencode({"query": query})
    encoded_catalog_query = urlencode({"ft": query})
    return [
        f"{BASE_URL}/api/io/_v/api/intelligent-search/product_search?{encoded_api_query}",
        f"{BASE_URL}/api/io/_v/api/intelligent-search/product_search/trade-policy/1?{encoded_api_query}",
        f"{BASE_URL}/api/catalog_system/pub/products/search?{encoded_catalog_query}",
        f"{BASE_URL}/supermercado?{encoded_query}",
        f"{BASE_URL}/supermercado?{encoded_search}",
    ]


def fetch_html(url: str, session: Optional[requests.Session] = None) -> str:
    client = session or requests.Session()
    response = client.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def extract_embedded_json_payloads(html: str) -> List[Dict[str, Any]]:
    """Extract JSON payloads embedded in HTML or returned as raw JSON.

    The Chedraui site sometimes returns pages built with React/Next.js that embed
    data in ``<script id="__NEXT_DATA__">`` tags or ``<script type="application/ld+json">``
    tags.  The site also exposes a public VTEX API that returns pure JSON without
    any surrounding HTML.  This function normalizes both cases by returning a
    list of dictionaries ready for traversal.  Plain JSON responses are detected
    by inspecting the initial characters of the input.
    """
    payloads: List[Dict[str, Any]] = []
    # Check if the provided HTML is actually a JSON document.  If so, parse it
    # directly rather than attempting to use BeautifulSoup.  We do a simple
    # check on the first non‑whitespace character.
    stripped = html.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            payloads.append(parsed)
            return payloads
        elif isinstance(parsed, list):
            payloads.extend([entry for entry in parsed if isinstance(entry, dict)])
            return payloads

    # Fallback to HTML parsing for Next.js/ld+json scripts
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"id": "__NEXT_DATA__"}):
        raw = script.string or script.get_text() or ""
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_text = script.string or script.get_text() or ""
        if not raw_text.strip():
            continue
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
        elif isinstance(parsed, list):
            payloads.extend([entry for entry in parsed if isinstance(entry, dict)])
    return payloads


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    match = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    if not match:
        return None
    return float(match.group(1))


def _is_weighted_product_name(product_name: str) -> bool:
    normalized_name = normalize_text(product_name)
    return "por kg" in normalized_name or "por kilo" in normalized_name


def _extract_price_values(node: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Extract current and old price values from a product node.

    The site uses a variety of field names for pricing.  This function attempts
    to find a reasonable current price (precio actual) and an old price (precio
    anterior) from any case of these fields.  It also falls back to prices
    nested inside VTEX API structures such as ``items -> sellers -> commertialOffer``.
    """
    current_candidates: List[Any] = []
    old_candidates: List[Any] = []
    product_name = str(node.get("name") or node.get("productName") or node.get("title") or "")
    is_weighted_product = _is_weighted_product_name(product_name)

    # Include values from keys regardless of case.  We consider several synonyms
    # for current and old prices.  Lower‑case the key for matching but store
    # the original value.
    for key, value in node.items():
        if value is None:
            continue
        k = key.lower()
        if k in {"price", "currentprice", "spotprice", "pricevalue", "bestprice", "sellprice", "sellingprice", "pricewithtax"}:
            current_candidates.append(value)
        if k in {"oldprice", "listprice", "pricewithoutdiscount", "highprice", "wasprice"}:
            old_candidates.append(value)

    # Handle "offers" dictionary similar to schema.org Product
    offers = node.get("offers")
    if isinstance(offers, dict):
        offer_type = str(offers.get("@type") or "").lower()
        is_aggregate_offer = offer_type == "aggregateoffer"

        if is_aggregate_offer:
            low_price = offers.get("lowPrice")
            high_price = offers.get("highPrice")
            if is_weighted_product:
                # VTEX publishes weighted produce as an AggregateOffer where
                # lowPrice is the minimum purchasable amount (e.g. 0.15 kg)
                # and highPrice is the displayed per-kg price shown on the site.
                # This range is not a promotion, so it must not populate the old price.
                if high_price is not None:
                    current_candidates.append(high_price)
                elif low_price is not None:
                    current_candidates.append(low_price)
            else:
                nested_offers = offers.get("offers")
                if isinstance(nested_offers, list):
                    for nested_offer in nested_offers:
                        if not isinstance(nested_offer, dict):
                            continue
                        for k in ("price", "priceValue", "bestPrice"):
                            val = nested_offer.get(k)
                            if val is not None:
                                current_candidates.append(val)
                if low_price is not None:
                    current_candidates.append(low_price)
                elif high_price is not None:
                    current_candidates.append(high_price)
        else:
            for k in ("price", "priceValue", "bestPrice", "lowPrice"):
                val = offers.get(k)
                if val is not None:
                    current_candidates.append(val)
            for k in ("oldPrice", "highPrice", "listPrice", "priceWithoutDiscount"):
                val = offers.get(k)
                if val is not None:
                    old_candidates.append(val)

    # If present, look into VTEX API structures: items -> sellers -> commertialOffer
    items = node.get("items")
    if isinstance(items, list):
        for item in items:
            sellers = item.get("sellers") or []
            for seller in sellers:
                # In VTEX naming, the field may be "commertialOffer" or "commercialOffer"
                offer = seller.get("commertialOffer") or seller.get("commercialOffer")
                if not isinstance(offer, dict):
                    continue
                # VTEX's commertialOffer exposes fields like Price (discounted price),
                # ListPrice (original list price), PriceWithoutDiscount (price before
                # applying campaign discounts) and BestPrice.  The current price
                # should come from fields like Price, PriceValue or BestPrice.  The
                # PriceWithoutDiscount is considered an old or reference price
                # because it reflects the value before discounts.  Therefore we treat
                # priceWithoutDiscount as an old candidate instead of a current one.
                for k, v in offer.items():
                    key_lower = k.lower()
                    if v is None:
                        continue
                    # Determine candidate lists by key semantics.  The set for
                    # current prices excludes 'pricewithoutdiscount'.
                    if key_lower in {"price", "pricevalue", "bestprice"}:
                        current_candidates.append(v)
                    if key_lower in {"listprice", "highprice", "wasprice", "pricewithoutdiscount"}:
                        old_candidates.append(v)

    # Coerce all candidate values to floats
    current_vals: List[float] = [p for p in (_safe_float(v) for v in current_candidates) if p is not None]
    old_vals: List[float] = [p for p in (_safe_float(v) for v in old_candidates) if p is not None]

    current_price = None
    old_price = None
    if current_vals:
        # Choose the lowest value from the current price candidates.  This guards
        # against cases where a high reference price accidentally appears in the
        # current candidate set (e.g. PriceWithoutDiscount mistakenly classified).
        current_price = min(current_vals)
    if old_vals:
        # Choose the highest value from the old price candidates; this aims to
        # capture the original list price when multiple reference prices are
        # present.
        old_price = max(old_vals)
    # If the extracted old price is not greater than the current price, treat it as
    # not a promotion and drop it.  Some sources report equal or smaller old prices.
    if old_price is not None and current_price is not None and old_price <= current_price:
        old_price = None
    return current_price, old_price


def _looks_like_product(node: Dict[str, Any]) -> bool:
    text_name = node.get("name") or node.get("productName") or node.get("title")
    if not text_name:
        return False

    current_price, _ = _extract_price_values(node)
    if current_price is not None:
        return True

    offers = node.get("offers")
    return isinstance(offers, dict) and _safe_float(offers.get("price")) is not None


def _collect_candidate_nodes(node: Any, items: List[Dict[str, Any]]) -> None:
    if isinstance(node, dict):
        if _looks_like_product(node):
            items.append(node)
        for value in node.values():
            _collect_candidate_nodes(value, items)
    elif isinstance(node, list):
        for entry in node:
            _collect_candidate_nodes(entry, items)


def extract_search_items(html: str) -> List[Dict[str, Any]]:
    payloads = extract_embedded_json_payloads(html)
    items: List[Dict[str, Any]] = []
    for payload in payloads:
        _collect_candidate_nodes(payload, items)

    deduped: Dict[str, Dict[str, Any]] = {}
    for item in items:
        key = normalize_text(str(item.get("name") or item.get("productName") or item.get("title") or ""))
        if not key:
            continue
        deduped.setdefault(key, item)
    return list(deduped.values())


def canonical_crop(product_name: str) -> Optional[str]:
    n = normalize_text(product_name)
    if "aguacate" in n:
        return "aguacate"
    if "jitomate" in n or re.search(r"\btomate\b", n):
        return "tomate"
    if "elote" in n:
        return "elote"
    if "zanahoria" in n:
        return "zanahoria"
    if "cebolla" in n:
        return "cebolla"
    if "jalape" in n:
        return "chile_jalapeno"
    if "limon" in n:
        return "limon"
    if "platano" in n:
        return "platano"
    if "mango" in n:
        return "mango"
    if _contains_term_as_word(n, "papa"):
        return "papa"
    return None


def extract_weight_kg_from_title(product_name: str) -> Optional[float]:
    n = normalize_text(product_name)
    match_kg = re.search(r"(\d+(?:\.\d+)?)\s*kg\b", n)
    if match_kg:
        return float(match_kg.group(1))
    match_g = re.search(r"(\d+(?:\.\d+)?)\s*g(?:r|rs|ms)?\b", n)
    if match_g:
        return float(match_g.group(1)) / 1000.0
    return None


def infer_unit(product_name: str) -> Optional[str]:
    n = normalize_text(product_name)
    if "por kg" in n or "por kilo" in n:
        return "kg"
    if "pieza" in n:
        return "pieza"
    if "rollo" in n:
        return "rollo"
    if "malla" in n or "enmallado" in n:
        return "malla"
    if extract_weight_kg_from_title(product_name) is not None:
        return "g_pack"
    return None


def estimate_price_per_kg(price: Optional[float], unit: Optional[str], product_name: str) -> Optional[float]:
    if price is None:
        return None
    if unit == "kg":
        return round(price, 4)
    weight_kg = extract_weight_kg_from_title(product_name)
    if weight_kg and weight_kg > 0:
        return round(price / weight_kg, 4)
    return None


def _build_source_page(node: Dict[str, Any]) -> str:
    for key in ("url", "link", "canonicalUrl", "@id"):
        value = node.get(key)
        if not isinstance(value, str) or not value:
            continue
        if value.startswith("http"):
            return value
        if value.startswith("/"):
            return f"{BASE_URL}{value}"
    return CATEGORY_URL


def item_to_record(item: Dict[str, Any], query_term: str, configured_product: Optional[str] = None) -> Optional[Dict[str, Any]]:
    product_name = str(item.get("name") or item.get("productName") or item.get("title") or "").strip()
    inferred_crop = canonical_crop(product_name)
    crop = configured_product or inferred_crop
    if not crop:
        return None

    price_mxn, old_price_mxn = _extract_price_values(item)
    if price_mxn is None:
        return None

    unit = infer_unit(product_name)

    return {
        "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "chedraui_mx",
        "source_page": _build_source_page(item),
        "source_query": query_term,
        "product_raw": product_name,
        "product_canonical": crop,
        "product_inferred": inferred_crop,
        "price_mxn": price_mxn,
        "old_price_mxn": old_price_mxn,
        "promo_flag": old_price_mxn is not None,
        "unit_raw": unit,
        "estimated_price_per_kg_mxn": estimate_price_per_kg(price_mxn, unit, product_name),
        "presentation_weight_kg": extract_weight_kg_from_title(product_name),
        "brand_raw": item.get("brand"),
        "category_path": "",
        "fresh_produce_flag": True,
    }


def query_relevance_penalty(record: Dict[str, Any], preferred_terms_map: Optional[Dict[str, List[str]]] = None) -> int:
    crop = record.get("product_canonical")
    query = normalize_text(record.get("source_query") or "")
    preferred_map = preferred_terms_map or TARGET_SEARCH_TERMS
    preferred_terms = [normalize_text(term) for term in preferred_map.get(crop, [])]
    if not preferred_terms:
        return 0
    return 0 if query in preferred_terms else 1


def record_rank(record: Dict[str, Any], preferred_terms_map: Optional[Dict[str, List[str]]] = None) -> Tuple[int, int, int, float]:
    unit = record.get("unit_raw")
    has_ppkg = record.get("estimated_price_per_kg_mxn") is not None
    promo_penalty = 0 if record.get("promo_flag") else 1

    if unit == "kg":
        unit_rank = 0
    elif has_ppkg:
        unit_rank = 1
    else:
        unit_rank = 2

    price_sort = record.get("estimated_price_per_kg_mxn") or record.get("price_mxn") or 999999
    return (unit_rank, promo_penalty, query_relevance_penalty(record, preferred_terms_map), price_sort)


def sort_records(records: Iterable[Dict[str, Any]], preferred_terms_map: Optional[Dict[str, List[str]]] = None) -> List[Dict[str, Any]]:
    return sorted(records, key=lambda record: record_rank(record, preferred_terms_map))


def choose_best_records(
    records: List[Dict[str, Any]],
    product_keys: Iterable[str],
    preferred_terms_map: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    best_records: List[Dict[str, Any]] = []

    for crop in product_keys:
        crop_records = [record for record in records if record["product_canonical"] == crop]
        if not crop_records:
            continue
        best_records.append(sort_records(crop_records, preferred_terms_map)[0])

    return sort_records(best_records, preferred_terms_map)


def choose_best_record_per_crop(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return choose_best_records(records, TARGET_CROPS, TARGET_SEARCH_TERMS)


def collect_search_records(
    session: Optional[requests.Session] = None,
    search_terms: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    client = session or requests.Session()
    query_map = search_terms or TARGET_SEARCH_TERMS
    deduped_records: Dict[Tuple[str, str, float], Dict[str, Any]] = {}

    # Iterate through each configured crop (e.g. "aguacate", "tomate", etc.) and the list of
    # associated search terms.  By default ``search_terms`` will be ``None`` which
    # triggers the use of ``TARGET_SEARCH_TERMS``.  We always set
    # ``configured_product`` when building records so that the resulting
    # ``product_canonical`` field corresponds to the crop we are currently
    # processing.  This avoids mis‑classifying products whose names might
    # contain ambiguous words.
    for configured_product, terms in query_map.items():
        for query_term in terms:
            items_by_name: Dict[str, Dict[str, Any]] = {}
            # Merge results across all search variants because some storefront
            # pages return a generic produce listing while the VTEX APIs
            # return the actual query-specific products.
            for search_url in build_search_urls(query_term):
                try:
                    html = fetch_html(search_url, session=client)
                except requests.RequestException:
                    continue
                for item in extract_search_items(html):
                    item_name = normalize_text(str(item.get("name") or item.get("productName") or item.get("title") or ""))
                    if item_name:
                        items_by_name.setdefault(item_name, item)

            items = list(items_by_name.values())

            # If no items were returned for this query we simply continue.
            if not items:
                continue

            # Normalize the query term once for efficient comparisons.  We use this to
            # filter out obviously unrelated products (e.g. when the search page returns
            # generic or promotional items unrelated to the term).  This prevents a
            # situation where the same unrelated product is selected across different
            # crops, such as "calabacita" appearing as the result for all searches.
            normalized_query = normalize_text(query_term)

            for item in items:
                # Extract the product name from the raw item data.  Some payloads use
                # different keys for the name, so we check them in order of priority.
                product_name = str(
                    item.get("name")
                    or item.get("productName")
                    or item.get("title")
                    or ""
                ).strip()
                normalized_name = normalize_text(product_name)
                # Skip items that do not contain the query term.  This helps remove
                # unrelated products that might otherwise pollute the results.
                if not _contains_term_as_word(normalized_name, normalized_query):
                    continue

                record = item_to_record(
                    item,
                    query_term,
                    # Always pass the configured crop name so that the canonical
                    # product assignment does not rely solely on heuristic matching.
                    configured_product=configured_product,
                )
                if record is None:
                    continue

                # Use a tuple of canonical crop, raw product name and price as a key
                # for deduplication.  If we encounter the same product more than
                # once, keep whichever record sorts higher based on ``record_rank``.
                key = (record["product_canonical"], record["product_raw"], record["price_mxn"])
                previous = deduped_records.get(key)
                if previous is None or record_rank(record, query_map) < record_rank(previous, query_map):
                    deduped_records[key] = record

    # Return the list of unique records
    return list(deduped_records.values())


def _records_to_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(records)


def _write_html_xls(df: pd.DataFrame, output_path: Path) -> None:
    html = df.to_html(index=False, na_rep="", border=1)
    output_path.write_text(html, encoding="utf-8")


def save_output(records: List[Dict[str, Any]], filepath: str, output_format: str) -> Path:
    if not records:
        print("No records to save.")
        return Path(filepath)

    output_path = Path(filepath)
    if output_path.suffix.lower() != f".{output_format}":
        output_path = output_path.with_suffix(f".{output_format}")

    df = _records_to_dataframe(records)
    localized_df = rename_columns(df, CHEDRAUI_EXPORT_COLUMN_MAP)
    if output_format == "csv":
        localized_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    elif output_format == "xlsx":
        localized_df.to_excel(output_path, index=False, engine="openpyxl")
    elif output_format == "xls":
        _write_html_xls(localized_df, output_path)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chedraui Mexico produce scraper")
    parser.add_argument("--output-format", choices=("csv", "xls", "xlsx"), default="csv")
    parser.add_argument("--output", help="Output file path. If omitted, a timestamped filename is generated.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = collect_search_records()
    best_records = choose_best_record_per_crop(records)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_output = f"chedraui_produce_{timestamp}.{args.output_format}"
    output_path = save_output(best_records, args.output or default_output, args.output_format)

    print(f"Saved {len(best_records)} records to {output_path}\\n")
    for record in best_records:
        print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
