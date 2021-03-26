import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pySim", 
    version="0.0.1",
    license = "AGPLv3",
    description="Utility for programmable SIM/USIM-Cards",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/osmocom/pysim",
    project_urls={
        "Bug Tracker": "https://github.com/osmocom/pysim/issues",
    },
    packages=setuptools.find_packages(),
    python_requires=">=3.6",
    install_requires=[
          'pyscard', # PcscSimLink
          'pybluez', # BluetoothSapSimLink
          'pytlv',
          'cmd2',
          'pyyaml',
          'pyserial @ git+https://github.com/mahatma1/pyserial.git@f251884cbcfd5c34ace7d31138d755b67c3db1a3#egg=pyserial', # Forked Pyserial with inter_byte_timeout fix
    ],
)