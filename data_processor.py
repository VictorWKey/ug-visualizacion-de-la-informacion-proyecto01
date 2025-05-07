import pandas as pd
import numpy as np
import os
import glob
import gc
import config
from utils import calculate_speed
import pyarrow 

def load_slow_points_from_cache():
    cache_filepath = os.path.join('.', config.CACHE_FILENAME)
    if os.path.exists(cache_filepath):
        try:
            slow_points = pd.read_parquet(cache_filepath)
            required_cols_for_heatmap = ['timestamp', 'longitude', 'latitude']
            if not all(col in slow_points.columns for col in required_cols_for_heatmap):
                print("Advertencia: El archivo caché no contiene las columnas esperadas (timestamp, longitude, latitude). Se recalculará.")
                return None
            slow_points['timestamp'] = pd.to_datetime(slow_points['timestamp'])
            return slow_points
        except Exception as e:
            try:
                os.remove(cache_filepath)
            except OSError:
                pass
            return None
    else:
        return None

def save_slow_points_to_cache(slow_points):
    """Guarda los puntos lentos en el archivo caché."""
    cache_filepath = os.path.join('.', config.CACHE_FILENAME)
    if not slow_points.empty:
        try:
            slow_points_to_save = slow_points[['timestamp', 'longitude', 'latitude']].copy()
            slow_points_to_save['timestamp'] = pd.to_datetime(slow_points_to_save['timestamp'])
            slow_points_to_save.to_parquet(cache_filepath, index=False)
        except Exception as e:
            print(f"Error")

def calculate_all_slow_points():
    all_files = glob.glob(os.path.join(config.DATA_DIR, "*.txt"))
    total_files = len(all_files)

    num_batches = int(np.ceil(total_files / config.BATCH_SIZE))
    print(f"Total de archivos: {total_files}. Tamaño de lote: {config.BATCH_SIZE}. Número de lotes: {num_batches}")

    all_slow_points_list = []
    expected_cols = ['taxi_id', 'timestamp', 'longitude', 'latitude']

    for i_batch in range(num_batches):
        start_index = i_batch * config.BATCH_SIZE
        end_index = min((i_batch + 1) * config.BATCH_SIZE, total_files)
        batch_files = all_files[start_index:end_index]
        print(f"--- Procesando Lote {i_batch + 1}/{num_batches} (Archivos {start_index + 1}-{end_index}) ---")

        batch_data = []
        for f in batch_files:
            try:
                df = pd.read_csv(
                    f,
                    header=None,
                    names=expected_cols,
                    parse_dates=['timestamp'],
                    date_format='%Y-%m-%d %H:%M:%S'
                )
                if df.empty: continue
                missing_cols = [col for col in expected_cols if col not in df.columns]
                if missing_cols: continue
                if not pd.api.types.is_numeric_dtype(df['longitude']) or \
                   not pd.api.types.is_numeric_dtype(df['latitude']): continue
                df['taxi_id'] = df['taxi_id'].astype(str)
                batch_data.append(df)
            except Exception:
                continue 
        
        if not batch_data: continue

        print(f"  Combinando {len(batch_data)} DataFrames del lote...")
        batch_df = pd.concat(batch_data, ignore_index=True)
        del batch_data; gc.collect()

        print(f"  Calculando velocidades para el lote {i_batch + 1}...")
        batch_with_speed = calculate_speed(batch_df) 
        del batch_df; gc.collect()

        if batch_with_speed.empty: continue

        print(f"  Filtrando y acumulando puntos lentos del lote {i_batch + 1}...")
        slow_points_batch = batch_with_speed[batch_with_speed['speed_kmh'] < config.SPEED_THRESHOLD_KMH]
        if not slow_points_batch.empty:
            all_slow_points_list.append(slow_points_batch[['timestamp', 'longitude', 'latitude']].copy())
        
        del batch_with_speed
        if 'slow_points_batch' in locals(): del slow_points_batch
        gc.collect()

    slow_points = pd.concat(all_slow_points_list, ignore_index=True)
    del all_slow_points_list; gc.collect()
    return slow_points

def get_processed_slow_points():
    slow_points = load_slow_points_from_cache()
    if slow_points is None:
        slow_points = calculate_all_slow_points()
        if slow_points is not None and not slow_points.empty:
            save_slow_points_to_cache(slow_points)

    if config.SAMPLE_FRACTION < 1.0:
        slow_points_sampled = slow_points.sample(frac=config.SAMPLE_FRACTION, random_state=42)
    else:
        slow_points_sampled = slow_points 

    print(f"Numero de puntos a usar para heatmaps: {len(slow_points_sampled)}")
    return slow_points_sampled 