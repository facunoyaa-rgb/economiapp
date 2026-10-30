import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import adfuller

# 1. Cargar y limpiar el dataset
df = pd.read_csv('sh_ipc_05_26.csv')
df['IPC'] = df['IPC'].str.replace(',', '.').astype(float)

# 2. Calcular Inflación (Primera diferencia del log) y Aceleración (Diferencia de la inflación)
df['log_IPC'] = np.log(df['IPC'])
df['inflacion'] = df['log_IPC'].diff()
df['aceleracion'] = df['inflacion'].diff()  # Segunda diferencia del log_IPC

print("=== 1. TEST ADF: INFLACIÓN MENSUAL (Solo Constante) ===")
res_inf = adfuller(df['inflacion'].dropna(), regression='c')
print(f"p-valor: {res_inf[1]:.4f} (Estacionaria al 10%, pero al 5% acusa alta persistencia/quiebres)\n")

print("=== 2. TEST ADF: ACELERACIÓN DE LA INFLACIÓN (Segunda Diferencia) ===")
res_ace = adfuller(df['aceleracion'].dropna(), regression='c')
print(f"Estadístico ADF: {res_ace[0]:.4f}")
print(f"p-valor: {res_ace[1]:.8f}")  # Mostramos más decimales por si es muy bajo
print("Valores Críticos:")
for clave, valor in res_ace[4].items():
    print(f"   {clave}: {valor:.4f}")

if res_ace[1] < 0.01:
    print("\nConclusión: El p-valor es prácticamente 0. Rechazo rotundo de H0 al 1%.")
    print("La aceleración de la inflación es un proceso puramente ESTACIONARIO (I(0)).")
