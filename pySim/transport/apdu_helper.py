import json
from importlib.resources import open_binary


# based on c sourcecode from osmocom: https://github.com/osmocom/libosmocore/blob/master/src/sim/class_tables.c
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

class ApduHelper(object):
	@ staticmethod
	def load_json(filename):
		with open_binary('pySim.transport.instructions', filename) as json_file:
			data = json.load(json_file)
			# convert hex keys from string to number:
			for key, value in list(data.items()):
				data[int(key, 16)] = value
				del data[key]
			return data

	iso7816_ins = load_json.__func__('iso7816_ins.json')
	gsm1111_ins = load_json.__func__('gsm1111_ins.json')
	uicc_ins_046 = load_json.__func__('uicc_ins_046.json')
	uicc_ins_8ce = load_json.__func__('uicc_ins_8ce.json')
	uicc_ins_80 = load_json.__func__('uicc_ins_80.json')
	usim_ins_case = load_json.__func__('usim_ins_case.json')

	osim_iso7816_cic_profile = {
		'name': 'ISO 7816-4',
		'description': 'ISO 7816-4',
		'cic_instructions': [
			{
				'cla': 0x00,
				'cla_mask': 0xF0,
				'instructions': iso7816_ins,
			},
			{
				'cla': 0x80,  # 0x80/0x90
				'cla_mask': 0xE0,
				'instructions': iso7816_ins,
			},
			{
				'cla': 0xB0,
				'cla_mask': 0xF0,
				'instructions': iso7816_ins,
			},
			{
				'cla': 0xC0,
				'cla_mask': 0xF0,
				'instructions': iso7816_ins,
			}
		]
	}

	osim_gsm1111_cic_profile = {
		'name': 'GSM SIM',
		'description': 'GSM/3GPP TS 11.11',
		'cic_instructions': [
			{
				'cla': 0xA0,
				'cla_mask': 0xFF,
				'instructions': gsm1111_ins,
			},
		]
	}

	@ staticmethod
	def uicc046_cla_ins_helper(header):
		ins = header[1]
		p1 = header[2]
		p2 = header[3]

		if ins == 0x73:  # MANAGE SECURE CHANNEL
			if p1 == 0x00:  # Retrieve UICC Endpoints
				return 2
			elif (p1 & 0x07 == 1 or  # Establish SA - Master SA
					p1 & 0x07 == 2 or  # Establish SA - Conn. SA
					p1 & 0x07 == 3):  # Start secure channel SA
				p2_cmd = p2 >> 5
				if (p2 == 0x80 or p2_cmd == 0):  # command data
					return 3
				elif (p2_cmd == 5 or p2_cmd == 1):  # response data
					return 2
			elif p1 & 0x07 == 4:  # Terminate secure chan SA
				return 3
		elif ins == 0x75:  # TRANSACT DATA
			if p1 & 0x04:
				return 3
			else:
				return 2
		return 0  # unknown case :X

	osim_uicc_cic_profile = {
		'name': 'UICC',
		'description': 'TS 102 221 / 3GPP TS 31.102',
		'cic_instructions': [
			{
				'cla': 0x80,
				'cla_mask': 0xFF,
				'instructions': uicc_ins_80,
			},
			{
				'cla': 0x00,
				'cla_mask': 0xF0,
				'instructions': uicc_ins_046,
				'helper': uicc046_cla_ins_helper.__func__
			},
			{
				'cla': 0x40,
				'cla_mask': 0xF0,
				'instructions': uicc_ins_046,
				'helper': uicc046_cla_ins_helper.__func__
			},
			{
				'cla': 0x60,
				'cla_mask': 0xF0,
				'instructions': uicc_ins_046,
				'helper': uicc046_cla_ins_helper.__func__
			},
			{
				'cla': 0x80,
				'cla_mask': 0xF0,
				'instructions': uicc_ins_8ce
			},
			{
				'cla': 0xC0,
				'cla_mask': 0xF0,
				'instructions': uicc_ins_8ce
			},
			{
				'cla': 0xE0,
				'cla_mask': 0xF0,
				'instructions': uicc_ins_8ce
			},
		]
	}

	osim_uicc_sim_cic_profile = {
		'name': 'UICC+SIM',
		'description': 'TS 102 221 / 3GPP TS 31.102 + GSM TS 11.11',
		'cic_instructions': osim_gsm1111_cic_profile['cic_instructions'] + osim_uicc_cic_profile['cic_instructions']
	}

	avail_profiles = [osim_iso7816_cic_profile, osim_gsm1111_cic_profile,
					  osim_uicc_cic_profile, osim_uicc_sim_cic_profile]

	def __init__(self, profile_name='UICC+SIM'):
		self.profile = next(
			(profile for profile in ApduHelper.avail_profiles if profile['name'] == profile_name), None)

	def classify_apdu(self, header):  # returns ins_name + case
		default_rc = {'name': 'UNKNOWN', 'case': 0}
		cla = header[0]
		ins = header[1]
		for ins_case in self.profile['cic_instructions']:
			if cla & ins_case['cla_mask'] == ins_case['cla']:
				rc = ins_case['instructions'].get(ins, default_rc)
				if rc['case'] == 5:
					rc['case'] = ins_case['helper'](header)
				if rc['case'] >= 1 and rc['case'] <= 4:
					return rc
		return default_rc
