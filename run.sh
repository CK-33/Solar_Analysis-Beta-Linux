#!/bin/bash
# ============================================================
# Lançador do Sistema de Análise Fotovoltaica (Ubuntu/Linux)
# ============================================================

# Muda para o diretório do script, independente de onde foi chamado
cd "$(dirname "$0")"

# Ativa o ambiente virtual se existir
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Verifica se python3 está disponível
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 não encontrado. Instale com: sudo apt install python3"
    exit 1
fi

# Verifica se o módulo tkinter está disponível
if ! python3 -c "import tkinter" &> /dev/null; then
    echo "❌ tkinter não encontrado. Instale com: sudo apt install python3-tk"
    exit 1
fi

echo "☀️  Iniciando Sistema de Análise Fotovoltaica..."
python3 run_gui.py
