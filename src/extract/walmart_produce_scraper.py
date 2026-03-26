import csv
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.walmart.com.mx"
CATEGORY_URL = f"{BASE_URL}/content/frutas-y-verduras/120007"
SEARCH_URL = f"{BASE_URL}/search"
SEARCH_PAGE_SIZE = 40

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

TARGET_SEARCH_TERMS = {
    "aguacate": ["aguacate"],
    "tomate": ["jitomate", "tomate"],
    "elote": ["elote por pieza", "elote"],
    "zanahoria": ["zanahoria"],
    "cebolla": ["cebolla"],
    "chile_jalapeno": ["chile jalapeno por kilo", "chile jalapeno", "jalapeno"],
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
        "Ã¡": "a",
        "Ã©": "e",
        "Ã­": "i",
        "Ã³": "o",
        "Ãº": "u",
        "Ã±": "n",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text)
    return text


def build_search_url(query: str, page_size: int = SEARCH_PAGE_SIZE) -> str:
    return f"{SEARCH_URL}?{urlencode({'q': query, 'ps': page_size})}"


def is_blocked_page(html: str) -> bool:
    normalized = normalize_text(html)
    return "verifica tu identidad" in normalized and "no eres un robot" in normalized


def fetch_html(url: str, session: Optional[requests.Session] = None) -> str:
    client = session or requests.Session()
    response = client.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    if is_blocked_page(response.text):
        raise RuntimeError(f"Walmart blocked the request for {url}")

    return response.text


