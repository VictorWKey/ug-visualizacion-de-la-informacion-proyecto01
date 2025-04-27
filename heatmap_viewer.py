import tkinter as tk
from tkinter import ttk, filedialog
from PIL import Image, ImageTk
import os
import glob
import re
from datetime import datetime
import argparse

# --- Configuración por Defecto ---
DEFAULT_HEATMAP_DIR = 'heatmaps_output'
# Patrón para extraer fecha/hora del nombre de archivo
# Asume formato: heatmap_NNNN_YYYYMMDD_HHMM_to_HHMM.png
FILENAME_PATTERN = re.compile(r"heatmap_\d+_(\d{8}_\d{4})_to_(\d{4})\.png")

# --- Funciones ---

def parse_arguments():
    """ Parsea argumentos de línea de comandos. """
    parser = argparse.ArgumentParser(description="Visualizador de Heatmaps con Slider.")
    parser.add_argument('--dir', type=str, default=DEFAULT_HEATMAP_DIR,
                        help=f"Directorio que contiene los heatmaps PNG (default: {DEFAULT_HEATMAP_DIR})")
    parser.add_argument('--width', type=int, default=800,
                        help="Ancho deseado para mostrar la imagen (se redimensionará manteniendo aspecto).")
    return parser.parse_args()

def parse_datetime_from_filename(filename):
    """ Extrae el datetime de inicio del nombre de archivo. """
    match = FILENAME_PATTERN.search(os.path.basename(filename))
    if match:
        start_str = match.group(1)
        try:
            # Ajustar formato si es necesario, ej: '%Y%m%d_%H%M'
            return datetime.strptime(start_str, '%Y%m%d_%H%M')
        except ValueError:
            return None # Formato inesperado
    return None

def get_interval_string(filename):
    """ Extrae la cadena de intervalo legible del nombre de archivo. """
    match = FILENAME_PATTERN.search(os.path.basename(filename))
    if match:
        start_dt = parse_datetime_from_filename(filename)
        end_hm = match.group(2) # Solo HHMM
        if start_dt:
             # Reconstruir la cadena de fin HHMM
             # Necesitamos inferir la fecha de fin, podría cruzar medianoche
             # Para simplificar, asumimos que está en la misma fecha o la siguiente
             # Una lógica más robusta requeriría el timedelta del script generador
             # Aquí solo mostramos el formato básico
             end_str = f"{end_hm[:2]}:{end_hm[2:]}"
             return f"{start_dt.strftime('%Y-%m-%d %H:%M')} a {end_str}"
    return os.path.basename(filename) # Fallback al nombre de archivo

def find_and_sort_images(image_dir):
    """ Encuentra archivos PNG y los ordena por fecha/hora en el nombre. """
    print(f"Buscando imágenes PNG en: {image_dir}")
    image_files = glob.glob(os.path.join(image_dir, "heatmap_*.png"))

    # Filtrar y parsear fechas
    parsed_files = []
    for f in image_files:
        dt = parse_datetime_from_filename(f)
        if dt:
            parsed_files.append({'path': f, 'datetime': dt})
        else:
            print(f"  Advertencia: No se pudo parsear la fecha del archivo: {os.path.basename(f)}")

    # Ordenar por fecha
    sorted_files_info = sorted(parsed_files, key=lambda x: x['datetime'])

    if not sorted_files_info:
        print("Error: No se encontraron imágenes con formato de nombre esperado.")
        return [], []

    sorted_paths = [item['path'] for item in sorted_files_info]
    print(f"Se encontraron y ordenaron {len(sorted_paths)} imágenes.")
    return sorted_paths, sorted_files_info

# --- Clases y Funciones GUI ---

