# ============================================================
# IRRADIANCE API - Busca irradiância e temperatura via Open-Meteo
# ============================================================

import pandas as pd
import requests


def buscar_irradiancia_api(
    data_inicio: pd.Timestamp,
    data_fim: pd.Timestamp,
    lat: float,
    lon: float,
    intervalo_min: int = 60,
    log_callback=None,
) -> pd.DataFrame:
    """
    Busca irradiância (shortwave_radiation) e temperatura (temperature_2m)
    da API Open-Meteo Archive para o período e localização dados.

    Args:
        data_inicio, data_fim: período dos dados do inversor
        lat, lon: coordenadas da planta (de CONFIG_SISTEMA)
        intervalo_min: resolução dos dados do inversor (para interpolação)
        log_callback: função de log opcional

    Returns:
        DataFrame indexado por datetime com colunas:
            'Rg Média'  (W/m²)
            'Tar med'   (°C)
        Dados interpolados para a resolução do inversor.
    """

    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg)

    log("🌐 Buscando dados de irradiância e temperatura via Open-Meteo...")

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": data_inicio.strftime('%Y-%m-%d'),
        "end_date": data_fim.strftime('%Y-%m-%d'),
        "hourly": ["shortwave_radiation", "temperature_2m"],
        "timezone": "auto",
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if 'hourly' not in data:
            raise ValueError("Resposta da API sem campo 'hourly'.")

        idx = pd.to_datetime(data['hourly']['time'])
        if idx.tz is not None:
            idx = idx.tz_localize(None)

        df_api = pd.DataFrame({
            'Rg Média': data['hourly']['shortwave_radiation'],
            'Tar med':  data['hourly']['temperature_2m'],
        }, index=idx)

        df_api.index.name = 'Time'
        log(f"   ✓ {len(df_api)} registros horários baixados da API")

        # ---- Interpola para a resolução do inversor ----
        if intervalo_min < 60:
            freq_str = f"{intervalo_min}min"
            # Cria um índice na resolução alvo dentro do mesmo período
            novo_idx = pd.date_range(
                start=df_api.index.min(),
                end=df_api.index.max(),
                freq=freq_str,
            )
            df_api = df_api.reindex(df_api.index.union(novo_idx))
            df_api = df_api.interpolate(method='time')
            df_api = df_api.reindex(novo_idx)
            log(f"   ✓ Interpolado para resolução de {intervalo_min} min "
                f"({len(df_api)} registros)")

        df_api.index.name = 'Time'
        return df_api

    except requests.RequestException as e:
        log(f"   ❌ Erro de conexão com API Open-Meteo: {e}")
        return pd.DataFrame(columns=['Rg Média', 'Tar med'])
    except Exception as e:
        log(f"   ❌ Erro ao processar resposta da API: {e}")
        return pd.DataFrame(columns=['Rg Média', 'Tar med'])
