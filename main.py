import os
import random

from PIL import Image, ImageChops

# ============================================================================
# PROYECTO: ColorVisualCrypto_Impl (Advanced)
# Técnica: Construction 2 + Floyd-Steinberg Error Diffusion
# Objetivo: Eliminar "ghosting" y mejorar calidad visual de las portadas.
# ============================================================================


class ColorVisualCrypto:
    def __init__(self):
        # Paleta RGBCMYWK
        self.palette = {
            "R": (255, 0, 0),
            "G": (0, 255, 0),
            "B": (0, 0, 255),
            "C": (0, 255, 255),
            "M": (255, 0, 255),
            "Y": (255, 255, 0),
            "W": (255, 255, 255),
            "K": (0, 0, 0),
        }
        self.keys = list(self.palette.keys())  # ['R', 'G', ...]
        self.sigma = ["R", "G", "B", "C", "M", "Y"]

    def get_complementary(self, code):
        map_c = {
            "R": "C",
            "G": "M",
            "B": "Y",
            "C": "R",
            "M": "G",
            "Y": "B",
            "W": "K",
            "K": "W",
        }
        return map_c.get(code, "K")

    def add_error(self, img_data, x, y, w, h, error_r, error_g, error_b):
        """Distribuye el error a los píxeles vecinos (Floyd-Steinberg)"""
        # Factores de distribución: 7/16, 3/16, 5/16, 1/16
        factors = [(1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)]

        for dx, dy, factor in factors:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                r, g, b = img_data[nx, ny]
                img_data[nx, ny] = (
                    int(min(255, max(0, r + error_r * factor))),
                    int(min(255, max(0, g + error_g * factor))),
                    int(min(255, max(0, b + error_b * factor))),
                )

    def get_best_color_code(self, target_rgb):
        """Encuentra el color de la paleta más cercano al deseado (incluyendo error acumulado)"""
        min_dist = float("inf")
        best_k = "W"

        # Solo buscamos entre colores de Sigma + Blanco (para covers)
        # Evitamos el negro puro para covers si es posible para dar color
        candidates = self.sigma + ["W"]

        for k in candidates:
            c_rgb = self.palette[k]
            # Distancia Euclidiana simple
            dist = (
                (c_rgb[0] - target_rgb[0]) ** 2
                + (c_rgb[1] - target_rgb[1]) ** 2
                + (c_rgb[2] - target_rgb[2]) ** 2
            )
            if dist < min_dist:
                min_dist = dist
                best_k = k

        # Pequeña aleatoriedad si es Blanco para evitar zonas planas
        if best_k == "W":
            return random.choice(self.sigma)
        return best_k

    def generate_shares(self, secret_p, cover1_p, cover2_p):
        print("--- Procesando con Difusión de Error (Anti-Ghosting) ---")

        try:
            # Cargar imágenes. Covers en RGB para poder guardar el 'error' flotante
            sec = Image.open(secret_p).convert("1")
            c1_img = Image.open(cover1_p).convert("RGB")
            c2_img = Image.open(cover2_p).convert("RGB")
        except Exception as e:
            print(f"Error cargando imágenes: {e}")
            return

        w, h = sec.size
        c1_img = c1_img.resize((w, h))
        c2_img = c2_img.resize((w, h))

        # Convertimos a listas de píxeles mutables para aplicar el error
        # (Es lento en Python puro, pero efectivo)
        c1_pixels = c1_img.load()
        c2_pixels = c2_img.load()
        s_pixels = sec.load()

        # Lienzos de salida
        out1 = Image.new("RGB", (w * 2, h))
        out2 = Image.new("RGB", (w * 2, h))
        d1 = out1.load()
        d2 = out2.load()

        print("Generando... (Paciencia, esto calcula mucho)")

        for y in range(h):
            for x in range(w):
                # 1. Leer el pixel actual (que ya incluye el error de los anteriores)
                target_rgb_1 = c1_pixels[x, y]
                target_rgb_2 = c2_pixels[x, y]
                is_secret_black = s_pixels[x, y] == 0

                # 2. Determinar el 'Código' ideal para este píxel
                code_c1 = self.get_best_color_code(target_rgb_1)
                code_c2 = self.get_best_color_code(target_rgb_2)

                # Lógica básica del paper para determinar estados (Simplificada para visualización)
                # Aquí siempre asumimos 'W' (color) a menos que sea negro negrísimo
                st1 = "K" if sum(target_rgb_1) < 30 else "W"
                st2 = "K" if sum(target_rgb_2) < 30 else "W"

                # 3. Elegir los colores de salida (Construction 2 Logic)
                # Intentamos satisfacer el color ideal de C1
                final_c1 = code_c1

                # Definir subpíxeles
                px1, px2 = [], []

                # APLICAMOS LÓGICA Y GESTIÓN DE CONFLICTOS
                if st1 == "W" and st2 == "W":
                    if not is_secret_black:  # SECRETO BLANCO -> Salidas Iguales
                        # Dilema: C1 quiere Rojo, C2 quiere Azul.
                        # Solución: Elegimos uno (ej: C1) y el error se difunde en C2.
                        chosen = final_c1
                        px1 = [chosen, code_c2]  # Segundo pixel intenta capturar C2
                        px2 = [chosen, code_c2]
                    else:  # SECRETO NEGRO -> Salidas Complementarias
                        # C1 quiere Rojo. Share 2 será Cian (Complementario).
                        # Si C2 quería Rojo, Share 2 tendrá un error enorme (Rojo vs Cian).
                        # Ese error se pasará al siguiente pixel.
                        px1 = [final_c1, code_c2]
                        px2 = [
                            self.get_complementary(final_c1),
                            self.get_complementary(code_c2),
                        ]

                elif st1 == "W" and st2 == "K":
                    # Similar logic...
                    chosen = final_c1
                    dummy = random.choice(self.sigma)
                    if not is_secret_black:
                        px1, px2 = [chosen, dummy], [chosen, "K"]
                    else:
                        px1, px2 = (
                            [chosen, dummy],
                            [self.get_complementary(chosen), "K"],
                        )

                elif st1 == "K" and st2 == "W":
                    chosen = code_c2
                    if not is_secret_black:
                        px1, px2 = ["K", chosen], ["K", chosen]
                    else:
                        px1, px2 = ["K", self.get_complementary(chosen)], ["K", chosen]
                else:
                    px1, px2 = ["K", "K"], ["K", "K"]

                # 4. Permutación de columnas (SEGURIDAD)
                idx = [0, 1]
                random.shuffle(idx)
                final_p1 = [px1[idx[0]], px1[idx[1]]]
                final_p2 = [px2[idx[0]], px2[idx[1]]]

                # 5. Dibujar y CALCULAR ERROR
                # Share 1
                res_rgb_1 = self.palette[
                    final_p1[0]
                ]  # Tomamos el 1er subpixel como representativo del error en X
                d1[x * 2, y] = self.palette[final_p1[0]]
                d1[x * 2 + 1, y] = self.palette[final_p1[1]]

                # Share 2
                res_rgb_2 = self.palette[final_p2[0]]
                d2[x * 2, y] = self.palette[final_p2[0]]
                d2[x * 2 + 1, y] = self.palette[final_p2[1]]

                # 6. DIFUSIÓN DEL ERROR
                # Error = Lo que quería (target) - Lo que puse (res)
                err1 = (
                    target_rgb_1[0] - res_rgb_1[0],
                    target_rgb_1[1] - res_rgb_1[1],
                    target_rgb_1[2] - res_rgb_1[2],
                )
                err2 = (
                    target_rgb_2[0] - res_rgb_2[0],
                    target_rgb_2[1] - res_rgb_2[1],
                    target_rgb_2[2] - res_rgb_2[2],
                )

                self.add_error(c1_pixels, x, y, w, h, *err1)
                self.add_error(c2_pixels, x, y, w, h, *err2)

        out1.save("output/share1.png")
        out2.save("output/share2.png")
        print("✅ Listas. Revisa output/share1.png y share2.png")

    def reconstruct(self, path1, path2):
        print("Reconstruyendo...")
        s1 = Image.open(path1).convert("RGB")
        s2 = Image.open(path2).convert("RGB")
        ImageChops.multiply(s1, s2).save("output/reconstructed.png")
        print("✅ Reconstrucción guardada.")


if __name__ == "__main__":
    vc = ColorVisualCrypto()
    if os.path.exists("input/secret.png"):
        vc.generate_shares("input/secret.png", "input/cover1.png", "input/cover2.png")
        vc.reconstruct("output/share1.png", "output/share2.png")
    else:
        print("Faltan inputs.")
