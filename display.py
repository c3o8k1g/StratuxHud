#!/usr/bin/env python

"""
Initializes the display, and holds common color values.
"""

import os
import sys
import random
import pygame
import lib.local_debug as local_debug

# The SunFounder 5" TFT
DEFAULT_SCREEN_SIZE = 800, 480

BLACK = (0,   0,   0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
BLUE = (0,   0, 255)
GREEN = (0, 255,   0)
RED = (255,   0,   0)
YELLOW = (255, 255, 0)

def display_init():
    """
    Initializes PyGame to run on the current screen.
    """

    size = DEFAULT_SCREEN_SIZE
    disp_no = os.getenv('DISPLAY')
    if disp_no:
        # if False:
        # print "I'm running under X display = {0}".format(disp_no)
        size = 320, 240
        screen = pygame.display.set_mode(size)
    else:
        drivers = ['directfb', 'fbcon', 'svgalib', 'directx', 'windib']
        found = False
        for driver in drivers:
            if not os.getenv('SDL_VIDEODRIVER'):
                os.putenv('SDL_VIDEODRIVER', driver)

            try:
                pygame.display.init()
            except pygame.error:
                print('Driver: {0} failed.'.format(driver))
                continue

            found = True
            break

        if not found:
            raise Exception('No suitable video driver found!')

        size = DEFAULT_SCREEN_SIZE
        screen_mode = pygame.RESIZABLE
        if not local_debug.is_debug():
            screen_mode = pygame.FULLSCREEN
            size = pygame.display.Info().current_w, pygame.display.Info().current_h
        screen = pygame.display.set_mode(size, screen_mode)

    return screen, size