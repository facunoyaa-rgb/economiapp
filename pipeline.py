import json
import os
import requests
import pandas as pd

def get_macro_data(config_path="config.json"):
    """
    Descarga series de tiempo macroeconómicas de datos.gob.ar basadas en el archivo config.json,
    unifica las fechas en formato datetime y retorna un DataFrame consolidado y limpio.
    """
    # 1. Cargar archivo de configuración
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"No se encontró el archivo de configuración en: {config_path}")
        
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    api_base = config.get("api", {}).get("base_url", "https://apis.datos.gob.ar/series/api")
    series_config = config.get("series", {})
    
    # 2. Definir mapeo de nombre de columna -> ID de la serie
    id_mapping = {
        "EMAE_Original": series_config["emae"]["opciones"]["original"]["id"],
        "EMAE_Desestacionalizado": series_config["emae"]["opciones"]["desestacionalizado"]["id"],
        "IPC_Nivel_General": series_config["ipc"]["opciones"]["nivel_general"]["id"],
        "IPC_Variacion_Mensual": series_config["ipc"]["opciones"]["variacion_mensual"]["id"],
        "Tasa_Interes_Nominal": series_config["tasa_interes"]["opciones"]["promedio_mensual"]["id"],
        "Exportaciones_FOB": series_config["exportaciones"]["id"],
        "Importaciones_CIF": series_config["importaciones"]["id"],
        "Gasto_Publico_Primario": series_config["gasto_publico"]["opciones"]["primario"]["id"],
        "Gasto_Publico_Total": series_config["gasto_publico"]["opciones"]["total"]["id"],
        "Credito_Interno": series_config["credito_interno"]["id"],
        "Salarios": series_config["salarios"]["id"]
    }
    
    dfs = []
    
    # 3. Descargar cada serie y estructurarla en un DataFrame
    for col_name, series_id in id_mapping.items():
        print(f"Descargando {col_name} (ID: {series_id})...")
        url = f"{api_base}/series/?ids={series_id}&limit=5000&format=json"
        
        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            response.raise_for_status()
            json_data = response.json()
            
            data_rows = json_data.get("data", [])
            
            # Fallback especial si la API devuelve data vacía pero existe distribución descargable en meta (ej. RIPTE)
            if not data_rows and json_data.get("meta"):
                for m in json_data["meta"]:
                    dist_url = m.get("distribution", {}).get("downloadURL")
                    if dist_url:
                        try:
                            csv_resp = requests.get(dist_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                            if csv_resp.status_code == 200:
                                import io
                                csv_df = pd.read_csv(io.StringIO(csv_resp.text))
                                date_col = [c for c in csv_df.columns if "fecha" in c.lower() or "tiempo" in c.lower()][0]
                                val_col = [c for c in csv_df.columns if c != date_col][0]
                                data_rows = csv_df[[date_col, val_col]].dropna().values.tolist()
                                print(f"  -> Recuperados {len(data_rows)} registros desde la distribución CSV de respaldo para {col_name}")
                                break
                        except Exception as csv_err:
                            print(f"  -> Error al obtener CSV de respaldo: {csv_err}")

            if not data_rows:
                print(f"Advertencia: No se encontraron datos para {col_name}")
                continue
                
            # Crear DataFrame para la serie individual e igualar a inicio de mes
            df = pd.DataFrame(data_rows, columns=["Fecha", col_name])
            df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.to_period('M').dt.to_timestamp()
            # Agrupar por si hay múltiples observaciones en el mismo mes y obtener el promedio
            df = df.groupby("Fecha", as_index=False).mean()
            dfs.append(df)
            print(f"  -> Cargadas {len(df)} observaciones de {col_name}")
            
        except Exception as e:
            print(f"Error al descargar {col_name} (ID: {series_id}): {e}")
            
    if not dfs:
        raise ValueError("No se pudo descargar ninguna de las series configuradas.")
        
    # 4. Consolidar todas las series en un único DataFrame mediante un outer join en 'Fecha'
    print("\nConsolidando y alineando series temporales...")
    merged_df = dfs[0]
    for df in dfs[1:]:
        merged_df = pd.merge(merged_df, df, on="Fecha", how="outer")
        
    # 5. Ordenar cronológicamente y limpiar índices
    merged_df = merged_df.sort_values(by="Fecha").reset_index(drop=True)
    print("Consolidación inicial finalizada.")
    
    # 6. Procesamiento de variables reales (Deflactación por IPC)
    # Encontrar el IPC más reciente válido
    ipc_general_valido = merged_df["IPC_Nivel_General"].dropna()
    if not ipc_general_valido.empty:
        ipc_reciente = ipc_general_valido.iloc[-1]
        ipc_fecha = merged_df.loc[ipc_general_valido.index[-1], 'Fecha'].strftime('%Y-%m-%d')
        print(f"IPC Base más reciente para deflactar: {ipc_reciente} ({ipc_fecha})")
        
        # Columnas a deflactar (nominal / IPC_periodo * IPC_reciente)
        deflate_cols = ["Gasto_Publico_Primario", "Gasto_Publico_Total", "Credito_Interno", "Salarios"]
        for col in deflate_cols:
            if col in merged_df.columns:
                merged_df[f"{col}_Real"] = (merged_df[col] / merged_df["IPC_Nivel_General"]) * ipc_reciente
                print(f"  -> Creada versión real: {col}_Real")
    else:
        print("Advertencia: No se encontró índice IPC válido para deflactación.")
        
    # 7. Cálculo de la Tasa de Interés Real Mensual (Fisher)
    if "Tasa_Interes_Nominal" in merged_df.columns and "IPC_Variacion_Mensual" in merged_df.columns:
        # i_m = TNA / 12 / 100
        i_m = merged_df["Tasa_Interes_Nominal"] / 12 / 100
        # inf_m ya es decimal en IPC_Variacion_Mensual
        inf_m = merged_df["IPC_Variacion_Mensual"]
        
        # Fisher exacta mensual: (1 + i_m) / (1 + inf_m) - 1 (convertido a porcentaje)
        merged_df["Tasa_Interes_Real_Mensual_Exacta"] = (((1 + i_m) / (1 + inf_m)) - 1) * 100
        # Fisher aproximada mensual: i_m - inf_m (en porcentaje)
        merged_df["Tasa_Interes_Real_Mensual_Aprox"] = (i_m - inf_m) * 100
        print("  -> Calculadas Tasas de Interés Real (Exacta y Aproximada)")
        
    return merged_df

if __name__ == "__main__":
    print("====================================================")
    print("Iniciando pipeline de descarga macroeconómica...")
    print("====================================================")
    try:
        df = get_macro_data()
        print("\n====================================================")
        print("¡El pipeline se ejecutó correctamente sin errores!")
        print("====================================================")
        print("\nInformación del DataFrame consolidado:")
        print(df.info())
        print("\nPrimeras 5 filas:")
        print(df.head())
        print("\nÚltimas 5 filas:")
        print(df.tail())
        
        # Guardar una vista previa local en CSV para control
        output_file = "macro_data_preview.csv"
        df.to_csv(output_file, index=False)
        print(f"\nVista previa guardada en: {output_file}")
        
    except Exception as e:
        print(f"\nError durante la ejecución del pipeline: {e}")
