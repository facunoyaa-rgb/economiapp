#!/bin/bash
# Script para iniciar el Dashboard Macroeconómico de Argentina (Dash)

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=================================================="
echo " Iniciando Dashboard Macroeconómico de Argentina..."
echo "=================================================="
echo "Directorio de trabajo: $DIR"
echo "URL: http://127.0.0.1:8050"

if [ -x ".venv/bin/python" ]; then
    .venv/bin/python app.py
elif [ -x "venv/bin/python" ]; then
    venv/bin/python app.py
else
    python3 app.py
fi

echo ""
echo "El servidor ha finalizado. Presiona Enter para cerrar esta ventana..."
read -r
