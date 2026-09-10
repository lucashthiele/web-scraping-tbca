DEFAULT_TBCA_URL = "https://www.tbca.net.br/base-dados/composicao_alimentos.php"
CHECKPOINT_ID = "tbca_import"
SCHEMA_VERSION = 2
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# TBCA source names intentionally remain in Portuguese. The mapping is explicit so
# unknown components are never translated or silently assigned an invented code.
NUTRIENT_CODES = {
    "Umidade": "humidity",
    "Carboidrato total": "carbohydrate",
    "Carboidrato disponível": "available_carbohydrate",
    "Proteína": "protein",
    "Proteína animal": "animal_protein",
    "Proteína vegetal": "plant_protein",
    "Lipídios": "lipids",
    "Fibra alimentar": "dietary_fiber",
    "Álcool": "alcohol",
    "Cinzas": "ashes",
    "Colesterol": "cholesterol",
    "Ácidos graxos saturados": "saturated_fat",
    "Ácidos graxos monoinsaturados": "monounsaturated_fat",
    "Ácidos graxos poliinsaturados": "polyunsaturated_fat",
    "Ácidos graxos trans": "trans_fat",
    "Cálcio": "calcium",
    "Ferro": "iron",
    "Sódio": "sodium",
    "Magnésio": "magnesium",
    "Fósforo": "phosphorus",
    "Potássio": "potassium",
    "Manganês": "manganese",
    "Zinco": "zinc",
    "Cobre": "copper",
    "Selênio": "selenium",
    "Vitamina A (RE)": "vitamin_a_re",
    "Vitamina A (RAE)": "vitamin_a_rae",
    "Vitamina D": "vitamin_d",
    "Alfa-tocoferol (Vitamina E)": "vitamin_e",
    "Tiamina": "thiamine",
    "Riboflavina": "riboflavin",
    "Niacina": "niacin",
    "Vitamina B6": "vitamin_b6",
    "Vitamina B12": "vitamin_b12",
    "Vitamina C": "vitamin_c",
    "Equivalente de folato": "folate_equivalent",
    "Sal de adição": "added_salt",
    "Açúcar de adição": "added_sugar",
    "Gordura de adição": "added_fat",
}
