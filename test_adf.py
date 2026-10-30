import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import adfuller

# 1. Cargar el dataset
# Nota: Como el archivo está en tu directorio actual, usamos el nombre directamente.
df = pd.read_csv('sh_ipc_05_26(1).csv')

# 2. Limpieza de datos: Reemplazar comas por puntos y convertir a flotante
df['IPC'] = df['IPC'].str.replace(',', '.').astype(float)

# 3. Ejecutar el test de Dickey-Fuller Aumentado (ADF) en niveles
# 'regression="c"' indica que incluimos una constante (intercepto) en la regresión
resultado_adf = adfuller(df['IPC'].dropna(), regression='c')

# 4. Desempaquetar y mostrar los resultados analíticamente
print("=== RESULTADOS DEL TEST ADF EN NIVELES ===")
print(f"Estadístico del Test ADF: {resultado_adf[0]:.4f}")
print(f"p-valor: {resultado_adf[1]:.4f}")
print(f"Número de rezagos utilizados de forma óptima: {resultado_adf[2]}")
print(f"Número de observaciones: {resultado_adf[3]}")
print("Valores Críticos Estatutarios:")
for clave, valor in resultado_adf[4].items():
    print(f"   {clave}: {valor:.4f}")

# 5. Regla de decisión automatizada
if resultado_adf[1] < 0.05:
    print("\nConclusión: El p-valor es menor a 0.05. Se rechaza H0. La serie es ESTACIONARIA.")
else:
    print("\nConclusión: El p-valor es mayor a 0.05. No se rechaza H0. La serie tiene una raíz unitaria (es NO ESTACIONARIA).")
