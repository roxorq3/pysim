# -*- coding: utf-8 -*-

""" pySim: Bluetooth rSAP transport link
"""

#
# Copyright (C) 2021  Gabriel K. Gegenhuber <ggegenhuber@sba-research.org>
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

import struct
import bluetooth

from pySim.exceptions import ReaderError, NoCardError, ProtocolError
from pySim.transport import LinkBase
from pySim.utils import b2h, h2b, rpad


# thx to osmocom/softsim
# SAP table 5.16
SAP_CONNECTION_STATUS = {
    0x00: "OK, Server can fulfill requirements",
    0x01: "Error, Server unable to establish connection",
    0x02: "Error, Server does not support maximum message size",
    0x03: "Error, maximum message size by Client is too small",
    0x04: "OK, ongoing call"
}
# SAP table 5.18
SAP_RESULT_CODE = {
    0x00: "OK, request processed correctly",
    0x01: "Error, no reason defined",
    0x02: "Error, card not accessible",
    0x03: "Error, card (already) powered off",
    0x04: "Error, card removed",
    0x05: "Error, card already powered on",
    0x06: "Error, data not available",
    0x07: "Error, not supported"
}
# SAP table 5.19
SAP_STATUS_CHANGE = {
    0x00: "Unknown Error",
    0x01: "Card reset",
    0x02: "Card not accessible",
    0x03: "Card removed",
    0x04: "Card inserted",
    0x05: "Card recovered"
}

# SAP table 5.15
SAP_PARAMETERS = [
    {
        'name': "MaxMsgSize",
        'length': 2,
        'id': 0x00
    },
    {
        'name': "ConnectionStatus",
        'length': 1,
        'id': 0x01
    },
    {
        'name': "ResultCode",
        'length': 1,
        'id': 0x02
    },
    {
        'name': "DisconnectionType",
        'length': 1,
        'id': 0x03
    },
    {
        'name': "CommandAPDU",
        'length': None,
        'id': 0x04
    },
    {
        'name': "ResponseAPDU",
        'length': None,
        'id': 0x05
    },
    {
        'name': "ATR",
        'length': None,
        'id': 0x06
    },
    {
        'name': "CardReaderdStatus",
        'length': 1,
        'id': 0x07
    },
    {
        'name': "StatusChange",
        'length': 1,
        'id': 0x08
    },
    {
        'name': "TransportProtocol",
        'length': 1,
        'id': 0x09
    },
    {
        'name': "CommandAPDU7816",
        'length': 2,
        'id': 0x10
    }
]


# SAP table 5.1
SAP_MESSAGES = [
    {
      'name': 'CONNECT_REQ',
      'client_to_server': True,
      'id': 0x00,
      'parameters': [(0x00, True)]
    },
    {
      'name': 'CONNECT_RESP',
      'client_to_server': False,
      'id': 0x01,
      'parameters': [(0x01, True), (0x00, False)]
    },
    {
      'name': 'DISCONNECT_REQ',
      'client_to_server': True,
      'id': 0x02,
      'parameters': []
    },
    {
      'name': 'DISCONNECT_RESP',
      'client_to_server': False,
      'id': 0x03,
      'parameters': []
    },
    {
      'name': 'DISCONNECT_IND',
      'client_to_server': False,
      'id': 0x04,
      'parameters': [(0x03, True)]
    },
    {
      'name': 'TRANSFER_APDU_REQ',
      'client_to_server': True,
      'id': 0x05,
      'parameters': [(0x04, False), (0x10, False)]
    },
    {
      'name': 'TRANSFER_APDU_RESP',
      'client_to_server': False,
      'id': 0x06,
      'parameters': [(0x02, True), (0x05, False)]
    },
    {
      'name': 'TRANSFER_ATR_REQ',
      'client_to_server': True,
      'id': 0x07,
      'parameters': []
    },
    {
      'name': 'TRANSFER_ATR_RESP',
      'client_to_server': False,
      'id': 0x08,
      'parameters': [(0x02, True), (0x06, False)]
    },
    {
      'name': 'POWER_SIM_OFF_REQ',
      'client_to_server': True,
      'id': 0x09,
      'parameters': []
    },
    {
      'name': 'POWER_SIM_OFF_RESP',
      'client_to_server': False,
      'id': 0x0A,
      'parameters': [(0x02, True)]
    },
    {
      'name': 'POWER_SIM_ON_REQ',
      'client_to_server': True,
      'id': 0x0B,
      'parameters': []
    },
    {
      'name': 'POWER_SIM_ON_RESP',
      'client_to_server': False,
      'id': 0x0C,
      'parameters': [(0x02, True)]
    },
    {
      'name': 'RESET_SIM_REQ',
      'client_to_server': True,
      'id': 0x0D,
      'parameters': []
    },
    {
      'name': 'RESET_SIM_RESP',
      'client_to_server': False,
      'id': 0x0E,
      'parameters': [(0x02, True)]
    },
    {
      'name': 'TRANSFER_CARD_READER_STATUS_REQ',
      'client_to_server': True,
      'id': 0x0F,
      'parameters': []
    },
    {
      'name': 'TRANSFER_CARD_READER_STATUS_RESP',
      'client_to_server': False,
      'id': 0x10,
      'parameters': [(0x02, True), (0x07, False)]
    },
    {
      'name': 'STATUS_IND',
      'client_to_server': False,
      'id': 0x11,
      'parameters': [(0x08, True)]
    },

    {
      'name': 'ERROR_RESP',
      'client_to_server': False,
      'id': 0x12,
      'parameters': []
    },
    {
      'name': 'SET_TRANSPORT_PROTOCOL_REQ',
      'client_to_server': True,
      'id': 0x13,
      'parameters': [(0x09, True)]
    },
    {
      'name': 'SET_TRANSPORT_PROTOCOL_RESP',
      'client_to_server': False,
      'id': 0x14,
      'parameters': [(0x02, True)]
    },

]


