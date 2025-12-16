#!/usr/bin/env python3
"""
PBO Manager para Arma 3 - 100% Python
Empaqueta y desempaqueta archivos .pbo sin dependencias externas
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import struct
import time
import threading
from pathlib import Path

class PBOFile:
    """Maneja la lectura y escritura de archivos PBO"""
    
    @staticmethod
    def pack_string(s):
        """Empaqueta un string con terminación null"""
        return s.encode('ascii', errors='ignore') + b'\x00'
    
    @staticmethod
    def unpack_string(data, offset):
        """Desempaqueta un string terminado en null"""
        end = data.find(b'\x00', offset)
        if end == -1:
            return "", len(data)
        return data[offset:end].decode('ascii', errors='ignore'), end + 1
    
    @staticmethod
    def create_pbo(source_folder, output_file, progress_callback=None):
        """Crea un archivo PBO desde una carpeta"""
        files_to_pack = []
        source_path = Path(source_folder)
        
        # Recolectar todos los archivos
        for root, dirs, files in os.walk(source_folder):
            for filename in files:
                filepath = Path(root) / filename
                relative_path = filepath.relative_to(source_path)
                # Usar forward slashes como en PBO
                packname = str(relative_path).replace(os.sep, '\\')
                files_to_pack.append((filepath, packname))
        
        if not files_to_pack:
            raise Exception("No hay archivos para empaquetar en la carpeta seleccionada")
        
        with open(output_file, 'wb') as pbo:
            # Escribir header vacío (producto/versión)
            pbo.write(b'\x00')
            pbo.write(b'sreV\x00')
            pbo.write(b'\x00' * 16)
            
            # Calcular offsets de datos
            current_offset = 0
            file_headers = []
            
            for filepath, packname in files_to_pack:
                file_size = filepath.stat().st_size
                timestamp = int(filepath.stat().st_mtime)
                
                file_headers.append({
                    'name': packname,
                    'method': 0,
                    'original_size': file_size,
                    'reserved': 0,
                    'timestamp': timestamp,
                    'data_size': file_size,
                    'offset': current_offset
                })
                
                current_offset += file_size
            
            # Escribir headers de archivos
            for header in file_headers:
                pbo.write(PBOFile.pack_string(header['name']))
                pbo.write(struct.pack('<I', header['method']))
                pbo.write(struct.pack('<I', header['original_size']))
                pbo.write(struct.pack('<I', header['reserved']))
                pbo.write(struct.pack('<I', header['timestamp']))
                pbo.write(struct.pack('<I', header['data_size']))
            
            # Escribir terminador de headers (nombre vacío con 5 campos más)
            pbo.write(b'\x00')
            pbo.write(struct.pack('<I', 0))  # method
            pbo.write(struct.pack('<I', 0))  # original_size
            pbo.write(struct.pack('<I', 0))  # reserved
            pbo.write(struct.pack('<I', 0))  # timestamp
            pbo.write(struct.pack('<I', 0))  # data_size
            
            # Escribir datos de archivos
            for i, (filepath, packname) in enumerate(files_to_pack):
                if progress_callback:
                    progress = int((i / len(files_to_pack)) * 100)
                    progress_callback(f"Empaquetando: {packname} ({progress}%)")
                
                with open(filepath, 'rb') as f:
                    data = f.read()
                    pbo.write(data)
            
            # Escribir checksum vacío (21 bytes de 0)
            pbo.write(b'\x00' * 21)
        
        return len(files_to_pack)
    
    @staticmethod
    def extract_pbo(pbo_file, output_folder, progress_callback=None):
        """Extrae un archivo PBO a una carpeta"""
        with open(pbo_file, 'rb') as pbo:
            data = pbo.read()
        
        offset = 0
        
        # Saltar header de producto (termina en el primer byte null)
        while offset < len(data) and data[offset] != 0:
            offset += 1
        offset += 1  # Saltar el null
        
        # Verificar si hay header sreV
        if offset + 4 < len(data) and data[offset:offset+4] == b'sreV':
            offset += 4
            offset += 1  # null después de sreV
            offset += 16  # datos adicionales del header
        
        # Leer headers de archivos
        files_info = []
        
        while offset < len(data):
            # Leer nombre del archivo
            filename, new_offset = PBOFile.unpack_string(data, offset)
            
            if not filename:  # Terminador de headers
                # Saltar los 5 campos del terminador
                offset = new_offset + 20  # 5 campos * 4 bytes
                break
            
            offset = new_offset
            
            # Verificar que hay suficientes bytes para leer el header
            if offset + 20 > len(data):
                break
            
            # Leer campos del header
            packing_method = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            
            original_size = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            
            reserved = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            
            timestamp = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            
            data_size = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            
            files_info.append({
                'name': filename,
                'size': data_size,
                'timestamp': timestamp
            })
        
        if not files_info:
            raise Exception("No se encontraron archivos en el PBO")
        
        # Extraer archivos
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for i, file_info in enumerate(files_info):
            if progress_callback:
                progress = int((i / len(files_info)) * 100)
                progress_callback(f"Extrayendo: {file_info['name']} ({progress}%)")
            
            # Convertir backslashes a slashes del sistema
            file_name = file_info['name'].replace('\\', os.sep)
            file_path = output_path / file_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Verificar que hay suficientes datos
            if offset + file_info['size'] > len(data):
                raise Exception(f"Datos insuficientes para el archivo {file_info['name']}")
            
            file_data = data[offset:offset+file_info['size']]
            offset += file_info['size']
            
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            # Restaurar timestamp
            try:
                os.utime(file_path, (file_info['timestamp'], file_info['timestamp']))
            except:
                pass
        
        return len(files_info)


class PBOManager:
    def __init__(self, root):
        self.root = root
        self.root.title("PBO Manager - Arma 3 (Pure Python)")
        self.root.geometry("550x320")
        self.root.resizable(False, False)
        
        self.crear_interfaz()
    
    def crear_interfaz(self):
        """Crea la interfaz gráfica"""
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Título
        titulo = ttk.Label(
            main_frame, 
            text="PBO Manager para Arma 3",
            font=("Arial", 16, "bold")
        )
        titulo.grid(row=0, column=0, columnspan=2, pady=(0, 5))
        
        # Subtítulo
        subtitulo = ttk.Label(
            main_frame,
            text="Empaqueta y desempaqueta archivos .pbo",
            font=("Arial", 9)
        )
        subtitulo.grid(row=1, column=0, columnspan=2, pady=(0, 5))
        
        # Info de versión
        version_label = ttk.Label(
            main_frame,
            text="✓ 100% Python - Sin dependencias externas",
            foreground="green",
            font=("Arial", 9, "bold")
        )
        version_label.grid(row=2, column=0, columnspan=2, pady=(0, 20))
        
        # Botón Crear PBO
        self.btn_crear = ttk.Button(
            main_frame,
            text="📦 Crear PBO desde carpeta",
            command=self.crear_pbo,
            width=45
        )
        self.btn_crear.grid(row=3, column=0, columnspan=2, pady=10, ipady=10)
        
        # Botón Extraer PBO
        self.btn_extraer = ttk.Button(
            main_frame,
            text="📂 Extraer PBO a carpeta",
            command=self.extraer_pbo,
            width=45
        )
        self.btn_extraer.grid(row=4, column=0, columnspan=2, pady=10, ipady=10)
        
        # Barra de progreso
        self.progress = ttk.Progressbar(
            main_frame,
            mode='determinate',
            length=450
        )
        self.progress.grid(row=5, column=0, columnspan=2, pady=15)
        
        # Label de estado
        self.status_label = ttk.Label(
            main_frame,
            text="Listo para empaquetar o extraer archivos PBO",
            font=("Arial", 9)
        )
        self.status_label.grid(row=6, column=0, columnspan=2)
        
        # Label de info adicional
        info_label = ttk.Label(
            main_frame,
            text="Los archivos PBO se crean sin compresión para máxima compatibilidad",
            font=("Arial", 8),
            foreground="gray"
        )
        info_label.grid(row=7, column=0, columnspan=2, pady=(10, 0))
    
    def actualizar_status(self, texto):
        """Actualiza el texto de estado"""
        self.status_label.config(text=texto)
        self.root.update()
    
    def actualizar_progreso(self, valor):
        """Actualiza la barra de progreso"""
        self.progress['value'] = valor
        self.root.update()
    
    def bloquear_botones(self):
        """Bloquea los botones durante operaciones"""
        self.btn_crear.configure(state='disabled')
        self.btn_extraer.configure(state='disabled')
    
    def desbloquear_botones(self):
        """Desbloquea los botones"""
        self.btn_crear.configure(state='normal')
        self.btn_extraer.configure(state='normal')
    
    def crear_pbo(self):
        """Crea un archivo PBO desde una carpeta"""
        # Seleccionar carpeta
        carpeta = filedialog.askdirectory(
            title="Selecciona la carpeta a empaquetar en PBO"
        )
        
        if not carpeta:
            return
        
        # Seleccionar ubicación de salida
        nombre_sugerido = os.path.basename(carpeta) + ".pbo"
        pbo_salida = filedialog.asksaveasfilename(
            title="Guardar archivo PBO como",
            defaultextension=".pbo",
            initialfile=nombre_sugerido,
            filetypes=[("Archivos PBO", "*.pbo"), ("Todos los archivos", "*.*")]
        )
        
        if not pbo_salida:
            return
        
        # Ejecutar en thread separado
        thread = threading.Thread(
            target=self._ejecutar_crear_pbo,
            args=(carpeta, pbo_salida)
        )
        thread.start()
    
    def _ejecutar_crear_pbo(self, carpeta, pbo_salida):
        """Ejecuta la creación del PBO"""
        self.bloquear_botones()
        self.actualizar_progreso(0)
        self.actualizar_status("Iniciando creación de PBO...")
        
        def progress_callback(msg):
            self.actualizar_status(msg)
        
        try:
            inicio = time.time()
            num_archivos = PBOFile.create_pbo(carpeta, pbo_salida, progress_callback)
            duracion = time.time() - inicio
            
            self.actualizar_progreso(100)
            
            if os.path.exists(pbo_salida):
                tamaño = os.path.getsize(pbo_salida) / 1024 / 1024  # MB
                self.actualizar_status(f"✓ PBO creado exitosamente ({num_archivos} archivos, {tamaño:.2f} MB en {duracion:.1f}s)")
                messagebox.showinfo(
                    "Éxito",
                    f"PBO creado exitosamente:\n\n{pbo_salida}\n\nArchivos: {num_archivos}\nTamaño: {tamaño:.2f} MB\nTiempo: {duracion:.1f}s"
                )
            else:
                self.actualizar_status("✗ Error: PBO no creado")
                messagebox.showerror("Error", "No se pudo crear el archivo PBO")
        
        except Exception as e:
            self.actualizar_status("✗ Error al crear PBO")
            messagebox.showerror(
                "Error al crear PBO",
                f"Ocurrió un error:\n\n{str(e)}"
            )
        
        finally:
            self.desbloquear_botones()
            self.actualizar_progreso(0)
    
    def extraer_pbo(self):
        """Extrae un archivo PBO a una carpeta"""
        # Seleccionar archivo PBO
        archivo = filedialog.askopenfilename(
            title="Selecciona el archivo PBO a extraer",
            filetypes=[
                ("Archivos PBO", "*.pbo"),
                ("Todos los archivos", "*.*")
            ]
        )
        
        if not archivo:
            return
        
        # Seleccionar carpeta destino
        nombre_sugerido = os.path.splitext(os.path.basename(archivo))[0]
        destino = filedialog.askdirectory(
            title="Selecciona dónde extraer el PBO"
        )
        
        if not destino:
            return
        
        # Crear carpeta con el nombre del PBO
        carpeta_destino = os.path.join(destino, nombre_sugerido)
        
        # Ejecutar en thread separado
        thread = threading.Thread(
            target=self._ejecutar_extraer_pbo,
            args=(archivo, carpeta_destino)
        )
        thread.start()
    
    def _ejecutar_extraer_pbo(self, archivo, carpeta_destino):
        """Ejecuta la extracción del PBO"""
        self.bloquear_botones()
        self.actualizar_progreso(0)
        self.actualizar_status("Iniciando extracción de PBO...")
        
        def progress_callback(msg):
            self.actualizar_status(msg)
        
        try:
            inicio = time.time()
            num_archivos = PBOFile.extract_pbo(archivo, carpeta_destino, progress_callback)
            duracion = time.time() - inicio
            
            self.actualizar_progreso(100)
            
            if os.path.exists(carpeta_destino):
                self.actualizar_status(f"✓ PBO extraído exitosamente ({num_archivos} archivos en {duracion:.1f}s)")
                messagebox.showinfo(
                    "Éxito",
                    f"PBO extraído exitosamente:\n\n{carpeta_destino}\n\nArchivos extraídos: {num_archivos}\nTiempo: {duracion:.1f}s"
                )
            else:
                self.actualizar_status("✗ Error: Carpeta no creada")
                messagebox.showerror("Error", "No se pudo extraer el PBO")
        
        except Exception as e:
            self.actualizar_status("✗ Error al extraer PBO")
            messagebox.showerror(
                "Error al extraer PBO",
                f"Ocurrió un error:\n\n{str(e)}"
            )
        
        finally:
            self.desbloquear_botones()
            self.actualizar_progreso(0)


def main():
    root = tk.Tk()
    app = PBOManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()