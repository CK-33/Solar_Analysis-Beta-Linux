# ============================================================
# GERENCIADOR DE ALERTAS - Detecção de Sujidade por Gradiente
# ============================================================

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import timedelta
import os

from src.config import CONFIG_ALERTAS


class GerenciadorAlertas:
    """
    Gerenciador de alertas de sujidade baseado em análise de gradiente.
    Usa consenso entre FF e PR para detectar degradação progressiva.
    Implementa janela deslizante configurável.

    Detecções adicionais:
    - Electrical fault: irradiância alta + potência ≈ 0 por período prolongado
    - Falha de datalogger: gaps significativos nos timestamps
    """

    def __init__(self, config_alertas=None):
        """
        Inicializa o gerenciador com configurações de CONFIG_ALERTAS.

        Args:
            config_alertas: dict com limites personalizados (opcional, sobrescreve CONFIG_ALERTAS)
        """
        # Usa CONFIG_ALERTAS como base
        self.config = dict(CONFIG_ALERTAS)

        # Sobrescreve com configurações personalizadas se fornecidas
        if config_alertas:
            self.config.update(config_alertas)

        # Resultados (preenchidos após análise)
        self.resultados = {}

    def analisar(self, dados_analisador, pasta_saida=".", log_callback=None):
        """
        Executa análise completa de sujidade com janela deslizante.

        Args:
            dados_analisador: dict retornado por analisador_core.executar_analise()
            pasta_saida: diretório para salvar gráficos
            log_callback: função callback para enviar mensagens à GUI

        Returns:
            dict com resultados da análise
        """
        def log(msg):
            print(msg)
            if log_callback:
                log_callback(msg)

        log("\n" + "=" * 70)
        log("GERENCIADOR DE ALERTAS - Detecção de Sujidade")
        log("=" * 70)

        # Extrai dados
        df = dados_analisador['df_completo']

        # 0. Detecções de falhas (usa dados completos, antes da janela)
        log("\n🔌 Detectando falhas elétricas e de datalogger...")
        falhas_eletricas = self._detectar_electrical_fault(df)
        falhas_datalogger = self._detectar_falha_datalogger(df)

        for falha in falhas_eletricas:
            log(f"   ⚡ ELECTRICAL FAULT (horário): {falha['inicio'].strftime('%d/%m/%Y %H:%M')} → "
                f"{falha['fim'].strftime('%d/%m/%Y %H:%M')} ({falha['duracao_h']:.1f}h)")

        for gap in falhas_datalogger:
            log(f"   📡 GAP DATALOGGER (ausência de dados): {gap['inicio'].strftime('%d/%m/%Y %H:%M')} → "
                f"{gap['fim'].strftime('%d/%m/%Y %H:%M')} ({gap['duracao_h']:.1f}h)")

        if not falhas_eletricas:
            log("   ✓ Nenhuma falha elétrica horária detectada")
        if not falhas_datalogger:
            log("   ✓ Nenhuma ausência de dados detectada")

        # 1. Prepara dados diários
        log("\n📊 Preparando dados diários para análise...")
        df_diario_completo = self._preparar_dados_diarios(df, log)

        # 1b. Detecção diária de falha elétrica (PR baixo com irradiância boa)
        log("\n⚡ Detectando possíveis falhas elétricas diárias (PR baixo com boa irradiância)...")
        falhas_eletricas_diarias = self._detectar_electrical_fault_diario(df_diario_completo, log)

        # 2. Aplica janela deslizante
        log(f"\n🪟 Aplicando janela deslizante de {self.config['janela_semanas']} semanas...")
        df_diario = self._filtrar_janela_deslizante(df_diario_completo, log)

        # 3. Calcula gradientes
        log("\n📈 Calculando gradientes (velocidades de mudança)...")
        df_diario = self._calcular_gradientes(df_diario, log)

        # 4. Calcula sinais de sujidade (PR) e saúde elétrica (FF/IHE)
        log("📡 Calculando sinal de sujidade (PR) e Índice de Saúde Elétrica (FF)...")
        df_diario, ihe = self._calcular_sinais(df_diario, df_diario_completo, log)
        self._ihe = ihe  # persiste para relatório e métricas

        # 5. Detecta eventos
        log("🔍 Detectando eventos de sujidade...")
        eventos = self._detectar_eventos(df_diario, log)

        # 6. Classifica status temporal
        log("🎯 Classificando status temporal...")
        df_diario = self._classificar_status(df_diario, log)

        # 7. Gera visualizações
        log("\n📊 Gerando visualizações de alertas...")
        self._gerar_visualizacoes(df_diario, eventos, pasta_saida)

        # 8. Gera relatório
        log("📋 Gerando relatório de alertas...")
        relatorio = self._gerar_relatorio(
            df_diario, eventos, falhas_eletricas, falhas_datalogger, falhas_eletricas_diarias
        )

        # Salva resultados
        self.resultados = {
            'df_diario': df_diario,
            'eventos': eventos,
            'relatorio': relatorio,
            'falhas_eletricas': falhas_eletricas,
            'falhas_eletricas_diarias': falhas_eletricas_diarias,
            'falhas_datalogger': falhas_datalogger,
            'metricas': self._calcular_metricas_resumo(df_diario, eventos, getattr(self, '_ihe', None))
        }

        log("\n✅ Análise de sujidade concluída!")
        log("=" * 70 + "\n")

        return self.resultados

    # ============================================================
    # DETECÇÃO DE FALHAS
    # ============================================================

    def _detectar_electrical_fault(self, df):
        """
        Detecta electrical fault: irradiância alta + potência ≈ 0 por período prolongado.

        Critério:
        - Irradiância > irrad_min_fault (padrão: 200 W/m²)
        - Potência < potencia_max_fault (padrão: 10 W)
        - Por pelo menos horas_min_fault horas consecutivas (padrão: 3h)
        """
        G = pd.to_numeric(df['Rg Média'], errors='coerce')
        P = pd.to_numeric(df['P MPPT (W)'], errors='coerce')

        irrad_min = self.config.get('irrad_min_fault', 200)
        pot_max = self.config.get('potencia_max_fault', 10)
        horas_min = self.config.get('horas_min_fault', 3)

        # Marca registros onde há sol mas não há geração
        mascara_fault = (G > irrad_min) & (P < pot_max)

        falhas = []
        inicio_fault = None
        count_consecutivo = 0

        for i, (ts, is_fault) in enumerate(mascara_fault.items()):
            if is_fault:
                if inicio_fault is None:
                    inicio_fault = ts
                count_consecutivo += 1
            else:
                if inicio_fault is not None and count_consecutivo >= horas_min:
                    fim_fault = mascara_fault.index[i - 1]
                    duracao = (fim_fault - inicio_fault).total_seconds() / 3600
                    falhas.append({
                        'inicio': inicio_fault,
                        'fim': fim_fault,
                        'duracao_h': duracao,
                        'registros': count_consecutivo
                    })
                inicio_fault = None
                count_consecutivo = 0

        # Verifica se terminou em fault
        if inicio_fault is not None and count_consecutivo >= horas_min:
            fim_fault = mascara_fault.index[-1]
            duracao = (fim_fault - inicio_fault).total_seconds() / 3600
            falhas.append({
                'inicio': inicio_fault,
                'fim': fim_fault,
                'duracao_h': duracao,
                'registros': count_consecutivo
            })

        return falhas

    def _detectar_falha_datalogger(self, df):
        """
        Detecta falhas de datalogger: gaps significativos nos timestamps.

        Critério: gap > gap_min_horas entre registros consecutivos.
        """
        gap_min = self.config.get('gap_min_horas', 2)

        timestamps = df.index.to_series()
        deltas = timestamps.diff()

        # Identifica gaps maiores que o limiar
        gaps = deltas[deltas > timedelta(hours=gap_min)]

        falhas = []
        for ts, delta in gaps.items():
            idx_pos = timestamps.index.get_loc(ts)
            if idx_pos > 0:
                inicio = timestamps.index[idx_pos - 1]
                falhas.append({
                    'inicio': inicio,
                    'fim': ts,
                    'duracao_h': delta.total_seconds() / 3600,
                })

        return falhas

    # ============================================================
    # ANÁLISE DE SUJIDADE
    # ============================================================

    def _preparar_dados_diarios(self, df, log):
        """Agrega dados horários em médias diárias."""
        df_diario = df.resample('D').agg({
            'FF_valido': 'mean',
            'PR': 'mean',
            'FF_MediaMovel': 'mean',
            'PR_MediaMovel': 'mean',
            'Rg Média': 'mean',
            'P MPPT (W)': 'sum'
        }).dropna(subset=['FF_valido', 'PR'])

        df_diario.columns = ['FF_Diario', 'PR_Diario', 'FF_MM', 'PR_MM',
                             'G_Media', 'Energia_Diaria']

        log(f"   ✓ {len(df_diario)} dias totais com dados válidos")
        return df_diario

    def _filtrar_janela_deslizante(self, df_diario, log):
        """Filtra dados para usar janela deslizante de N semanas."""
        if len(df_diario) == 0:
            log("   ⚠️  DataFrame vazio!")
            return df_diario

        janela_semanas = self.config['janela_semanas']
        dias_janela = janela_semanas * 7

        data_fim = df_diario.index.max()
        data_inicio = data_fim - timedelta(days=dias_janela)
        df_filtrado = df_diario[df_diario.index >= data_inicio].copy()
        dias_disponiveis = len(df_filtrado)

        log(f"   📅 Janela configurada: {janela_semanas} semanas ({dias_janela} dias)")
        log(f"   📊 Dados na janela: {dias_disponiveis} dias")
        log(f"   🗓️  Período: {df_filtrado.index.min().strftime('%d/%m/%Y')} a "
            f"{df_filtrado.index.max().strftime('%d/%m/%Y')}")

        if dias_disponiveis < 7:
            log(f"   ⚠️  AVISO: Poucos dados ({dias_disponiveis} dias). Mínimo recomendado: 7 dias")

        return df_filtrado

    def _calcular_gradientes(self, df_diario, log):
        """Calcula velocidades de mudança (gradientes temporais)."""
        janela = self.config['janela_analise']
        janela_limpeza = self.config['janela_limpeza']

        df_diario['Vel_FF'] = df_diario['FF_Diario'].diff(periods=janela) / janela
        df_diario['Vel_PR'] = df_diario['PR_Diario'].diff(periods=janela) / janela

        df_diario['Vel_FF_3d'] = df_diario['FF_Diario'].diff(periods=janela_limpeza) / janela_limpeza
        df_diario['Vel_PR_3d'] = df_diario['PR_Diario'].diff(periods=janela_limpeza) / janela_limpeza

        df_diario = df_diario.dropna(subset=['Vel_FF', 'Vel_PR'])

        if len(df_diario) > 0:
            vel_ff_media = df_diario['Vel_FF'].mean() * 7 * 100
            vel_pr_media = df_diario['Vel_PR'].mean() * 7 * 100
            log(f"   ✓ Velocidade FF média: {vel_ff_media:.2f}%/semana")
            log(f"   ✓ Velocidade PR média: {vel_pr_media:.2f}%/semana")
        else:
            log("   ⚠️  Nenhum gradiente calculado (dados insuficientes)")

        return df_diario

    def _calcular_sinais(self, df_diario, df_completo, log):
        """
        Separa os dois papéis:
        - Vel_PR: sinal primário de sujidade (queda operacional)
        - IHE: Índice de Saúde Elétrica baseado em FF vs baseline (degradação estrutural)

        Confiança é calculada sobre a estabilidade do próprio PR.
        """
        if len(df_diario) == 0:
            log("   ⚠️  DataFrame vazio, pulando cálculo de sinais")
            return df_diario, None

        # --- Sinal de sujidade: PR ---
        # Confiança baseada na consistência dos gradientes de PR dentro da janela
        std_pr = df_diario['Vel_PR'].std()
        mean_abs_pr = df_diario['Vel_PR'].abs().mean()
        if mean_abs_pr > 0.0001:
            df_diario['Confianca'] = float(np.clip(1 - (std_pr / (mean_abs_pr + std_pr)), 0, 1))
        else:
            df_diario['Confianca'] = 1.0

        vel_pr_media = df_diario['Vel_PR'].mean() * 7 * 100
        conf_media = df_diario['Confianca'].mean() * 100
        log(f"   ✓ Velocidade PR média: {vel_pr_media:.2f}%/semana")
        log(f"   ✓ Confiança (PR): {conf_media:.1f}%")

        # --- Índice de Saúde Elétrica (IHE): FF atual vs baseline ---
        # Baseline = média de FF de todo o período de dados disponível
        # df_completo é o df_diario_completo (dados diários), coluna 'FF_Diario'
        ff_col = 'FF_Diario' if 'FF_Diario' in df_completo.columns else None
        ihe = None
        if ff_col is not None:
            ff_baseline = df_completo[ff_col].mean()
            ff_janela = df_diario['FF_Diario'].mean()
            if ff_baseline > 0.01:
                ihe = ff_janela / ff_baseline
                if ihe < 0.90:
                    status_eletrico = "CRÍTICO"
                elif ihe < 0.95:
                    status_eletrico = "ATENÇÃO"
                else:
                    status_eletrico = "NORMAL"
                log(f"   ✓ IHE (FF atual/baseline): {ihe:.3f} → {status_eletrico}")

        return df_diario, ihe

    def _detectar_eventos(self, df_diario, log):
        """Detecta eventos de limpeza e degradação (baseado em PR).

        Nota: os limiares em CONFIG_ALERTAS são em unidades semanais (fração/semana).
        Vel_PR e Vel_PR_3d são em fração/dia, portanto multiplicamos por 7 antes de comparar.
        """
        eventos = {
            'limpeza': [],
            'degradacao_critica': [],
            'periodos_estaveis': []
        }

        if len(df_diario) == 0:
            log("   ⚠️  Nenhum dado para detectar eventos")
            return eventos

        # Velocidades semanais para comparação com limiares
        vel_pr_sem = df_diario['Vel_PR'] * 7
        vel_pr_3d_sem = df_diario['Vel_PR_3d'] * 7

        # Eventos de limpeza: PR com alta positiva rápida de 3 dias
        df_diario['Evento_Limpeza'] = (
            vel_pr_3d_sem > self.config['limiar_limpeza']
        )

        for idx, row in df_diario[df_diario['Evento_Limpeza']].iterrows():
            eventos['limpeza'].append({
                'data': idx,
                'vel_pr': row['Vel_PR_3d'] * 7 * 100,
                'magnitude': row['Vel_PR_3d'] * 7 * 100
            })

        log(f"   🌧️  Eventos de limpeza (PR): {len(eventos['limpeza'])}")
        for evt in eventos['limpeza']:
            log(f"      • {evt['data'].strftime('%d/%m/%Y')}: +{evt['magnitude']:.1f}%/sem")

        # Degradação crítica: PR caindo com confiança suficiente
        df_diario['Degradacao_Critica'] = (
            (vel_pr_sem < self.config['limiar_atencao']) &
            (df_diario['Confianca'] > self.config['confianca_minima'])
        )

        dias_criticos = df_diario['Degradacao_Critica'].sum()
        log(f"   🔴 Dias em degradação crítica: {dias_criticos} "
            f"({dias_criticos / len(df_diario) * 100:.1f}%)")

        # Períodos estáveis: PR dentro da banda estável
        df_diario['Periodo_Estavel'] = (
            (vel_pr_sem >= self.config['limiar_estavel_min']) &
            (vel_pr_sem <= self.config['limiar_estavel_max'])
        )

        dias_estaveis = df_diario['Periodo_Estavel'].sum()
        log(f"   🟢 Dias estáveis: {dias_estaveis} ({dias_estaveis / len(df_diario) * 100:.1f}%)")

        return eventos

    def _classificar_status(self, df_diario, log):
        """Classifica status diário de sujidade com base em Vel_PR.

        Nota: limiares são em unidades semanais; Vel_PR é diário, por isso multiplica-se por 7.
        """
        if len(df_diario) == 0:
            log("   ⚠️  Nenhum dado para classificar")
            return df_diario

        def classificar(row):
            vel_sem = row['Vel_PR'] * 7   # converte para unidade semanal
            conf = row['Confianca']

            if row.get('Evento_Limpeza', False):
                return "🌧️ LIMPEZA"
            if conf < self.config['confianca_minima']:
                return "⚠️ INCERTO"
            if vel_sem < self.config['limiar_critico']:
                return "🔴 CRÍTICO"
            elif vel_sem < self.config['limiar_atencao']:
                return "🟡 SUJANDO"
            elif vel_sem > self.config['limiar_limpeza']:
                return "🟢 RECUPERANDO"
            elif self.config['limiar_estavel_min'] <= vel_sem <= self.config['limiar_estavel_max']:
                return "🟢 ESTÁVEL"
            else:
                return "🟡 MUDANÇA LEVE"

        df_diario['Status'] = df_diario.apply(classificar, axis=1)

        log("   ✓ Distribuição de status (PR):")
        for status in df_diario['Status'].unique():
            count = (df_diario['Status'] == status).sum()
            pct = count / len(df_diario) * 100
            log(f"      {status}: {count} dias ({pct:.1f}%)")

        return df_diario

    # ============================================================
    # VISUALIZAÇÕES
    # ============================================================

    def _gerar_visualizacoes(self, df_diario, eventos, pasta_saida):
        """Gera gráfico de timeline de alertas."""
        if len(df_diario) == 0:
            print("   ⚠️  Nenhum dado para visualizar")
            return

        def formatar_datas(ax):
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

        cores_status = {
            '🔴 CRÍTICO': 'red',
            '🟡 SUJANDO': 'orange',
            '🟢 ESTÁVEL': 'lightgreen',
            '🟢 RECUPERANDO': 'lightblue',
            '🌧️ LIMPEZA': 'green',
            '⚠️ DIVERGENTE': 'yellow',
            '🟡 MUDANÇA LEVE': 'lightyellow'
        }

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 12), sharex=True)

        # Painel 1: FF e PR com zonas de status
        ax1.plot(df_diario.index, df_diario['FF_MM'], color='purple',
                 linewidth=2, label='FF', alpha=0.8)
        ax1.plot(df_diario.index, df_diario['PR_MM'], color='darkblue',
                 linewidth=2, label='PR', alpha=0.8, linestyle='--')

        for i in range(len(df_diario) - 1):
            status = df_diario.iloc[i]['Status']
            cor = cores_status.get(status, 'gray')
            ax1.axvspan(df_diario.index[i], df_diario.index[i + 1], alpha=0.15, color=cor)

        for evt in eventos['limpeza']:
            ax1.axvline(x=evt['data'], color='green', alpha=0.5, linewidth=2)

        ax1.set_ylabel('FF / PR', fontsize=12)
        ax1.set_title(f'Timeline de Alertas - Janela: {self.config["janela_semanas"]} semanas',
                      fontsize=14, fontweight='bold')
        ax1.legend(loc='upper right')
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(0, 1.0)

        # Painel 2: Velocidade de PR (sinal de sujidade)
        ax2.plot(df_diario.index, df_diario['Vel_PR'] * 100, color='darkblue',
                 linewidth=2, label='Vel. PR', alpha=0.85)

        ax2.axhline(y=0, color='gray', linewidth=1, alpha=0.5)
        ax2.axhline(y=self.config['limiar_atencao'] * 100, color='orange',
                    linestyle='--', alpha=0.6, label='Atenção')
        ax2.axhline(y=self.config['limiar_critico'] * 100, color='red',
                    linestyle='--', alpha=0.6, label='Crítico')

        ax2.fill_between(df_diario.index, 0, df_diario['Vel_PR'] * 100,
                         where=(df_diario['Vel_PR'] < 0), color='red', alpha=0.2)
        ax2.fill_between(df_diario.index, 0, df_diario['Vel_PR'] * 100,
                         where=(df_diario['Vel_PR'] >= 0), color='green', alpha=0.2)

        ax2.set_ylabel('Velocidade PR (%/dia)', fontsize=12)
        ax2.set_title('Velocidade de Degradação (PR)', fontsize=12)
        ax2.legend(loc='upper right', fontsize=9)
        ax2.grid(True, alpha=0.3)

        # Painel 3: Confiança
        ax3.fill_between(df_diario.index, 0, df_diario['Confianca'] * 100,
                         color='blue', alpha=0.4)
        ax3.plot(df_diario.index, df_diario['Confianca'] * 100, color='darkblue',
                 linewidth=1.5)
        ax3.axhline(y=self.config['confianca_minima'] * 100, color='red',
                    linestyle='--', alpha=0.6)

        ax3.set_ylabel('Confiança (%)', fontsize=12)
        ax3.set_xlabel('Tempo', fontsize=12)
        ax3.set_title('Confiança do Consenso FF+PR', fontsize=12)
        ax3.grid(True, alpha=0.3)
        ax3.set_ylim(0, 105)

        formatar_datas(ax3)
        plt.tight_layout()
        plt.savefig(os.path.join(pasta_saida, 'Alertas_Timeline.png'),
                    dpi=150, bbox_inches='tight')
        plt.close()
        print("   ✓ Salvo: Alertas_Timeline.png")

    # ============================================================
    # RELATÓRIO
    # ============================================================

    def _gerar_relatorio(self, df_diario, eventos, falhas_eletricas, falhas_datalogger):
        """Gera relatório textual completo."""
        r = []
        r.append("=" * 70)
        r.append("RELATÓRIO DE ALERTAS DE SUJIDADE")
        r.append(f"Janela de Análise: {self.config['janela_semanas']} semanas")
        r.append("=" * 70)
        r.append("")

        if len(df_diario) == 0:
            r.append("⚠️  Nenhum dado disponível para análise")
            r.append("=" * 70)
            return "\n".join(r)

        r.append(f"📅 Período: {df_diario.index.min().strftime('%d/%m/%Y')} a "
                 f"{df_diario.index.max().strftime('%d/%m/%Y')}")
        r.append(f"📊 Dias analisados: {len(df_diario)}")
        r.append("")

        # Falhas elétricas
        r.append("⚡ FALHAS ELÉTRICAS (Electrical Faults):")
        if falhas_eletricas:
            for f in falhas_eletricas:
                r.append(f"   • {f['inicio'].strftime('%d/%m/%Y %H:%M')} → "
                         f"{f['fim'].strftime('%d/%m/%Y %H:%M')} ({f['duracao_h']:.1f}h)")
        else:
            r.append("   ✓ Nenhuma falha elétrica detectada")
        r.append("")

        # Falhas de datalogger
        r.append("📡 FALHAS DE DATALOGGER (Gaps nos dados):")
        if falhas_datalogger:
            for g in falhas_datalogger:
                r.append(f"   • {g['inicio'].strftime('%d/%m/%Y %H:%M')} → "
                         f"{g['fim'].strftime('%d/%m/%Y %H:%M')} ({g['duracao_h']:.1f}h)")
        else:
            r.append("   ✓ Nenhuma falha de datalogger detectada")
        r.append("")

        # Eventos de sujidade
        r.append("🔍 EVENTOS DETECTADOS:")
        r.append(f"   🌧️  Limpezas: {len(eventos['limpeza'])}")
        for evt in eventos['limpeza']:
            r.append(f"      • {evt['data'].strftime('%d/%m/%Y')}: +{evt['magnitude']:.1f}%/sem")

        dias_criticos = (df_diario['Status'] == '🔴 CRÍTICO').sum()
        dias_sujando = (df_diario['Status'] == '🟡 SUJANDO').sum()
        dias_estaveis = df_diario['Periodo_Estavel'].sum()

        r.append(f"   🔴 Dias críticos: {dias_criticos}")
        r.append(f"   🟡 Dias sujando: {dias_sujando}")
        r.append(f"   🟢 Dias estáveis: {dias_estaveis}")
        r.append("")

        # Tendência de sujidade (PR)
        vel_pr = df_diario['Vel_PR'].mean() * 7 * 100
        r.append("📈 TENDÊNCIA DE SUJIDADE (PR):")
        r.append(f"   Velocidade PR: {vel_pr:.2f}%/semana")
        r.append(f"   Confiança: {df_diario['Confianca'].mean() * 100:.1f}%")
        r.append("")

        # Diagnóstico de sujidade
        r.append("💡 DIAGNÓSTICO DE SUJIDADE:")
        if vel_pr < self.config['limiar_critico'] * 7 * 100:
            r.append("   🔴 CRÍTICO: Degradação rápida - Limpeza URGENTE")
        elif vel_pr < self.config['limiar_atencao'] * 7 * 100:
            r.append("   🟡 ATENÇÃO: Sistema sujando progressivamente")
        elif vel_pr > self.config['limiar_limpeza'] * 7 * 100:
            r.append("   🟢 RECUPERANDO: Sistema em melhoria")
        else:
            r.append("   🟢 ESTÁVEL: Sem mudanças significativas")

        if len(eventos['limpeza']) > 0:
            ultima = eventos['limpeza'][-1]['data']
            dias_desde = (df_diario.index[-1] - ultima).days
            r.append(f"\n🌧️  Última limpeza: {ultima.strftime('%d/%m/%Y')} ({dias_desde} dias atrás)")

        r.append("")

        # Saúde elétrica (FF / IHE)
        ihe = getattr(self, '_ihe', None)
        r.append("🔧 SAÚDE ELÉTRICA (FF):")
        if ihe is not None:
            if ihe < 0.90:
                status_eletrico = "🔴 CRÍTICO"
                detalhe = "Possível degradação estrutural, envelhecimento ou falha de célula"
            elif ihe < 0.95:
                status_eletrico = "🟡 ATENÇÃO"
                detalhe = "FF abaixo do baseline — monitorar evolução"
            else:
                status_eletrico = "🟢 NORMAL"
                detalhe = "Fill Factor dentro do padrão histórico"
            r.append(f"   IHE (FF atual / baseline): {ihe:.3f} ({ihe * 100:.1f}%)")
            r.append(f"   Status: {status_eletrico} — {detalhe}")
        else:
            r.append("   ⚠️  IHE não disponível (dados de FF insuficientes)")

        r.append("")
        r.append("=" * 70)

        texto = "\n".join(r)
        print("\n" + texto)
        return texto

    def _calcular_metricas_resumo(self, df_diario, eventos, ihe=None):
        """Calcula métricas resumidas para exibição na GUI."""
        if len(df_diario) == 0:
            return {
                'status_geral': "⚠️ SEM DADOS",
                'velocidade_degradacao': 0,
                'confianca': 0,
                'num_limpezas': 0,
                'dias_criticos': 0,
                'dias_estaveis': 0,
                'recomendacao': "Dados insuficientes para análise",
                'ihe': None,
                'status_eletrico': "—"
            }

        vel_pr_dia = df_diario['Vel_PR'].mean()
        vel_pr_sem = vel_pr_dia * 7   # converte para unidade semanal (igual aos limiares)
        confianca = df_diario['Confianca'].mean()

        if vel_pr_sem < self.config['limiar_critico']:
            status_geral = "🔴 CRÍTICO"
        elif vel_pr_sem < self.config['limiar_atencao']:
            status_geral = "🟡 ATENÇÃO"
        elif vel_pr_sem > self.config['limiar_limpeza']:
            status_geral = "🟢 RECUPERANDO"
        else:
            status_geral = "🟢 ESTÁVEL"

        if vel_pr_sem < self.config['limiar_critico']:
            recomendacao = "Limpeza URGENTE recomendada"
        elif vel_pr_sem < self.config['limiar_atencao']:
            dias = int(abs(0.10 / vel_pr_sem) * 7) if vel_pr_sem < 0 else 999
            recomendacao = f"Agendar limpeza em {dias} dias"
        else:
            recomendacao = "Sistema em boas condições"

        # IHE e status elétrico
        if ihe is not None:
            if ihe < 0.90:
                status_eletrico = "🔴 CRÍTICO"
            elif ihe < 0.95:
                status_eletrico = "🟡 ATENÇÃO"
            else:
                status_eletrico = "🟢 NORMAL"
        else:
            status_eletrico = "—"

        return {
            'status_geral': status_geral,
            'velocidade_degradacao': vel_pr_sem,   # semanal, consistente com display
            'confianca': confianca,
            'num_limpezas': len(eventos['limpeza']),
            'dias_criticos': (df_diario['Status'] == '🔴 CRÍTICO').sum(),
            'dias_estaveis': df_diario['Periodo_Estavel'].sum(),
            'recomendacao': recomendacao,
            'ihe': ihe,
            'status_eletrico': status_eletrico
        }

    def salvar_relatorio(self, caminho="Relatorio_Alertas.txt"):
        """Salva relatório em arquivo texto."""
        if 'relatorio' not in self.resultados:
            print("⚠️  Execute analisar() antes de salvar o relatório")
            return
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write(self.resultados['relatorio'])
        print(f"💾 Relatório salvo: {caminho}")

    def salvar_dados(self, caminho="Dados_Alertas.csv"):
        """Salva dados processados em CSV."""
        if 'df_diario' not in self.resultados:
            print("⚠️  Execute analisar() antes de salvar os dados")
            return
        self.resultados['df_diario'].to_csv(caminho)
        print(f"💾 Dados salvos: {caminho}")


# ============================================================
# FUNÇÃO DE CONVENIÊNCIA
# ============================================================

def detectar_sujidade(dados_analisador, config_alertas=None, pasta_saida=".", log_callback=None):
    """
    Função de conveniência para detecção rápida de sujidade.

    Args:
        dados_analisador: resultado de analisador_core.executar_analise()
        config_alertas: configurações personalizadas (opcional)
        pasta_saida: pasta para salvar resultados
        log_callback: função callback para log na GUI

    Returns:
        dict com resultados completos
    """
    gerenciador = GerenciadorAlertas(config_alertas)
    resultados = gerenciador.analisar(dados_analisador, pasta_saida, log_callback)
    return resultados
