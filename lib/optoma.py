# -*- coding: utf-8 -*-
# Copyright (c) 2015,2018 Fredrik Eriksson <git@wb9.se>
# This file is covered by the BSD-3-Clause license, read LICENSE for details.

# Added by benjikimix in April 2021

"""Module for communicating with Optoma projectors over RS232 serial interface.

Protocol description fetched on 2021-04-10 from
https://www.optoma.fr/ContentStorage/Documents/286c27f6-93f7-4274-acf9-67b225f99e34.pdf
"""

import os
import select

import serial

import lib.commands
import lib.errors

from lib.helpers import log

# List of all valid models and their input sources
# Remember to add new models to the settings.xml-file as well
_valid_sources_ = {
        "Generic": {
            "HDMI":             "1",
            "HDMI1":            "1",
            "HDMI/MHL":         "1",
            "HDMI1/MHL":        "1",
            "HDMI2":            "15",
            "HDMI2/MHL":        "15",
            "HDMI3":            "16",
            "DVI-D":            "2",
            "DVI-A":            "3",
            "VGA":              "5",
            "VGA1":             "5",
            "VGA2":             "6",
            "Component":        "14",
            "S-Video":          "9",
            "Video":            "10",
            "DisplayPort":      "20",
            "HDBaseT":          "21",
            "BNC":              "4",
            "Wireless":         "11",
            "Flash Drive":      "17",
            "Network Display":  "18",
            "USB Display":      "19",
            "Multimedia":       "23",
            "3G-SDI":           "22",
            "Smart TV":         "24"
            },
        "EH470": {
            "HDMI1":            "1",
            "HDMI2":            "15",
            "VGA":              "5",
            "USB Display":      "19"
            }
        }

# List of all valid current input sources, but indexed
# according to the response to the CMD_SRC_QUERY
# Strangely the numbers are not the same for query and set
# in the Optoma RS232 reference
_valid_sources_query_ = {
        "Generic": {
            "0":    "No signal",
            "1":    "DVI",
            "2":    "VGA1",
            "3":    "VGA2",
            "4":    "S-Video",
            "5":    "Video",
            "6":    "BNC",
            "7":    "HDMI1",
            "8":    "HDMI2",
            "9":    "HDMI3",
            "10":   "Wireless",
            "11":   "Component",
            "12":   "Flash Drive",
            "13":   "Network Display",
            "14":   "USB Display",
            "15":   "DisplayPort",
            "16":   "HDBaseT",
            "17":   "Multimedia",
            "18":   "3D-SDI",
            "19":   "Unknown",
            "20":   "Smart TV"
            },
        "EH470": {
            "7":    "HDMI1",
            "8":    "HDMI2",
            "2":    "VGA",
            "14":   "USB Display"
            }
        }

# map the generic commands to ESC/VP21 commands
_command_mapping_ = {
        lib.CMD_PWR_ON: "~0000 1",
        lib.CMD_PWR_OFF: "~0000 0",
        lib.CMD_PWR_QUERY: "~00124 1",

        lib.CMD_SRC_QUERY: "~00121 1",
        lib.CMD_SRC_SET: "~0012 {source_id}"
        }

_serial_options_ = {
        "baudrate": 9600,
        "bytesize": serial.EIGHTBITS,
        "parity": serial.PARITY_NONE,
        "stopbits": serial.STOPBITS_ONE
}

def get_valid_sources(model):
    """Return all valid source strings for this model"""
    if model in _valid_sources_:
        return list(_valid_sources_[model].keys())
    return None

def get_serial_options():
    return _serial_options_

def get_source_id(model, source):
    """Return the "real" source ID based on projector model and human readable
    source string"""
    if model in _valid_sources_ and source in _valid_sources_[model]:
        return _valid_sources_[model][source]
    return None

