import setuptools

with open('README.md', 'r', encoding='utf-8') as fh:
    long_description = fh.read()

setuptools.setup(
    name='pySim',
    version='1.0',
    packages=['pySim'],
    url='https://osmocom.org/projects/pysim/wiki',
    license='GPLv2',
    author_email='simtrace@lists.osmocom.org',
    description='Tools related to SIM/USIM/ISIM cards',
    long_description=long_description,
    long_description_content_type='text/markdown',
    python_requires='>=3.6',
    install_requires=[
          'pyscard', # PcscSimLink
          'pybluez', # BluetoothSapSimLink
          'pytlv',
          'cmd2',
          'pyyaml',
          'jsonpath-ng',
          'construct',
          'pyserial @ git+https://github.com/mahatma1/pyserial.git@f251884cbcfd5c34ace7d31138d755b67c3db1a3#egg=pyserial', # Forked Pyserial with inter_byte_timeout fix
    ],
    scripts=[
        'pySim-prog.py',
        'pySim-read.py',
        'pySim-shell.py'
    ]
)