class HeatmapViewer:
    def __init__(self, root, image_paths, image_info, display_width):
        self.root = root
        self.image_paths = image_paths
        self.image_info = image_info
        self.display_width = display_width
        self.current_image = None # Para mantener referencia

        if not self.image_paths:
            root.title("Visor de Heatmaps - Error")
            error_label = tk.Label(root, text="No se encontraron imágenes válidas en el directorio especificado.")
            error_label.pack(padx=20, pady=20)
            return

        root.title("Visor de Heatmaps")

        # --- Widgets ---
        # Etiqueta para mostrar intervalo de tiempo
        self.time_label = tk.Label(root, text="Intervalo:", font=("Arial", 12))
        self.time_label.pack(pady=5)

        # Etiqueta para mostrar la imagen
        self.image_label = tk.Label(root)
        self.image_label.pack(padx=10, pady=5, fill='both', expand=True)

        # Slider (Escala)
        self.slider = ttk.Scale(root, from_=0, to=len(self.image_paths) - 1, orient='horizontal',
                                command=self.update_display_from_slider)
        self.slider.pack(fill='x', padx=10, pady=10)

        # Botón para seleccionar directorio (opcional)
        # self.browse_button = tk.Button(root, text="Cambiar Directorio", command=self.browse_directory)
        # self.browse_button.pack(pady=5)

        # --- Inicialización ---
        self.update_display(0) # Mostrar la primera imagen

    def update_display_from_slider(self, slider_value_str):
        """ Callback del slider, convierte valor a int. """
        try:
            index = int(float(slider_value_str))
            self.update_display(index)
        except ValueError:
            pass # Ignorar si el valor no es convertible

    def update_display(self, index):
        """ Carga y muestra la imagen en el índice dado. """
        if 0 <= index < len(self.image_paths):
            filepath = self.image_paths[index]
            interval_str = get_interval_string(filepath)

            try:
                img = Image.open(filepath)

                # Redimensionar manteniendo aspecto
                img_width, img_height = img.size
                aspect_ratio = img_height / img_width
                new_height = int(self.display_width * aspect_ratio)
                img_resized = img.resize((self.display_width, new_height), Image.Resampling.LANCZOS) # Usar LANCZOS para mejor calidad

                # Convertir para Tkinter
                photo = ImageTk.PhotoImage(img_resized)

                # Actualizar widgets
                self.image_label.config(image=photo)
                # ¡Importante! Mantener referencia para evitar garbage collection
                self.image_label.image = photo

                self.time_label.config(text=f"Intervalo {index + 1}/{len(self.image_paths)}: {interval_str}")

                # Actualizar valor del slider (si no fue llamado desde él)
                # Evita bucles si se llama desde el propio slider
                current_slider_int = int(self.slider.get())
                if current_slider_int != index:
                     self.slider.set(index)

            except Exception as e:
                print(f"Error al cargar/mostrar la imagen {filepath}: {e}")
                self.image_label.config(image=None, text=f"Error cargando imagen:\n{os.path.basename(filepath)}")
                self.time_label.config(text="Error")
        else:
            print(f"Índice fuera de rango: {index}")

    # --- Funcionalidad Adicional (Opcional) ---
    # def browse_directory(self):
    #     new_dir = filedialog.askdirectory(title="Selecciona el directorio de heatmaps")
    #     if new_dir:
    #         self.image_paths, self.image_info = find_and_sort_images(new_dir)
    #         if self.image_paths:
    #             # Reconfigurar slider y mostrar primera imagen
    #             self.slider.config(to=len(self.image_paths) - 1)
    #             self.update_display(0)
    #         else:
    #             # Manejar caso sin imágenes en el nuevo directorio
    #             self.image_label.config(image=None, text="No se encontraron imágenes válidas en el nuevo directorio.")
    #             self.time_label.config(text="Error")
    #             self.slider.config(to=0)


# --- Flujo Principal ---
if __name__ == "__main__":
    args = parse_arguments()

    # Verificar si Pillow está instalado
    try:
        from PIL import Image, ImageTk
    except ImportError:
        print("Error: La biblioteca Pillow es necesaria para mostrar imágenes.")
        print("Instálala con: pip install Pillow")
        exit()

    image_paths, image_info = find_and_sort_images(args.dir)

    # Crear la ventana principal y la aplicación
    root = tk.Tk()
    app = HeatmapViewer(root, image_paths, image_info, args.width)
    root.mainloop()