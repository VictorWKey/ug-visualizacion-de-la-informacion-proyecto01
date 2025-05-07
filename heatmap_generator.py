import pandas as pd
import numpy as np
import os
import gc
from datetime import timedelta
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.colors as colors
from matplotlib.ticker import LinearLocator, ScalarFormatter
import config

def generate_heatmap(interval_data, output_filename, interval_start, interval_end, bins, cmap, norm):
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

    _, _, _, im = ax.hist2d(
        x=interval_data['longitude'],
        y=interval_data['latitude'],
        bins=bins,
        cmap=cmap,
        norm=norm,
        range=[[config.MAP_BOUNDS['lon_min'], config.MAP_BOUNDS['lon_max']],
                [config.MAP_BOUNDS['lat_min'], config.MAP_BOUNDS['lat_max']]]
    )

    cbar_label = 'Densidad puntos lentos (Log Scale)' if isinstance(norm, colors.LogNorm) else 'Densidad puntos lentos (Linear Scale)'
    cbar = fig.colorbar(im, ax=ax, label=cbar_label)
    cbar.ax.yaxis.label.set_color('white')
    cbar.ax.tick_params(axis='y', colors='white')

    num_ticks_deseado = 12
    locator = LinearLocator(numticks=num_ticks_deseado)
    cbar.ax.yaxis.set_major_locator(locator)

    formatter = ScalarFormatter()
    formatter.set_powerlimits((-3, 4))
    cbar.ax.yaxis.set_major_formatter(formatter)

    ax.set_xlim(config.MAP_BOUNDS['lon_min'], config.MAP_BOUNDS['lon_max'])
    ax.set_ylim(config.MAP_BOUNDS['lat_min'], config.MAP_BOUNDS['lat_max'])

    ax.set_title(f"Densidad Puntos Lentos ({interval_start.strftime('%Y-%m-%d %H:%M')} - {interval_end.strftime('%Y-%m-%d %H:%M')})")
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    plt.tight_layout()

    print(f"    Guardando: {output_filename}")
    plt.savefig(output_filename, dpi=150, facecolor=fig.get_facecolor())
    return True

def calculate_global_density_range(slow_points_sampled):
    """Calcula el rango global de densidad basado en percentiles."""
    print("\nCalculando rango global de densidad basado en percentiles ")
    all_counts_list = []
    processed_intervals_pass1 = 0

    start_time = slow_points_sampled['timestamp'].min().floor('h')
    end_time = slow_points_sampled['timestamp'].max().ceil('h')
        
    interval_td = timedelta(hours=config.TIME_INTERVAL_HOURS)
    temp_current_time = start_time

    while temp_current_time < end_time:
        interval_start_p1 = temp_current_time
        interval_end_p1 = temp_current_time + interval_td

        interval_data_p1 = slow_points_sampled[
            (slow_points_sampled['timestamp'] >= interval_start_p1) &
            (slow_points_sampled['timestamp'] < interval_end_p1)
        ]

        min_points_threshold_p1 = 5
        if len(interval_data_p1) >= min_points_threshold_p1:
            counts, _, _ = np.histogram2d(
                x=interval_data_p1['longitude'],
                y=interval_data_p1['latitude'],
                bins=250,
                range=[[config.MAP_BOUNDS['lon_min'], config.MAP_BOUNDS['lon_max']],
                        [config.MAP_BOUNDS['lat_min'], config.MAP_BOUNDS['lat_max']]]
            )
            counts_gt_zero = counts[counts > 0]
            if counts_gt_zero.size > 0:
                all_counts_list.extend(counts_gt_zero)

        
        del interval_data_p1
        gc.collect()

        processed_intervals_pass1 += 1
        if processed_intervals_pass1 % 10 == 0:
            print(f"    ... {processed_intervals_pass1} intervalos revisados para rango.")
        
        temp_current_time += interval_td

    if not all_counts_list:
        global_min_density = 1.0
        global_max_density = 10.0
    else:
        all_counts_array = np.array(all_counts_list)
        lower_percentile = 0
        upper_percentile = 99
        global_min_density = np.percentile(all_counts_array, lower_percentile)
        global_max_density = np.percentile(all_counts_array, upper_percentile)
        global_min_density = max(1.0, global_min_density)
        if global_max_density <= global_min_density:
            abs_max = all_counts_array.max()
            global_max_density = max(global_min_density * 10, abs_max)
        del all_counts_array
        del all_counts_list
        gc.collect()

    global_norm = colors.LogNorm(vmin=global_min_density, vmax=global_max_density)

    return global_norm, start_time, end_time 