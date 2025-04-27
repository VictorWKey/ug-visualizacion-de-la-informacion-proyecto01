import pandas as pd
import numpy as np
import os
import glob
from math import radians, cos, sin, asin, sqrt
from datetime import timedelta
import matplotlib.pyplot as plt
import seaborn as sns
import gc # Importar garbage collector para forzar limpieza
import matplotlib.colors as colors # Importar colors para LogNorm
# from scipy.stats import gaussian_kde # Ya no se usa
# Opcional: para mapas base geográficos
try:
    import contextily as cx
    CONTEXTILY_AVAILABLE = True
except ImportError:
    CONTEXTILY_AVAILABLE = False
    print("Contextily no encontrado. Los mapas de calor se generarán sin mapa base.")
    print("Puedes instalarlo con: pip install contextily")

# --- Configuración ---
DATA_DIR = 'taxi_log_2008_by_id' # Directorio con los archivos .txt
OUTPUT_DIR = 'heatmaps_output'  # Directorio donde se guardarán las imágenes
TIME_INTERVAL_HOURS = 1      # Intervalo de tiempo para cada heatmap
SPEED_THRESHOLD_KMH = 25      # Umbral para considerar "tráfico" (velocidad baja)
MAX_TIME_DELTA_SECONDS = 600    # Máximo tiempo entre puntos para calcular velocidad (10 min)
MAX_SPEED_KMH = 150             # Máxima velocidad realista para filtrar errores
BATCH_SIZE = 500                # Número de archivos a procesar en cada lote (Ajusta según tu RAM)
CACHE_FILENAME = 'cached_slow_points.parquet'

# Límites aproximados para Beijing (ajusta si es necesario)
# Estos ayudan a mantener el mapa consistente entre imágenes
MAP_BOUNDS = {
    'lon_min': 116.15,
    'lon_max': 116.6,
    'lat_min': 39.75,
    'lat_max': 40.1
}

# --- Funciones ---

def haversine(lon1, lat1, lon2, lat2):
    """
    Calcula la distancia entre dos puntos lat/lon en la Tierra (en km).
    """
    # Convertir grados decimales a radianes
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # Fórmula Haversine
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371 # Radio de la Tierra en kilómetros
    return c * r

def calculate_speed(df):
    """
    Calcula la velocidad entre puntos consecutivos para cada taxi.
    Asume que el df está ordenado por taxi_id y timestamp.
    Modificado para devolver solo las columnas necesarias para el heatmap.
    """
    if df.empty:
        return pd.DataFrame(columns=['timestamp', 'longitude', 'latitude', 'speed_kmh'])

    df = df.sort_values(by=['taxi_id', 'timestamp'])
    df['lat_prev'] = df.groupby('taxi_id')['latitude'].shift(1)
    df['lon_prev'] = df.groupby('taxi_id')['longitude'].shift(1)
    df['time_prev'] = df.groupby('taxi_id')['timestamp'].shift(1)

    # Eliminar filas donde no hay punto previo para calcular velocidad
    df = df.dropna(subset=['lat_prev', 'lon_prev', 'time_prev'])
    if df.empty:
        return pd.DataFrame(columns=['timestamp', 'longitude', 'latitude', 'speed_kmh'])

    # Calcular distancia y tiempo delta
    # Usar .loc para evitar SettingWithCopyWarning
    df_loc = df.loc[:, ['longitude', 'latitude', 'lon_prev', 'lat_prev', 'timestamp', 'time_prev']].copy()
    df_loc['distance_km'] = df_loc.apply(
        lambda row: haversine(row['lon_prev'], row['lat_prev'], row['longitude'], row['latitude']),
        axis=1
    )
    df_loc['time_delta_sec'] = (df_loc['timestamp'] - df_loc['time_prev']).dt.total_seconds()

    # Calcular velocidad en km/h
    df_loc['speed_kmh'] = 0.0
    valid_time = (df_loc['time_delta_sec'] > 1) & (df_loc['time_delta_sec'] <= MAX_TIME_DELTA_SECONDS)

    # Asegurarse de que time_delta_sec no sea cero donde valid_time es True para evitar división por cero
    safe_denominator = df_loc.loc[valid_time, 'time_delta_sec'].replace(0, np.nan).dropna()
    if not safe_denominator.empty:
         df_loc.loc[safe_denominator.index, 'speed_kmh'] = (df_loc.loc[safe_denominator.index, 'distance_km'] / (safe_denominator / 3600))

    # Filtrar velocidades irreales
    df_loc = df_loc[df_loc['speed_kmh'] <= MAX_SPEED_KMH]

    # Devolver solo columnas relevantes
    return df_loc[['timestamp', 'longitude', 'latitude', 'speed_kmh']]

