import pygame
import os

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

TILE_COLORS = {
    "blue": (0, 140, 220),
    "yellow": (250, 210, 30),
    "red": (210, 40, 40),
    "black": (50, 50, 55),
    "white": (230, 225, 215),
}

TILE_ACCENTS = {
    "blue": (100, 190, 250),
    "yellow": (255, 230, 100),
    "red": (240, 100, 100),
    "black": (100, 100, 105),
    "white": (255, 255, 250),
}


def create_tile_image(color_name, size=64):
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    base = TILE_COLORS[color_name]
    accent = TILE_ACCENTS[color_name]

    rect = pygame.Rect(2, 2, size - 4, size - 4)
    pygame.draw.rect(surf, base, rect, border_radius=8)
    pygame.draw.rect(surf, (255, 255, 255, 60), rect, 2, border_radius=8)

    inner = pygame.Rect(6, 6, size - 12, size - 12)
    pygame.draw.rect(surf, accent, inner, border_radius=5)

    return surf


def generate_all():
    pygame.init()
    os.makedirs(ASSETS_DIR, exist_ok=True)
    for color_name in TILE_COLORS:
        surf = create_tile_image(color_name)
        path = os.path.join(ASSETS_DIR, f"{color_name}.png")
        pygame.image.save(surf, path)
        print(f"Créé: {path}")

    icon = create_tile_image("blue", 32)
    icon_path = os.path.join(ASSETS_DIR, "icon.png")
    pygame.image.save(icon, icon_path)
    print(f"Créé: {icon_path}")

    pygame.quit()
    print("Tous les assets ont été générés!")


if __name__ == "__main__":
    generate_all()
