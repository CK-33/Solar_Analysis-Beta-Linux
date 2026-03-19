# ============================================================
# CONFIGURAÇÃO DA PLANTA FOTOVOLTAICA
# ============================================================

CONFIG_SISTEMA = {
    # --- Parâmetros elétricos (STC) ---
    "P_nominal": 3510,          # Potência de pico sob STC (W)
    "I_sc_ref": 14.55,          # Corrente de curto-circuito (A)
    "V_oc_ref": 6 * 51.16,      # Tensão de circuito aberto (V) — 6 módulos em série
    "G_ref": 1000,              # Irradiância de referência (W/m²)
    "T_ref": 25,                # Temperatura de referência (°C)
    "alpha": 0.047 / 100,       # Coeficiente de temperatura de I_sc (%/°C → fração/°C)
    "beta": -0.260 / 100,       # Coeficiente de temperatura de V_oc (%/°C → fração/°C)

    # --- Localização (usada na API OpenMeteo para dados pluviométricos) ---
    "lat": -9.410861,           # Latitude da planta
    "lon": -40.514194,          # Longitude da planta

    # --- Parâmetros de análise ---
    "janela_mm": 168,           # Janela da média móvel (168 h = 7 dias)
    "intervalo_grid": 7,        # Espaçamento do grid de datas nos gráficos (dias)
}

# Limites para classificação de estado da planta.
CONFIG_ALERTAS = {
    "janela_semanas": 2,          # Janela deslizante de análise (semanas)
    "janela_analise": 7,          # Janela para cálculo de velocidade (dias)
    "janela_limpeza": 3,          # Janela para detecção de limpeza (dias)
    "limiar_estavel_min": -0.02,  # Velocidade mínima para "estável" (%/dia)
    "limiar_estavel_max": +0.02,  # Velocidade máxima para "estável" (%/dia)
    "limiar_atencao": -0.05,      # Limiar de atenção (%/dia) → -5%/semana
    "limiar_critico": -0.10,      # Limiar crítico (%/dia) → -10%/semana
    "limiar_limpeza": +0.05,      # Limiar de evento de limpeza (%/dia)
    "confianca_minima": 0.60,     # Confiança mínima para diagnóstico (0–1)

    # --- Detecção de falhas ---
    "irrad_min_fault": 200,       # Irradiância mínima para considerar electrical fault (W/m²)
    "potencia_max_fault": 10,     # Potência máxima para considerar como "zero" (W)
    "horas_min_fault": 3,         # Horas consecutivas para confirmar electrical fault
    "gap_min_horas": 2,           # Gap mínimo nos timestamps para falha de datalogger (horas)

    # --- Detecção de falha elétrica diária (PR baixo com irradiância boa) ---
    "pr_min_fault_diario": 0.20,  # PR diário abaixo deste valor com irradiância boa = suspeito
    "irrad_min_fault_diario": 150, # Irradiância média diária mínima (W/m²) para considerar falha
}
