# ============================================================
# ANALISADOR CORE - Cálculo de FF, PR e Gráficos
# ============================================================

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Backend não-interativo para salvar figuras
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy import stats
import requests

from src.config import CONFIG_SISTEMA


# ============================================================
# 1. UTILIDADES
# ============================================================

def selecionar_arquivo(diretorio="."):
    """Busca arquivos .csv com 'Processados' no nome do diretório dado."""
    arquivos = [f for f in os.listdir(diretorio) if f.endswith('.csv')]
    if not arquivos:
        print("Nenhum arquivo CSV encontrado.")
        return None

    print("\n--- Arquivos Disponíveis ---")
    for i, arq in enumerate(arquivos):
        print(f"[{i}] {arq}")

    try:
        idx = int(input("\nSelecione o número do arquivo: "))
        return os.path.join(diretorio, arquivos[idx])
    except Exception:
        print("Seleção inválida.")
        return None


def selecionar_graficos():
    """Menu interativo para seleção de gráficos."""
    opcoes = {
        1: "FF vs PR Lado a Lado",
        2: "Correlação Scatter",
        3: "Potência vs Irradiância",
        4: "Taxas de Variação",
        5: "Validação com Chuva",
        6: "Resíduos PR",
    }

    print("\n=== Escolha os gráficos que deseja gerar ===")
    for k, v in opcoes.items():
        print(f"[{k}] {v}")

    print("\nDigite os números separados por vírgula (ex: 1,3,5)")
    print("Digite 'all' para gerar todos.")

    escolha = input("Sua escolha: ")

    if escolha.lower() == "all":
        return list(opcoes.keys())

    try:
        selecionados = [int(x.strip()) for x in escolha.split(",")]
        return [x for x in selecionados if x in opcoes]
    except Exception:
        return []


def carregar_dados(caminho_arquivo):
    """Carrega CSV e converte coluna Time para datetime."""
    df = pd.read_csv(caminho_arquivo)
    df['Time'] = pd.to_datetime(df['Time'], format='%m.%d.%y %H:%M')
    df.set_index('Time', inplace=True)
    return df


