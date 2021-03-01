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
)