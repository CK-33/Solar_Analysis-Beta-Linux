# ============================================================
# ADAPTERS - Converte diferentes formatos para o schema padrão
# ============================================================

import pandas as pd
import numpy as np
from .irradiance_api import buscar_irradiancia_api


def adaptar_dataset(
    df_raw: pd.DataFrame,
    mapeamento: dict,
    buscar_api: bool = False,
    lat: float = None,
    lon: float = None,
    log_callback=None,
) -> pd.DataFrame:
    """
    Recebe um DataFrame bruto e o mapeamento de colunas, e retorna
    o DataFrame no schema padrão esperado pelo analisador_core.

    Schema Padrão: Index (Time), 'P MPPT (W)', 'Rg Média', 'Tar med'

    Args:
        df_raw: DataFrame original (já com Time como index)
        mapeamento: Dict de mapeamento {col_origem: col_destino}
        buscar_api: Se True, busca irradiância/temperatura via API se faltarem
        lat, lon: Coordenadas para busca na API
        log_callback: Função de log opcional

    Returns:
        DataFrame processado no schema padrão.
    """

    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg)

    df = df_raw.copy()
    colunas_finais = {}

    # 1. Trata Potência (P MPPT (W))
    # Caso 1: Coluna direta
    for col_orig, col_dest in mapeamento.items():
        if col_dest == 'P MPPT (W)':
            colunas_finais['P MPPT (W)'] = df[col_orig]
            break

    # Caso 2: Cálculo V × I (colunas compostas)
    if 'P MPPT (W)' not in colunas_finais:
        v_col = next((k for k, v in mapeamento.items() if v == '__Vdc__'), None)
        i_col = next((k for k, v in mapeamento.items() if v == '__Idc__'), None)
        if v_col and i_col:
            log(f"⚡ Calculando Potência: {v_col} × {i_col} → P MPPT (W)")
            colunas_finais['P MPPT (W)'] = df[v_col] * df[i_col]

    if 'P MPPT (W)' not in colunas_finais:
        raise ValueError("Coluna de potência não identificada ou incompleta.")

    # 2. Trata Irradiância (Rg Média)
    col_irrad = next((k for k, v in mapeamento.items() if v == 'Rg Média'), None)
    if col_irrad:
        colunas_finais['Rg Média'] = df[col_irrad]

    # 3. Trata Temperatura (Tar med)
    col_temp = next((k for k, v in mapeamento.items() if v == 'Tar med'), None)
    if col_temp:
        colunas_finais['Tar med'] = df[col_temp]

    # Cria DataFrame base
    df_adaptado = pd.DataFrame(colunas_finais, index=df.index)
    df_adaptado.index.name = 'Time'

    # 4. Busca API se necessário
    if buscar_api and (lat is not None and lon is not None):
        precisa_irrad = 'Rg Média' not in colunas_finais
        precisa_temp = 'Tar med' not in colunas_finais

        if precisa_irrad or precisa_temp:
            from .detector import detectar_intervalo_minutos
            intervalo = detectar_intervalo_minutos(df)
            
            df_api = buscar_irradiancia_api(
                data_inicio=df.index.min(),
                data_fim=df.index.max(),
                lat=lat,
                lon=lon,
                intervalo_min=intervalo,
                log_callback=log_callback
            )

            if not df_api.empty:
                # Remove da API o que já temos localmente (para evitar '_x' e '_y')
                colunas_api_manter = [c for c in df_api.columns if c not in df_adaptado.columns]
                
                if colunas_api_manter:
                    df_adaptado = pd.merge_asof(
                        df_adaptado.sort_index().reset_index(),
                        df_api[colunas_api_manter].sort_index().reset_index(),
                        on='Time',
                        direction='nearest',
                        tolerance=pd.Timedelta('1h')
                    ).set_index('Time')
                    log("   ✓ Dados ausentes (API) integrados ao dataset.")
                else:
                    log("   ✓ Nenhuma nova coluna da API necessária.")
            else:
                log("   ⚠️ Falha ao obter dados da API.")

    # Garante que temos as colunas, mesmo que vazias (evita quebra no core)
    for col in ['Rg Média', 'Tar med']:
        if col not in df_adaptado.columns:
            df_adaptado[col] = np.nan

    # Limpeza final: remove NaNs na potência (essencial)
    df_adaptado.dropna(subset=['P MPPT (W)'], inplace=True)
    
    return df_adaptado
