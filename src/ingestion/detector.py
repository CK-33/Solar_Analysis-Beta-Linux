# ============================================================
# DETECTOR - Identifica o formato/tipo do dataset de entrada
# ============================================================

import pandas as pd
import numpy as np
from pathlib import Path


# Schema padrão esperado pelo analisador_core
SCHEMA_PADRAO = {'P MPPT (W)', 'Rg Média', 'Tar med'}

# Mapeamentos conhecidos de colunas alternativas → schema padrão
MAPEAMENTOS_CONHECIDOS = {
    # Potência: cálculo de P = V × I (quando colunas separadas)
    'potencia': {
        'diretas': ['P MPPT (W)', 'Pac', 'P_ac', 'Power', 'Potencia', 'P(W)', 'P_out', 'Pdc1', 'P_dc', 'Pdc'],
        'compostas': [('Vdc1', 'Idc1'), ('Vdc', 'Idc'), ('V_dc', 'I_dc'),
                      ('Tensao', 'Corrente'), ('V', 'I')],
    },
    # Irradiância
    'irradiancia': {
        'diretas': ['Rg Média', 'Rg_Media', 'Irradiancia', 'Irradiance',
                    'GHI', 'POA', 'G', 'Irr', 'Solar', 'Rad'],
    },
    # Temperatura
    'temperatura': {
        'diretas': ['Tar med', 'Tar_med', 'Temperatura', 'Temperature',
                    'T_amb', 'Tamb', 'Temp', 'T_air', 'T (°C)'],
    },
}


def detectar_intervalo_minutos(df: pd.DataFrame) -> int:
    """Detecta o intervalo de amostragem predominante em minutos."""
    if len(df) < 2:
        return 60
    deltas = df.index.to_series().diff().dt.total_seconds().dropna() / 60
    # Usa a mediana para ignorar possíveis gaps
    intervalo = int(deltas[deltas > 0].median())
    return max(1, intervalo)


def detectar_formato(df: pd.DataFrame) -> dict:
    """
    Analisa as colunas do DataFrame e retorna um dict descrevendo:
      - tipo: 'A' (pré-processado), 'B_C' (inversor bruto)
      - mapeamento: {col_origem: col_destino}  (editável pelo usuário)
      - tem_irradiancia: bool
      - tem_temperatura: bool
      - intervalo_min: int
      - colunas_compostas_potencia: tuple ou None
    """
    colunas = set(df.columns)
    resultado = {
        'tipo': None,
        'mapeamento': {},
        'tem_irradiancia': False,
        'tem_temperatura': False,
        'intervalo_min': detectar_intervalo_minutos(df),
        'colunas_compostas_potencia': None,
    }

    # ---- Tipo A: já tem schema padrão? ----
    if SCHEMA_PADRAO.issubset(colunas):
        resultado['tipo'] = 'A'
        resultado['mapeamento'] = {c: c for c in SCHEMA_PADRAO}
        resultado['tem_irradiancia'] = True
        resultado['tem_temperatura'] = True
        return resultado

    # ---- Tenta mapear potência ----
    mapa = {}

    # Potência direta
    encontrou_potencia = False
    for col in MAPEAMENTOS_CONHECIDOS['potencia']['diretas']:
        if col in colunas:
            mapa[col] = 'P MPPT (W)'
            encontrou_potencia = True
            break

    # Potência composta (V × I)
    if not encontrou_potencia:
        for v_col, i_col in MAPEAMENTOS_CONHECIDOS['potencia']['compostas']:
            if v_col in colunas and i_col in colunas:
                mapa[v_col] = '__Vdc__'
                mapa[i_col] = '__Idc__'
                resultado['colunas_compostas_potencia'] = (v_col, i_col)
                encontrou_potencia = True
                break

    # ---- Tenta mapear irradiância ----
    for col in MAPEAMENTOS_CONHECIDOS['irradiancia']['diretas']:
        if col in colunas:
            mapa[col] = 'Rg Média'
            resultado['tem_irradiancia'] = True
            break

    # ---- Tenta mapear temperatura ----
    for col in MAPEAMENTOS_CONHECIDOS['temperatura']['diretas']:
        if col in colunas:
            mapa[col] = 'Tar med'
            resultado['tem_temperatura'] = True
            break

    resultado['mapeamento'] = mapa
    resultado['tipo'] = 'A' if resultado['tem_irradiancia'] else 'B_C'

    return resultado


def carregar_csv_raw(caminho: str) -> pd.DataFrame:
    """
    Carrega um CSV inferindo a coluna de data/hora automaticamente.
    Suporta: 'Time', 'Datetime', 'date', 'timestamp', etc.
    """
    df = pd.read_csv(caminho)

    # Tenta encontrar coluna de data/hora
    candidatas_dt = ['Time', 'Datetime', 'datetime', 'Date', 'date',
                     'Timestamp', 'timestamp', 'DATA', 'DATETIME']
    col_dt = None
    for c in candidatas_dt:
        if c in df.columns:
            col_dt = c
            break

    if col_dt is None:
        # Tentativa: primeira coluna que converte para datetime
        for c in df.columns:
            try:
                pd.to_datetime(df[c].iloc[:5])
                col_dt = c
                break
            except Exception:
                continue

    if col_dt is None:
        raise ValueError(
            "Não foi possível identificar a coluna de data/hora no CSV.\n"
            "Certifique-se de que há uma coluna chamada 'Time', 'Datetime', etc."
        )

    df[col_dt] = pd.to_datetime(df[col_dt], errors='coerce')
    df.dropna(subset=[col_dt], inplace=True)
    df.set_index(col_dt, inplace=True)
    
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
        
    df.index.name = 'Time'
    return df