# --- Mover la definición de generate_heatmap aquí --- #
def generate_heatmap(interval_data, output_filename, interval_start, interval_end, bins, cmap, norm): # Añadido 'norm'
    """ Genera y guarda un heatmap (hist2d) para los datos de un intervalo. """
    min_points_threshold = 5
    if len(interval_data) < min_points_threshold:
        print(f"    Datos insuficientes ({len(interval_data)} puntos, umbral={min_points_threshold}) para hist2d. Omitiendo.")
        return False

    fig, ax = plt.subplots(figsize=(10, 10))
    fig.patch.set_facecolor('darkslategray')
    ax.set_facecolor('black')
    ax.tick_params(axis='x', colors='white')
    ax.tick_params(axis='y', colors='white')
    ax.yaxis.label.set_color('white')
    ax.xaxis.label.set_color('white')
    ax.title.set_color('white')

    try:
        # Ya no calculamos la norma aquí, la recibimos como argumento

        # Calcular y mostrar histograma 2D usando la norma global
        _, _, _, im = ax.hist2d(
            x=interval_data['longitude'],
            y=interval_data['latitude'],
            bins=bins,
            cmap=cmap,
            norm=norm, # Usar la norma global precalculada
            range=[[MAP_BOUNDS['lon_min'], MAP_BOUNDS['lon_max']],
                   [MAP_BOUNDS['lat_min'], MAP_BOUNDS['lat_max']]]
        )

        cbar_label = 'Densidad puntos lentos (Log Scale)' if isinstance(norm, colors.LogNorm) else 'Densidad puntos lentos (Linear Scale)'
        cbar = fig.colorbar(im, ax=ax, label=cbar_label)
        cbar.ax.yaxis.label.set_color('white')
        cbar.ax.tick_params(axis='y', colors='white')

        # --- Personalizar Ticks de la Colorbar (Lineal con más ticks) --- # Añadido/Modificado
        from matplotlib.ticker import LinearLocator, ScalarFormatter

        num_ticks_deseado = 12 # Elige el número total de ticks (ej. 11 para 10 intervalos)
        locator = LinearLocator(numticks=num_ticks_deseado)
        cbar.ax.yaxis.set_major_locator(locator)

        # Forzar formato escalar (números normales)
        formatter = ScalarFormatter()
        formatter.set_powerlimits((-3, 4)) # Evita notación científica para números en este rango de potencias de 10
        cbar.ax.yaxis.set_major_formatter(formatter)
        # --- Fin Personalización Ticks --- #

        ax.set_xlim(MAP_BOUNDS['lon_min'], MAP_BOUNDS['lon_max'])
        ax.set_ylim(MAP_BOUNDS['lat_min'], MAP_BOUNDS['lat_max'])

        ax.set_title(f"Densidad Puntos Lentos ({interval_start.strftime('%Y-%m-%d %H:%M')} - {interval_end.strftime('%Y-%m-%d %H:%M')})")
        ax.set_xlabel("Longitud")
        ax.set_ylabel("Latitud")
        plt.tight_layout()

        print(f"    Guardando: {output_filename}")
        plt.savefig(output_filename, dpi=150, facecolor=fig.get_facecolor())
        return True

    except Exception as e:
        print(f"    Error generando hist2d para el intervalo {interval_start}-{interval_end}: {e}. Omitiendo.")
        return False
    finally:
        plt.close(fig)
        # No necesitamos borrar interval_data aquí, se borra en main
        gc.collect()
