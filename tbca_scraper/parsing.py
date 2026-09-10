import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .constants import DEFAULT_TBCA_URL, NUTRIENT_CODES


FoodReference = Dict[str, Any]
FoodPayload = Dict[str, Any]

STANDARD_PORTION_LABEL = "Valor por 100g"
PORTION_PATTERN = re.compile(
    r"^(?P<label>.*?)\s*\(\s*(?P<quantity>\d+(?:[.,]\d+)?)"
    r"\s*(?P<unit>[^\d()\s]+)?\s*\)\s*$"
)
UNIT_ALIASES = {
    "kcal": "kcal",
    "kj": "kJ",
    "g": "g",
    "mg": "mg",
    "mcg": "mcg",
    "µg": "mcg",
    "μg": "mcg",
    "ml": "mL",
}


def normalize_source_text(value: str) -> str:
    """Remove whitespace introduced by HTML without translating source text."""
    return " ".join(value.split())


def normalize_metadata_text(value: str) -> str:
    """Remove redundant HTML whitespace around source-language punctuation."""
    value = normalize_source_text(value)
    return re.sub(r"\s+([,.;:])", r"\1", value)


def normalize_unit(value: str) -> str:
    """Normalize the spelling of known technical units without converting values."""
    normalized = normalize_source_text(value)
    return UNIT_ALIASES.get(normalized.casefold(), normalized)


def parse_localized_number(value: str) -> float:
    """Parse a TBCA decimal while preserving precision represented by JSON numbers."""
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    return float(value)


def parse_nutrient_value(raw_value: str, unit: str) -> Tuple[Dict[str, Any], bool]:
    """Build a nutrient value and report whether its token is unknown."""
    value = normalize_source_text(raw_value)
    token_statuses = {
        "tr": "TRACE",
        "na": "NOT_ANALYZED",
        "-": "NOT_AVAILABLE",
    }
    status = token_statuses.get(value.casefold())
    if status is not None:
        return {
            "amount": None,
            "unit": unit,
            "status": status,
            "rawValue": value,
        }, False

    try:
        amount = parse_localized_number(value)
    except ValueError:
        return {
            "amount": None,
            "unit": unit,
            "status": "UNKNOWN",
            "rawValue": value,
        }, True

    if amount.is_integer():
        amount = int(amount)
    return {
        "amount": amount,
        "unit": unit,
        "status": "VALUE",
        "rawValue": value,
    }, False


def nutrient_code(name: str, unit: str) -> Optional[str]:
    """Return the explicit technical code for a known TBCA nutrient."""
    normalized_name = normalize_source_text(name)
    if normalized_name == "Energia":
        return {
            "kcal": "energy_kcal",
            "kJ": "energy_kj",
        }.get(unit)
    return NUTRIENT_CODES.get(normalized_name)


