# ============================================================
# MAIN - Menu interativo CLI
# ============================================================

import os
import sys

# Adiciona diretório pai ao path para importações
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import CONFIG_SISTEMA, CONFIG_ALERTAS
from src.analisador_core import selecionar_arquivo, selecionar_graficos, executar_analise
from src.gerenciador_alertas import detectar_sujidade


DIRETORIO_DADOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados")


def menu_principal():
    """Menu interativo principal."""
    print("\n" + "=" * 60)
    print("  ☀️  SISTEMA DE ANÁLISE FOTOVOLTAICA")
    print("  Análise de FF, PR e Detecção de Sujidade")
    print("=" * 60)

    while True:
        print("\n--- MENU PRINCIPAL ---")
        print("[1] Apenas Análise FF / PR (gráficos)")
        print("[2] Análise Completa (FF + PR + Alertas de Sujidade)")
        print("[3] Apenas Alertas de Sujidade")
        print("[0] Sair")

        opcao = input("\nEscolha: ").strip()

        if opcao == "0":
            print("\n👋 Até mais!")
            break
        elif opcao in ("1", "2", "3"):
            executar_opcao(opcao)
        else:
            print("❌ Opção inválida!")


def executar_opcao(opcao):
    """Executa a opção selecionada."""
    # Seleciona arquivo
    print(f"\n📂 Buscando arquivos em: {DIRETORIO_DADOS}")
    caminho = selecionar_arquivo(DIRETORIO_DADOS)
    if not caminho:
        print("❌ Nenhum arquivo selecionado.")
        return

    if opcao in ("1", "2"):
        # Seleciona gráficos
        graficos = selecionar_graficos()
        if not graficos:
            print("❌ Nenhum gráfico selecionado.")
            return

        # Executa análise core
        resultado = executar_analise(
            caminho_csv=caminho,
            graficos_selecionados=graficos,
            config=CONFIG_SISTEMA
        )

        if opcao == "2":
            # Executa gerenciador de alertas
            resultado_alertas = detectar_sujidade(
                dados_analisador=resultado,
                config_alertas=CONFIG_ALERTAS,
                pasta_saida=resultado['pasta_saida']
            )
            print(f"\n📁 Resultados completos em: {resultado['pasta_saida']}")

    elif opcao == "3":
        # Apenas alertas (precisa rodar análise sem gráficos)
        print("\n⚙️  Executando cálculos base para alertas...")
        resultado = executar_analise(
            caminho_csv=caminho,
            graficos_selecionados=[],
            config=CONFIG_SISTEMA
        )
        resultado_alertas = detectar_sujidade(
            dados_analisador=resultado,
            config_alertas=CONFIG_ALERTAS,
            pasta_saida=resultado['pasta_saida']
        )
        print(f"\n📁 Resultados em: {resultado['pasta_saida']}")


if __name__ == "__main__":
    menu_principal()
