import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from statsmodels.tsa.api import VAR

# ========================================================
# 1. CARGA, LIMPIEZA Y ENSAMBLE MACROECONÓMICA
# ========================================================
df_ipc = pd.read_csv('sh_ipc_05_26(1).csv')
df_ipc['IPC'] = df_ipc['IPC'].str.replace(',', '.').astype(float)
df_ipc['Fecha'] = pd.date_range(start='2016-12-01', periods=len(df_ipc), freq='ME')

df_tc = pd.read_csv('tipo_cambio_promedio_mensual_argentina.csv')
df_tc['Fecha'] = pd.date_range(start='2016-01-01', periods=len(df_tc), freq='ME')

df_macro = pd.merge(df_ipc[['Fecha', 'IPC']], df_tc[['Fecha', df_tc.columns[1]]], on='Fecha', how='inner')
df_macro.columns = ['Fecha', 'IPC', 'TC'] 

df_macro['inflacion'] = np.log(df_macro['IPC']).diff() * 100
df_macro['devaluacion'] = np.log(df_macro['TC']).diff() * 100

# Mantenemos el orden Cholesky: devaluación primero, inflación segundo
df_final = df_macro[['devaluacion', 'inflacion']].dropna()
df_final.index = df_macro['Fecha'].dropna().iloc[1:]

# ========================================================
# 2. ESTIMACIÓN DEL MODELO VAR (8 rezagos)
# ========================================================
modelo = VAR(df_final)
resultado_var = modelo.fit(8)

# ========================================================
# 3. DESCOMPOSICIÓN DE LA VARIANZA (FEVD) - CORREGIDA
# ========================================================
print("\n=== DESCOMPOSICIÓN DE LA VARIANZA DEL ERROR DE PRONÓSTICO (FEVD) ===")
# Calculamos la descomposición para un horizonte de 12 meses
fevd = resultado_var.fevd(periods=12)

# fevd.decomp es un array de tres dimensiones: [variable][horizonte][porcentaje_contribucion]
# En statsmodels, el orden de las variables sigue la estructura del DataFrame original.
# Dado que pusimos 'devaluacion' en la posición 0 e 'inflacion' en la posición 1,
# extraemos el índice [1] correspondiente a los errores de la INFLACIÓN.
tabla_fevd_inf = pd.DataFrame(fevd.decomp[1] * 100, 
                              columns=['Shocks de Devaluación (%)', 'Shocks de Inflación (%)'],
                              index=[f'Mes {i}' for i in range(1, 13)])

print("\n¿Qué explica la variabilidad de la INFLACIÓN MENSUAL?")
print(tabla_fevd_inf.round(2))

# 4. Generar gráfico analítico de la FEVD
fevd.plot()
plt.tight_layout()
plt.show()
