# ============================================================
# GUI - Interface Gráfica (tkinter + Pillow)
# ============================================================

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from PIL import Image, ImageTk

# Adiciona diretório pai ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import CONFIG_SISTEMA, CONFIG_ALERTAS
from src.analisador_core import executar_analise, MAPA_GRAFICOS
from src.gerenciador_alertas import GerenciadorAlertas
from src.ingestion.gui_wizard import ImportWizard


# ============================================================
# CORES DO TEMA ESCURO
# ============================================================
CORES = {
    'bg': '#1a1a2e',
    'bg_painel': '#16213e',
    'bg_input': '#0f3460',
    'bg_botao': '#1a5276',
    'bg_botao_hover': '#2471a3',
    'bg_botao_primario': '#2e86de',
    'bg_botao_primario_hover': '#54a0ff',
    'bg_botao_alerta': '#e67e22',
    'bg_botao_alerta_hover': '#f39c12',
    'fg': '#e0e0e0',
    'fg_titulo': '#ffffff',
    'fg_label': '#b0b0b0',
    'fg_destaque': '#00d2ff',
    'borda': '#2c3e50',
    'verde': '#27ae60',
    'amarelo': '#f1c40f',
    'vermelho': '#e74c3c',
    'tab_ativo': '#2e86de',
    'tab_inativo': '#1a1a2e',
}


