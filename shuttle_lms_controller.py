#!/usr/bin/env python3

import argparse
import evdev
import os
import sys
import logging
from pylms.player import Player
from pylms.server import Server

"""
TODO:
    - test
    - systemd unit
"""

HOST="192.168.0.100"
PORT=9090
NAME="cube"

class DeviceNotFound(Exception):
    pass

class LMSException(Exception):
    pass


class ButtonMethods(object):
    VOLUME_INCREMENT = 5

    def __init__(self, host, port, name):
        self._last_volume = 0
        self._player = None
        self._host = host
        self._port = port
        self._name = name
        self._get_player()

    def _get_player(self):
        """
        lookup the LMS player object we'll use for all the control methods
        FIXME: this probably won't work if the listener starts at the same time as LMS
        should write a decorator that attempts to lookup the player each time a command is run
        """
        host = self._host
        port = self._port
        name = self._name
        s = Server(hostname=host, port=port)
        try:
            s.connect()
        except:
            logging.error(f"could not contact server {host} {port} {name}")
            return
        for player in s.players:
            this_name = player.name
            if this_name == name:
                self._player = player
        if self._player is None:
            raise LMSException(f"could not find player with name {name}")

    @property
    def player(self):
        if self._player is None:
            self._get_player()
        return self._player

    def _check_player(func):
        def check(self, *args, **kwargs):
            if self.player is None:
                logging.error("no player available; cannot run command")
            else:
                func(self, *args, **kwargs)
        return check

    @_check_player
    def volume(self, event):
        val = event.value
        if val > self._last_volume:
            logging.info("volume up")
            self._player.volume_up(self.VOLUME_INCREMENT)
        elif val < self._last_volume:
            logging.info("volume down")
            self._player.volume_down(self.VOLUME_INCREMENT)
        else:
            # this could be a recurring event - nothing to do
            pass
        if(self._last_volume == val):
            logging.debug(f"current volume: {self._player.get_volume()}")
        else:
            logging.info(f"current volume: {self._player.get_volume()}")
        self._last_volume = val

    @_check_player
    def play_pause(self, event):
        if event.value == 1:
            logging.info("toggle")
            self._player.toggle()

    @_check_player
    def skip_forward(self, event):
        if event.value == 1:
            logging.info("forward")
            self._player.next()

    @_check_player
    def skip_backward(self, event):
        if event.value == 1:
            logging.info("back-to-beginning")
            self._player.seek_to(0)

    def echo(self, event):
        """
        used as a blank response for events we want to record but not attach a method for
        """
        logging.info(f"type: {event.type} -- code: {event.code} -- value: {event.value}")

class ShuttleManager(object):
    def __init__(self, event_map, search_string="Shuttle"):
        self._event_map = event_map
        self._device = self._find_device(search_string)

    @staticmethod
    def _find_device(search_string):
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            if search_string in device.name:
                return device
        logging.warn(f"{','.join([ d.name for d in devices ])}")
        raise DeviceNotFound(f"Could not find device with name {search_string}")

    def main_loop(self):
        device = self._device
        for event in device.read_loop():
            logging.debug(f"saw event type: {event.type} code: {event.code} value: {event.value}")
            if(event.code in self._event_map):
                func = self._event_map[event.code]
                func(event)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default=HOST, help="hostname/IP")
    parser.add_argument('--port', default=PORT, help="port number")
    parser.add_argument("--name", default=NAME, help="name of player to control")
    parser.add_argument("-L", "--loglevel", default="INFO", help="log level")
    args = parser.parse_args()

    if not hasattr(logging, args.loglevel):
        print(f"unrecognised log level {args.loglevel}")
        sys.exit(1)

    logging.basicConfig(level=getattr(logging, args.loglevel),
                        format='%(asctime)s %(levelname)-8s %(message)s')

    bm = ButtonMethods(args.host, args.port, args.name)
    logging.debug(bm._player)
    EVENT_MAP = {
        evdev.ecodes.ecodes["BTN_4"]: bm.echo,
        evdev.ecodes.ecodes["BTN_5"]: bm.skip_backward,
        evdev.ecodes.ecodes["BTN_6"]: bm.play_pause,
        evdev.ecodes.ecodes["BTN_7"]: bm.skip_forward,
        evdev.ecodes.ecodes["BTN_8"]: bm.echo,
        evdev.ecodes.ecodes["REL_DIAL"]: bm.volume
    }

    sm = ShuttleManager(event_map=EVENT_MAP)
    logging.debug(sm._device)

    sm.main_loop()

