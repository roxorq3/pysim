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

# class VirtualSimCallback(object):
#    def handle_apdu(self, pdu, expected_len):
#    pass

import logging
import threading
from pySim.exceptions import NotInitializedError
from pySim.transport.serial_base import SerialBase
from pySim.transport.apdu_helper import ApduHelper
from pySim.utils import h2b, b2h


class VirtualSim(threading.Thread):
    # with this atr max avail speed is same as initial speed --> no pps
    ATR_SLOW = h2b(
        "3b 9f 01 80 1f c6 80 31 e0 73 fe 21 1b 66 d0 02 21 ab 11 18 03 15")
    # offer faster baudrate to modem, modem will usually do select fastest rate
    ATR_OFFER_PPS = h2b(
        "3b 9f 96 80 1f c6 80 31 e0 73 fe 21 1b 66 d0 02 21 ab 11 18 03 82")

    def __init__(self, device='/dev/ttyUSB0', clock=3842000, apdu_callback_handler=None, timeout=60):
        super(VirtualSim, self).__init__()
        self.daemon = True
        self._sl = SerialBase(device, clock, timeout)
        # handle_apdu(pdu, len)
        self._handle_apdu_callback = apdu_callback_handler
        self._apdu_helper = ApduHelper()
        self._initialized = False
        self._wxt_timer = None
        self._alive = False

    def __del__(self):
        self.disconnect()

    def disconnect(self):
        if (hasattr(self, "_sl")):
            self._sl.close()

    def send_atr(self, do_pps=True):
        self._sl.reset_input_buffer()
        atr = VirtualSim.ATR_OFFER_PPS if do_pps else VirtualSim.ATR_SLOW

        self._sl.tx_bytes(atr)
        self._sl.atr_recieved(atr)
        if do_pps:
            pps_request = self._sl.rx_bytes(SerialBase.PPS_LEN)
            self._sl.tx_bytes(pps_request)
            self._sl.pps_sent(pps_request)
        self._initialized = True

    def send_wxt(self):
        self._sl.tx_bytes(bytes([SerialBase.WXT_BYTE]))
        logging.info("half waiting time exceeded --> wxt sent")

    def get_wxt_timeout(self):
        return self._sl.get_waiting_time()/2

    def create_wxt_thread(self):
        stop = threading.Event()

        def loop():
            while not stop.wait(self.get_wxt_timeout()):
                self.send_wxt()
        threading.Thread(target=loop, daemon=True).start()
        return stop

    def handle_apdu(self, apdu, expected_len):
        #virtual, needs to be implemented
        raise NotImplementedError()

    def handle_apdu_with_wxt(self, apdu, expected_len):
        stop_wxt_thread = self.create_wxt_thread()
        try:
            logging.info(f"forward apdu[{len(apdu)}]: {b2h(apdu)}")
            response = self.handle_apdu(apdu, expected_len)
            logging.info(f"recieved apdu response: {b2h(response)}")
            return response
        except:
            logging.error("handle_apdu_callback raised exception :X")
            raise
        finally:
            stop_wxt_thread.set()  # disalbe wxt thread by setting event
            return

    def run(self):
        if not self._sl.get_atr():
            raise NotInitializedError(
                "ATR not received yet --> cannot start apdu loop!")
        self._alive = True
        self.run_apdu_loop()
        return

    def stop(self):
        self._alive = False
        if hasattr(self._sl, 'cancel_read'):
            self._sl.cancel_read()
        self.join(timeout=5)

    def run_apdu_loop(self):
        try:
            while self._alive:
                apdu, le = self.rx_apdu()
                response = self.handle_apdu_with_wxt(apdu, le + SerialBase.SW_LEN)
                self._sl.tx_bytes(response)
        # except Exception as e:
        #    logging.info(e)
        finally:
            if self._alive:
                logging.info("leaving apdu loop")
            else:
                logging.info("something went wrong -> leaving apdu loop")
            self._alive = False
            self.disconnect()

    def rx_apdu(self):
        # receive (cla, ins, p1, p2, p3)
        apdu = self._sl.rx_bytes(SerialBase.HEADER_LEN)
        logging.info("header: {b2h(data)}")
        cla, ins, p1, p2, p3 = apdu
        apdu_type = self._apdu_helper.classify_apdu(apdu)
        ins_name = apdu_type['name']
        case = apdu_type['case']
        le = SerialBase.SW_LEN  # per default two SW bytes as expected response

        logging.info(f"{ins_name} -> case {case}")

        if case == 1:  # P3 == 0 -> No Lc/Le
            # self.tx_bytes(bytes([ins])) #actually it still works when sending the procedure byte :O
            return apdu, le
        if case == 2:  # P3 == Le
            self._sl.tx_bytes(bytes([ins]))
            if p3 == 0:
                le += 256
            else:
                le += p3
            return apdu, le
        if (case == 3 or  # P3 = Lc
                case == 4):  # P3 = Lc, Le encoded in SW
            lc = p3
            if lc > 0:
                # send proc byte and recieve rest of command
                self._sl.tx_bytes(bytes([ins]))
                data = self._sl.rx_bytes(lc)
                logging.info(f"data: {b2h(data)}")
                apdu += data
            return apdu, le
        else:
            logging.error(f"cannot determine case for apdu ({b2h(apdu)}) :|")
            return apdu, le
