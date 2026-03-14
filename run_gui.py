#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Atalho para iniciar a GUI do Sistema de Análise Fotovoltaica.
Pode ser executado diretamente ou chamado pelo run.bat.
"""

import os
import sys

# Garante que o diretório do projeto é o diretório de trabalho
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.gui import iniciar_gui

if __name__ == "__main__":
    iniciar_gui()
