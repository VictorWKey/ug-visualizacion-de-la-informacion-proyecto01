# --- Configuración ---
DATA_DIR = 'taxi_log_2008_by_id'
OUTPUT_DIR = 'heatmaps_output'
TIME_INTERVAL_HOURS = 1
SPEED_THRESHOLD_KMH = 20
MAX_TIME_DELTA_SECONDS = 600    
MAX_SPEED_KMH = 150       
BATCH_SIZE = 500                
CACHE_FILENAME = 'cached_slow_points.parquet'

MAP_BOUNDS = {
    'lon_min': 116.15,
    'lon_max': 116.6,
    'lat_min': 39.75,
    'lat_max': 40.1
}

SAMPLE_FRACTION = 1 # 1 = 100%