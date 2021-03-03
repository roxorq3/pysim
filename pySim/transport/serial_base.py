#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Copyright (C) 2018-2021  Gabriel K. Gegenhuber <ggegenhuber@sba-research.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import absolute_import

import serial
import logging
import os.path

from pySim.exceptions import ProtocolError, NotInitializedError
from pySim.utils import calculate_checksum_xor, b2h, i2h


class SerialBase(object):
    DEFAULT_FI = 0
    DEFAULT_DI = 1
    DEFAULT_WI = 10

    TBL_CLOCKRATECONVERSION = [372, 372, 558, 744, 1116, 1488, 1860, 'RFU',
                               'RFU', 512, 768, 1024, 1536, 2048, 'RFU', 'RFU',
                               'RFU']

    TBL_BITRATEFACTOR = ['RFU', 1, 2, 4, 8, 16, 32, 'RFU', 12, 20, 'RFU',
                         'RFU', 'RFU', 'RFU', 'RFU', 'RFU']

    HEADER_LEN = 5  # 5 header bytes (cla, ins, p1, p2, p3)
    PPS_LEN = 4
    SW_LEN = 2

    ATR_BYTE = 0x3b
    PPS_BYTE = 0xff
    WXT_BYTE = 0x60

    BUF_SIZE = 256

    def __init__(self, device='/dev/ttyUSB0', clock=3571200, timeout=1):
        if not os.path.exists(device):
            raise ValueError("device file %s does not exist -- abort" % device)
        self._clk = clock
        self._fi = SerialBase.DEFAULT_FI
        self._di = SerialBase.DEFAULT_DI
        self._wi = SerialBase.DEFAULT_WI
        self._atr = None
        self._sl = serial.Serial(
            port=device,
            parity=serial.PARITY_EVEN,
            bytesize=serial.EIGHTBITS,
            stopbits=serial.STOPBITS_TWO,
            timeout=timeout,
            xonxoff=0,
            rtscts=0,
            baudrate=self._calculate_baudrate(),
            inter_byte_timeout=0.1
        )

    def __del__(self):
        self.close()

    def close(self):
        if (hasattr(self, "_sl")):
            self._sl.close()

    def _set_baudrate(self, baudrate):
        self._sl.baudrate = baudrate

    def _set_inter_byte_timeout(self, inter_byte_timeout):
        self._sl.inter_byte_timeout = inter_byte_timeout

    def _calculate_baudrate(self):
        return round(self._clk / self._calculate_f() * self._calculate_d())

    def _calculate_f(self):
        return SerialBase.TBL_CLOCKRATECONVERSION[self._fi]

    def _calculate_d(self):
        return SerialBase.TBL_BITRATEFACTOR[self._di]

    def _get_work_etu(self):  # page 383
        return self._calculate_f() / self._clk / self._calculate_d()

    def get_waiting_time(self):
        return (960 * self._calculate_d() * self._wi) * self._get_work_etu()

    def get_atr(self):
        return self._atr

    def atr_recieved(self, atr):
        if atr[0] != SerialBase.ATR_BYTE:
            raise ProtocolError(
                f"Bad ATR header. Expected {SerialBase.ATR_BYTE}, got {atr[0]})")
        self._atr = bytes(atr)

    def pps_sent(self, pps):
        if pps[0] != SerialBase.PPS_BYTE:
            raise ProtocolError(
                f"Bad PPS header. Expected {SerialBase.PPS_BYTE}, got {pps[0]})")

        fidi = pps[2]
        self._fi = fidi >> 4 & 0x0f
        self._di = fidi & 0x0f

        serial_baudrate = self._calculate_baudrate()
        self._set_baudrate(serial_baudrate)
        self._set_inter_byte_timeout(0.01)
        logging.info(
            f"update fidi: {self._calculate_f()}/{self._calculate_d()} --> new baudrate: {serial_baudrate}")

    def get_pps_proposal(self):
        if not self._atr:
            raise NotInitializedError(
                "ATR not received yet --> cannot calculate pps!")
        pps = bytearray([0xff, 0x10])
        pps.append(self._atr[2])  # TA1
        pps.append(calculate_checksum_xor(pps))
        return pps

    def tx_byte(self, b):
        logging.debug(f"tx_byte: {b2h(b)}")
        self._sl.write(b)
        r = self._sl.read()
        if r != b:  # TX and RX are tied, so we must clear the echo
            raise ProtocolError("Bad echo value. Expected %02x, got %s)" % (
                ord(b), '%02x' % ord(r) if r else '(nil)'))

    def tx_bytes(self, buf):
        """This is only safe if it's guaranteed the card won't send any data
        during the time of tx of the string !!!"""
        logging.debug(f"tx_bytes [{len(buf)}]: {b2h(buf)}")
        self._sl.write(buf)
        r = self._sl.read(len(buf))
        if r != buf:    # TX and RX are tied, so we must clear the echo
            raise ProtocolError(
                f"Bad echo value (Expected: {b2h(buf)}, got {b2h(r)})")

    def rx_byte(self):
        #tmp = self._sl.timeout
        # self._sl.timeout = 0 #non blocking mode --> return empty string when there is nothing to read
        b = self._sl.read()
        #self._sl.timeout = tmp
        logging.debug(f"rx_byte: {i2h(b)}")
        return b

    def rx_bytes(self, size=None):
        if size is None:
            size = SerialBase.BUF_SIZE
        buf = self._sl.read(size)
        logging.debug(f"rx_bytes [{len(buf)}/{size}]: {b2h(buf)}")
        return buf

    def reset_input_buffer(self):
        self._sl.reset_input_buffer()

    def setRTS(self, level=True):
        self._sl.rts = level

    def setDTR(self, level=True):
        self._sl.dtr = level

    def is_open(self):
        return self._sl.is_open

    def cancel_read(self):
        if hasattr(self._sl, 'cancel_read'):
            self._sl.cancel_read()
