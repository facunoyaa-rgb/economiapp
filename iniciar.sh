#!/bin/bash
# Script para iniciar el Dashboard Macroeconómico de Argentina

# Obtener la ruta del directorio donde está guardado este script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=================================================="
echo " Iniciando Dashboard Macroeconómico de Argentina..."
echo "=================================================="
echo "Directorio de trabajo: $DIR"

# Activar el entorno virtual si existiera (por si en el futuro se crea uno)
if [ -d ".venv" ]; then
    echo "Activando entorno virtual .venv..."
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo "Activando entorno virtual venv..."
    source venv/bin/activate
fi

# Ejecutar streamlit
if command -v streamlit &> /dev/null; then
    streamlit run app.py
elif [ -f "$HOME/.local/bin/streamlit" ]; then
    "$HOME/.local/bin/streamlit" run app.py
else
    python3 -m streamlit run app.py
fi

# Pausar en caso de que la terminal se cierre inmediatamente si hay un error
echo ""
echo "Streamlit ha finalizado. Presiona Enter para cerrar esta ventana..."
read -r