class BluetoothSapSimLink(LinkBase):
    # UUID for SIM Access Service
    UUID_SIM_ACCESS = '0000112d-0000-1000-8000-00805f9b34fb'
    SAP_MAX_MSG_SIZE = 0xffff

    def __init__(self, bt_mac_addr):
        self._bt_mac_addr = bt_mac_addr
        # at first try to find the bluetooth device
        if not bluetooth.find_service(address=bt_mac_addr):
            raise ReaderError(f"Cannot find bluetooth device [{bt_mac_addr}]")
        # then check for rSAP support
        self._sim_service = next(iter(bluetooth.find_service(
            uuid=BluetoothSapSimLink.UUID_SIM_ACCESS, address=bt_mac_addr)), None)
        if not self._sim_service:
            raise ReaderError(
                f"Bluetooth device [{bt_mac_addr}] does not support SIM Access service")

    def __del__(self):
        #TODO: do something here
        pass

    # def wait_for_card(self, timeout=None, newcardonly=False):
        """cr = CardRequest(readers=[self._reader], timeout=timeout, newcardonly=newcardonly)
        try:
            cr.waitforcard()
        except CardRequestTimeoutException:
            raise NoCardError()
        self.connect()"""

    def connect(self):
        try:
            self._sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self._sock.connect((self._sim_service['host'], self._sim_service['port']))
            connect_req = self.craft_sap_message("CONNECT_REQ", [("MaxMsgSize", 0xffff)])
            
            print(f"send : {b2h(connect_req)}")
            self._sock.send(connect_req)
            connect_resp = self._sock.recv(1024)
            print(f"recv : {self.parse_sap_message(connect_resp)} ({b2h(connect_resp)})")

            
            connect_resp = self._sock.recv(1024)
            print(f"recv : {self.parse_sap_message(connect_resp)} ({b2h(connect_resp)})")
        except:
            raise ReaderError("Cannot connect to SIM Access service")

    # def get_atr(self):
    #	return bytes(self._con.getATR())

    def disconnect(self):
        self._sock.close()

    # def reset_card(self):
    #	self.disconnect()
    #	self.connect()
    #	return 1

    # def send_apdu_raw(self, pdu):
    #	"""see LinkBase.send_apdu_raw"""
    #
    #	apdu = h2i(pdu)
    #
    # 	data, sw1, sw2 = self._con.transmit(apdu)
    #
    #	sw = [sw1, sw2]
    #
    #	# Return value
    #	return i2h(data), i2h(sw)
    
    def craft_sap_message(self, msg_name, param_list=[]):
        msg_info = next((x for x in SAP_MESSAGES if x.get('name') == msg_name), None)
        if not msg_info:
            raise ProtocolError(f"Unknown SAP message name ({msg_name})")
        
        msg_id = msg_info.get('id')
        msg_params = msg_info.get('parameters')
        #msg_direction = msg_info.get('client_to_server')

        param_cnt = len(param_list)

        msg_bytes = struct.pack(
            '!BBH',
            msg_id,
            param_cnt,
            0
        )

        allowed_params = (x[0] for x in msg_params)
        mandatory_params = (x[0] for x in msg_params if x[1] == True)
        
        collected_param_ids = []

        for p in param_list:
            param_name = p[0]
            param_value = p[1]

            param_id = next((x.get('id') for x in SAP_PARAMETERS if x.get('name') == param_name), None)
            if param_id is None:
                raise ProtocolError(f"Unknown SAP param name ({param_name})")
            if param_id not in allowed_params:
                raise ProtocolError(f"Parameter {param_name} not allowed in message {msg_name}")

            
            collected_param_ids.append(param_id)
            msg_bytes += self.craft_sap_parameter(param_name, param_value)

        if not set(collected_param_ids).issubset(mandatory_params):
            raise ProtocolError(f"Missing mandatory parameter for message {msg_name} (mandatory: {*mandatory_params,}, present: {*collected_param_ids,})")

        return msg_bytes


    def calc_padding_len(self, length, blocksize = 4):
      extra = length % blocksize
      if extra > 0:
            return blocksize-extra
      return 0

    def pad_bytes(self, b, blocksize = 4):
        padding_len = self.calc_padding_len(len(b), blocksize)
        return b + bytearray(padding_len)

    def craft_sap_parameter(self, param_name, param_value):
        param_info = next((x for x in SAP_PARAMETERS if x.get('name') == param_name), None)
        param_id = param_info.get('id')
        param_len = param_info.get('length')

        if isinstance(param_value, str):
            param_value = h2b(param_value)

        if isinstance(param_value, int):
            param_value = (param_value).to_bytes(param_len, byteorder='big')    #TODO: when param len is not set we have a problem :X

        if param_len is None:
            param_len = len(param_value)    #just assume param length from bytearray
        elif param_len != len(param_value):
            raise ProtocolError(f"Invalid param length (epected {param_len} but got {len(param_value)} bytes)")

        param_bytes = struct.pack(
            f'!BBH{param_len}s',
            param_id,
            0, #reserved
            param_len,
            param_value
        )
        param_bytes = self.pad_bytes(param_bytes)
        return param_bytes

    def parse_sap_message(self, msg_bytes):
      header_struct = struct.Struct('!BBH')
      msg_id, param_cnt, reserved = header_struct.unpack_from(msg_bytes)
      msg_bytes = msg_bytes[header_struct.size:]

      msg_info = next((x for x in SAP_MESSAGES if x.get('id') == msg_id), None)
      
      msg_name = msg_info.get('name')
      msg_params = msg_info.get('parameters')
      #msg_direction = msg_info.get('client_to_server')

      # TODO: check if params allowed etc
      #allowed_params = (x[0] for x in msg_params)
      #mandatory_params = (x[0] for x in msg_params if x[1] == True)

      param_list=[]

      for x in range(param_cnt):
        param_name, param_value, total_len = self.parse_sap_parameter(msg_bytes)
        param_list.append((param_name, param_value))
        msg_bytes = msg_bytes[total_len:]

      return msg_name, param_list
    
    def parse_sap_parameter(self, param_bytes):
      header_struct = struct.Struct('!BBH')
      total_len = header_struct.size
      param_id, reserved, param_len = header_struct.unpack_from(param_bytes)
      padding_len = self.calc_padding_len(param_len)
      paramval_struct = struct.Struct(f'!{param_len}s{padding_len}s')
      param_value, padding = paramval_struct.unpack_from(param_bytes[total_len:])
      total_len += paramval_struct.size

      param_info = next((x for x in SAP_PARAMETERS if x.get('id') == param_id), None)
      param_name = param_info.get('name') # TODO: check if param found, length plausible, ...
      #param_len = param_info.get('length')
      return param_name, param_value, total_len

      


if __name__ == "__main__":
    # execute only if run as a script
    link = BluetoothSapSimLink("80:5A:04:0E:90:F6") # nexus 5
    #link = BluetoothSapSimLink("40:A1:08:91:E2:6A")
    link.connect()