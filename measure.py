import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import math
import numpy as np
import cv2
import os

SMALL_VALUE = 1e-6

font_large = ("Arial", 14)
overlay_color = "#FF8E7A"
overlay_outline = "#D04830"

def line_label_pos(p1, p2, offset=15):
    _p1 = np.array(p1)
    _p2 = np.array(p2)

    midpoint = (_p1 + _p2) / 2
    tangent = (_p2 - _p1) / (np.linalg.norm(_p2 - _p1) + SMALL_VALUE)
    normal = np.array([-tangent[1], tangent[0]])
    return tuple(midpoint + offset * normal)

def resize_image(img: Image.Image, scale: float):
    pixels = np.array(img)
    return Image.fromarray(cv2.resize(pixels, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA))

class WaveMeasureApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Wavelength Measurement Tool (Tkinter)")

        # State 
        self.images = []
        self.current_index = -1
        self.ratio = 1.0
        self.start_point = None
        self.line = None
        # Measurements per image: {image_path: [measurement, ...]}
        self.measurements_by_image = {}
        self.scale = 1.0
        self.min_scale = 1.0
        self.max_scale = 1.0
        self.pan_start = None

        self.marker_radius = 4
        self.start_marker = None
        self.end_marker = None
        self.length_label = None
        self.editing_measurement = False
        # Store marker positions in image coordinates (for zoom/pan adjustment)
        self.start_img_pos = None
        self.end_img_pos = None

        # === UI setup ===
        control_frame = tk.Frame(root)
        control_frame.pack(side=tk.TOP, fill=tk.X, ipady=5)

        tk.Button(control_frame, text="Open Images", command=self.open_images).pack(side=tk.LEFT, padx=(10, 20))

        self.prev_button = tk.Button(control_frame, text="<", command=self.prev_image, state=tk.DISABLED)
        self.prev_button.pack(side=tk.LEFT)
        self.index_label = tk.Label(control_frame, text=f"{self.current_index + 1} / {len(self.images)}", font=font_large)
        self.index_label.pack(side=tk.LEFT, padx=5)
        self.next_button = tk.Button(control_frame, text=">", command=self.next_image, state=tk.DISABLED)
        self.next_button.pack(side=tk.LEFT)

        tk.Label(control_frame, text="Ratio:").pack(side=tk.LEFT, padx=(20, 0))
        self.ratio_entry = tk.Entry(control_frame, width=10)
        self.ratio_entry.insert(0, "1.0")
        self.ratio_entry.pack(side=tk.LEFT)
        tk.Button(control_frame, text="Set", command=self.set_ratio).pack(side=tk.LEFT)

        # New buttons and label for zoom controls
        self.scale_label = tk.Label(control_frame, text="Scale: 100%", font=font_large)
        self.scale_label.pack(side=tk.LEFT, padx=(20, 0))
        tk.Button(control_frame, text="Fit", command=self.fit_image).pack(side=tk.LEFT)
        tk.Button(control_frame, text="1:1", command=self.actual_size).pack(side=tk.LEFT)

        tk.Button(control_frame, text="Export", command=self.export_data).pack(side=tk.RIGHT, padx=10)

        # Create a frame to hold canvas and right panel (listbox + buttons) side by side
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(main_frame, bg="gray")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Create a right panel to hold both the listbox and the button frame in a vertical column
        right_panel = tk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(right_panel, width=30)
        self.listbox.pack(fill=tk.Y, expand=True)

        # Create a frame below the listbox to hold the "+" and "-" buttons side by side
        button_frame = tk.Frame(right_panel)
        button_frame.pack(side=tk.TOP, fill=tk.X, pady=(5, 10))

        self.ok_button = tk.Button(button_frame, text="+", command=self.finalize_measurement, state=tk.DISABLED, width=4)
        self.ok_button.pack(side=tk.LEFT, padx=(0, 5))
        self.delete_button = tk.Button(button_frame, text="-", command=self.delete_selected_measurement, width=4)
        self.delete_button.pack(side=tk.LEFT)

        # === Canvas bindings ===
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<MouseWheel>", self.on_zoom)
        self.canvas.bind("<ButtonPress-2>", self.start_pan)
        self.canvas.bind("<B2-Motion>", self.on_pan)
        self.canvas.bind("<ButtonRelease-2>", self.end_pan)
        self.canvas.bind("<Configure>", self.on_resize)

        # Bind mouse events for dragging markers
        self.canvas.bind("<ButtonPress-1>", self.on_press_marker, add=True)
        self.canvas.bind("<B1-Motion>", self.on_drag_marker, add=True)
        self.canvas.bind("<ButtonRelease-1>", self.on_release_marker, add=True)

        self.tk_img = None
        self.img = None
        self.display_img = None
        self.image_id = None

        self.dragging_marker = None

    def open_images(self):
        files = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp")]
        )
        if files:
            self.images = list(files)
            self.current_index = 0
            # Initialize measurements for each image if not already present
            for path in self.images:
                if path not in self.measurements_by_image:
                    self.measurements_by_image[path] = []
            self.load_image()

    def load_image(self):
        if 0 <= self.current_index < len(self.images):
            self.index_label.config(text=f"{self.current_index + 1} / {len(self.images)}")
            self.prev_button.config(state=tk.NORMAL if self.current_index > 0 else tk.DISABLED)
            self.next_button.config(state=tk.NORMAL if self.current_index < len(self.images) - 1 else tk.DISABLED)

            path = self.images[self.current_index]
            self.img = Image.open(path).transpose(Image.TRANSPOSE)
            self.display_img = self.img.copy()
            self.tk_img = ImageTk.PhotoImage(self.display_img)
            self.canvas.delete("all")
            self.image_id = self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)
            self.root.title(f"Wavelength Measurement - {os.path.basename(path)}")
            self.min_scale = min(self.canvas.winfo_width() / self.img.width, self.canvas.winfo_height() / self.img.height)
            self.scale = self.min_scale
            self.start_point = None
            self.line = None
            self.clear_editing_measurement()

            # Clear and show measurements for this image
            self.listbox.delete(0, tk.END)
            if path not in self.measurements_by_image:
                self.measurements_by_image[path] = []
            for val in self.measurements_by_image[path]:
                self.listbox.insert(tk.END, f"{val:.4f}")

            self.canvas.configure(scrollregion=self.canvas.bbox(tk.ALL))
            self.update_zoom()

    def next_image(self):
        if self.current_index + 1 < len(self.images):
            self.current_index += 1
            self.load_image()

    def prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.load_image()

    def set_ratio(self):
        try:
            self.ratio = float(self.ratio_entry.get())
            messagebox.showinfo("Ratio set", f"Pixel-to-length ratio set to {self.ratio}")
        except ValueError:
            messagebox.showerror("Invalid input", "Please enter a valid number.")
        finally:
            self.update_length_label(self.start_point, self.get_marker_center(self.end_marker))

    # Mouse events
    def on_click(self, event):
        if self.tk_img is None:
            return

        # If currently editing a measurement, ignore new clicks until OK pressed
        if self.editing_measurement:
            return

        # Convert canvas coordinates to image coordinates
        x_canvas = self.canvas.canvasx(event.x)
        y_canvas = self.canvas.canvasy(event.y)
        img_coords = self.canvas.coords(self.image_id)
        if not img_coords or self.img is None:
            return
        img_x, img_y = img_coords
        scale = self.scale
        # Convert canvas position to image coordinates
        x_img = (x_canvas - img_x) / scale
        y_img = (y_canvas - img_y) / scale

        if not self.start_point:
            # Start marker: record in image coordinates
            self.start_img_pos = (x_img, y_img)
            self.start_point = (x_canvas, y_canvas)
            # Draw start marker
            self.start_marker = self.canvas.create_oval(
                x_canvas - self.marker_radius, y_canvas - self.marker_radius,
                x_canvas + self.marker_radius, y_canvas + self.marker_radius,
                fill=overlay_color, outline=overlay_outline, width=2
            )
            if self.line:
                self.canvas.delete(self.line)
                self.line = None
            if self.end_marker:
                self.canvas.delete(self.end_marker)
                self.end_marker = None
            if self.length_label:
                self.canvas.delete(self.length_label)
                self.length_label = None
            self.ok_button.config(state=tk.DISABLED)
        else:
            # End marker: record in image coordinates
            self.end_img_pos = (x_img, y_img)
            end_point = (x_canvas, y_canvas)
            self.end_marker = self.canvas.create_oval(
                x_canvas - self.marker_radius, y_canvas - self.marker_radius,
                x_canvas + self.marker_radius, y_canvas + self.marker_radius,
                fill=overlay_color, outline=overlay_outline, width=2
            )
            self.line = self.canvas.create_line(
                self.start_point[0], self.start_point[1],
                end_point[0], end_point[1],
                fill=overlay_color, width=2
            )
            # Show length label near midpoint
            self.update_length_label(self.start_point, end_point)
            self.editing_measurement = True
            self.ok_button.config(state=tk.NORMAL)

    def update_length_label(self, p1, p2):
        # Calculate length in physical units
        dx = (p2[0] - p1[0]) / self.scale
        dy = (p2[1] - p1[1]) / self.scale
        pixel_dist = math.hypot(dx, dy)
        physical_length = pixel_dist * self.ratio

        if self.length_label:
            self.canvas.delete(self.length_label)
        self.length_label = self.canvas.create_text(
            *line_label_pos(p1, p2, offset=30),
            text=f"{physical_length:.3f}",
            fill=overlay_color,
            font=("Arial", 14, "bold"),
            anchor="center"
        )

    def clear_editing_measurement(self):
        if self.start_marker:
            self.canvas.delete(self.start_marker)
            self.start_marker = None
        if self.end_marker:
            self.canvas.delete(self.end_marker)
            self.end_marker = None
        if self.line:
            self.canvas.delete(self.line)
            self.line = None
        if self.length_label:
            self.canvas.delete(self.length_label)
            self.length_label = None
        self.start_point = None
        self.editing_measurement = False
        self.ok_button.config(state=tk.DISABLED)
        self.start_img_pos = None
        self.end_img_pos = None

    def finalize_measurement(self):
        if not self.editing_measurement:
            return
        # Measure distance from current markers
        p1 = self.get_marker_center(self.start_marker)
        p2 = self.get_marker_center(self.end_marker)
        if p1 is None or p2 is None:
            messagebox.showerror("Error", "Markers missing.")
            return
        dx = (p2[0] - p1[0]) / self.scale
        dy = (p2[1] - p1[1]) / self.scale
        pixel_dist = math.hypot(dx, dy)
        physical_length = pixel_dist * self.ratio
        # Store measurement for current image
        if 0 <= self.current_index < len(self.images):
            path = self.images[self.current_index]
            if path not in self.measurements_by_image:
                self.measurements_by_image[path] = []
            self.measurements_by_image[path].append(physical_length)
            # Update listbox
            self.listbox.insert(tk.END, f"{physical_length:.4f}")
        self.clear_editing_measurement()

    def get_marker_center(self, marker_id):
        if marker_id is None:
            return None
        coords = self.canvas.coords(marker_id)
        if not coords or len(coords) != 4:
            return None
        x = (coords[0] + coords[2]) / 2
        y = (coords[1] + coords[3]) / 2
        return (x, y)

    def on_press_marker(self, event):
        if not self.editing_measurement:
            return
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        # Check if click is near start_marker
        if self.start_marker and self.point_near_marker(x, y, self.start_marker):
            self.dragging_marker = "start"
        elif self.end_marker and self.point_near_marker(x, y, self.end_marker):
            self.dragging_marker = "end"
        else:
            self.dragging_marker = None

    def on_drag_marker(self, event):
        if not self.editing_measurement or self.dragging_marker is None:
            return
        x_canvas = self.canvas.canvasx(event.x)
        y_canvas = self.canvas.canvasy(event.y)

        # Constrain x, y to canvas boundaries
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        x_canvas = max(min(x_canvas, canvas_w - self.marker_radius), self.marker_radius)
        y_canvas = max(min(y_canvas, canvas_h - self.marker_radius), self.marker_radius)

        # Constrain to image boundaries
        img_coords = self.canvas.coords(self.image_id)
        if img_coords and self.img is not None:
            img_x, img_y = img_coords
            img_w, img_h = self.img.size
            img_w = int(img_w * self.scale)
            img_h = int(img_h * self.scale)
            
            x_canvas = max(min(x_canvas, img_x + img_w), img_x + self.marker_radius)
            y_canvas = max(min(y_canvas, img_y + img_h), img_y + self.marker_radius)

        # Move the corresponding marker
        marker = self.start_marker if self.dragging_marker == "start" else self.end_marker
        self.canvas.coords(
            marker,
            x_canvas - self.marker_radius, y_canvas - self.marker_radius,
            x_canvas + self.marker_radius, y_canvas + self.marker_radius
        )
        # Update line coordinates
        start_pos = self.get_marker_center(self.start_marker)
        end_pos = self.get_marker_center(self.end_marker)
        if self.line:
            self.canvas.coords(self.line, start_pos[0], start_pos[1], end_pos[0], end_pos[1])
        # Update length label position and text
        self.update_length_label(start_pos, end_pos)
        # Update image coordinates for marker that was dragged
        img_coords = self.canvas.coords(self.image_id)
        if img_coords and self.img is not None:
            img_x, img_y = img_coords
            scale = self.scale
            if self.dragging_marker == "start":
                self.start_img_pos = ((x_canvas - img_x) / scale, (y_canvas - img_y) / scale)
            else:
                self.end_img_pos = ((x_canvas - img_x) / scale, (y_canvas - img_y) / scale)

    def on_release_marker(self, event):
        self.dragging_marker = None

    def point_near_marker(self, x, y, marker_id):
        coords = self.canvas.coords(marker_id)
        if not coords or len(coords) != 4:
            return False
        x0, y0, x1, y1 = coords
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        dist = math.hypot(x - cx, y - cy)
        return dist <= self.marker_radius + 3

    def measure_distance(self, p1, p2):
        # Convert canvas distance to original image pixels
        dx = (p2[0] - p1[0]) / self.scale
        dy = (p2[1] - p1[1]) / self.scale
        pixel_dist = math.hypot(dx, dy)
        physical_length = pixel_dist * self.ratio
        self.measurements.append(physical_length)
        self.listbox.insert(tk.END, f"{physical_length:.4f}")

    def on_zoom(self, event):
        if self.img is None:
            return

        # Get mouse position in canvas coordinates
        mouse_x_canvas = self.canvas.canvasx(event.x)
        mouse_y_canvas = self.canvas.canvasy(event.y)

        # Get image top-left corner
        img_x, img_y = self.canvas.coords(self.image_id)

        # Mouse position relative to image
        rel_x = mouse_x_canvas - img_x
        rel_y = mouse_y_canvas - img_y

        # Save the relative zoom origin (within image coordinates)
        self.zoom_origin = (rel_x, rel_y)

        # Compute old scale and new scale
        old_scale = self.scale
        if event.delta > 0:
            self.scale *= 1.1
        else:
            self.scale *= 0.9

        # Clamp zoom
        self.scale = max(self.min_scale, min(self.max_scale, self.scale))

        # Update image with correct offset
        self.update_zoom(old_scale)

    def update_zoom(self, old_scale=None):
        if old_scale is None:
            old_scale = self.scale

        w, h = self.img.size
        new_w = int(w * self.scale)
        new_h = int(h * self.scale)
        self.display_img = resize_image(self.img, self.scale)
        self.tk_img = ImageTk.PhotoImage(self.display_img)
        self.canvas.itemconfig(self.image_id, image=self.tk_img)

        # Update label
        self.scale_label.config(text=f"Scale: {self.scale*100:.0f}%")

        # Get current image position
        img_x, img_y = self.canvas.coords(self.image_id)

        # Calculate new top-left to preserve zoom origin
        if hasattr(self, "zoom_origin") and old_scale != 0:
            ox, oy = self.zoom_origin
            scale_ratio = self.scale / old_scale
            new_x = img_x - ox * (scale_ratio - 1)
            new_y = img_y - oy * (scale_ratio - 1)
        else:
            new_x, new_y = img_x, img_y

        # Boundaries
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        max_x, max_y = 0, 0
        min_x = canvas_w - new_w
        min_y = canvas_h - new_h

        # Keep image within canvas
        if new_w < canvas_w:
            new_x = (canvas_w - new_w) // 2
        else:
            new_x = min(max_x, max(min_x, new_x))

        if new_h < canvas_h:
            new_y = (canvas_h - new_h) // 2
        else:
            new_y = min(max_y, max(min_y, new_y))

        self.canvas.coords(self.image_id, new_x, new_y)
        self.canvas.configure(scrollregion=self.canvas.bbox(tk.ALL))

        # When zoom or pan changes, adjust marker and line positions accordingly
        if self.editing_measurement and self.start_marker and self.end_marker and self.line:
            # Use stored image coordinates to recalculate canvas positions
            if self.start_img_pos and self.end_img_pos:
                sx_img, sy_img = self.start_img_pos
                ex_img, ey_img = self.end_img_pos
                scale = self.scale
                # Get new image position
                img_coords = self.canvas.coords(self.image_id)
                if img_coords:
                    img_x, img_y = img_coords
                    sx_canvas = img_x + sx_img * scale
                    sy_canvas = img_y + sy_img * scale
                    ex_canvas = img_x + ex_img * scale
                    ey_canvas = img_y + ey_img * scale
                    # Move start marker
                    self.canvas.coords(
                        self.start_marker,
                        sx_canvas - self.marker_radius, sy_canvas - self.marker_radius,
                        sx_canvas + self.marker_radius, sy_canvas + self.marker_radius
                    )
                    # Move end marker
                    self.canvas.coords(
                        self.end_marker,
                        ex_canvas - self.marker_radius, ey_canvas - self.marker_radius,
                        ex_canvas + self.marker_radius, ey_canvas + self.marker_radius
                    )
                    # Move line
                    self.canvas.coords(
                        self.line,
                        sx_canvas, sy_canvas, ex_canvas, ey_canvas
                    )
                    # Move label
                    self.update_length_label((sx_canvas, sy_canvas), (ex_canvas, ey_canvas))

    def start_pan(self, event):
        self.pan_start = (event.x, event.y)

    def on_pan(self, event):
        if self.pan_start:
            dx = event.x - self.pan_start[0]
            dy = event.y - self.pan_start[1]

            # Get current image position
            coords = self.canvas.coords(self.image_id)
            if not coords:
                x, y = 0, 0
            else:
                x, y = coords[0], coords[1]

            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            img_w = self.display_img.width
            img_h = self.display_img.height

            # Calculate new position with constraints
            new_x = x + dx
            new_y = y + dy

            max_x = 0
            max_y = 0
            min_x = canvas_w - img_w
            min_y = canvas_h - img_h

            # If image smaller than canvas, center it and ignore pan
            if img_w <= canvas_w:
                new_x = (canvas_w - img_w) // 2
            else:
                new_x = min(max_x, max(min_x, new_x))

            if img_h <= canvas_h:
                new_y = (canvas_h - img_h) // 2
            else:
                new_y = min(max_y, max(min_y, new_y))

            self.canvas.coords(self.image_id, new_x, new_y)
            self.pan_start = (event.x, event.y)

            # After moving the image, update marker, line, and label positions
            if self.editing_measurement and self.start_marker and self.end_marker and self.line:
                # Use stored image coordinates to recalculate canvas positions
                if self.start_img_pos and self.end_img_pos:
                    sx_img, sy_img = self.start_img_pos
                    ex_img, ey_img = self.end_img_pos
                    scale = self.scale
                    # Get new image position
                    img_coords = self.canvas.coords(self.image_id)
                    if img_coords:
                        img_x, img_y = img_coords
                        sx_canvas = img_x + sx_img * scale
                        sy_canvas = img_y + sy_img * scale
                        ex_canvas = img_x + ex_img * scale
                        ey_canvas = img_y + ey_img * scale
                        # Move start marker
                        self.canvas.coords(
                            self.start_marker,
                            sx_canvas - self.marker_radius, sy_canvas - self.marker_radius,
                            sx_canvas + self.marker_radius, sy_canvas + self.marker_radius
                        )
                        # Move end marker
                        self.canvas.coords(
                            self.end_marker,
                            ex_canvas - self.marker_radius, ey_canvas - self.marker_radius,
                            ex_canvas + self.marker_radius, ey_canvas + self.marker_radius
                        )
                        # Move line
                        self.canvas.coords(
                            self.line,
                            sx_canvas, sy_canvas, ex_canvas, ey_canvas
                        )
                        # Move label
                        self.update_length_label((sx_canvas, sy_canvas), (ex_canvas, ey_canvas))

    def end_pan(self, event):
        self.pan_start = None

    def export_data(self):
        # Gather all images with measurements
        images_with_measurements = [
            (path, vals) for path, vals in self.measurements_by_image.items() if vals
        ]
        if not images_with_measurements:
            messagebox.showerror("No data", "No measurements to export.")
            return
        outdir = filedialog.askdirectory(
            title="Select Output Folder"
        )
        if not outdir:
            return
        for img_path, vals in images_with_measurements:
            base = os.path.splitext(os.path.basename(img_path))[0]
            txt_path = os.path.join(outdir, f"{base}.txt")
            with open(txt_path, "w") as f:
                for v in vals:
                    f.write(f"{v:.4f}\n")
        messagebox.showinfo("Exported", f"Exported {len(images_with_measurements)} file(s) to {outdir}")

    def fit_image(self):
        self.scale = self.min_scale
        self.update_zoom()

    def actual_size(self):
        self.scale = 1.0
        self.update_zoom()

    def on_resize(self, event):
        if self.img is None:
            return
        
        self.min_scale = min(self.canvas.winfo_width() / self.img.width, self.canvas.winfo_height() / self.img.height)
        self.update_zoom()
    
    def delete_selected_measurement(self):
        # Remove the currently selected measurement from the list and measurements_by_image
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("No selection", "Please select a measurement to delete.")
            return
        idx = selection[0]
        if 0 <= self.current_index < len(self.images):
            path = self.images[self.current_index]
            if path in self.measurements_by_image and 0 <= idx < len(self.measurements_by_image[path]):
                del self.measurements_by_image[path][idx]
        self.listbox.delete(idx)


if __name__ == "__main__":
    root = tk.Tk()
    app = WaveMeasureApp(root)
    root.geometry("1000x700+200+100")
    root.mainloop()
