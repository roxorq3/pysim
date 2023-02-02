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
#    def handle_apdu(self, pdu):
#    pass

import logging
import threading
from pySim.exceptions import NotInitializedError, ProtocolError
from pySim.transport.serial_base import SerialBase
from pySim.transport.apdu_helper import ApduHelper
from pySim.utils import h2b, b2h

logger = logging.getLogger(__name__)

class VirtualSim(threading.Thread):
	# with this atr max avail speed is same as initial speed --> no pps
	ATR_SLOW = h2b(
		"3b 9f 01 80 1f c6 80 31 e0 73 fe 21 1b 66 d0 02 21 ab 11 18 03 15")
	# offer faster baudrate to modem, modem will usually do select fastest rate
	ATR_OFFER_PPS = h2b(
		"3b 9f 96 80 1f c6 80 31 e0 73 fe 21 1b 66 d0 02 21 ab 11 18 03 82")

	def __init__(self, device='/dev/ttyUSB0', clock=3842000, timeout=600, do_pps=True):
		threading.Thread.__init__(self) #super(VirtualSim, self).__init__()
		self.daemon = True
		self._sl = SerialBase(device, clock, timeout)
		self._do_pps = do_pps
		self._apdu_helper = ApduHelper()
		self._initialized = False
		self._wxt_timer = None
		self._alive = False
		self._restart = True	#try to restart connection (wait for reset) in case of error 
		self._get_response_cache = None

	def __del__(self):
		self.stop()
		self.disconnect()

	def _rx_apdu(self):
		# receive (cla, ins, p1, p2, p3)
		apdu = self._sl.rx_bytes(SerialBase.HEADER_LEN)
		logger.debug(f"header: {b2h(apdu)}")
		cla, ins, p1, p2, p3 = apdu
		apdu_type = self._apdu_helper.classify_apdu(apdu)
		ins_name = apdu_type['name']
		case = apdu_type['case']
		le = SerialBase.SW_LEN  # per default two SW bytes as expected response

		logger.info(f"{ins_name} -> case {case}")

		if case == 1:  # P3 == 0 -> No Lc/Le
			return apdu, le
		if case == 2:  # P3 == Le
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
				logger.debug(f"data: {b2h(data)}")
				apdu += data
			# if case == 4:  case 4 in sim is not allowed --> request seperately
			#    le += SerialBase.MAX_LENGTH
			return apdu, le
		else:
			logger.error(f"cannot determine case for apdu ({b2h(apdu)}) :|")
			return apdu, SerialBase.MAX_LENGTH

	def _send_wxt(self):
		try:
			self._sl.tx_bytes(bytes([SerialBase.WXT_BYTE]))
			logger.info("half waiting time exceeded --> wxt sent")
		except ProtocolError as e:	# not sure what to do here...send wxt again, just wait and hope modem recieved the right byte? start over?
			logger.error("dang, wxt was prolly not sent...")

	def _get_wxt_timeout(self):
		return self._sl.get_waiting_time()/2

	def _create_wxt_thread(self):
		stop = threading.Event()

		def loop():
			while not stop.wait(self._get_wxt_timeout()):
				self._send_wxt()
		threading.Thread(target=loop, daemon=True).start()
		return stop

	def _handle_apdu_with_wxt(self, apdu, expected_len):
		stop_wxt_thread = self._create_wxt_thread()
		try:
			logger.info(f"forward apdu[{len(apdu)}]: {b2h(apdu)}")
			response = self.handle_apdu_with_get_response_fix(apdu, expected_len)
			# modem expects additional instruction byte in response for apdu case 2
			if len(response) > 2:
				response = bytes([apdu[1]]) + response
			logger.info(f"recieved apdu response: {b2h(response)}")
			return response
		except:
			logger.error("handle_apdu_callback raised exception :X")
			raise
		finally:
			stop_wxt_thread.set()  # disalbe wxt thread by setting event

	def _run_apdu_loop(self):
		try:
			self._alive = True
			while self._alive:
				apdu, le = self._rx_apdu()
				response = self._handle_apdu_with_wxt(apdu, le)
				self._sl.tx_bytes(response)
		except Exception as e:
			if not self._alive:
				logger.info("thread stop requested, leaving apdu loop")
				self._restart = False
			else:
				logger.error("exc_info", exc_info=True)
				logger.info("something went wrong -> leaving apdu loop")
		finally:
			self._alive = False

	def run(self):
		while(self._restart):
			self.wait_for_reset()
			self.send_atr(self._do_pps)
			self._run_apdu_loop()
			self._do_pps = False #when the sim gets reset continue at slow rate without pps
		return

	def stop(self):
		self._alive = False
		if hasattr(self._sl, 'cancel_read'):
			self._sl.cancel_read()
		self.join(timeout=5)

	def disconnect(self):
		if (hasattr(self, "_sl")):
			self._sl.close()

	def send_atr(self, do_pps=True):
		self._sl.reset_card()
		self._sl.reset_input_buffer()
		atr = VirtualSim.ATR_OFFER_PPS if do_pps else VirtualSim.ATR_SLOW

		self._sl.tx_bytes(atr)
		self._sl.atr_recieved(atr)
		if do_pps:
			pps_request = self._sl.rx_bytes(SerialBase.PPS_LEN)
			self._sl.tx_bytes(pps_request)
			self._sl.pps_sent(pps_request)
		self._initialized = True

	def handle_apdu_with_get_response_fix(self, apdu, expected_len):
		"""
		In the T = 0 protocol, it is not possible to send a block of data to the smart card and receive
		a block of data from the smart cardwithin a single command–response cycle. 5 This protocol
		thus does not support case 4 commands, although they are frequently used. It is thus necessary
		to use a work-around for the T = 0 protocol. This operates in a simple manner. The case 4
		command is ﬁrst sent to the card, and if it is successful, a special return code is sent to the
		terminal to advise the terminal that the command has generated data that are waiting to be
		retrieved. The terminal then sends a GET RESPONSE command to the smart card and receives
		the data in the response. This completes the command–response cycle for the ﬁrst command.
		As long as no command other than GET RESPONSE is sent to the card, the response data can
		be requested multiple times.
		"""
		if self._get_response_cache is not None:
			if apdu[1] == 0xC0: #get response command
				logger.debug(f"return cached response")
				return self._get_response_cache
		self._get_response_cache = None
		response = self.handle_apdu(apdu)
		response_len = len(response)

		if response_len == expected_len: #everything perfect
			return response
		elif response_len < SerialBase.SW_LEN:
			logger.error(f"response too short: {b2h(response)}")
			return response
		else: #response_len != expected_len -> either bigger or smaller than expected
			self._get_response_cache = response
			ret_sw = bytearray(2)
			if response_len > expected_len:
				ret_sw[0] = 0x61
				ret_sw[1] = len(response) - SerialBase.SW_LEN
				logger.debug(f"case 4 --> response bigger than expected --> cache response and send sw with response length {ret_sw} instead")
			else: # response < expected
				ret_sw[0] = 0x6c
				ret_sw[1] = response_len - 2
				logger.debug(f"case 4 --> respons smaller than expected --> signal modem correct size (TODO: response is cached, so the answer to the repeated request could be returned)")
			return ret_sw

	def handle_apdu(self, apdu):
		# virtual, needs to be implemented
		raise NotImplementedError()

	def wait_for_reset(self):
		# virtual, needs to be implemented
		raise NotImplementedError()