# --- Fin definición generate_heatmap ---

# --- Script Principal ---

print("Iniciando script de generación de heatmaps con procesamiento por lotes...")

# 1. Crear directorio de salida
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Lógica de Caché --- # Modificado para cargar/guardar PUNTOS LENTOS
cache_filepath = os.path.join('.', CACHE_FILENAME)
slow_points = None # Cambiado de speed_points

if os.path.exists(cache_filepath):
    print(f"Encontrado archivo caché: {CACHE_FILENAME}. Cargando puntos lentos precalculados...") # Mensaje cambiado
    try:
        import pyarrow
        slow_points = pd.read_parquet(cache_filepath)
        print(f"Puntos lentos cargados desde caché: {len(slow_points)}")
        # Validar columnas básicas y tipo de timestamp
        required_cols_for_heatmap = ['timestamp', 'longitude', 'latitude'] # Solo estas 3
        if not all(col in slow_points.columns for col in required_cols_for_heatmap):
            print("Advertencia: El archivo caché no contiene las columnas esperadas (timestamp, longitude, latitude). Se recalculará.")
            slow_points = None
            os.remove(cache_filepath)
        else:
             slow_points['timestamp'] = pd.to_datetime(slow_points['timestamp'])

    except ImportError:
        print("Error: Se necesita la biblioteca 'pyarrow' para leer archivos Parquet.")
        print("Instálala con: pip install pyarrow")
        print("Continuando sin usar caché...")
        slow_points = None
    except Exception as e:
        print(f"Error cargando el archivo caché {CACHE_FILENAME}: {e}")
        print("Se procederá a recalcular desde cero.")
        try:
            os.remove(cache_filepath)
        except OSError:
            pass
        slow_points = None
else:
    print(f"No se encontró archivo caché: {CACHE_FILENAME}. Se calcularán los puntos lentos...") # Mensaje cambiado

