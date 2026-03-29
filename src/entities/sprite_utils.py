import pygame

from src.config import (
    SPRITESHEET_FRAME_COUNT,
    SPRITESHEET_FRAME_HEIGHT,
    SPRITESHEET_FRAME_WIDTH,
)


def load_sprite_frames(sprite_sheet_path):
    sprite_sheet = pygame.image.load(sprite_sheet_path).convert_alpha()
    frame_list = []

    for frame_index in range(SPRITESHEET_FRAME_COUNT):
        source_rect = pygame.Rect(
            frame_index * SPRITESHEET_FRAME_WIDTH,
            0,
            SPRITESHEET_FRAME_WIDTH,
            SPRITESHEET_FRAME_HEIGHT,
        )
        frame_surface = pygame.Surface((SPRITESHEET_FRAME_WIDTH, SPRITESHEET_FRAME_HEIGHT), pygame.SRCALPHA)
        frame_surface.blit(sprite_sheet, (0, 0), source_rect)
        frame_list.append(frame_surface)

    return frame_list