def extract_next_data(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        raise ValueError("Could not find __NEXT_DATA__ payload in Walmart search page.")
    return json.loads(script.string)


def extract_search_items(next_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    search_result = (
        next_data
        .get("props", {})
        .get("pageProps", {})
        .get("initialData", {})
        .get("searchResult", {})
    )

    item_stacks = search_result.get("itemStacks") or []
    items: List[Dict[str, Any]] = []

    for stack in item_stacks:
        for item in stack.get("items") or []:
            if item.get("__typename") == "Product":
                items.append(item)

    return items


def parse_currency_value(text: Optional[str]) -> Optional[float]:
    if not text:
        return None

    match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", text)
    if not match:
        return None

    return float(match.group(1))


def parse_price_text(text: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    if not text:
        return None, None

    match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)(?:\s*/\s*([a-zA-Z]+))?", text)
    if not match:
        return None, None

    unit = match.group(2).lower() if match.group(2) else None
    return float(match.group(1)), unit


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
    if "papa" in n:
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


def infer_unit(
    product_name: str,
    price_info: Dict[str, Any],
    sales_unit_type: Optional[str],
) -> Optional[str]:
    current_price_text = price_info.get("linePrice") or price_info.get("itemPrice")
    _, inline_unit = parse_price_text(current_price_text)
    if inline_unit:
        return inline_unit

    if sales_unit_type == "EACH_WEIGHT":
        return "kg"

    n = normalize_text(product_name)
    if "por kilo" in n:
        return "kg"
    if "por pieza" in n:
        return "pieza"
    if "manojo" in n:
        return "manojo"
    if "malla" in n:
        return "malla"
    if "bolsa" in n:
        return "bolsa"
    if re.search(r"\b\d+(?:\.\d+)?\s*g(?:r|rs|ms)?\b", n):
        return "g_pack"

    return None


def estimate_price_per_kg(
    price: Optional[float],
    unit: Optional[str],
    product_name: str,
) -> Optional[float]:
    if price is None:
        return None

    if unit == "kg":
        return round(price, 4)

    weight_kg = extract_weight_kg_from_title(product_name)
    if weight_kg and weight_kg > 0:
        return round(price / weight_kg, 4)

    return None


def extract_category_names(item: Dict[str, Any]) -> List[str]:
    category = item.get("category") or {}
    path = category.get("path") or []
    names: List[str] = []

    for entry in path:
        if isinstance(entry, dict) and entry.get("name"):
            names.append(str(entry["name"]))

    return names


def is_fresh_produce_item(item: Dict[str, Any], product_name: str) -> bool:
    brand = normalize_text(item.get("brand") or "")
    category_names = [normalize_text(name) for name in extract_category_names(item)]
    product_name_normalized = normalize_text(product_name)

    if brand == "frutas y verduras frescas":
        return True

    if any(name in {"frutas y verduras", "frutas", "verduras"} for name in category_names):
        return True

    if item.get("salesUnitType") == "EACH_WEIGHT":
        return True

    positive_terms = [
        "por pieza",
        "por kilo",
        "manojo",
        "malla",
        "bolsa",
    ]
    return any(term in product_name_normalized for term in positive_terms)


def item_to_record(item: Dict[str, Any], query_term: str) -> Optional[Dict[str, Any]]:
    product_name = item.get("name") or ""
    crop = canonical_crop(product_name)
    if crop not in TARGET_CROPS:
        return None

    price_info = item.get("priceInfo") or {}
    current_price_text = price_info.get("linePrice") or price_info.get("itemPrice")
    old_price_text = price_info.get("wasPrice") or price_info.get("itemPrice")

    price_mxn, _ = parse_price_text(current_price_text)
    if price_mxn is None:
        return None

    old_price_mxn = parse_currency_value(old_price_text)
    if old_price_mxn == price_mxn:
        old_price_mxn = None

    unit = infer_unit(product_name, price_info, item.get("salesUnitType"))
    category_names = extract_category_names(item)
    source_path = item.get("canonicalUrl") or ""
    source_page = f"{BASE_URL}{source_path}" if source_path.startswith("/") else CATEGORY_URL

    return {
        "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "walmart_mx",
        "source_page": source_page,
        "source_query": query_term,
        "product_raw": product_name,
        "product_canonical": crop,
        "price_mxn": price_mxn,
        "old_price_mxn": old_price_mxn,
        "promo_flag": bool(price_info.get("savingsAmt")) or old_price_mxn is not None,
        "unit_raw": unit,
        "estimated_price_per_kg_mxn": estimate_price_per_kg(price_mxn, unit, product_name),
        "presentation_weight_kg": extract_weight_kg_from_title(product_name),
        "sales_unit_type": item.get("salesUnitType"),
        "average_weight_kg": item.get("averageWeight") or None,
        "brand_raw": item.get("brand"),
        "category_path": " > ".join(category_names),
        "fresh_produce_flag": is_fresh_produce_item(item, product_name),
    }


def record_rank(record: Dict[str, Any]) -> Tuple[int, int, int, int, float]:
    unit = record.get("unit_raw")
    has_ppkg = record.get("estimated_price_per_kg_mxn") is not None
    promo_penalty = 0 if record.get("promo_flag") else 1
    fresh_penalty = 0 if record.get("fresh_produce_flag") else 1

    if unit == "kg":
        unit_rank = 0
    elif has_ppkg:
        unit_rank = 1
    else:
        unit_rank = 2

    price_sort = record.get("estimated_price_per_kg_mxn") or record.get("price_mxn") or 999999
    return (fresh_penalty, unit_rank, promo_penalty, query_relevance_penalty(record), price_sort)


def query_relevance_penalty(record: Dict[str, Any]) -> int:
    crop = record.get("product_canonical")
    query = normalize_text(record.get("source_query") or "")
    preferred_terms = [normalize_text(term) for term in TARGET_SEARCH_TERMS.get(crop, [])]
    return 0 if query in preferred_terms else 1


def collect_search_records(
    session: Optional[requests.Session] = None,
    search_terms: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    client = session or requests.Session()
    query_map = search_terms or TARGET_SEARCH_TERMS

    deduped_records: Dict[Tuple[str, float], Dict[str, Any]] = {}

    for terms in query_map.values():
        for query_term in terms:
            html = fetch_html(build_search_url(query_term), session=client)
            next_data = extract_next_data(html)
            items = extract_search_items(next_data)

            for item in items:
                record = item_to_record(item, query_term)
                if record is None:
                    continue

                key = (record["product_raw"], record["price_mxn"])
                previous = deduped_records.get(key)
                if previous is None or record_rank(record) < record_rank(previous):
                    deduped_records[key] = record

    return list(deduped_records.values())


def choose_best_record_per_crop(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_records: List[Dict[str, Any]] = []

    for crop in TARGET_CROPS:
        crop_records = [record for record in records if record["product_canonical"] == crop]
        if not crop_records:
            continue
        best_records.append(sort_records(crop_records)[0])

    return sort_records(best_records)


def sort_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(records, key=record_rank)


def save_csv(records: List[Dict[str, Any]], filepath: str) -> None:
    if not records:
        print("No records to save.")
        return

    fieldnames = list(records[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    records = collect_search_records()
    best_records = choose_best_record_per_crop(records)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = f"walmart_produce_{timestamp}.csv"
    save_csv(best_records, out_csv)

    print(f"Saved {len(best_records)} records to {out_csv}\n")
    for record in best_records:
        print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