def obter_chuva_historica(data_inicio, data_fim, config):
    """Busca dados pluviométricos da API OpenMeteo."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": config["lat"],
        "longitude": config["lon"],
        "start_date": data_inicio.strftime('%Y-%m-%d'),
        "end_date": data_fim.strftime('%Y-%m-%d'),
        "daily": "precipitation_sum",
        "timezone": "auto"
    }

    try:
        print("Buscando histórico de chuva...")
        response = requests.get(url, params=params, timeout=15).json()

        df_chuva = pd.DataFrame({
            'Chuva_mm': response['daily']['precipitation_sum']
        }, index=pd.to_datetime(response['daily']['time']))

        return df_chuva
    except Exception:
        print("⚠️  Erro ao buscar dados de chuva (API indisponível ou sem conexão).")
        return pd.DataFrame()


def formatar_eixo_datas(ax, config):
    """Formata eixo X com datas legíveis."""
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=config["intervalo_grid"]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')


# ============================================================
# 2. CÁLCULOS PRINCIPAIS
# ============================================================

def calcular_metricas(df, config):
    """
    Calcula FF, PR, médias móveis e variações diárias.
    Retorna (df_com_metricas, mascara_solar).
    """
    G = pd.to_numeric(df['Rg Média'], errors='coerce')
    T = pd.to_numeric(df['Tar med'], errors='coerce')
    P_mp = pd.to_numeric(df['P MPPT (W)'], errors='coerce')

    # Corrente de curto-circuito corrigida
    df['I_SC_Calc'] = (G / config["G_ref"]) * (
        config["I_sc_ref"] + config["alpha"] * (T - config["T_ref"])
    )

    # Tensão de circuito aberto corrigida
    term_log = np.where(G > 2, np.log(G / config["G_ref"]), 0)
    voc_termico = config["V_oc_ref"] * (1 + config["beta"] * (T - config["T_ref"]))
    df['V_OC_Calc'] = np.where(G > 2, voc_termico + term_log, 0)

    # Potência máxima teórica
    df['P_MAX_Calc'] = df['V_OC_Calc'] * df['I_SC_Calc']

    # Fill Factor
    df['FF'] = 0.0
    mask_valid_ff = df['P_MAX_Calc'] > 1
    df.loc[mask_valid_ff, 'FF'] = P_mp[mask_valid_ff] / df.loc[mask_valid_ff, 'P_MAX_Calc']

    df['FF_valido'] = df['FF'].where((df['FF'] > 0) & (df['FF'] < 1), np.nan)

    df['FF_MediaMovel'] = df['FF_valido'].rolling(
        window=config["janela_mm"], min_periods=24
    ).mean()

    df['FF_Variacao_Diaria'] = df['FF_MediaMovel'].diff(periods=24)

    # Máscara solar: ignora registros com baixa irradiância e fora do horário solar
    mask_sol = (G > 50) & (df.index.hour >= 6) & (df.index.hour <= 18)

    # Performance Ratio
    df['PR'] = np.nan
    df.loc[mask_sol, 'PR'] = P_mp[mask_sol] / (
        config["P_nominal"] * (G[mask_sol] / 1000)
    )

    df['PR'] = df['PR'].clip(0, 1.1)

    df['PR_MediaMovel'] = df['PR'].rolling(
        window=config["janela_mm"], min_periods=24
    ).mean()

    df['PR_Variacao_Diaria'] = df['PR_MediaMovel'].diff(periods=24)

    return df, mask_sol


def agregar_dados_diarios(df, mask_sol, config):
    """Agrega dados horários em dados diários e junta com chuva."""
    df_diario = df[mask_sol].resample('D').agg({
        'FF_valido': 'mean',
        'PR': 'mean',
        'P MPPT (W)': 'sum',
        'Rg Média': 'mean'
    })

    df_diario.columns = ['FF_Diario', 'PR_Diario', 'Energia_Wh', 'G_Media']

    df_chuva = obter_chuva_historica(
        df_diario.index.min(),
        df_diario.index.max(),
        config
    )

    if not df_chuva.empty:
        df_diario = df_diario.join(df_chuva)

    return df_diario


# ============================================================
# 3. GRÁFICOS (6 funções)
# ============================================================

def grafico_ff_pr_lado_a_lado(df, config, pasta_saida, log_callback=None):
    """Gráfico 1: FF vs PR lado a lado em subplots."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

    # FF
    ax1.scatter(df.index, df['FF_valido'], alpha=0.1, s=2, color='purple', label='FF instantâneo')
    ax1.plot(df.index, df['FF_MediaMovel'], color='darkviolet', linewidth=2, label='FF Média Móvel')
    ax1.set_ylabel('Fill Factor (FF)', fontsize=12)
    ax1.set_title('Evolução do Fill Factor (FF)', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, 1)

    # PR
    ax2.scatter(df.index, df['PR'], alpha=0.1, s=2, color='royalblue', label='PR instantâneo')
    ax2.plot(df.index, df['PR_MediaMovel'], color='darkblue', linewidth=2, label='PR Média Móvel')
    ax2.set_ylabel('Performance Ratio (PR)', fontsize=12)
    ax2.set_xlabel('Tempo', fontsize=12)
    ax2.set_title('Evolução do Performance Ratio (PR)', fontsize=14, fontweight='bold')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(0, 1.1)

    formatar_eixo_datas(ax2, config)
    plt.tight_layout()

    caminho = os.path.join(pasta_saida, '1_FF_vs_PR_Lado_a_Lado.png')
    plt.savefig(caminho, dpi=150, bbox_inches='tight')
    plt.close()

    msg = f"   ✓ Salvo: {os.path.basename(caminho)}"
    print(msg)
    if log_callback:
        log_callback(msg)
    return caminho


