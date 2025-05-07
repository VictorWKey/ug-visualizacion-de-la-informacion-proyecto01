import pandas as pd
import numpy as np
import os
from datetime import timedelta
import gc
import config
from data_processor import get_processed_slow_points
from heatmap_generator import calculate_global_density_range, generate_heatmap

def main():
    print("Iniciando script de generación de heatmaps...")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    
    slow_points_sampled = get_processed_slow_points()
    print("\nIniciando calculo de rango de densidad global para heatmaps...")
    density_calc_results = calculate_global_density_range(slow_points_sampled)

    global_norm, start_time, end_time = density_calc_results

    interval_td = timedelta(hours=config.TIME_INTERVAL_HOURS)
    image_count = 0
    generated_count = 0
    
    total_intervals = 0

    total_seconds_range = (end_time - start_time).total_seconds()
    total_intervals = int(np.ceil(total_seconds_range / interval_td.total_seconds()))
        
    print(f"\nGenerando {total_intervals} heatmaps")

    current_time = start_time
    while current_time < end_time:
        interval_start = current_time
        interval_end = current_time + interval_td
        time_str = interval_start.strftime('%Y%m%d_%H%M') + '_to_' + interval_end.strftime('%H%M')
        output_filename = os.path.join(config.OUTPUT_DIR, f'heatmap_{image_count:04d}_{time_str}.png')

        print(f"\nProcesando intervalo {generated_count + 1}/{total_intervals}: {interval_start.strftime('%Y-%m-%d %H:%M')} a {interval_end.strftime('%Y-%m-%d %H:%M')}")

        interval_data = slow_points_sampled[
            (slow_points_sampled['timestamp'] >= interval_start) & (slow_points_sampled['timestamp'] < interval_end)
        ]
        print(f"    Puntos en este intervalo: {len(interval_data)}")

        if generate_heatmap(interval_data, output_filename, interval_start, interval_end, 750, 'hot', global_norm):
            generated_count += 1

        del interval_data
        gc.collect()

        current_time += interval_td

    print(f"Heatmaps generados exitosamente: {generated_count}")

if __name__ == "__main__":
    main() 