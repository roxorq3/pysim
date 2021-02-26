#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" pySim: Transport Link for serial (RS232) based readers included with simcard
"""

#
# Copyright (C) 2018-2021  Gabriel K. Gegenhuber <ggegenhuber@sba-research.org>
# Copyright (C) 2009-2010  Sylvain Munaut <tnt@246tNt.com>
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

import time

from pySim.exceptions import NoCardError, ProtocolError
from pySim.transport import LinkBase
from pySim.transport.serial_base import SerialBase
from pySim.transport.apdu_helper import ApduHelper
from pySim.utils import h2b, b2h


class SerialSimLink(LinkBase):
    def __init__(self, device='/dev/ttyUSB0', clock=3579545, rst='-rts'):
        self._rst_pin = rst
        self._sl = SerialBase(device, clock)
        self._apdu_helper = ApduHelper()

    def __del__(self):
        self.disconnect()

    def wait_for_card(self, timeout=None, newcardonly=False):
        # Direct try
        existing = False

        try:
            self.reset_card()
            if not newcardonly:
                return
            else:
                existing = True
        except NoCardError:
            pass

        # Poll ...
        mt = time.time() + timeout if timeout is not None else None
        pe = 0

        while (mt is None) or (time.time() < mt):
            try:
                time.sleep(0.5)
                self.reset_card()
                if not existing:
                    return
            except NoCardError:
                existing = False
            except ProtocolError:
                if existing:
                    existing = False
                else:
                    # Tolerate a couple of protocol error ... can happen if
                    # we try when the card is 'half' inserted
                    pe += 1
                    if (pe > 2):
                        raise

        # Timed out ...
        raise NoCardError()

    def connect(self, do_pbs=True):
        self.reset_card()
        if do_pbs:
            pbs_request = self.get_pbs_proposal()  # just accept fastest baudrate
            self.tx_bytes(pbs_request)
            pbs_response = self.rx_bytes()
            if pbs_request != pbs_response:  # TX and RX are tied, so we must clear the echo
                raise ProtocolError(
                    f"Bad PBS reponse (Expected: {b2h(pbs_request)}, got {b2h(pbs_response)})")
            logging.info(f"PBS: {b2h(pbs_response)}")

    def get_atr(self):
        return self.sl.get_atr()

    def disconnect(self):
        self._sl.close()

    def reset_card(self):
        rv = self._reset_card()
        if rv == 0:
            raise NoCardError()
        elif rv < 0:
            raise ProtocolError()

    def _reset_card(self):
        atr = None
        rst_meth_map = {
            'rts': self._sl.setRTS,
            'dtr': self._sl.setDTR,
        }
        rst_val_map = {'+': 0, '-': 1}

        try:
            rst_meth = rst_meth_map[self._rst_pin[1:]]
            rst_val = rst_val_map[self._rst_pin[0]]
        except:
            raise ValueError('Invalid reset pin %s' % self._rst_pin)

        rst_meth(rst_val)
        time.sleep(0.1)  # 100 ms
        self._sl.reset_input_buffer()
        rst_meth(rst_val ^ 1)

        b = self._sl.rx_byte()
        if not b:
            return 0
        if ord(b) != 0x3b:
            return -1
        logging.debug("TS: 0x%x Direct convention" % ord(b))

        while ord(b) == 0x3b:
            b = self._sl.rx_byte()

        if not b:
            return -1
        t0 = ord(b)
        logging.debug("T0: 0x%x" % t0)
        atr = [0x3b, ord(b)]

        for i in range(4):
            if t0 & (0x10 << i):
                b = self._sl.rx_byte()
                atr.append(ord(b))
                logging.debug("T%si = %x" % (chr(ord('A')+i), ord(b)))

        for i in range(0, t0 & 0xf):
            b = self._sl.rx_byte()
            atr.append(ord(b))
            logging.debug("Historical = %x" % ord(b))

        while True:
            x = self._sl.rx_byte()
            if not x:
                break
            atr.append(ord(x))
            logging.debug("Extra: %x" % ord(x))

        self.sl.atr_recieved(atr)

        return 1

    """
    def tx_byte(self, b):
        return self._sl.tx_byte(b)

    def tx_bytes(self, buf):
        return self._sl.tx_bytes(buf)

    def rx_byte(self):
        return self._sl.rx_byte()

    def rx_bytes(self, size=SerialBase.BUF_SIZE):
        return self._sl.rx_bytes()
    """

    """
    def rx_card_response(self, size=SerialBase.BUF_SIZE, proc = None, wxt = SerialBase.WXT_BYTE): #wxt can be set to None when not needed
        buf = _sl.rx_bytes(size)
        while len(buf) > 0:
            if bytes[0] == wxt:
                logging.info("Received wxt!")
                buf = bytes[1:]
            elif bytes[0] == proc:
                logging.info("Received proc!")
                buf = bytes[1:]
            else:
                break
        if len(buf) < 1:
            return self._sl.rx_bytes(size)
        return buf
    """

    # wxt can be set to None when not needed
    def rx_card_response(self, size=SerialBase.BUF_SIZE, proc=None, wxt=SerialBase.WXT_BYTE):
        if(size > 1 and any([proc, wxt])):
            while True:
                # recieve first byte and check if it should be discarded, then recieve the rest
                b = self._sl.rx_byte()
                if b == wxt:
                    logging.info("Received wxt!")
                elif b == proc:
                    logging.info("Received proc!")
                else:
                    return [b] + self._sl.rx_bytes(size - 1)
                    break
        else:
            return self._sl.rx_bytes(size)

    def tx_apdu(self, apdu):
        header = apdu[0:5]
        data = apdu[5:]
        self.tx_bytes(header)  # send 5 header bytes (cla, ins, p1, p2, p3)
        print("header: {}".format(header.hex()))
        cla, ins, p1, p2, p3 = header

        apdu_type = self._apdu_helper.classify_apdu(header)
        ins_name = apdu_type['name']
        case = apdu_type['case']
        le = 2  # per default two SW bytes as expected response

        print("{} -> case {}".format(ins_name, case))

        if case == 1:  # P3 == 0 -> No Lc/Le
            return self.rx_card_response(le, ins)
        if case == 2:  # P3 == Le
            if p3 == 0:
                le += 256
            else:
                le += p3
            return self.rx_card_response(le+1, ins)
        if (case == 3 or  # P3 = Lc
                case == 4):  # P3 = Lc, Le encoded in SW
            lc = p3
            proc = self.rx_card_response(1)
            if proc[0] != ins:
                print("proc byte {} expected but {} recieved".format(
                    ins, proc[0]))
            if lc > 0 and len(data):
                # send proc byte and recieve rest of command
                self.tx_bytes(data)
                print("data: {}".format(data.hex()))
            return self.rx_card_response(le, ins)
        else:
            print("unknown apdu case :|")
            return self.rx_card_response(le, ins)

    def send_apdu_raw(self, pdu):
        if isinstance(pdu, str):
            pdu = hex2bin(pdu)

        response = tx_apdu(pdu)
        # Split datafield from SW
        if len(data) < 2:
            return None, None
        sw = data[-2:]
        data = data[0:-2]

        # Return value
        return b2h(data), b2h(sw)

    def send_apdu_raw_deprecated(self, pdu):
        """see LinkBase.send_apdu_raw"""

        if isinstance(pdu, str):
            pdu = hex2bin(pdu)
        data_len = ord(pdu[4])  # P3

        # Send first CLASS,INS,P1,P2,P3
        self._tx_string(pdu[0:5])

        # Wait ack which can be
        #  - INS: Command acked -> go ahead
        #  - 0x60: NULL, just wait some more
        #  - SW1: The card can apparently proceed ...
        while True:
            b = self._sl.rx_byte()
            if b == pdu[1]:
                break
            elif b != '\x60':
                # Ok, it 'could' be SW1
                sw1 = b
                sw2 = self._sl.rx_byte()
                nil = self._sl.rx_byte()
                if (sw2 and not nil):
                    return '', b2h(sw1+sw2)

                raise ProtocolError()

        # Send data (if any)
        if len(pdu) > 5:
            self._tx_string(pdu[5:])

        # Receive data (including SW !)
        #  length = [P3 - tx_data (=len(pdu)-len(hdr)) + 2 (SW1//2) ]
        to_recv = data_len - len(pdu) + 5 + 2

        data = ''
        while (len(data) < to_recv):
            b = self._sl.rx_byte()
            if (to_recv == 2) and (b == '\x60'):  # Ignore NIL if we have no RX data (hack ?)
                continue
            if not b:
                break
            data += b

        # Split datafield from SW
        if len(data) < 2:
            return None, None
        sw = data[-2:]
        data = data[0:-2]

        # Return value
        return b2h(data), b2h(sw)