def parse_portion(raw_label: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """Parse a household portion header without inferring missing information."""
    raw_label = normalize_source_text(raw_label)
    match = PORTION_PATTERN.match(raw_label)
    if match is None:
        return {
            "type": "HOUSEHOLD",
            "label": raw_label,
            "rawLabel": raw_label,
            "quantity": None,
            "unit": None,
            "nutrients": {},
        }, "Household portion could not be parsed: {!r}".format(raw_label)

    quantity = parse_localized_number(match.group("quantity"))
    if quantity.is_integer():
        quantity = int(quantity)
    source_unit = match.group("unit")
    unit = normalize_unit(source_unit) if source_unit else None
    warning = None
    if unit is None:
        warning = "Household portion has a quantity but no unit: {!r}".format(
            raw_label
        )

    return {
        "type": "HOUSEHOLD",
        "label": normalize_source_text(match.group("label")),
        "rawLabel": raw_label,
        "quantity": quantity,
        "unit": unit,
        "nutrients": {},
    }, warning


def parse_listing(html: str, base_url: str = DEFAULT_TBCA_URL) -> List[FoodReference]:
    """Extract food references and source-language metadata from a listing page."""
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.find("tbody")
    if tbody is None:
        return []

    foods = []
    for row in tbody.find_all("tr"):
        columns = row.find_all("td")
        if len(columns) < 4:
            continue

        detail_link = columns[0].find("a", href=True)
        if detail_link is None:
            continue

        brand = (
            normalize_metadata_text(columns[4].get_text(" ", strip=True))
            if len(columns) >= 5
            else ""
        )
        foods.append(
            {
                "externalId": normalize_source_text(
                    columns[0].get_text(" ", strip=True)
                ),
                "name": normalize_metadata_text(columns[1].get_text(" ", strip=True)),
                "brand": brand or None,
                "category": normalize_metadata_text(
                    columns[3].get_text(" ", strip=True)
                ),
                "url": urljoin(base_url, detail_link["href"]),
            }
        )
    return foods


def _find_nutrition_table(soup: BeautifulSoup) -> Any:
    for table in soup.find_all("table"):
        head = table.find("thead")
        body = table.find("tbody")
        if head is None or body is None:
            continue
        headers = [
            normalize_source_text(cell.get_text(" ", strip=True))
            for cell in head.find_all("th")
        ]
        if headers[:3] == ["Componente", "Unidades", STANDARD_PORTION_LABEL]:
            return table
    return None


def _description_from_overview(soup: BeautifulSoup, external_id: str) -> str:
    overview = soup.find("h5", {"id": "overview"})
    if overview is None:
        raise ValueError("Detail page has no #overview element for {}".format(external_id))
    description = re.search(
        r"Descrição:\s*(.*?)(?:\s*<<|$)",
        overview.get_text(" ", strip=True),
        re.DOTALL,
    )
    if description is None:
        raise ValueError("Description not found for {}".format(external_id))
    return normalize_metadata_text(description.group(1))


def parse_food_detail(content: bytes, queue_item: FoodReference) -> FoodPayload:
    """Convert a TBCA detail page into the self-contained food contract."""
    soup = BeautifulSoup(content, "html.parser")
    external_id = queue_item["externalId"]
    name = queue_item.get("name") or _description_from_overview(soup, external_id)

    table = _find_nutrition_table(soup)
    if table is None:
        raise ValueError("Nutrition table not found for {}".format(external_id))

    headers = [
        normalize_source_text(cell.get_text(" ", strip=True))
        for cell in table.find("thead").find_all("th")
    ]
    portion_headers = headers[2:]
    portions = [
        {
            "type": "STANDARD",
            "label": "100 g",
            "rawLabel": STANDARD_PORTION_LABEL,
            "quantity": 100,
            "unit": "g",
            "nutrients": {},
        }
    ]
    quality_warnings = []  # type: List[str]
    for raw_label in portion_headers[1:]:
        portion, warning = parse_portion(raw_label)
        portions.append(portion)
        if warning:
            quality_warnings.append(warning)

    unmapped_nutrients = []  # type: List[Dict[str, Any]]
    for row in table.find("tbody").find_all("tr"):
        values = [
            normalize_source_text(cell.get_text(" ", strip=True))
            for cell in row.find_all("td")
        ]
        if len(values) < 2:
            continue

        source_name = values[0]
        unit = normalize_unit(values[1])
        code = nutrient_code(source_name, unit)
        raw_values = values[2:]
        if code is None:
            unmapped_nutrients.append(
                {
                    "name": source_name,
                    "unit": unit,
                    "values": dict(zip(portion_headers, raw_values)),
                }
            )
            quality_warnings.append(
                "Nutrient has no explicit mapping: {!r} ({})".format(
                    source_name, unit
                )
            )
            continue

        for index, portion in enumerate(portions):
            raw_value = raw_values[index] if index < len(raw_values) else ""
            nutrient, is_unknown = parse_nutrient_value(raw_value, unit)
            portion["nutrients"][code] = nutrient
            if is_unknown:
                quality_warnings.append(
                    "Unknown value token for {} in {!r}: {!r}".format(
                        code, portion["rawLabel"], raw_value
                    )
                )

    food = {
        "externalId": external_id,
        "name": normalize_metadata_text(name),
        "brand": normalize_metadata_text(queue_item["brand"])
        if queue_item.get("brand")
        else None,
        "category": normalize_metadata_text(queue_item["category"]),
        "portions": portions,
        "qualityWarnings": quality_warnings,
    }  # type: FoodPayload
    if unmapped_nutrients:
        food["unmappedNutrients"] = unmapped_nutrients
    return food
