# ☀️ Sistema de Análise Fotovoltaica

Ferramenta para análise de performance de usinas fotovoltaicas, com cálculo de **Fill Factor (FF)** e **Performance Ratio (PR)**, detecção de sujidade por gradiente e alertas automáticos.

## Funcionalidades

- **Cálculo de FF e PR** com médias móveis e variação diária
- **6 gráficos analíticos** (FF vs PR, Correlação, Potência vs Irradiância, Taxas de variação, Validação com chuva, Resíduos PR)
- **Gerenciador de Alertas** com janela deslizante de 2 semanas
- **Detecção de sujidade** por consenso de gradiente FF + PR
- **Detecção de falhas elétricas** (irradiância alta + geração zero)
- **Detecção de falhas de datalogger** (gaps nos dados)
- **Interface gráfica** (tkinter) com tema escuro

## Como usar

### Via GUI (recomendado)
```
run.bat
```
Ou diretamente:
```
python run_gui.py
```

### Via CLI
```
python -m src.main
```

## Instalação

```bash
pip install -r requirements.txt
```

## Estrutura

```
solar_analysis/
├── run_gui.py              # Atalho para iniciar a GUI
├── run.bat                 # Lançador Windows
├── src/
│   ├── config.py           # Parâmetros da planta
│   ├── analisador_core.py  # Cálculo de FF, PR, gráficos
│   ├── gerenciador_alertas.py  # Detecção de sujidade
│   ├── gui.py              # Interface gráfica
│   └── main.py             # CLI interativo
├── dados/                  # Coloque seus CSVs aqui
├── requirements.txt
├── .gitignore
└── README.md
```

## Formato do CSV esperado

| Coluna       | Descrição                          |
|--------------|-------------------------------------|
| `Time`       | Timestamp (`MM.DD.YY HH:MM`)       |
| `Rg Média`   | Irradiância média (W/m²)           |
| `Tar med`    | Temperatura do ar média (°C)       |
| `P MPPT (W)` | Potência no ponto de máxima potência (W) |