class ProjectorInstance:
    
    def __init__(self, model, ser, timeout=5):
        """Class for managing Optoma projectors

        :param model: Optoma model
        :param ser: open Serial port for the serial console
        :param timeout: time to wait for response from projector
        """
        self.serial = ser
        self.timeout = timeout
        self.model = model
        res = self._verify_connection()
        if not res:
            raise lib.errors.ProjectorError(
                    "Could not verify ready-state of projector"
                    #"Verify returned {}".format(res)
                    )


    def _verify_connection(self):
        """Verify that the projecor is ready to receive commands.
        The projector is ready when it answers OK0 or OK1 to a power state request.
        This is the only command that works even when the projector is powered off.
        """
        res = self._send_command(_command_mapping_[lib.CMD_PWR_QUERY])
        if res is not None:
            return True
        else:
            return False

    def _read_response(self):
        """Read response from projector"""
        read = ""
        res = ""
        while not read.endswith('\r'):
            r, w, x = select.select([self.serial.fileno()], [], [], self.timeout) 
            if len(r) == 0:
                raise lib.errors.ProjectorError(
                        "Timeout when reading response from projector"
                        )
            for f in r:
                try:
                    read = os.read(f, 256)
                    res += read
                except OSError as e:
                    raise lib.errors.ProjectorError(
                            "Error when reading response from projector: {}".format(e),
                            )
                    return None

        part = res.split('\r', 1)
        log("projector responded: '{}'".format(part[0]))
        return part[0]


    def _send_command(self, cmd_str):
        """Send command to the projector.

        :param cmd_str: Full raw command string to send to the projector
        """

        log("_send_command() :: cmd_str='{}'".format(cmd_str)) # DEBUG

        ret = None
        try:
            self.serial.write("{}\r".format(cmd_str))
        except OSError as e:
            raise lib.errors.ProjectorError(
                    "Error when Sending command '{}' to projector: {}".\
                        format(cmd_str, e)
                    )
            return ret

        log("_send_command() :: self.serial.write() with no error") # DEBUG
        
        # Read the command result

        log("_send_command() :: Executing _read_response()...") # DEBUG

        ret = self._read_response()
        
        log("_send_command() :: ret='{}'".format(ret)) # DEBUG
        
        # SET commands get either 'P' (Pass) or 'F' (Fail) response
        # QUERY commands get either 'OKxxxx' (Pass, returned value = xxxx, variable length) of 'F' (Fail) response
        if not ret.upper().startswith("OK") and ret != 'P' and ret != 'F':

            log("_send_command() :: ret does not yet have a valid format: {}".format(ret)) # DEBUG

            raise lib.errors.ProjectorError(
                    "Error processing the response '{}' of the projector when sending command '{}' to projector.".format(ret, cmd_str)
                    )
            return ret
        
        log("_send_command() :: ret='{}'".format(ret)) # DEBUG
        
        # If command failed
        if ret == 'F':
            log("Projector responded with Error!")
            return None
        
        log("Command sent successfully")
        
        # If SET command passed
        if ret == "P":
            ret = True
        
            log("_send_command() :: Response was P. ret=True") # DEBUG
        
        # If QUERY command passed
        elif ret.upper().startswith("OK"):
            
            log("_send_command() :: Response was OK. Checking read value.") # DEBUG
        
            ret = ret[2:]

            log("_send_command() :: Read value='{}'".format(ret)) # DEBUG
        
            # Check response for CMD_PWR_QUERY
            if cmd_str == _command_mapping_[lib.CMD_PWR_QUERY]:
                if ret == "1":
                    ret = True
            
                    log("_send_command() :: Command was CMD_PWR_QUERY. ret=True") # DEBUG
        
                else:
                    ret = False
            
                    log("_send_command() :: Command was CMD_PWR_QUERY. ret=False") # DEBUG
        
            # Check response for CMD_SRC_QUERY
            elif cmd_str == _command_mapping_[lib.CMD_SRC_QUERY]:
            
                log("_send_command() :: Command was CMD_SRC_QUERY") # DEBUG
        
                if ret in [_valid_sources_query_[self.model][x] for x in _valid_sources_query_[self.model]]:
                    ret = [x for x in _valid_sources_query_[self.model] if _valid_sources_query_[self.model][x] == ret][0]
            
                log("_send_command() :: Command was CMD_SRC_QUERY. ret='{}'".format(ret)) # DEBUG
        

        log("_send_command() :: End of function. Will return ret='{}'".format(ret)) # DEBUG
        
        return ret

    def send_command(self, command, **kwargs):
        """Send command to the projector.

        :param command: A valid command from lib
        :param **kwargs: Optional parameters to the command. For Optoma the only
            valid keyword is "source_id" on CMD_SRC_SET.

        :return: True or False on CMD_PWR_QUERY, a source string on
            CMD_SRC_QUERY, otherwise None.
        """
        if not command in _command_mapping_:
            raise lib.errors.InvalidCommandError(
                    "Command {} not supported".format(command)
                    )

        if command == lib.CMD_SRC_SET:
            cmd_str = _command_mapping_[command].format(**kwargs)
        else:
            cmd_str = _command_mapping_[command]

        log("sending command '{}'".format(cmd_str))
        res = self._send_command(cmd_str)
        log("send_command returned {}".format(res))
        return res