# --- Bloque de Cálculo (Solo si no se cargó desde caché) ---
if slow_points is None:
    # 2. Encontrar todos los archivos de datos
    all_files = glob.glob(os.path.join(DATA_DIR, "*.txt"))
    total_files = len(all_files)
    if not all_files:
        print(f"Error: No se encontraron archivos .txt en el directorio '{DATA_DIR}'")
        exit()

    # 3. Procesar archivos en lotes
    num_batches = int(np.ceil(total_files / BATCH_SIZE))
    print(f"Total de archivos: {total_files}. Tamaño de lote: {BATCH_SIZE}. Número de lotes: {num_batches}")

    all_slow_points_list = [] # Cambiado nombre de la lista
    expected_cols = ['taxi_id', 'timestamp', 'longitude', 'latitude']

    for i_batch in range(num_batches):
        start_index = i_batch * BATCH_SIZE
        end_index = min((i_batch + 1) * BATCH_SIZE, total_files)
        batch_files = all_files[start_index:end_index]

        print(f"--- Procesando Lote {i_batch + 1}/{num_batches} (Archivos {start_index + 1}-{end_index}) ---")

        batch_data = []
        files_processed_in_batch = 0
        valid_files_in_batch = 0

        # Cargar y validar archivos del lote
        for f in batch_files:
            try:
                df = pd.read_csv(
                    f,
                    header=None,
                    names=expected_cols,
                    parse_dates=['timestamp'],
                    date_format='%Y-%m-%d %H:%M:%S'
                )
                if df.empty:
                    # print(f"  Advertencia: Archivo omitido (vacío): {os.path.basename(f)}") # Opcional: muy verboso
                    continue
                missing_cols = [col for col in expected_cols if col not in df.columns]
                if missing_cols:
                    print(f"  Advertencia: Archivo omitido (faltan columnas: {missing_cols}): {os.path.basename(f)}")
                    continue
                if not pd.api.types.is_numeric_dtype(df['longitude']) or \
                   not pd.api.types.is_numeric_dtype(df['latitude']):
                     print(f"  Advertencia: Archivo omitido (lat/lon no numéricas): {os.path.basename(f)}")
                     continue

                df['taxi_id'] = df['taxi_id'].astype(str)
                batch_data.append(df)
                valid_files_in_batch += 1

            except pd.errors.EmptyDataError:
                # print(f"  Advertencia: Archivo omitido (error al leer, posible vacío): {os.path.basename(f)}") # Opcional: muy verboso
                continue
            except Exception as e:
                print(f"  Error procesando archivo {os.path.basename(f)}: {e}. Omitiendo.")
                continue
            finally:
                 files_processed_in_batch += 1
                 # Mini progreso dentro del lote (opcional)
                 # if files_processed_in_batch % (BATCH_SIZE // 5) == 0:
                 #      print(f"    ... {files_processed_in_batch}/{len(batch_files)} archivos del lote revisados.")


        if not batch_data:
            print("  Lote vacío o sin datos válidos. Pasando al siguiente lote.")
            # Forzar limpieza de memoria por si acaso
            gc.collect()
            continue

        # Combinar datos del lote actual
        print(f"  Combinando {len(batch_data)} DataFrames válidos del lote...")
        batch_df = pd.concat(batch_data, ignore_index=True)
        print(f"  Registros en el lote: {len(batch_df)}")
        del batch_data # Liberar memoria de la lista de dataframes
        gc.collect()

        # Calcular velocidades para el lote actual
        print(f"  Calculando velocidades para el lote {i_batch + 1}...")
        batch_with_speed = calculate_speed(batch_df)
        print(f"  Registros con velocidad válida en el lote: {len(batch_with_speed)}")
        del batch_df # Liberar memoria del dataframe combinado del lote
        gc.collect()

        if batch_with_speed.empty:
            print("  No se calcularon velocidades válidas en este lote.")
            del batch_with_speed
            gc.collect()
            continue # Pasar al siguiente lote

        # --- Filtrar y Acumular PUNTOS LENTOS --- # Modificado
        print(f"  Filtrando y acumulando puntos lentos del lote {i_batch + 1}...")
        slow_points_batch = batch_with_speed[batch_with_speed['speed_kmh'] < SPEED_THRESHOLD_KMH]
        print(f"  Puntos lentos encontrados en el lote: {len(slow_points_batch)}")

        if not slow_points_batch.empty:
             # Guardar solo columnas necesarias
             all_slow_points_list.append(slow_points_batch[['timestamp', 'longitude', 'latitude']].copy())
        # --- Fin Filtrar y Acumular --- #

        # Liberar memoria del lote
        del batch_with_speed
        if 'slow_points_batch' in locals(): # Asegurar que exista antes de borrar
           del slow_points_batch
        gc.collect()

    # --- Fin del procesamiento por lotes ---
    if not all_slow_points_list:
        print("\nError: No se encontraron puntos lentos en ningún lote.")
        exit()

    # 4. Combinar todos los puntos LENTOS acumulados
    print(f"\nCombinando puntos lentos de todos los {len(all_slow_points_list)} lotes procesados...")
    slow_points = pd.concat(all_slow_points_list, ignore_index=True)
    del all_slow_points_list
    gc.collect()
    print(f"Total de puntos lentos (< {SPEED_THRESHOLD_KMH} km/h): {len(slow_points)}")

    # --- Guardar en Caché --- # Modificado para guardar slow_points
    if not slow_points.empty:
        print(f"Guardando puntos lentos calculados en caché: {CACHE_FILENAME}...")
        try:
            import pyarrow
            slow_points['timestamp'] = pd.to_datetime(slow_points['timestamp'])
            # Guardar columnas necesarias (timestamp, lon, lat)
            slow_points_to_save = slow_points[['timestamp', 'longitude', 'latitude']].copy()
            slow_points_to_save.to_parquet(cache_filepath, index=False)
            print("Puntos lentos guardados en caché.")
        except ImportError:
            print("Advertencia: Se necesita 'pyarrow' para guardar el caché Parquet. No se guardará.")
            print("Instálala con: pip install pyarrow")
        except Exception as e:
            print(f"Error guardando el archivo caché {CACHE_FILENAME}: {e}")

