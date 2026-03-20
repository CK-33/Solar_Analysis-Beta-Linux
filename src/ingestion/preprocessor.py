# ============================================================
# PREPROCESSOR - Merge Inversor + Dados Climáticos (Tipo B)
# ============================================================
# Replica e generaliza o script manual de pré-processamento
# fornecido pelo usuário. Mantém a resolução original do inversor
# (sem resampling forçado para 1h).
# ============================================================

import os
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

def filtrar_periodo_noturno(df: pd.DataFrame, hora_inicio: int = 6, hora_fim: int = 18) -> pd.DataFrame:
    """
    Zera a geração e a irradiância durante a noite para evitar que ruídos noturnos
    afetem os cálculos posteriores. As linhas são mantidas para não quebrar a 
    continuidade do índice temporal (necessário para médias móveis).
    """
    df_filtrado = df.copy()
    mascara_noite = (df_filtrado.index.hour < hora_inicio) | (df_filtrado.index.hour >= hora_fim)
    
    if 'P MPPT (W)' in df_filtrado.columns:
        df_filtrado.loc[mascara_noite, 'P MPPT (W)'] = 0.0
    if 'Rg Média' in df_filtrado.columns:
        df_filtrado.loc[mascara_noite, 'Rg Média'] = 0.0
        
    return df_filtrado