class SolarAnalysisGUI:
    """Interface gráfica do Sistema de Análise Fotovoltaica."""

    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Análise Fotovoltaica")
        self.root.configure(bg=CORES['bg'])
        self.root.attributes('-zoomed', True)  # Maximizado no Ubuntu/Linux
        self.root.minsize(1200, 700)

        # Estado
        self.caminho_csv = tk.StringVar(value="")
        self.graficos_vars = {}
        self.resultado_analise = None
        self.resultado_alertas = None
        self.imagens_graficos = []
        self.img_index = 0
        self._photo_ref = None  # Referência para evitar garbage collection

        # Configura estilo
        self._configurar_estilo()

        # Monta layout
        self._criar_layout()

        # Lembrete automático de configuração (500 ms após abrir)
        self.root.after(500, self._mostrar_lembrete_config)

    def _mostrar_lembrete_config(self):
        messagebox.showinfo(
            "Bem-vindo(a)!",
            "Lembrete: Antes de iniciar sua análise, por favor confirme se os dados "
            "da planta fotovoltaica (Potência Nominal, Coordenadas, I_sc, V_oc, etc.) "
            "na aba 'Config' correspondem ao sistema atual.\n\n"
            "Valores antigos ou incorretos podem gerar resultados muito baixos (tenebrosos) "
            "de PR e Fill Factor."
        )

    def _configurar_estilo(self):
        """Configura estilos ttk para tema escuro."""
        style = ttk.Style()
        style.theme_use('clam')

        style.configure('Dark.TFrame', background=CORES['bg'])
        style.configure('Panel.TFrame', background=CORES['bg_painel'])
        style.configure('Dark.TLabel', background=CORES['bg_painel'],
                        foreground=CORES['fg'], font=('DejaVu Sans', 10))
        style.configure('Title.TLabel', background=CORES['bg'],
                        foreground=CORES['fg_titulo'], font=('DejaVu Sans', 16, 'bold'))
        style.configure('Section.TLabel', background=CORES['bg_painel'],
                        foreground=CORES['fg_destaque'], font=('DejaVu Sans', 10, 'bold'))
        style.configure('Metric.TLabel', background=CORES['bg_painel'],
                        foreground=CORES['fg'], font=('DejaVu Sans Mono', 10))
        style.configure('Dark.TCheckbutton', background=CORES['bg_painel'],
                        foreground=CORES['fg'], font=('DejaVu Sans', 9))

    def _criar_layout(self):
        """Cria o layout principal: painel esquerdo + painel direito."""
        # Título superior
        header = tk.Frame(self.root, bg=CORES['bg'], height=50)
        header.pack(fill='x', padx=10, pady=(10, 5))
        header.pack_propagate(False)

        tk.Label(header, text="✦", font=('DejaVu Sans', 18), bg=CORES['bg'],
                 fg=CORES['fg_destaque']).pack(side='left', padx=(10, 5))
        tk.Label(header, text="Sistema de Análise Fotovoltaica",
                 font=('DejaVu Sans', 16, 'bold'), bg=CORES['bg'],
                 fg=CORES['fg_titulo']).pack(side='left')

        # Container principal
        main_container = tk.Frame(self.root, bg=CORES['bg'])
        main_container.pack(fill='both', expand=True, padx=10, pady=5)

        # === PAINEL ESQUERDO ===
        self.painel_esquerdo = tk.Frame(main_container, bg=CORES['bg_painel'],
                                         width=480, relief='flat', bd=0)
        self.painel_esquerdo.pack(side='left', fill='y', padx=(0, 5))
        self.painel_esquerdo.pack_propagate(False)

        self._criar_secao_arquivo()
        self._criar_secao_acoes()
        self._criar_secao_graficos()
        self._criar_secao_metricas()
        self._criar_secao_log()

        # === PAINEL DIREITO ===
        self.painel_direito = tk.Frame(main_container, bg=CORES['bg_painel'])
        self.painel_direito.pack(side='left', fill='both', expand=True)

        self._criar_abas()

    # ============================================================
    # PAINEL ESQUERDO - Controles
    # ============================================================

    def _criar_secao_arquivo(self):
        """Seção: Arquivo CSV."""
        frame = tk.Frame(self.painel_esquerdo, bg=CORES['bg_painel'])
        frame.pack(fill='x', padx=10, pady=(10, 5))

        tk.Label(frame, text="ARQUIVO CSV", font=('DejaVu Sans', 10, 'bold'),
                 bg=CORES['bg_painel'], fg=CORES['fg_destaque']).pack(anchor='w')

        row = tk.Frame(frame, bg=CORES['bg_painel'])
        row.pack(fill='x', pady=(5, 0))

        self.entry_csv = tk.Entry(row, textvariable=self.caminho_csv,
                                   font=('DejaVu Sans Mono', 9), bg=CORES['bg_input'],
                                   fg=CORES['fg'], insertbackground=CORES['fg'],
                                   relief='flat', bd=5)
        self.entry_csv.pack(side='left', fill='x', expand=True, padx=(0, 5))

        btn_procurar = tk.Button(row, text="Procurar...", font=('DejaVu Sans', 9),
                                  bg=CORES['bg_botao'], fg=CORES['fg'],
                                  activebackground=CORES['bg_botao_hover'],
                                  activeforeground=CORES['fg_titulo'],
                                  relief='flat', bd=0, padx=15, pady=5,
                                  command=self._procurar_csv)
        btn_procurar.pack(side='right')

        btn_importar = tk.Button(row, text="Importar/Converter...", font=('DejaVu Sans', 9),
                                  bg=CORES['bg_botao_primario'], fg='white',
                                  activebackground=CORES['bg_botao_primario_hover'],
                                  activeforeground='white',
                                  relief='flat', bd=0, padx=15, pady=5,
                                  command=self._abrir_wizard_importacao)
        btn_importar.pack(side='right', padx=(0, 5))

    def _criar_secao_acoes(self):
        """Seção: Botões de ação."""
        frame = tk.Frame(self.painel_esquerdo, bg=CORES['bg_painel'])
        frame.pack(fill='x', padx=10, pady=5)

        tk.Label(frame, text="AÇÕES", font=('DejaVu Sans', 10, 'bold'),
                 bg=CORES['bg_painel'], fg=CORES['fg_destaque']).pack(anchor='w', pady=(0, 5))

        # Botão 1: Análise Completa
        btn1 = tk.Button(frame, text="▶  Análise Completa (FF + PR + Alertas)",
                          font=('DejaVu Sans', 10, 'bold'),
                          bg=CORES['bg_botao_primario'], fg='white',
                          activebackground=CORES['bg_botao_primario_hover'],
                          activeforeground='white',
                          relief='flat', bd=0, pady=10,
                          command=lambda: self._executar_threaded("completa"))
        btn1.pack(fill='x', pady=2)

        # Botão 2: Apenas Análise FF/PR
        btn2 = tk.Button(frame, text="📊  Apenas Análise FF / PR",
                          font=('DejaVu Sans', 10),
                          bg=CORES['bg_botao'], fg=CORES['fg'],
                          activebackground=CORES['bg_botao_hover'],
                          activeforeground='white',
                          relief='flat', bd=0, pady=8,
                          command=lambda: self._executar_threaded("analise"))
        btn2.pack(fill='x', pady=2)

        # Botão 3: Apenas Alertas
        btn3 = tk.Button(frame, text="⚠  Apenas Alertas de Sujidade",
                          font=('DejaVu Sans', 10),
                          bg=CORES['bg_botao_alerta'], fg='white',
                          activebackground=CORES['bg_botao_alerta_hover'],
                          activeforeground='white',
                          relief='flat', bd=0, pady=8,
                          command=lambda: self._executar_threaded("alertas"))
        btn3.pack(fill='x', pady=2)

    def _criar_secao_graficos(self):
        """Seção: Checkboxes de gráficos."""
        frame = tk.Frame(self.painel_esquerdo, bg=CORES['bg_painel'])
        frame.pack(fill='x', padx=10, pady=5)

        tk.Label(frame, text="ESCOLHER GRÁFICOS", font=('DejaVu Sans', 10, 'bold'),
                 bg=CORES['bg_painel'], fg=CORES['fg_destaque']).pack(anchor='w', pady=(0, 5))

        grid = tk.Frame(frame, bg=CORES['bg_painel'])
        grid.pack(fill='x')

        nomes = {
            1: "FF vs PR Lado a Lado",
            2: "Correlação Scatter",
            3: "Potência vs Irradiância",
            4: "Taxas de Variação",
            5: "Validação com Chuva",
            6: "Resíduos PR",
        }

        for i, (num, nome) in enumerate(nomes.items()):
            var = tk.BooleanVar(value=True)
            self.graficos_vars[num] = var
            col = i % 2
            row = i // 2
            cb = tk.Checkbutton(grid, text=nome, variable=var,
                                 font=('DejaVu Sans', 9), bg=CORES['bg_painel'],
                                 fg=CORES['fg'], selectcolor=CORES['bg_input'],
                                 activebackground=CORES['bg_painel'],
                                 activeforeground=CORES['fg'])
            cb.grid(row=row, column=col, sticky='w', padx=(0, 10), pady=1)

    def _criar_secao_metricas(self):
        """Seção: Métricas do gerenciador de alertas."""
        frame = tk.Frame(self.painel_esquerdo, bg=CORES['bg_painel'])
        frame.pack(fill='x', padx=10, pady=5)

        tk.Label(frame, text="MÉTRICAS", font=('DejaVu Sans', 10, 'bold'),
                 bg=CORES['bg_painel'], fg=CORES['fg_destaque']).pack(anchor='w', pady=(0, 5))

        self.metricas_labels = {}
        campos = [
            ("Status Geral:", "status_geral"),
            ("Vel. Degradação:", "velocidade_degradacao"),
            ("Confiança:", "confianca"),
            ("Ev. Limpeza:", "num_limpezas"),
            ("Dias Críticos:", "dias_criticos"),
            ("Dias Estáveis:", "dias_estaveis"),
            ("IHE (Saúde FF):", "ihe"),
            ("Saúde Elét.:", "status_eletrico"),
            ("Recomendação:", "recomendacao"),
        ]

        for texto, chave in campos:
            row = tk.Frame(frame, bg=CORES['bg_painel'])
            row.pack(fill='x', pady=1)

            tk.Label(row, text=texto, font=('DejaVu Sans', 9),
                     bg=CORES['bg_painel'], fg=CORES['fg_label'],
                     width=18, anchor='w').pack(side='left')

            lbl = tk.Label(row, text="—", font=('DejaVu Sans Mono', 9),
                           bg=CORES['bg_painel'], fg=CORES['fg'], anchor='w')
            lbl.pack(side='left', fill='x', expand=True)
            self.metricas_labels[chave] = lbl

    def _criar_secao_log(self):
        """Seção: Log de execução."""
        frame = tk.Frame(self.painel_esquerdo, bg=CORES['bg_painel'])
        frame.pack(fill='both', expand=True, padx=10, pady=(5, 10))

        tk.Label(frame, text="LOG DE EXECUÇÃO", font=('DejaVu Sans', 10, 'bold'),
                 bg=CORES['bg_painel'], fg=CORES['fg_destaque']).pack(anchor='w', pady=(0, 5))

        self.log_text = scrolledtext.ScrolledText(
            frame, font=('DejaVu Sans Mono', 8), bg='#0d1117', fg='#c9d1d9',
            insertbackground=CORES['fg'], relief='flat', bd=5, height=8,
            wrap='word'
        )
        self.log_text.pack(fill='both', expand=True)

    # ============================================================
    # PAINEL DIREITO - Abas (Gráficos, Relatório, Config)
    # ============================================================

    def _criar_abas(self):
        """Cria sistema de abas customizado."""
        # Barra de abas
        tab_bar = tk.Frame(self.painel_direito, bg=CORES['bg'])
        tab_bar.pack(fill='x')

        self.aba_atual = tk.StringVar(value="graficos")
        self.frames_abas = {}
        self.botoes_abas = {}

        for nome, texto in [("graficos", "📊 Gráficos"), ("relatorio", "📋 Relatório"),
                             ("config", "⚙ Config")]:
            btn = tk.Button(tab_bar, text=texto, font=('DejaVu Sans', 10),
                             bg=CORES['tab_ativo'] if nome == 'graficos' else CORES['tab_inativo'],
                             fg='white', relief='flat', bd=0, padx=20, pady=8,
                             command=lambda n=nome: self._trocar_aba(n))
            btn.pack(side='left')
            self.botoes_abas[nome] = btn

        # Indicador "Concluído"
        self.label_status = tk.Label(tab_bar, text="", font=('DejaVu Sans', 9),
                                      bg=CORES['bg'], fg=CORES['verde'])
        self.label_status.pack(side='right', padx=10)

        # Container de conteúdo
        content = tk.Frame(self.painel_direito, bg=CORES['bg_painel'])
        content.pack(fill='both', expand=True)

        # Aba Gráficos
        self.frame_graficos = tk.Frame(content, bg=CORES['bg_painel'])
        self.frame_graficos.pack(fill='both', expand=True)
        self.frames_abas['graficos'] = self.frame_graficos

        self.canvas_grafico = tk.Canvas(self.frame_graficos, bg='#0d1117',
                                         highlightthickness=0)
        self.canvas_grafico.pack(fill='both', expand=True, padx=5, pady=5)

        # Navegação de gráficos
        nav = tk.Frame(self.frame_graficos, bg=CORES['bg_painel'])
        nav.pack(fill='x', padx=5, pady=(0, 5))

        self.btn_prev = tk.Button(nav, text="◀ Anterior", font=('DejaVu Sans', 9),
                                   bg=CORES['bg_botao'], fg=CORES['fg'],
                                   relief='flat', bd=0, padx=10, pady=3,
                                   command=self._grafico_anterior)
        self.btn_prev.pack(side='left')

        self.label_grafico_nome = tk.Label(nav, text="", font=('DejaVu Sans', 10),
                                            bg=CORES['bg_painel'], fg=CORES['fg_destaque'])
        self.label_grafico_nome.pack(side='left', fill='x', expand=True)

        self.btn_next = tk.Button(nav, text="Próximo ▶", font=('DejaVu Sans', 9),
                                   bg=CORES['bg_botao'], fg=CORES['fg'],
                                   relief='flat', bd=0, padx=10, pady=3,
                                   command=self._proximo_grafico)
        self.btn_next.pack(side='right')

        # Aba Relatório
        self.frame_relatorio = tk.Frame(content, bg=CORES['bg_painel'])
        self.frames_abas['relatorio'] = self.frame_relatorio

        self.relatorio_text = scrolledtext.ScrolledText(
            self.frame_relatorio, font=('DejaVu Sans Mono', 10), bg='#0d1117',
            fg='#c9d1d9', relief='flat', bd=10, wrap='word'
        )
        self.relatorio_text.pack(fill='both', expand=True, padx=5, pady=5)

        # Aba Config
        self.frame_config = tk.Frame(content, bg=CORES['bg_painel'])
        self.frames_abas['config'] = self.frame_config
        self._criar_aba_config()

    def _criar_aba_config(self):
        """Cria conteúdo da aba de configuração."""
        canvas = tk.Canvas(self.frame_config, bg=CORES['bg_painel'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.frame_config, orient='vertical', command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=CORES['bg_painel'])

        scroll_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=scroll_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scrollbar.pack(side='right', fill='y')

        # CONFIG_SISTEMA
        tk.Label(scroll_frame, text="CONFIG_SISTEMA", font=('DejaVu Sans', 12, 'bold'),
                 bg=CORES['bg_painel'], fg=CORES['fg_destaque']).pack(anchor='w', padx=10, pady=(10, 5))

        self.config_entries = {}

        for chave, valor in CONFIG_SISTEMA.items():
            row = tk.Frame(scroll_frame, bg=CORES['bg_painel'])
            row.pack(fill='x', padx=10, pady=2)

            tk.Label(row, text=f"{chave}:", font=('DejaVu Sans Mono', 9),
                     bg=CORES['bg_painel'], fg=CORES['fg_label'],
                     width=20, anchor='w').pack(side='left')

            entry = tk.Entry(row, font=('DejaVu Sans Mono', 9), bg=CORES['bg_input'],
                              fg=CORES['fg'], relief='flat', bd=3, width=20,
                              insertbackground=CORES['fg'])
            entry.insert(0, str(valor))
            entry.pack(side='left', padx=(5, 0))
            self.config_entries[('sistema', chave)] = entry

        # CONFIG_ALERTAS
        tk.Label(scroll_frame, text="CONFIG_ALERTAS", font=('DejaVu Sans', 12, 'bold'),
                 bg=CORES['bg_painel'], fg=CORES['fg_destaque']).pack(anchor='w', padx=10, pady=(15, 5))

        for chave, valor in CONFIG_ALERTAS.items():
            row = tk.Frame(scroll_frame, bg=CORES['bg_painel'])
            row.pack(fill='x', padx=10, pady=2)

            tk.Label(row, text=f"{chave}:", font=('DejaVu Sans Mono', 9),
                     bg=CORES['bg_painel'], fg=CORES['fg_label'],
                     width=20, anchor='w').pack(side='left')

            entry = tk.Entry(row, font=('DejaVu Sans Mono', 9), bg=CORES['bg_input'],
                              fg=CORES['fg'], relief='flat', bd=3, width=20,
                              insertbackground=CORES['fg'])
            entry.insert(0, str(valor))
            entry.pack(side='left', padx=(5, 0))
            self.config_entries[('alertas', chave)] = entry

    def _trocar_aba(self, nome):
        """Troca entre abas."""
        # Esconde todas
        for frame in self.frames_abas.values():
            frame.pack_forget()

        # Mostra a selecionada
        self.frames_abas[nome].pack(fill='both', expand=True)
        self.aba_atual.set(nome)

        # Atualiza cores dos botões
        for n, btn in self.botoes_abas.items():
            btn.configure(bg=CORES['tab_ativo'] if n == nome else CORES['tab_inativo'])

    # ============================================================
    # AÇÕES
    # ============================================================

    def _procurar_csv(self):
        """Abre diálogo para selecionar CSV."""
        dados_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados")
        caminho = filedialog.askopenfilename(
            title="Selecionar arquivo CSV",
            initialdir=dados_dir if os.path.exists(dados_dir) else ".",
            filetypes=[("Arquivos CSV", "*.csv"), ("Todos", "*.*")]
        )
        if caminho:
            self.caminho_csv.set(caminho)

    def _abrir_wizard_importacao(self):
        """Abre o assistente de importação."""
        wizard = ImportWizard(self.root, CORES, on_success_callback=self._on_import_success)
        wizard.grab_set()

    def _on_import_success(self, caminho_final):
        """Callback chamado pelo wizard ao finalizar com sucesso."""
        self.caminho_csv.set(caminho_final)
        self._log(f"📥 Novo arquivo importado e selecionado: {caminho_final}")
        # Sugere análise automática? Talvez não para não assustar o usuário.

    def _log(self, msg):
        """Adiciona mensagem ao log (thread-safe)."""
        self.root.after(0, self._log_impl, msg)

    def _log_impl(self, msg):
        """Implementação do log na thread principal."""
        self.log_text.insert('end', msg + "\n")
        self.log_text.see('end')

    def _ler_config_gui(self):
        """Lê configurações das entradas da aba Config."""
        config_sistema = dict(CONFIG_SISTEMA)
        config_alertas = dict(CONFIG_ALERTAS)

        for (tipo, chave), entry in self.config_entries.items():
            try:
                valor_str = entry.get().strip()
                valor = float(valor_str)
                if valor == int(valor):
                    valor = int(valor)
                if tipo == 'sistema':
                    config_sistema[chave] = valor
                else:
                    config_alertas[chave] = valor
            except ValueError:
                pass  # Mantém valor original

        return config_sistema, config_alertas

    def _graficos_selecionados(self):
        """Retorna lista de gráficos selecionados, ou todos se nenhum marcado."""
        selecionados = [num for num, var in self.graficos_vars.items() if var.get()]
        if not selecionados:
            return list(MAPA_GRAFICOS.keys())  # Todos se nenhum marcado
        return selecionados

    def _executar_threaded(self, modo):
        """Inicia execução em thread separada para não travar a GUI."""
        if not self.caminho_csv.get():
            self._log("❌ Selecione um arquivo CSV primeiro!")
            return

        if not os.path.exists(self.caminho_csv.get()):
            self._log(f"❌ Arquivo não encontrado: {self.caminho_csv.get()}")
            return

        self.log_text.delete('1.0', 'end')
        self.label_status.config(text="⏳ Processando...", fg=CORES['amarelo'])

        thread = threading.Thread(target=self._executar, args=(modo,), daemon=True)
        thread.start()

    def _executar(self, modo):
        """Executa análise na thread de trabalho."""
        try:
            config_sistema, config_alertas = self._ler_config_gui()
            caminho_csv = self.caminho_csv.get()
            graficos = self._graficos_selecionados()

            if modo in ("completa", "analise"):
                self._log(f"🚀 Iniciando análise ({modo})...")

                resultado = executar_analise(
                    caminho_csv=caminho_csv,
                    graficos_selecionados=graficos,
                    config=config_sistema,
                    log_callback=self._log
                )
                self.resultado_analise = resultado

                # Carrega gráficos na GUI
                self.root.after(0, self._carregar_graficos, resultado['caminhos_graficos'])

                if modo == "completa":
                    self._log("\n🔍 Executando análise de sujidade...")
                    gerenciador = GerenciadorAlertas(config_alertas)
                    resultado_alertas = gerenciador.analisar(
                        resultado, resultado['pasta_saida'], self._log
                    )
                    self.resultado_alertas = resultado_alertas
                    self.root.after(0, self._atualizar_metricas, resultado_alertas['metricas'])
                    self.root.after(0, self._atualizar_relatorio, resultado_alertas['relatorio'])

            elif modo == "alertas":
                self._log("⚙️  Calculando base para alertas...")
                resultado = executar_analise(
                    caminho_csv=caminho_csv,
                    graficos_selecionados=[],
                    config=config_sistema,
                    log_callback=self._log
                )
                self.resultado_analise = resultado

                self._log("\n🔍 Executando análise de sujidade...")
                gerenciador = GerenciadorAlertas(config_alertas)
                resultado_alertas = gerenciador.analisar(
                    resultado, resultado['pasta_saida'], self._log
                )
                self.resultado_alertas = resultado_alertas
                self.root.after(0, self._atualizar_metricas, resultado_alertas['metricas'])
                self.root.after(0, self._atualizar_relatorio, resultado_alertas['relatorio'])

                # Carrega gráfico de timeline se existir
                timeline_path = os.path.join(resultado['pasta_saida'], 'Alertas_Timeline.png')
                if os.path.exists(timeline_path):
                    self.root.after(0, self._carregar_graficos, [timeline_path])

            self._log("\n✅ Análise concluída! Resultados em:")
            self._log(f"   {resultado['pasta_saida']}")
            self.root.after(0, lambda: self.label_status.config(
                text="✓ Concluído", fg=CORES['verde']))

        except Exception as e:
            self._log(f"\n❌ ERRO: {e}")
            import traceback
            self._log(traceback.format_exc())
            self.root.after(0, lambda: self.label_status.config(
                text="✗ Erro", fg=CORES['vermelho']))

    # ============================================================
    # ATUALIZAÇÃO DA GUI
    # ============================================================

    def _carregar_graficos(self, caminhos):
        """Carrega lista de gráficos para navegação."""
        self.imagens_graficos = [c for c in caminhos if c and os.path.exists(c)]
        self.img_index = 0
        if self.imagens_graficos:
            self._exibir_grafico(0)
            self._trocar_aba('graficos')

    def _exibir_grafico(self, index):
        """Exibe gráfico no canvas."""
        if not self.imagens_graficos or index < 0 or index >= len(self.imagens_graficos):
            return

        self.img_index = index
        caminho = self.imagens_graficos[index]

        try:
            self.canvas_grafico.update_idletasks()
            canvas_w = self.canvas_grafico.winfo_width()
            canvas_h = self.canvas_grafico.winfo_height()

            if canvas_w < 50 or canvas_h < 50:
                canvas_w, canvas_h = 800, 500

            img = Image.open(caminho)
            img_w, img_h = img.size

            # Calcula escala mantendo proporção
            scale = min(canvas_w / img_w, canvas_h / img_h, 1.0)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)

            img = img.resize((new_w, new_h), Image.LANCZOS)
            self._photo_ref = ImageTk.PhotoImage(img)

            self.canvas_grafico.delete('all')
            self.canvas_grafico.create_image(
                canvas_w // 2, canvas_h // 2,
                image=self._photo_ref, anchor='center'
            )

            nome_arquivo = os.path.basename(caminho)
            self.label_grafico_nome.config(
                text=f"{nome_arquivo}  ({index + 1}/{len(self.imagens_graficos)})"
            )

        except Exception as e:
            self._log(f"❌ Erro ao exibir gráfico: {e}")

    def _grafico_anterior(self):
        """Navega para gráfico anterior."""
        if self.imagens_graficos and self.img_index > 0:
            self._exibir_grafico(self.img_index - 1)

    def _proximo_grafico(self):
        """Navega para próximo gráfico."""
        if self.imagens_graficos and self.img_index < len(self.imagens_graficos) - 1:
            self._exibir_grafico(self.img_index + 1)

    def _atualizar_metricas(self, metricas):
        """Atualiza labels das métricas."""
        formatacao = {
            'status_geral': lambda v: str(v),
            'velocidade_degradacao': lambda v: f"{v * 100:.2f}%/sem",
            'confianca': lambda v: f"{v * 100:.1f}%",
            'num_limpezas': lambda v: str(v),
            'dias_criticos': lambda v: str(v),
            'dias_estaveis': lambda v: str(v),
            'ihe': lambda v: f"{v:.3f} ({v * 100:.1f}%)" if v is not None else "—",
            'status_eletrico': lambda v: str(v),
            'recomendacao': lambda v: str(v),
        }

        for chave, lbl in self.metricas_labels.items():
            if chave in metricas:
                try:
                    texto = formatacao[chave](metricas[chave])
                    lbl.config(text=texto)

                    # Cores por status
                    if chave == 'status_geral':
                        if 'CRÍTICO' in texto:
                            lbl.config(fg=CORES['vermelho'])
                        elif 'ATENÇÃO' in texto or 'SUJANDO' in texto:
                            lbl.config(fg=CORES['amarelo'])
                        else:
                            lbl.config(fg=CORES['verde'])
                    elif chave == 'status_eletrico':
                        if 'CRÍTICO' in texto:
                            lbl.config(fg=CORES['vermelho'])
                        elif 'ATENÇÃO' in texto:
                            lbl.config(fg=CORES['amarelo'])
                        elif 'NORMAL' in texto:
                            lbl.config(fg=CORES['verde'])
                    elif chave == 'ihe' and metricas['ihe'] is not None:
                        v = metricas['ihe']
                        if v < 0.90:
                            lbl.config(fg=CORES['vermelho'])
                        elif v < 0.95:
                            lbl.config(fg=CORES['amarelo'])
                        else:
                            lbl.config(fg=CORES['verde'])
                except Exception:
                    lbl.config(text=str(metricas[chave]))

    def _atualizar_relatorio(self, texto_relatorio):
        """Atualiza aba de relatório."""
        self.relatorio_text.delete('1.0', 'end')
        self.relatorio_text.insert('1.0', texto_relatorio)


# ============================================================
# ENTRADA
# ============================================================

def iniciar_gui():
    """Inicia a interface gráfica."""
    root = tk.Tk()
    app = SolarAnalysisGUI(root)
    root.mainloop()


if __name__ == "__main__":
    iniciar_gui()