# --- Fin Bloque de Cálculo ---

if slow_points is None or slow_points.empty:
    print("\nError: No hay datos de puntos lentos. No se puede continuar.")
    exit()

# --- Muestreo --- # Aplicado a slow_points
SAMPLE_FRACTION = 1
# if len(slow_points) * SAMPLE_FRACTION > 1000000:
#     print(f"El {SAMPLE_FRACTION*100}% de los puntos lentos sigue siendo grande, limitando muestra a ~1,000,000 puntos.")
#     slow_points_sampled = slow_points.sample(n=2000000)
# else:
print(f"Tomando una muestra aleatoria del {SAMPLE_FRACTION*100}% de los puntos lentos...")
print(f"Número de fraccion de puntos lentos: {len(slow_points) * SAMPLE_FRACTION}")
slow_points_sampled = slow_points

print(f"Número de puntos a usar para heatmaps: {len(slow_points_sampled)}")
del slow_points
gc.collect()

# --- Generación de Heatmaps ---
print("\nIniciando generación de heatmaps...")
slow_points_sampled['timestamp'] = pd.to_datetime(slow_points_sampled['timestamp'])
start_time = slow_points_sampled['timestamp'].min().floor('h')
end_time = slow_points_sampled['timestamp'].max().ceil('h')

if pd.isna(start_time) or pd.isna(end_time) or start_time >= end_time:
    print("\nError: Rango de tiempo inválido en los datos muestreados.")
    exit()

interval_td = timedelta(hours=TIME_INTERVAL_HOURS)
# current_time = start_time # Se inicializará después de la pasada 1

# --- PASADA 1: Calcular Rango Global de Densidad (Basado en Percentiles) --- # Modificado
print("\nCalculando rango global de densidad basado en percentiles (Pasada 1)...")
all_counts_list = [] # Lista para acumular todos los conteos > 0
processed_intervals_pass1 = 0

temp_current_time = start_time
while temp_current_time < end_time:
    interval_start_p1 = temp_current_time
    interval_end_p1 = temp_current_time + interval_td

    interval_data_p1 = slow_points_sampled[
        (slow_points_sampled['timestamp'] >= interval_start_p1) & (slow_points_sampled['timestamp'] < interval_end_p1)
    ]

    min_points_threshold_p1 = 5
    if len(interval_data_p1) >= min_points_threshold_p1:
        try:
            counts, _, _ = np.histogram2d(
                x=interval_data_p1['longitude'],
                y=interval_data_p1['latitude'],
                bins=250,
                range=[[MAP_BOUNDS['lon_min'], MAP_BOUNDS['lon_max']],
                       [MAP_BOUNDS['lat_min'], MAP_BOUNDS['lat_max']]]
            )
            counts_gt_zero = counts[counts > 0]
            if counts_gt_zero.size > 0:
                all_counts_list.extend(counts_gt_zero) # Acumular conteos > 0

        except Exception as e_hist:
            print(f"    Advertencia: Error calculando histograma en Pasada 1 para {interval_start_p1}-{interval_end_p1}: {e_hist}")

    del interval_data_p1
    gc.collect()

    processed_intervals_pass1 += 1
    if processed_intervals_pass1 % 10 == 0 : # Progreso más frecuente
         print(f"    ... {processed_intervals_pass1} intervalos revisados para rango.")

    temp_current_time += interval_td
