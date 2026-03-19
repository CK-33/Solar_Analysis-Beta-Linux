# ☀️ Sistema de Análise Fotovoltaica (BETA)

> **⚠️ VERSÃO BETA**: Este software está em fase de testes (Beta). Existem problemas e erros conhecidos mapeados para correção em futuras atualizações.

Ferramenta para análise de performance de usinas fotovoltaicas, com cálculo de **Fill Factor (FF)** e **Performance Ratio (PR)**, detecção de sujidade por gradiente e alertas automáticos.

## Funcionalidades

- **Módulo de Ingestão de Dados**: Suporta múltiplos formatos, mesclagem inteligente e requisição de dados faltantes (temperatura) via API Open-Meteo.
- **Cálculo de FF e PR** com médias móveis dinâmicas para qualquer resolução temporal (15 min, 1h, etc.)
- **6 gráficos analíticos** (FF vs PR, Correlação, Potência vs Irradiância, Taxas de variação, Validação com chuva, Resíduos PR)
- **Gerenciador de Alertas** com janela deslizante e detecção de sujidade por consenso
- **Interface Gráfica Integrada** com Assistente (Wizard) de Importação de Dados.

## Instalação (Ubuntu/Linux)

### 1. Dependências do sistema
```bash
sudo apt update
sudo apt install python3 python3-pip python3-tk python3-venv -y
```

### 2. Ambiente Virtual (Recomendado)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Como usar

### Via GUI (recomendado)
```bash
chmod +x run.sh
./run.sh
```

## Estrutura

```
solar_analysis/
├── run_gui.py              # Atalho para iniciar a GUI
├── run.sh                  # Lançador Linux/Ubuntu
├── src/
│   ├── config.py           # Parâmetros da planta e alertas
│   ├── analisador_core.py  # Cálculo matemático e métricas
│   ├── gerenciador_alertas.py  # Detecção de sujidade
│   ├── gui.py              # Interface gráfica principal
│   ├── main.py             # CLI interativo
│   └── ingestion/          # Módulo de pré-processamento de dados
│       ├── adapters.py
│       ├── detector.py
│       ├── gui_wizard.py
│       ├── irradiance_api.py
│       └── preprocessor.py
```

## Formato Interno Padrão

O sistema unifica os dados importados para a seguinte estrutura base:

| Coluna       | Descrição                          |
|--------------|-------------------------------------|
| `Time`       | Timestamp (Formato automático)     |
| `Rg Média`   | Irradiância média (W/m²)           |
| `Tar med`    | Temperatura do ar média (°C)       |
| `P MPPT (W)` | Potência no ponto de máxima potência (W) |
