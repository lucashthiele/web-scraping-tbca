import unittest

from tbca_scraper.cli import parse_args
from tbca_scraper.http import TbcaClient
from tbca_scraper.parsing import (
    parse_food_detail,
    parse_listing,
    parse_nutrient_value,
    parse_portion,
)


# Portuguese text in these fixtures represents source data returned by TBCA and
# must be preserved by the scraper.
LISTING_HTML = """
<table><tbody>
<tr><td><a href="detail.php?id=1">BRC0001</a></td><td>Alimento , Brasil</td><td></td><td>Frutas e derivados</td><td></td></tr>
<tr><td><a href="detail.php?id=2">BRC0002</a></td><td>Achocolatado</td><td></td><td>Açúcares e doces</td><td>Nescau</td></tr>
</tbody></table>
"""

DETAIL_HTML = """
<h5 id="overview">Descrição: Alimento de teste &lt;&lt; Test food &gt;&gt;</h5>
<table>
  <thead><tr><th>Componente</th><th>Unidades</th><th>Valor por 100g</th><th>Colher sopa cheia (20 g)</th><th>Copo (200 mL)</th></tr></thead>
  <tbody>
    <tr><td>Energia</td><td>kcal</td><td>100</td><td>20</td><td>200</td></tr>
    <tr><td>Energia</td><td>kJ</td><td>418</td><td>84</td><td>836</td></tr>
    <tr><td>Proteína</td><td>g</td><td>1,15</td><td>tr</td><td>NA</td></tr>
    <tr><td>Componente novo</td><td>mg</td><td>7</td><td>1,4</td><td>14</td></tr>
  </tbody>
</table>
"""


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient(TbcaClient):
    def __init__(self, pages):
        self.pages = pages
        self.requested_pages = []

    def get(self, url, params=None):
        page = params["pagina"]
        self.requested_pages.append(page)
        return FakeResponse(self.pages.get(page, "<table><tbody></tbody></table>"))


class ScraperTests(unittest.TestCase):
    def test_listing_preserves_source_metadata(self):
        foods = parse_listing(LISTING_HTML, "https://example.test/list/")

        self.assertEqual(["BRC0001", "BRC0002"], [food["externalId"] for food in foods])
        self.assertEqual("Alimento, Brasil", foods[0]["name"])
        self.assertEqual("Frutas e derivados", foods[0]["category"])
        self.assertIsNone(foods[0]["brand"])
        self.assertEqual("Nescau", foods[1]["brand"])
        self.assertEqual("https://example.test/list/detail.php?id=1", foods[0]["url"])

    def test_food_detail_uses_self_contained_portions(self):
        food = parse_food_detail(
            DETAIL_HTML.encode("utf-8"),
            {
                "externalId": "BRC0001",
                "name": "Alimento de teste",
                "brand": None,
                "category": "Frutas e derivados",
            },
        )

        self.assertEqual("BRC0001", food["externalId"])
        self.assertEqual("Alimento de teste", food["name"])
        self.assertEqual(3, len(food["portions"]))
        standard = food["portions"][0]
        self.assertEqual(
            {
                "type": "STANDARD",
                "label": "100 g",
                "rawLabel": "Valor por 100g",
                "quantity": 100,
                "unit": "g",
            },
            {key: value for key, value in standard.items() if key != "nutrients"},
        )
        self.assertEqual(100, standard["nutrients"]["energy_kcal"]["amount"])
        self.assertEqual(418, standard["nutrients"]["energy_kj"]["amount"])
        self.assertEqual(1.15, standard["nutrients"]["protein"]["amount"])

        household = food["portions"][1]
        self.assertEqual("Colher sopa cheia", household["label"])
        self.assertEqual(20, household["quantity"])
        self.assertEqual("g", household["unit"])
        self.assertEqual("TRACE", household["nutrients"]["protein"]["status"])
        self.assertEqual(
            "NOT_ANALYZED",
            food["portions"][2]["nutrients"]["protein"]["status"],
        )
        self.assertEqual("Componente novo", food["unmappedNutrients"][0]["name"])
        self.assertTrue(food["qualityWarnings"])

    def test_food_without_household_portions_still_has_standard_portion(self):
        detail = """
        <h5 id="overview">Descrição: Apenas padrão</h5>
        <table><thead><tr><th>Componente</th><th>Unidades</th><th>Valor por 100g</th></tr></thead>
        <tbody><tr><td>Sódio</td><td>mg</td><td>-</td></tr></tbody></table>
        """
        food = parse_food_detail(
            detail.encode("utf-8"),
            {"externalId": "BRC9", "category": "Frutas e derivados"},
        )

        self.assertEqual(1, len(food["portions"]))
        self.assertEqual([], food["qualityWarnings"])
        self.assertEqual(
            "NOT_AVAILABLE", food["portions"][0]["nutrients"]["sodium"]["status"]
        )

    def test_invalid_portion_keeps_quantity_without_inventing_unit(self):
        portion, warning = parse_portion("Colher sopa cheia (9 )")

        self.assertEqual("Colher sopa cheia (9 )", portion["rawLabel"])
        self.assertEqual("Colher sopa cheia", portion["label"])
        self.assertEqual(9, portion["quantity"])
        self.assertIsNone(portion["unit"])
        self.assertIsNotNone(warning)

    def test_portion_supports_nested_labels_and_decimal_quantities(self):
        nested, nested_warning = parse_portion(
            "Pedaço/ Unidade/ Fatia (M) (370 g)"
        )
        decimal, decimal_warning = parse_portion("Colher café cheia (2.3 g)")

        self.assertEqual("Pedaço/ Unidade/ Fatia (M)", nested["label"])
        self.assertEqual(370, nested["quantity"])
        self.assertIsNone(nested_warning)
        self.assertEqual(2.3, decimal["quantity"])
        self.assertIsNone(decimal_warning)

    def test_unknown_nutrient_value_is_preserved(self):
        nutrient, is_unknown = parse_nutrient_value("ND", "mg")

        self.assertTrue(is_unknown)
        self.assertEqual(
            {"amount": None, "unit": "mg", "status": "UNKNOWN", "rawValue": "ND"},
            nutrient,
        )

    def test_max_pages_never_requests_next_page(self):
        client = FakeClient({1: LISTING_HTML, 2: LISTING_HTML, 3: LISTING_HTML})
        foods = client.list_foods(max_pages=2, url="https://example.test/list")
        self.assertEqual([1, 2], client.requested_pages)
        self.assertEqual(2, len(foods))

    def test_unlimited_stops_on_empty_page(self):
        client = FakeClient({1: LISTING_HTML})
        client.list_foods(url="https://example.test/list")
        self.assertEqual([1, 2], client.requested_pages)

    def test_invalid_page_limit_is_rejected(self):
        with self.assertRaises(SystemExit):
            parse_args(["--max-pages", "0"])


if __name__ == "__main__":
    unittest.main()
