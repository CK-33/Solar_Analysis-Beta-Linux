# ============================================================
# GUI WIZARD - Assistente de Importação e Conversão de Dados
# ============================================================

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import threading

from src.ingestion.detector import carregar_csv_raw, detectar_formato
from src.ingestion.adapters import adaptar_dataset
from src.ingestion.preprocessor import processar_inversor_clima
from src.config import CONFIG_SISTEMA


class ImportWizard(tk.Toplevel):
    """
    Wizard de 3 a 5 etapas para importação de dados solares.
    """

    def __init__(self, parent, cores, on_success_callback):
        super().__init__(parent)
        self.title("Assistente de Importação de Dados")
        self.geometry("900x700")
        self.configure(bg=cores['bg'])
        self.cores = cores
        self.on_success = on_success_callback

        # Estado do Wizard
        self.etapa_atual = 1
        self.tipo_importacao = tk.StringVar(value="C")  # A: Pré, B: Inv+Clima, C: API
        self.caminho_inversor = tk.StringVar()
        self.caminho_clima = tk.StringVar()
        self.df_raw = None
        self.info_deteccao = None
        self.mapeamento_vars = {}
        self.buscar_api_var = tk.BooleanVar(value=True)

        self._criar_layout()
        self._mostrar_etapa(1)

    def _criar_layout(self):
        """Estrutura básica: Header, Body, Footer."""
        # Header
        header = tk.Frame(self, bg=self.cores['bg_painel'], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)

        self.lbl_titulo_etapa = tk.Label(
            header, text="Passo 1: Tipo de Importação",
            font=('DejaVu Sans', 14, 'bold'),
            bg=self.cores['bg_painel'], fg=self.cores['fg_destaque']
        )
        self.lbl_titulo_etapa.pack(side='left', padx=20)

        # Body (Container de etapas)
        self.container = tk.Frame(self, bg=self.cores['bg'])
        self.container.pack(fill='both', expand=True, padx=20, pady=20)

        # Footer (Botões de navegação)
        footer = tk.Frame(self, bg=self.cores['bg_painel'], height=60)
        footer.pack(fill='x')
        footer.pack_propagate(False)

        self.btn_voltar = tk.Button(
            footer, text="◀ Voltar", font=('DejaVu Sans', 10),
            bg=self.cores['bg_botao'], fg=self.cores['fg'],
            relief='flat', padx=20, command=self._voltar
        )
        self.btn_voltar.pack(side='left', padx=20, pady=12)

        self.btn_proximo = tk.Button(
            footer, text="Próximo ▶", font=('DejaVu Sans', 10, 'bold'),
            bg=self.cores['bg_botao_primario'], fg='white',
            relief='flat', padx=25, command=self._proximo
        )
        self.btn_proximo.pack(side='right', padx=20, pady=12)

    def _mostrar_etapa(self, n):
        """Limpa o container e renderiza a etapa N."""
        for widget in self.container.winfo_children():
            widget.destroy()

        self.etapa_atual = n
        self.btn_voltar.config(state='normal' if n > 1 else 'disabled')
        btn_txt = "Confirmar e Salvar" if n == 4 else "Próximo ▶"
        self.btn_proximo.config(text=btn_txt)

        if n == 1: self._render_etapa_1()
        elif n == 2: self._render_etapa_2()
        elif n == 3: self._render_etapa_3()
        elif n == 4: self._render_etapa_4()

    # --- ETAPA 1: Tipo de Dado ---
    def _render_etapa_1(self):
        self.lbl_titulo_etapa.config(text="Passo 1: Qual a origem dos seus dados?")
        
        frame = tk.Frame(self.container, bg=self.cores['bg'])
        frame.pack(fill='both', expand=True, pady=30)

        opcoes = [
            ("C", "Apenas Inversor (Buscar Irradiância via API)", 
             "Tenho um CSV com dados de potência ou V/I, mas NÃO tenho dados de sol.\nO sistema buscará irradiância da API OpenMeteo automaticamente."),
            ("B", "Inversor + Clima (Excel INMET/Estação)", 
             "Tenho o CSV do inversor e o Excel de clima (formato INMET) e quero uni-los."),
            ("A", "Arquivo Pré-processado", 
             "Já tenho o CSV no formato padrão (Time, P MPPT, Rg Média, Tar med).")
        ]

        for valor, titulo, desc in opcoes:
            row = tk.Frame(frame, bg=self.cores['bg_painel'], padx=15, pady=15, 
                          highlightbackground=self.cores['borda'], highlightthickness=1)
            row.pack(fill='x', pady=5)
            
            rb = tk.Radiobutton(
                row, text=titulo, variable=self.tipo_importacao, value=valor,
                font=('DejaVu Sans', 11, 'bold'), bg=self.cores['bg_painel'], 
                fg=self.cores['fg_destaque'], selectcolor=self.cores['bg_input'],
                activebackground=self.cores['bg_painel'], activeforeground=self.cores['fg_destaque']
            )
            rb.pack(anchor='w')
            
            tk.Label(row, text=desc, font=('DejaVu Sans', 9), justify='left',
                     bg=self.cores['bg_painel'], fg=self.cores['fg_label']).pack(anchor='w', padx=25)

    # --- ETAPA 2: Seleção de Arquivos ---
    def _render_etapa_2(self):
        tipo = self.tipo_importacao.get()
        self.lbl_titulo_etapa.config(text="Passo 2: Seleção de Arquivos")
        
        # Arquivo 1 (Inversor)
        tk.Label(self.container, text="Arquivo Principal (Inversor/CSV):", 
                 font=('DejaVu Sans', 10, 'bold'), bg=self.cores['bg'], fg=self.cores['fg']).pack(anchor='w', pady=(20, 5))
        
        row1 = tk.Frame(self.container, bg=self.cores['bg'])
        row1.pack(fill='x')
        tk.Entry(row1, textvariable=self.caminho_inversor, bg=self.cores['bg_input'], fg='white', relief='flat').pack(side='left', fill='x', expand=True, padx=(0, 10))
        tk.Button(row1, text="Selecionar", command=lambda: self._select_file(self.caminho_inversor)).pack(side='right')

        # Arquivo 2 (Clima - apenas Tipo B)
        if tipo == "B":
            tk.Label(self.container, text="Arquivo de Clima (Excel/CSV):", 
                     font=('DejaVu Sans', 10, 'bold'), bg=self.cores['bg'], fg=self.cores['fg']).pack(anchor='w', pady=(20, 5))
            row2 = tk.Frame(self.container, bg=self.cores['bg'])
            row2.pack(fill='x')
            tk.Entry(row2, textvariable=self.caminho_clima, bg=self.cores['bg_input'], fg='white', relief='flat').pack(side='left', fill='x', expand=True, padx=(0, 10))
            tk.Button(row2, text="Selecionar", command=lambda: self._select_file(self.caminho_clima, [("Excel/CSV", "*.xlsx *.xls *.csv")])).pack(side='right')

    # --- ETAPA 3: Mapeamento de Colunas ---
    def _render_etapa_3(self):
        self.lbl_titulo_etapa.config(text="Passo 3: Mapeamento de Colunas")
        
        if self.df_raw is None:
            try:
                self.df_raw = carregar_csv_raw(self.caminho_inversor.get())
                self.info_deteccao = detectar_formato(self.df_raw)
            except Exception as e:
                messagebox.showerror("Erro", str(e))
                self._mostrar_etapa(2)
                return

        tk.Label(self.container, text="O sistema detectou as seguintes colunas. Ajuste se necessário:",
                 font=('DejaVu Sans', 9), bg=self.cores['bg'], fg=self.cores['fg_label']).pack(anchor='w', pady=(0, 15))

        # Tabela de Mapeamento
        frame_map = tk.Frame(self.container, bg=self.cores['bg_painel'], padx=10, pady=10)
        frame_map.pack(fill='both', expand=True)

        # Cabeçalhos
        tk.Label(frame_map, text="Coluna no Arquivo", font=('DejaVu Sans', 9, 'bold'), bg=self.cores['bg_painel'], fg=self.cores['fg_destaque'], width=30, anchor='w').grid(row=0, column=0, pady=5)
        tk.Label(frame_map, text="Tipo de Dado", font=('DejaVu Sans', 9, 'bold'), bg=self.cores['bg_painel'], fg=self.cores['fg_destaque'], width=30, anchor='w').grid(row=0, column=1, pady=5)

        opcoes_destino = ["(Ignorar)", "P MPPT (W)", "__Vdc__", "__Idc__", "Rg Média", "Tar med"]
        
        self.mapeamento_vars = {}
        for i, col in enumerate(self.df_raw.columns):
            tk.Label(frame_map, text=col, font=('DejaVu Sans Mono', 9), bg=self.cores['bg_painel'], fg=self.cores['fg'], width=35, anchor='w').grid(row=i+1, column=0, pady=2)
            
            # Valor sugerido pelo detector
            sugerido = self.info_deteccao['mapeamento'].get(col, "(Ignorar)")
            var = tk.StringVar(value=sugerido)
            self.mapeamento_vars[col] = var
            
            cb = ttk.Combobox(frame_map, textvariable=var, values=opcoes_destino, state="readonly", width=25)
            cb.grid(row=i+1, column=1, pady=2, padx=5)

        # Checklist API
        if self.tipo_importacao.get() == "C":
            cb_api = tk.Checkbutton(
                self.container, text="Buscar irradiância/temperatura via API se faltarem",
                variable=self.buscar_api_var, font=('DejaVu Sans', 9), bg=self.cores['bg'],
                fg=self.cores['fg'], selectcolor=self.cores['bg_input'], activebackground=self.cores['bg']
            )
            cb_api.pack(anchor='w', pady=15)

    # --- ETAPA 4: Prévia e Processamento ---
    def _render_etapa_4(self):
        self.lbl_titulo_etapa.config(text="Passo 4: Prévia do Resultado")
        
        frame_prog = tk.Frame(self.container, bg=self.cores['bg'])
        frame_prog.pack(fill='both', expand=True)
        
        self.lbl_status = tk.Label(frame_prog, text="⚙️ Processando dados...", font=('DejaVu Sans', 10), bg=self.cores['bg'], fg='white')
        self.lbl_status.pack(pady=20)
        
        self.progress = ttk.Progressbar(frame_prog, orient='horizontal', length=400, mode='indeterminate')
        self.progress.pack(pady=10)
        self.progress.start()

        # Roda processamento em thread
        threading.Thread(target=self._executar_processamento, daemon=True).start()

    def _executar_processamento(self):
        try:
            tipo = self.tipo_importacao.get()
            mapa = {k: v.get() for k, v in self.mapeamento_vars.items() if v.get() != "(Ignorar)"}

            if tipo == "B":
                # Caso B: Inversor + Clima
                df_final = processar_inversor_clima(
                    self.caminho_inversor.get(),
                    self.caminho_clima.get()
                )
            else:
                # Caso A ou C: Adaptador
                df_final = adaptar_dataset(
                    self.df_raw,
                    mapa,
                    buscar_api=self.buscar_api_var.get(),
                    lat=CONFIG_SISTEMA['lat'],
                    lon=CONFIG_SISTEMA['lon']
                )

            self.df_resultado = df_final
            self.after(0, self._mostrar_previa)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Erro no Processamento", str(e)))
            self.after(0, lambda: self._mostrar_etapa(3))

    def _mostrar_previa(self):
        self.progress.stop()
        for w in self.container.winfo_children(): w.destroy()
        
        tk.Label(self.container, text=f"Sucesso! {len(self.df_resultado)} registros gerados.", 
                 font=('DejaVu Sans', 10, 'bold'), bg=self.cores['bg'], fg=self.cores['verde']).pack(pady=(0, 10))
        
        # Tabela de prévia (text area)
        txt = tk.Text(self.container, height=15, bg='#0d1117', fg='#c9d1d9', font=('DejaVu Sans Mono', 8))
        txt.pack(fill='both', expand=True)
        txt.insert('end', self.df_resultado.head(20).to_string())
        txt.config(state='disabled')

        res = self.df_resultado.index.to_series().diff().median()
        tk.Label(self.container, text=f"Resolução detectada: {res}", font=('DejaVu Sans', 9), bg=self.cores['bg'], fg=self.cores['fg_label']).pack(pady=5)

    # --- NAVEGAÇÃO ---
    def _select_file(self, var, types=[("Arquivos CSV", "*.csv")]):
        path = filedialog.askopenfilename(filetypes=types)
        if path: var.set(path)

    def _proximo(self):
        if self.etapa_atual == 2 and not self.caminho_inversor.get():
            messagebox.showwarning("Aviso", "Selecione o arquivo do inversor!"); return
        
        if self.etapa_atual == 4:
            self._finalizar()
        else:
            self._mostrar_etapa(self.etapa_atual + 1)

    def _voltar(self):
        self._mostrar_etapa(self.etapa_atual - 1)

    def _finalizar(self):
        # Salva em dados/ convertido
        nome_orig = os.path.splitext(os.path.basename(self.caminho_inversor.get()))[0]
        ext = "_processado.csv"
        dados_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "dados")
        os.makedirs(dados_dir, exist_ok=True)
        
        caminho_saida = os.path.join(dados_dir, nome_orig + ext)
        self.df_resultado.to_csv(caminho_saida)
        
        messagebox.showinfo("Sucesso", f"Arquivo convertido e salvo em:\n{caminho_saida}")
        self.on_success(caminho_saida)
        self.destroy()
