import json
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

caminho_arquivo = "alimentos.json"

url_base = 'https://www.tbca.net.br/base-dados/composicao_alimentos.php'

cod_alimentos = []

parametros = {'pagina': 1}

continuar_loop = True

while continuar_loop:
    response = requests.get(url_base, params=parametros)

    if response.status_code == 200:
        html_content = response.text

        soup = BeautifulSoup(html_content, 'html.parser')

        tbody_element = soup.find('tbody')

        if tbody_element:

            tr_elements = tbody_element.find_all('tr')

            if tr_elements:

                for tr in tr_elements:
                    td_elements = tr.find_all('td')

                    if len(td_elements) < 4:
                        continue

                    link_detalhes = td_elements[0].find('a', href=True)

                    if not link_detalhes:
                        continue

                    codigo = td_elements[0].text.strip()
                    classe = td_elements[3].text.strip()
                    url_detalhes = urljoin(url_base, link_detalhes['href'])
                    cod_alimentos.append((codigo, classe, url_detalhes))
            else:

                continuar_loop = False
        else:

            continuar_loop = False

        parametros['pagina'] += 1

    else:
        continuar_loop = False

cod_alimentos = list(set(cod_alimentos))

result = []

for cod_alimento, classe_alimento, url_detalhes in cod_alimentos:

    response = requests.get(url_detalhes)

    soup = BeautifulSoup(response.content, 'html.parser')

    description_element = soup.find('h5', {'id': 'overview'})
    descricao = description_element.text.split('Descrição:')[1].split('<<')[0].strip()

    table = soup.find('table')

    thead = table.find('thead')
    headers = [header.text.strip() for header in thead.find_all('th')]
    headers_nutrientes = headers[:3]
    headers_porcoes = headers[3:]

    tbody = table.find('tbody')
    rows = tbody.find_all('tr')

    nutrientes = []

    for row in rows:
        values = [value.text.strip() for value in row.find_all('td')]

        if len(values) < len(headers_nutrientes):
            continue

        row_data = dict(zip(headers_nutrientes, values[:3]))
        row_data['porcoes'] = dict(zip(headers_porcoes, values[3:]))
        nutrientes.append(row_data)

    alimento_json = {
        'codigo': cod_alimento,
        'classe': classe_alimento,
        'descricao': descricao,
        'porcoes': headers_porcoes,
        'nutrientes': nutrientes
    }

    result.append(alimento_json)

with open(caminho_arquivo, "w", encoding="utf-8") as file:
    json.dump(result, file, ensure_ascii=False, indent=2)