def _ler_inversor_csv(caminho: str) -> pd.DataFrame:
    """
    Lê CSV do inversor. Suporta múltiplos formatos de coluna de potência.
    Mantém a resolução original (sem resampling).
    """
    df = pd.read_csv(caminho, header=0)

    # Detecta e trata coluna de data/hora
    candidatas_dt = ['Time', 'Datetime', 'datetime', 'Date', 'date',
                     'Timestamp', 'timestamp']
    col_dt = None
    for c in candidatas_dt:
        if c in df.columns:
            col_dt = c
            break
    if col_dt is None:
        # Tenta a primeira coluna
        col_dt = df.columns[0]

    df[col_dt] = pd.to_datetime(df[col_dt], errors='coerce', format='mixed')
    df.dropna(subset=[col_dt], inplace=True)
    df.set_index(col_dt, inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index.name = 'Time'

    # Converte todas as colunas numéricas
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    return df


def _ler_clima_excel(caminho: str, log_callback=None) -> pd.DataFrame:
    """
    Lê arquivo Excel de clima com abas mensais (formato INMET/estação).
    Suporta: Ano + Dia Juliano + Horário  OU  colunas de data normais.
    Converte vírgulas decimais para ponto.
    """
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg)

    xls = pd.ExcelFile(caminho)
    lista = []
    cols_necessarias = ['Ano', 'Dia', 'Horário', 'Chuva', 'Tar med', 'Rg Média']

    for nome_aba in xls.sheet_names:
        if 'ANUAL' in nome_aba.upper():
            continue
        try:
            df_aba = pd.read_excel(xls, sheet_name=nome_aba, header=2)
            df_aba.dropna(how='all', inplace=True)

            if all(c in df_aba.columns for c in ['Ano', 'Dia', 'Horário']):
                cols_existentes = [c for c in cols_necessarias if c in df_aba.columns]
                lista.append(df_aba[cols_existentes].copy())
            else:
                log(f"   -> Aba '{nome_aba}' ignorada (sem Ano/Dia/Horário).")
        except Exception as e:
            log(f"   -> Aba '{nome_aba}' erro: {e}")

    if not lista:
        raise ValueError("Nenhuma aba de clima válida encontrada no Excel.")

    df_clima = pd.concat(lista, ignore_index=True)

    # Converte colunas de data
    for col in ['Ano', 'Dia', 'Horário']:
        df_clima[col] = pd.to_numeric(df_clima[col], errors='coerce')
    df_clima.dropna(subset=['Ano', 'Dia', 'Horário'], inplace=True)

    # Dia Juliano → data gregoriana
    ano_str = df_clima['Ano'].astype(int).astype(str)
    dia_str = df_clima['Dia'].astype(int).astype(str).str.zfill(3)
    df_clima['Data_Base'] = pd.to_datetime(ano_str + dia_str, format='%Y%j')

    # Hora (suporte a 2400 → 00h do dia seguinte)
    horas = df_clima['Horário'].astype(int)
    df_clima['Time'] = df_clima['Data_Base'] + pd.to_timedelta(horas // 100, unit='h')
    df_clima['Time'] = df_clima['Time'].dt.floor('min')
    df_clima.set_index('Time', inplace=True)

    # Limpa colunas de dados (vírgula → ponto e converte para float)
    colunas_dados = [c for c in df_clima.columns
                     if c not in ['Ano', 'Dia', 'Horário', 'Data_Base']]
    for col in colunas_dados:
        if df_clima[col].dtype == 'object':
            df_clima[col] = df_clima[col].astype(str).str.replace(',', '.', regex=False)
        df_clima[col] = pd.to_numeric(df_clima[col], errors='coerce')

    return df_clima[colunas_dados]


def _ler_clima_csv(caminho: str) -> pd.DataFrame:
    """Lê CSV de clima simples com colunas padrão."""
    df = pd.read_csv(caminho)
    # Detecta coluna de data
    for c in ['Time', 'Datetime', 'datetime', 'Date']:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors='coerce', format='mixed')
            df.dropna(subset=[c], inplace=True)
            df.set_index(c, inplace=True)
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df.index.name = 'Time'
            break
    for c in df.columns:
        if df[c].dtype == 'object':
            df[c] = df[c].astype(str).str.replace(',', '.', regex=False)
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def processar_inversor_clima(
    caminho_inversor: str,
    caminho_clima: str,
    col_potencia_inv: str = 'P MPPT (W)',
    log_callback=None,
) -> pd.DataFrame:
    """
    Une dados do inversor com dados climáticos (Tipo B).

    Mantém a resolução temporal original do inversor.
    Usa merge_asof para alinhar o clima (que pode ter resolução diferente).

    Args:
        caminho_inversor: caminho para CSV do inversor
        caminho_clima: caminho para Excel (.xlsx) ou CSV do clima
        col_potencia_inv: nome da coluna de potência no CSV do inversor
        log_callback: função de log

    Returns:
        DataFrame no schema padrão do analisador_core
    """
    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg)

    log(f"📂 Lendo inversor: {os.path.basename(caminho_inversor)}")
    df_inv = _ler_inversor_csv(caminho_inversor)

    # Garante que a coluna de potência existe
    if col_potencia_inv not in df_inv.columns:
        # Tenta achar qualquer coluna de potência
        candidatas = [c for c in df_inv.columns if 'P' in c.upper() or 'POT' in c.upper()]
        if candidatas:
            col_potencia_inv = candidatas[0]
            log(f"   ⚠️  Coluna de potência alternativa usada: '{col_potencia_inv}'")
        else:
            raise ValueError(f"Coluna de potência não encontrada no inversor.")

    df_inv_clean = df_inv[[col_potencia_inv]].copy()
    df_inv_clean.rename(columns={col_potencia_inv: 'P MPPT (W)'}, inplace=True)
    log(f"   ✓ {len(df_inv_clean)} registros de inversor carregados")

    log(f"📂 Lendo clima: {os.path.basename(caminho_clima)}")
    ext = os.path.splitext(caminho_clima)[1].lower()
    if ext in ('.xlsx', '.xls'):
        df_clima = _ler_clima_excel(caminho_clima, log_callback)
    else:
        df_clima = _ler_clima_csv(caminho_clima)
    log(f"   ✓ {len(df_clima)} registros de clima carregados")

    # ---- Merge por proximidade temporal (merge_asof) ----
    # Garante que ambos estão ordenados
    df_inv_clean = df_inv_clean.sort_index()
    df_clima = df_clima.sort_index()

    df_final = pd.merge_asof(
        df_inv_clean.reset_index(),
        df_clima.reset_index(),
        on='Time',
        direction='nearest',
        tolerance=pd.Timedelta('1h'),
    )
    df_final.set_index('Time', inplace=True)
    df_final.dropna(subset=['P MPPT (W)'], inplace=True)

    # Aplica o filtro noturno modular
    df_final = filtrar_periodo_noturno(df_final)

    log(f"   ✓ Merge concluído: {len(df_final)} registros (filtro noturno aplicado)")
    return df_final

