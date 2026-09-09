
# Tabela Brasileira de Composição de Alimentos - Web Scraping - Download 

Este projeto consiste em um web scraping que obtém as informações da Tabela Brasileira de Composição de Alimentos (TBCA) e as armazena em um arquivo JSON. O objetivo principal é disponibilizar os dados nutricionais de mais de 5.500 alimentos em um formato fácil de ser utilizado por outros aplicativos ou sistemas.



## Requisitos

[![Python](https://img.shields.io/badge/Python-3.8-blue)](https://www.python.org/downloads/release/python-380/)
[![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup-4.12.2-brightgreen)](https://pypi.org/project/beautifulsoup4/)



## Uso dos Dados
O arquivo `alimentos.json` contém os dados nutricionais dos alimentos em uma lista JSON. Ele pode ser facilmente importado e utilizado em outros aplicativos, sistemas ou projetos relacionados à nutrição.

Quando a TBCA disponibiliza medidas caseiras para um alimento, o campo `porcoes`
do alimento lista essas medidas e cada nutriente contém os valores correspondentes:

```json
{
  "codigo": "BRC0001G",
  "classe": "Leite e derivados",
  "descricao": "Bebida láctea (média de diferentes sabores), Brasil",
  "porcoes": [
    "Copo americano duplo (240 mL)",
    "Copo americano pequeno (165 mL)"
  ],
  "nutrientes": [
    {
      "Componente": "Energia",
      "Unidades": "kJ",
      "Valor por 100g": "286",
      "porcoes": {
        "Copo americano duplo (240 mL)": "686",
        "Copo americano pequeno (165 mL)": "471"
      }
    }
  ]
}
```