# --- Fin Bucle Pasada 1 ---

# Calcular percentiles si hay datos
if all_counts_list:
    all_counts_array = np.array(all_counts_list)
    # Definir percentiles (puedes ajustarlos)
    lower_percentile = 0
    upper_percentile = 99
    global_min_density = np.percentile(all_counts_array, lower_percentile)
    global_max_density = np.percentile(all_counts_array, upper_percentile)
    # Asegurar vmin >= 1 para LogNorm y min < max
    global_min_density = max(1.0, global_min_density)
    if global_max_density <= global_min_density:
        print(f"Advertencia: Percentil {upper_percentile} ({global_max_density:.2f}) no es mayor que Percentil {lower_percentile} ({global_min_density:.2f}). Usando máximo absoluto o ajuste.")
        # Como fallback, usa el 99p y el máximo real si p99 <= p1
        abs_max = all_counts_array.max()
        global_max_density = max(global_min_density * 10, abs_max) # Asegura un rango
    print(f"Rango global de densidad calculado (Percentiles {lower_percentile}-{upper_percentile}): min={global_min_density:.2f}, max={global_max_density:.2f}")
    del all_counts_array # Liberar memoria
    del all_counts_list
else:
    print("Advertencia: No se encontraron densidades positivas en ningún intervalo. Usando rango por defecto [1, 10].")
    global_min_density = 1.0
    global_max_density = 10.0
    gc.collect()

# --- Siempre usar escala Lineal (Normalize) --- # Modificado
# try:
#     global_norm = colors.LogNorm(vmin=global_min_density, vmax=global_max_density)
#     print("Usando escala Logarítmica global basada en percentiles.")
# except ValueError as e_norm:
#      print(f"Error creando LogNorm global ({e_norm}). Usando escala Lineal global.")
#      global_norm = colors.Normalize(vmin=global_min_density, vmax=global_max_density)
global_norm = colors.LogNorm(vmin=global_min_density, vmax=global_max_density)
print("Usando escala Lineal global basada en percentiles.")
# --- Fin PASADA 1 --- #

image_count = 0
generated_count = 0
interval_seconds = interval_td.total_seconds()
total_intervals = 0
if interval_seconds > 0:
    total_seconds = (end_time - start_time).total_seconds()
    total_intervals = int(np.ceil(total_seconds / interval_seconds))

if total_intervals <= 0:
    print("\nError: No se pudo determinar número de intervalos.")
    exit()

print(f"\nGenerando {total_intervals} heatmaps usando rango de densidad fijo (Pasada 2)...")

# --- PASADA 2: Generación Real de Heatmaps --- #
current_time = start_time # Reiniciar tiempo para la segunda pasada
while current_time < end_time:
    interval_start = current_time
    interval_end = current_time + interval_td
    time_str = interval_start.strftime('%Y%m%d_%H%M') + '_to_' + interval_end.strftime('%H%M')
    output_filename = os.path.join(OUTPUT_DIR, f'heatmap_{image_count:04d}_{time_str}.png')

    print(f"\nProcesando intervalo {image_count + 1}/{total_intervals}: {interval_start.strftime('%Y-%m-%d %H:%M')} a {interval_end.strftime('%Y-%m-%d %H:%M')}")

    interval_data = slow_points_sampled[
        (slow_points_sampled['timestamp'] >= interval_start) & (slow_points_sampled['timestamp'] < interval_end)
    ]
    print(f"    Puntos en este intervalo: {len(interval_data)}")

    # Llamar a la función generate_heatmap pasando la norma global
    if generate_heatmap(interval_data, output_filename, interval_start, interval_end, 250, 'hot', global_norm):
         generated_count += 1

    del interval_data
    gc.collect()

    image_count += 1
    current_time += interval_td
    # --- Fin PASADA 2 --- #

print(f"\n¡Proceso completado! Se intentó generar {total_intervals} heatmaps.")

