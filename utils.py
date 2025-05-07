import pandas as pd
import numpy as np
from math import radians, cos, sin, asin, sqrt
from datetime import timedelta
import config

# --- Funciones ---
def haversine(lon1, lat1, lon2, lat2):
    """
    Calcula la distancia entre dos puntos lat/lon en la Tierra (en km).
    """
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # Fórmula Haversine
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371
    return c * r

def calculate_speed(df):
    """
    Calcula la velocidad entre puntos consecutivos para cada taxi.
    """
    if df.empty:
        return pd.DataFrame(columns=['timestamp', 'longitude', 'latitude', 'speed_kmh'])

    df = df.sort_values(by=['taxi_id', 'timestamp'])
    df['lat_prev'] = df.groupby('taxi_id')['latitude'].shift(1)
    df['lon_prev'] = df.groupby('taxi_id')['longitude'].shift(1)
    df['time_prev'] = df.groupby('taxi_id')['timestamp'].shift(1)

    df = df.dropna(subset=['lat_prev', 'lon_prev', 'time_prev'])
    if df.empty:
        return pd.DataFrame(columns=['timestamp', 'longitude', 'latitude', 'speed_kmh'])

    df_loc = df.loc[:, ['longitude', 'latitude', 'lon_prev', 'lat_prev', 'timestamp', 'time_prev']].copy()
    df_loc['distance_km'] = df_loc.apply(
        lambda row: haversine(row['lon_prev'], row['lat_prev'], row['longitude'], row['latitude']),
        axis=1
    )
    df_loc['time_delta_sec'] = (df_loc['timestamp'] - df_loc['time_prev']).dt.total_seconds()

    df_loc['speed_kmh'] = 0.0
    valid_time = (df_loc['time_delta_sec'] > 1) & (df_loc['time_delta_sec'] <= config.MAX_TIME_DELTA_SECONDS)


    safe_denominator = df_loc.loc[valid_time, 'time_delta_sec'].replace(0, np.nan).dropna()
    if not safe_denominator.empty:
         df_loc.loc[safe_denominator.index, 'speed_kmh'] = (df_loc.loc[safe_denominator.index, 'distance_km'] / (safe_denominator / 3600))

    df_loc = df_loc[df_loc['speed_kmh'] <= config.MAX_SPEED_KMH]

    return df_loc[['timestamp', 'longitude', 'latitude', 'speed_kmh']] 