def grafico_correlacao_scatter(df, config, pasta_saida, log_callback=None):
    """Gráfico 2: Correlação Scatter FF vs PR, colorido por irradiância."""
    mask = df['FF_valido'].notna() & df['PR'].notna() & (df['PR'] > 0)
    ff_vals = df.loc[mask, 'FF_valido']
    pr_vals = df.loc[mask, 'PR']
    g_vals = pd.to_numeric(df.loc[mask, 'Rg Média'], errors='coerce')

    fig, ax = plt.subplots(figsize=(10, 8))

    scatter = ax.scatter(ff_vals, pr_vals, c=g_vals, cmap='plasma',
                         alpha=0.3, s=5, edgecolors='none')
    plt.colorbar(scatter, ax=ax, label='Irradiância (W/m²)')

    # Regressão linear
    if len(ff_vals) > 10:
        slope, intercept, r_value, _, _ = stats.linregress(ff_vals, pr_vals)
        x_line = np.linspace(ff_vals.min(), ff_vals.max(), 100)
        ax.plot(x_line, slope * x_line + intercept, color='red', linewidth=2,
                label=f'Regressão (R²={r_value**2:.3f})')
        ax.legend(fontsize=11)

    ax.set_xlabel('Fill Factor (FF)', fontsize=12)
    ax.set_ylabel('Performance Ratio (PR)', fontsize=12)
    ax.set_title('Correlação FF vs PR', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    caminho = os.path.join(pasta_saida, '2_Correlacao_Scatter.png')
    plt.savefig(caminho, dpi=150, bbox_inches='tight')
    plt.close()

    msg = f"   ✓ Salvo: {os.path.basename(caminho)}"
    print(msg)
    if log_callback:
        log_callback(msg)
    return caminho


def grafico_potencia_vs_irradiancia(df, config, pasta_saida, log_callback=None):
    """Gráfico 3: Potência vs Irradiância (clipping), colorido por hora do dia."""
    G = pd.to_numeric(df['Rg Média'], errors='coerce')
    P = pd.to_numeric(df['P MPPT (W)'], errors='coerce')
    mask = (G > 10) & P.notna()

    fig, ax = plt.subplots(figsize=(12, 8))

    horas = df.loc[mask].index.hour
    scatter = ax.scatter(G[mask], P[mask], c=horas, cmap='twilight_shifted',
                         alpha=0.3, s=5, edgecolors='none')
    plt.colorbar(scatter, ax=ax, label='Hora do dia')

    # Linhas teóricas
    g_range = np.linspace(0, 1200, 200)
    p_nominal = config["P_nominal"] * g_range / 1000
    ax.plot(g_range, p_nominal, 'r--', linewidth=2, alpha=0.7, label=f'P nominal ({config["P_nominal"]}W)')

    # P_MAX calculado (média)
    if 'P_MAX_Calc' in df.columns:
        p_max_mean = df.loc[mask, 'P_MAX_Calc'].mean()
        ax.axhline(y=p_max_mean, color='orange', linestyle=':', linewidth=1.5, alpha=0.6,
                   label=f'P_MAX médio ({p_max_mean:.0f}W)')

    ax.set_xlabel('Irradiância (W/m²)', fontsize=12)
    ax.set_ylabel('Potência MPPT (W)', fontsize=12)
    ax.set_title('Potência vs Irradiância', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    caminho = os.path.join(pasta_saida, '3_Potencia_vs_Irradiancia.png')
    plt.savefig(caminho, dpi=150, bbox_inches='tight')
    plt.close()

    msg = f"   ✓ Salvo: {os.path.basename(caminho)}"
    print(msg)
    if log_callback:
        log_callback(msg)
    return caminho


def grafico_taxas_variacao(df, config, pasta_saida, log_callback=None):
    """Gráfico 4: Taxas de Variação Diária (ΔFF/dia, ΔPR/dia) com zonas coloridas."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

    # ΔFF
    ff_var = df['FF_Variacao_Diaria'].dropna()
    ax1.plot(ff_var.index, ff_var.values * 100, color='purple', linewidth=1, alpha=0.8)
    ax1.fill_between(ff_var.index, 0, ff_var.values * 100,
                      where=(ff_var.values < 0), color='red', alpha=0.3, label='Degradação')
    ax1.fill_between(ff_var.index, 0, ff_var.values * 100,
                      where=(ff_var.values >= 0), color='green', alpha=0.3, label='Recuperação')
    ax1.axhline(y=0, color='gray', linewidth=1, alpha=0.5)
    ax1.set_ylabel('ΔFF/dia (%)', fontsize=12)
    ax1.set_title('Taxas de Variação Diária', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)

    # ΔPR
    pr_var = df['PR_Variacao_Diaria'].dropna()
    ax2.plot(pr_var.index, pr_var.values * 100, color='darkblue', linewidth=1, alpha=0.8)
    ax2.fill_between(pr_var.index, 0, pr_var.values * 100,
                      where=(pr_var.values < 0), color='red', alpha=0.3, label='Degradação')
    ax2.fill_between(pr_var.index, 0, pr_var.values * 100,
                      where=(pr_var.values >= 0), color='green', alpha=0.3, label='Recuperação')
    ax2.axhline(y=0, color='gray', linewidth=1, alpha=0.5)
    ax2.set_ylabel('ΔPR/dia (%)', fontsize=12)
    ax2.set_xlabel('Tempo', fontsize=12)
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)

    formatar_eixo_datas(ax2, config)
    plt.tight_layout()

    caminho = os.path.join(pasta_saida, '4_Taxas_Variacao.png')
    plt.savefig(caminho, dpi=150, bbox_inches='tight')
    plt.close()

    msg = f"   ✓ Salvo: {os.path.basename(caminho)}"
    print(msg)
    if log_callback:
        log_callback(msg)
    return caminho


def grafico_validacao_chuva(df_diario, config, pasta_saida, log_callback=None):
    """Gráfico 5: Validação com Chuva (ΔPR vs Precipitação)."""
    fig, ax1 = plt.subplots(figsize=(16, 7))

    # ΔPR diário
    if 'PR_Diario' in df_diario.columns:
        delta_pr = df_diario['PR_Diario'].diff() * 100
        ax1.plot(delta_pr.index, delta_pr.values, color='darkblue', linewidth=1.5,
                 alpha=0.8, label='ΔPR diário (%)')
        ax1.axhline(y=0, color='gray', linewidth=1, alpha=0.5)

    ax1.set_ylabel('ΔPR diário (%)', fontsize=12, color='darkblue')
    ax1.tick_params(axis='y', labelcolor='darkblue')
    ax1.set_title('Validação: Variação de PR vs Precipitação', fontsize=14, fontweight='bold')

    # Chuva
    if 'Chuva_mm' in df_diario.columns:
        ax2 = ax1.twinx()
        ax2.bar(df_diario.index, df_diario['Chuva_mm'].fillna(0),
                color='lightskyblue', alpha=0.6, width=0.8, label='Chuva (mm)')
        ax2.set_ylabel('Precipitação (mm)', fontsize=12, color='lightskyblue')
        ax2.tick_params(axis='y', labelcolor='lightskyblue')
        ax2.invert_yaxis()

        # Combina legendas
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
    else:
        ax1.legend(loc='upper right')
        ax1.text(0.5, 0.95, '⚠️ Dados de chuva indisponíveis',
                 transform=ax1.transAxes, ha='center', fontsize=12, color='orange')

    ax1.grid(True, alpha=0.3)
    formatar_eixo_datas(ax1, config)
    plt.tight_layout()

    caminho = os.path.join(pasta_saida, '5_Validacao_Chuva.png')
    plt.savefig(caminho, dpi=150, bbox_inches='tight')
    plt.close()

    msg = f"   ✓ Salvo: {os.path.basename(caminho)}"
    print(msg)
    if log_callback:
        log_callback(msg)
    return caminho


def grafico_residuos_pr(df_diario, config, pasta_saida, log_callback=None):
    """Gráfico 6: Resíduos do PR (medido - referência/mediana)."""
    if 'PR_Diario' not in df_diario.columns or df_diario['PR_Diario'].dropna().empty:
        msg = "   ⚠️  Sem dados diários de PR para gerar resíduos."
        print(msg)
        if log_callback:
            log_callback(msg)
        return None

    pr_ref = df_diario['PR_Diario'].median()
    residuos = df_diario['PR_Diario'] - pr_ref

    fig, ax = plt.subplots(figsize=(16, 7))

    ax.bar(residuos.index, residuos.values, color=np.where(residuos.values >= 0, 'green', 'red'),
           alpha=0.6, width=0.8)
    ax.axhline(y=0, color='gray', linewidth=1.5, alpha=0.7)

    ax.set_ylabel('Resíduo PR (medido - referência)', fontsize=12)
    ax.set_xlabel('Tempo', fontsize=12)
    ax.set_title(f'Resíduos do PR (Referência = mediana: {pr_ref:.3f})', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y')

    formatar_eixo_datas(ax, config)
    plt.tight_layout()

    caminho = os.path.join(pasta_saida, '6_Residuos_PR.png')
    plt.savefig(caminho, dpi=150, bbox_inches='tight')
    plt.close()

    msg = f"   ✓ Salvo: {os.path.basename(caminho)}"
    print(msg)
    if log_callback:
        log_callback(msg)
    return caminho


# Mapa de gráficos: número → (função, precisa_df_diario?)
MAPA_GRAFICOS = {
    1: ("FF vs PR Lado a Lado",      grafico_ff_pr_lado_a_lado,        False),
    2: ("Correlação Scatter",         grafico_correlacao_scatter,        False),
    3: ("Potência vs Irradiância",    grafico_potencia_vs_irradiancia,   False),
    4: ("Taxas de Variação",          grafico_taxas_variacao,            False),
    5: ("Validação com Chuva",        grafico_validacao_chuva,           True),
    6: ("Resíduos PR",                grafico_residuos_pr,               True),
}


# ============================================================
# 4. ORQUESTRADOR
# ============================================================

def executar_analise(caminho_csv, graficos_selecionados=None, config=None,
                     pasta_saida=None, log_callback=None):
    """
    Executa a análise completa: carrega dados, calcula métricas e gera gráficos.

    Args:
        caminho_csv: caminho para o arquivo CSV
        graficos_selecionados: lista de IDs de gráficos (1-6), ou None para todos
        config: dict de configuração (usa CONFIG_SISTEMA se None)
        pasta_saida: diretório para salvar gráficos
        log_callback: função para enviar mensagens de log à GUI

    Returns:
        dict com df_completo, df_diario, mask_sol, caminhos_graficos
    """
    if config is None:
        config = CONFIG_SISTEMA

    if graficos_selecionados is None:
        graficos_selecionados = list(MAPA_GRAFICOS.keys())

    # Pasta de saída baseada no nome do arquivo + timestamp
    if pasta_saida is None:
        from datetime import datetime
        nome_base = os.path.splitext(os.path.basename(caminho_csv))[0]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pasta_saida = os.path.join(
            os.path.dirname(caminho_csv),
            f"analise_ffpr_{nome_base}_{timestamp}"
        )

    os.makedirs(pasta_saida, exist_ok=True)

    def log(msg):
        print(msg)
        if log_callback:
            log_callback(msg)

    log(f"\n{'='*60}")
    log("ANALISADOR CORE - Cálculo de FF e PR")
    log(f"{'='*60}")
    log(f"📂 Arquivo: {caminho_csv}")
    log(f"📁 Saída: {pasta_saida}")

    # Carrega dados
    log("\n📊 Carregando dados...")
    df = carregar_dados(caminho_csv)
    log(f"   ✓ {len(df)} registros carregados")
    log(f"   📅 Período: {df.index.min().strftime('%d/%m/%Y')} a {df.index.max().strftime('%d/%m/%Y')}")

    # Calcula métricas
    log("\n⚙️  Calculando métricas (FF, PR)...")
    df, mask_sol = calcular_metricas(df, config)
    registros_solares = mask_sol.sum()
    log(f"   ✓ {registros_solares} registros solares válidos")

    ff_medio = df['FF_valido'].mean()
    pr_medio = df['PR'].mean()
    log(f"   FF médio: {ff_medio:.3f}")
    log(f"   PR médio: {pr_medio:.3f}")

    # Agrega dados diários
    log("\n📅 Agregando dados diários...")
    df_diario = agregar_dados_diarios(df, mask_sol, config)
    log(f"   ✓ {len(df_diario)} dias com dados válidos")

    # Gera gráficos
    log(f"\n🎨 Gerando {len(graficos_selecionados)} gráfico(s)...")
    caminhos_graficos = []

    for num in graficos_selecionados:
        if num in MAPA_GRAFICOS:
            nome, func, usa_diario = MAPA_GRAFICOS[num]
            log(f"\n   [{num}] {nome}...")
            try:
                if usa_diario:
                    caminho = func(df_diario, config, pasta_saida, log_callback)
                else:
                    caminho = func(df, config, pasta_saida, log_callback)
                if caminho:
                    caminhos_graficos.append(caminho)
            except Exception as e:
                log(f"   ❌ Erro no gráfico {num}: {e}")

    log(f"\n{'='*60}")
    log(f"✅ Análise concluída! Resultados em:")
    log(f"   {pasta_saida}")
    log(f"{'='*60}\n")

    return {
        'df_completo': df,
        'df_diario': df_diario,
        'mask_sol': mask_sol,
        'caminhos_graficos': caminhos_graficos,
        'pasta_saida': pasta_saida,
        'config': config,
    }
