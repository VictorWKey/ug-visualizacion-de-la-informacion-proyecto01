import os
import re
import cv2
from datetime import datetime

input_folder = './heatmaps_output'
output_video = 'heatmaps_video.mp4'
frame_duration = 0.25
fps = int(1 / frame_duration)

pattern = re.compile(r'heatmap_\d+_(\d{8})_(\d{4})_to_\d{4}\.png')

image_files = []
for filename in os.listdir(input_folder):
    match = pattern.match(filename)
    if match:
        date_str = match.group(1)
        time_str = match.group(2)
        dt = datetime.strptime(date_str + time_str, '%Y%m%d%H%M')
        image_files.append((dt, os.path.join(input_folder, filename)))

image_files.sort(key=lambda x: x[0])
sorted_paths = [path for _, path in image_files]

first_image = cv2.imread(sorted_paths[0])
height, width, layers = first_image.shape
size = (width, height)

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(output_video, fourcc, fps, size)

for path in sorted_paths:
    frame = cv2.imread(path)
    if frame.shape[:2] != (height, width):
        frame = cv2.resize(frame, size)
    out.write(frame)

out.release()
print(f"Video generado correctamente: {output_video}")
