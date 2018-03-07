#!/usr/bin/env python

import math
import json
import os
import sys
import random
import argparse
import datetime
import pygame
import display
import traffic
from configuration import *
from aircraft import Aircraft

# TODO - Add the G-Meter
# TODO - Disable functionality based on the enabled StratuxCapabilities
# TODO - Check for the key existance anyway... cross update the capabilties
# TODO - Add roll indicator

# Traffic description in https://github.com/cyoung/stratux/blob/master/notes/app-vendor-integration.md
# WebSockets docs at https://ws4py.readthedocs.io/en/latest/
# pip install ws4py
# pip install requests


class HeadsUpDisplay(object):
    """
    Class to handle the HUD work...
    """

    DEGREES_OF_PITCH = 90
    PITCH_DEGREES_DISPLAY_SCALER = 2.0

    def run(self):
        clock = pygame.time.Clock()

        while self.tick(clock):
            pass

        pygame.quit()

    def tick(self, clock):
        """
        Run for a single frame.

        Arguments:
            clock {pygame.time.Clock} -- game/frame clock

        Returns:
            bool -- True if the code should run for another tick.
        """

        clock.tick(MAX_FRAMERATE)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

        orientation = self.__aircraft__.get_orientation()

        self.__backpage_framebuffer__.fill(display.BLACK)

        if self.__aircraft__.is_ahrs_available():
            # Order of drawing is important
            # The pitch lines are drawn before the other
            # referenence information so they will be pushed to the
            # background.
            # The reference text is also intentionally
            # drawn with a black background
            # to overdraw the pitch lines
            # and improve readability
            self.__render_level_reference__()
            self.__render_pitch__(orientation.pitch, orientation.roll)
            self.__render_heading__(orientation)
            self.__render_altitude__(orientation)
            self.__render_g_load_and_skid__(orientation)
            self.__render_roll__(orientation)
            self.__render_adsb_traffic__(orientation)
            self.__render_adsb_onscreen_targets__(orientation)
        else:
            # Should do this if the signal is lost...
            self.__render_ahrs_not_available__()

        # Change the frame buffer
        flipped = pygame.transform.flip(
            self.__backpage_framebuffer__, self.__configuration__.flip_horizonal, self.__configuration__.flip_vertical)
        self.__backpage_framebuffer__.blit(flipped, [0, 0])
        pygame.display.flip()

        return True

    def __get_traffic_projection__(self, orientation, traffic):
        """
        Attempts to figure out where the traffic reticle should be rendered.
        Returns value within screen space
        """

        # Assumes traffic.position_valid
        # TODO - Account for aircraft roll...

        altitude_delta = int(traffic.altitude - orientation.alt)
        slope = altitude_delta / traffic.distance
        vertical_degrees_to_target = math.degrees(math.atan(slope))
        vertical_degrees_to_target -= orientation.pitch

        # TODO - Double check ALL of this math...
        compass = orientation.get_heading()
        horizontal_degrees_to_target = traffic.bearing - compass

        screen_y = -vertical_degrees_to_target * self.__get_pixels_per_degree_y__()
        screen_x = horizontal_degrees_to_target * self.__get_pixels_per_degree_y__()

        return self.__center__[0] + screen_x, self.__center__[1] + screen_y

    def get_above_reticle(self, center_x, center_y, scale):
        """Generates the coordinates for a reticle indicating
        traffic is above use.

        Arguments:
            center_x {int} -- Center X screen position
            center_y {int} -- Center Y screen position
            scale {float} -- The scale of the reticle relative to the screen.
        """

        size = int(self.__height__ * scale)

        above_reticle = [
            [center_x - size, 0 + size],
            [center_x, 0],
            [center_x + size, 0 + size]
        ]

        return above_reticle

    def get_below_reticle(self, center_x, center_y, scale):
        """Generates the coordinates for a reticle indicating
        traffic is above use.

        Arguments:
            center_x {int} -- Center X screen position
            center_y {int} -- Center Y screen position
            scale {float} -- The scale of the reticle relative to the screen.
        """

        size = int(self.__height__ * scale)

        below_reticle = [
            [center_x - size, self.__height__ - size],
            [center_x, self.__height__],
            [center_x + size, self.__height__ - size]
        ]

        return below_reticle

    def get_onscreen_reticle(self, center_x, center_y, scale):
        size = int(self.__height__ * scale)

        on_screen_reticle = [
            [center_x, center_y - size],
            [center_x + size, center_y],
            [center_x, center_y + size],
            [center_x - size, center_y]
        ]

        return on_screen_reticle

    def __render_target_reticle__(self, identifier, center_x, center_y, reticle_lines, roll):
        """
        Renders a targetting reticle on the screen.
        Assumes the X/Y projection has already been performed.
        """

        border_space = int(self.__font__.get_height() * 3.0)

        if center_y < border_space:
            center_y = border_space

        if center_y > (self.__height__ - border_space):
            center_y = int(self.__height__ - border_space)

        pygame.draw.lines(self.__backpage_framebuffer__,
                          display.RED, True, reticle_lines, 2)
        
        # Move the identifer text away from the reticle
        if center_y < self.__center__[1]:
            text_y = center_y + border_space
        else:
            text_y = center_y - border_space

        self.__render_text__(identifier, display.YELLOW,
                             center_x, text_y, roll)

    def __render_text__(self, text, color, position_x, position_y, roll, background_color=None):
        """
        Renders the text with the results centered on the given
        position.
        """

        rendered_text = self.__font__.render(
            text, True, color, background_color)
        text_width, text_height = rendered_text.get_size()

        text = pygame.transform.rotate(rendered_text, roll)

        self.__backpage_framebuffer__.blit(
            text, (position_x - (text_width >> 1), position_y - (text_height >> 1)))

        return text_width, text_height

    def __render_heading__(self, orientation):
        """
        Renders the current heading to the HUD.
        """

        cardinal_direction_line_proportion = 0.05
        compass = int(orientation.compass_heading)
        if compass is None or compass > 360 or compass < 0:
            compass = '---'

        heading_text_y = int(self.__font__.get_height() * 2)
        compass_text_y = int(self.__font__.get_height() * 3)

        # Render a crude compass
        # Render a heading strip along the top
        pixels_per_degree = self.__width__ / 360.0

        heading = orientation.get_heading()
        for heading_strip in range(0, 180, 1):
            to_the_left = int((heading - heading_strip) + 0.5)
            to_the_right = int((heading + heading_strip) + 0.5)

            if to_the_left < 0:
                to_the_left += 360

            if to_the_right > 360:
                to_the_right -= 360

            line_x_left = self.__center__[0] - \
                int(pixels_per_degree * heading_strip)
            line_x_right = self.__center__[0] + \
                int(pixels_per_degree * heading_strip)

            if (to_the_left % 90) == 0:
                pygame.draw.lines(self.__backpage_framebuffer__, display.GREEN, True, [
                    [line_x_left, self.__height__ * cardinal_direction_line_proportion], [line_x_left, 0]], 2)

                self.__render_text__(str(to_the_left), display.GREEN,
                                     line_x_left, heading_text_y, 0,
                                     display.BLACK)

            if (to_the_right % 90) == 0:
                pygame.draw.lines(self.__backpage_framebuffer__, display.GREEN, True, [
                    [line_x_right, self.__height__ * cardinal_direction_line_proportion], [line_x_right, 0]], 2)

                self.__render_text__(str(to_the_right), display.GREEN,
                                     line_x_right, heading_text_y, 0,
                                     display.BLACK)

        # Render the text that is showing our AHRS and GPS headings
        cover_old_rendering_spaces = "     "
        heading_text = "{0}{1} / {2}{0}".format(cover_old_rendering_spaces,
                                                compass, int(orientation.gps_heading))
        box_width, box_height = self.__render_text__(heading_text, display.GREEN,
                                                     self.__center__[
                                                         0], compass_text_y, 0,
                                                     display.BLACK)

        border_vertical_size = (box_height >> 1) + (box_height >> 2)

        pygame.draw.lines(self.__backpage_framebuffer__, display.GREEN, True, [
            [self.__center__[0] - (box_width >> 1),
             compass_text_y - border_vertical_size],
            [self.__center__[0] + (box_width >> 1),
             compass_text_y - border_vertical_size],
            [self.__center__[0] + (box_width >> 1),
             compass_text_y + border_vertical_size],
            [self.__center__[0] - (box_width >> 1), compass_text_y + border_vertical_size]], 2)

    def __render_altitude__(self, orientation):
        """
        Renders the GPS altitude to the HUD.
        """

        altitude_text = str(int(orientation.alt)) + "' MSL"
        alt_texture = self.__font__.render(
            altitude_text, True, display.WHITE, display.BLACK)
        text_width, text_height = alt_texture.get_size()
        right_hand_side = int(0.9 * self.__width__)
        self.__backpage_framebuffer__.blit(
            alt_texture, (right_hand_side - text_width, self.__center__[1] - (text_height >> 1)))

    def __render_g_load_and_skid__(self, orientation):
        # G-loading and skids...
        g_load_text = "{0:.1f}Gs".format(orientation.g_load)
        texture = self.__font__.render(
            g_load_text, True, display.WHITE, display.BLACK)
        text_width, text_height = texture.get_size()
        right_hand_side = int(0.9 * self.__width__)
        self.__backpage_framebuffer__.blit(
            texture, (right_hand_side - text_width, (self.__font__.get_height() * 2) + self.__center__[1] - (text_height >> 1)))

    def __render_roll__(self, orientation):
        """
        Renders our AHRS roll to the HUD.
        """

        roll_text = str(int(math.fabs(orientation.roll)))
        roll_texture = self.__font__.render(
            roll_text, True, display.WHITE, display.BLACK)
        roll_texture = pygame.transform.rotate(roll_texture, orientation.roll)
        text_width, text_height = roll_texture.get_size()
        self.__backpage_framebuffer__.blit(
            roll_texture, (self.__center__[0] - (text_width >> 1), self.__center__[1] - (text_height >> 1)))

    def __render_level_reference__(self):
        """
        Renders a "straight and level" line to the HUD.
        """

        width = self.__width__
        height = self.__height__

        edge_reference_proportion = int(width * 0.05)

        artificial_horizon_level = [[int(width * 0.4),  self.__center__[1]],
                                    [int(width * 0.6),  self.__center__[1]]]

        pygame.draw.lines(self.__backpage_framebuffer__,
                          display.GRAY, True, artificial_horizon_level, 2)

        pygame.draw.lines(self.__backpage_framebuffer__, display.WHITE, False, [
            [0, self.__center__[1]], [edge_reference_proportion, self.__center__[1]]], 2)
        pygame.draw.lines(self.__backpage_framebuffer__, display.WHITE, False, [
            [self.__width__ - edge_reference_proportion, self.__center__[1]], [self.__width__, self.__center__[1]]], 2)

    def __rotate_reticle__(self, reticle, roll):
        """
        Takes a series of line segments and rotates them (roll) about
        the screen's center

        Arguments:
            reticle {list of tuples} -- The line segments
            roll {float} -- The amount to rotate about the center by.

        Returns:
            list of lists -- The new list of line segments
        """

        # Takes the roll in degrees
        # Example input..
        # [
        #     [center_x, center_y - size],
        #     [center_x + size, center_y],
        #     [center_x, center_y + size],
        #     [center_x - size, center_y]
        # ]

        translated_points = []

        roll_radians = math.radians(roll)
        cos_roll = math.cos(roll_radians)
        sin_roll = math.sin(roll_radians)
        ox, oy = self.__center__

        for x_y in reticle:
            px, py = x_y

            qx = ox + cos_roll * (px - ox) - sin_roll * (py - oy)
            qy = oy + sin_roll * (px - ox) + cos_roll * (py - oy)

            translated_points.append([qx, qy])

        return translated_points

    def __get_distance_string__(self, distance):
        sm = "statute"
        nm = "knots"
        metric = "metric"

        feet_to_nm = 6076.12
        feet_to_sm = 5280.0
        feet_to_km = 3280.84
        feet_to_m = 3.28084
        imperial_nearby = 3000.0

        units = self.__configuration__.__get_config_value__(
            Configuration.DISTANCE_UNITS_KEY, sm)

        if units is not metric:
            if distance < imperial_nearby:
                return distance + "'"

            if units is nm:
                return "{0:.1f}NM".format(distance / feet_to_nm)

            return "{0:.1f}SM".format(distance / feet_to_sm)
        else:
            conversion = distance / feet_to_km

            if conversion > 0.5:
                return "{0:.1f}km".format(conversion)

            return "{0:.1f}m".format(distance / feet_to_m)

        return "{0:.0f}'".format(distance)

    def pad_right(self, text, longest):
        delta = longest - len(text)

        padded_text = text

        for i in range(0, delta, 1):
            padded_text += ' '

        return padded_text

    def pad_left(self, text, longest):
        delta = longest - len(text)

        padded_text = ''

        for i in range(0, delta, 1):
            padded_text += ' '

        return padded_text + text

    def __render_adsb_traffic__(self, orientation):
        if self.traffic is None:
            return

        # Render a heading strip along the top
        pixels_per_degree = self.__width__ / 360.0

        heading = orientation.get_heading()

        # Get the traffic, and bail out of we have none
        traffic_reports = self.traffic.TRAFFIC_MANAGER.get_traffic_with_position()

        if traffic_reports is None:
            return

        # Render a list of traffic that we have positions
        # for, along with the tail number
        y_pos = int(self.__detail_font__.get_height() * 4)
        x_pos = int(self.__width__ * 0.01)

        max_identifier_length = 0
        max_bearing_length = 0
        max_altitude_length = 0
        max_distance_length = 0
        pre_padded_text = []
        for traffic in traffic_reports:
            identifier = traffic.get_identifer()
            altitude_delta = int(traffic.altitude - orientation.alt)
            distance_text = self.__get_distance_string__(traffic.distance)
            delta_sign = ''
            if altitude_delta > 0:
                delta_sign = '+'
            altitude_text = "{0}{1}'".format(delta_sign, altitude_delta)
            bearing_text = "{0:.0f}".format(traffic.bearing)

            identifier_length = len(identifier)
            bearing_length = len(bearing_text)
            altitude_length = len(altitude_text)
            distance_length = len(distance_text)

            if identifier_length > max_identifier_length:
                max_identifier_length = identifier_length

            if bearing_length > max_bearing_length:
                max_bearing_length = bearing_length

            if altitude_length > max_altitude_length:
                max_altitude_length = altitude_length

            if distance_length > max_distance_length:
                max_distance_length = distance_length

            pre_padded_text.append(
                [identifier, bearing_text, distance_text, altitude_text])

        for report in pre_padded_text:
            identifier = report[0]
            bearing = report[1]
            distance_text = report[2]
            altitude = report[3]
            traffic_report = "{0} {1} {2} {3}".format(self.pad_right(identifier, max_identifier_length),
                                                      self.pad_left(
                                                          bearing, max_bearing_length),
                                                      self.pad_left(
                                                          distance_text, max_distance_length),
                                                      self.pad_left(altitude, max_altitude_length))

            traffic_text_texture = self.__detail_font__.render(
                traffic_report, True, display.WHITE, display.BLACK)
            text_width, text_height = traffic_text_texture.get_size()
            self.__backpage_framebuffer__.blit(
                traffic_text_texture, (x_pos, y_pos))

            y_pos += int(1.5 * text_height)

            # Now find where to draw the reticle....
            reticle_x, reticle_y = self.__get_traffic_projection__(
                orientation, traffic)

            # Render using the Above us bug
            target_bug_scale = 0.02

            bearing = (heading - traffic.bearing)
            if bearing < -180:
                bearing += 360

            if bearing > 180:
                bearing -= 180
            heading_bug_x = int(
                self.__center__[0] - (bearing * pixels_per_degree))

            if reticle_y <= self.__top_border__:
                reticle = self.get_above_reticle(
                    heading_bug_x, reticle_y, target_bug_scale)
            elif reticle_y >= self.__bottom_border__:
                reticle = self.get_below_reticle(
                    heading_bug_x, reticle_y, target_bug_scale)
            else:
                continue

            self.__render_target_reticle__(
                identifier, reticle_x, reticle_y, reticle, 0)

            # Draw a line pointing to it.. for debugging purposes
            # pygame.draw.lines(self.__backpage_framebuffer__, display.RED, True, [
            #    self.__center__, [reticle_x, reticle_y]], 2)

    def __render_adsb_onscreen_targets__(self, orientation):
        if self.traffic is None:
            return

        # Get the traffic, and bail out of we have none
        traffic_reports = self.traffic.TRAFFIC_MANAGER.get_traffic_with_position()

        if traffic_reports is None:
            return

        for traffic in traffic_reports:
            identifier = traffic.get_identifer()

            # Find where to draw the reticle....
            reticle_x, reticle_y = self.__get_traffic_projection__(
                orientation, traffic)

            # Render using the Above us bug
            on_screen_reticle_scale = 0.05
            reticle = self.get_onscreen_reticle(
                reticle_x, reticle_y, on_screen_reticle_scale)

            if reticle_y < self.__top_border__ or reticle_y > self.__bottom_border__:
                continue
            else:
                reticle = self.__rotate_reticle__(reticle, orientation.roll)
                reticle_x, reticle_y = self.__rotate_reticle__(
                    [[reticle_x, reticle_y]], orientation.roll)[0]

                self.__render_target_reticle__(
                    identifier, reticle_x, reticle_y, reticle, orientation.roll)

    def __get_pixels_per_degree_y__(self):
        return (self.__height__ / HeadsUpDisplay.DEGREES_OF_PITCH) * HeadsUpDisplay.PITCH_DEGREES_DISPLAY_SCALER

    def __get_line_coords__(self, pitch=0, roll=0, hash_mark_angle=0):
        """
        Get the coordinate for the lines for a given pitch and roll.
        """

        if hash_mark_angle == 0:
            length = self.__width__ * .2
        elif (hash_mark_angle % 10) == 0:
            length = self.__width__ * 0.1

        ahrs_center_x, ahrs_center_y = self.__center__
        px_per_deg_y = self.__get_pixels_per_degree_y__()
        pitch_offset = px_per_deg_y * (-pitch + hash_mark_angle)

        roll_radians = math.radians(roll)
        roll_delta_radians = math.radians(90 - roll)

        center_x = int(
            (ahrs_center_x - (pitch_offset * math.cos(roll_delta_radians))) + 0.5)
        center_y = int(
            (ahrs_center_y - (pitch_offset * math.sin(roll_delta_radians))) + 0.5)

        x_len = int((length * math.cos(roll_radians)) + 0.5)
        y_len = int((length * math.sin(roll_radians)) + 0.5)

        start_x = center_x - (x_len >> 1)
        end_x = center_x + (x_len >> 1)
        start_y = center_y + (y_len >> 1)
        end_y = center_y - (y_len >> 1)

        return [[start_x, start_y], [end_x, end_y]]

    def __init__(self):
        """
        Initialize and create a new HUD.
        """

        self.__configuration__ = Configuration(DEFAULT_CONFIG_FILE)

        adsb_traffic_address = "ws://{0}/traffic".format(
            self.__configuration__.stratux_address())
        self.traffic = traffic.AdsbTrafficClient(adsb_traffic_address)
        self.traffic.run_in_background()

        self.__backpage_framebuffer__, screen_size = display.display_init()  # args.debug)
        self.__width__, self.__height__ = screen_size
        pygame.mouse.set_visible(False)

        pygame.font.init()

        font_name = "consolas,arial,helvetica"

        self.__font__ = pygame.font.SysFont(font_name, int(self.__height__ / 20.0), True, False)
        self.__detail_font__ = pygame.font.SysFont(font_name, int(self.__height__ / 20.0), False, False)

        self.__aircraft__ = Aircraft()

        self.__center__ = (
            self.__width__ >> 1, self.__height__ >> 1)

        self.__top_border__ = int(self.__height__ * 0.1)
        self.__bottom_border__ = self.__height__ - self.__top_border__

    def __render_ahrs_not_available__(self):
        """
        Render an "X" over the screen to indicate the AHRS is not
        available.
        """
        pygame.draw.lines(self.__backpage_framebuffer__, display.RED, True, [
            [0, 0], [self.__width__, self.__height__]], 10)
        pygame.draw.lines(self.__backpage_framebuffer__, display.RED, True, [
            [0, self.__height__], [self.__width__, 0]], 10)

    def __render_pitch__(self, pitch, roll):
        """
        Render the pitch hash marks.
        """

        for reference_angle in range(-HeadsUpDisplay.DEGREES_OF_PITCH, HeadsUpDisplay.DEGREES_OF_PITCH + 1, 10):
            line_coords = self.__get_line_coords__(
                pitch, roll, reference_angle)

            # Perform some trivial clipping of the lines
            # This also prevents early text rasterization
            if line_coords[0][1] < 0 and line_coords[1][1] < 0:
                continue

            if line_coords[0][1] > self.__height__ and line_coords[1][1] > self.__height__:
                continue

            pygame.draw.lines(self.__backpage_framebuffer__,
                              display.GREEN, True, line_coords, 2)

            text = self.__font__.render(
                str(reference_angle), True, display.WHITE, display.BLACK)
            text = pygame.transform.rotate(text, roll)
            text_width, text_height = text.get_size()
            half_text_width = text_width >> 1
            center_x = int(
                ((line_coords[0][0] + line_coords[1][0]) >> 1) - half_text_width)
            center_y = int(
                ((line_coords[0][1] + line_coords[1][1]) >> 1) - half_text_width)

            self.__backpage_framebuffer__.blit(text, (center_x, center_y))


if __name__ == '__main__':
    hud = HeadsUpDisplay()
    sys.exit(hud.run())