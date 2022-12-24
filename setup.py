# Always prefer setuptools over distutils
from setuptools import setup, find_packages
from os import path

# io.open is needed for projects that support Python 2.7
# It ensures open() defaults to text mode with universal newlines,
# and accepts an argument to specify the text encoding
# Python 3 only projects can skip this import
from io import open

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

# Arguments marked as "Required" below must be included for upload to PyPI.
# Fields marked as "Optional" may be commented out.

setup(
    name="k2000",
    version="1.0.0",
    description="A library for working with the Kurzweil K2000/K2500/K2600 series of synthesizers.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/psobot/k2000",
    author="Peter Sobot",
    author_email="github@petersobot.com",
    classifiers=[  # Optional
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    keywords="kurzweil midi synthesizer k2000 k2vx k2500 k2600",
    packages=find_packages(exclude=["contrib", "docs", "tests"]),
    install_requires=["tqdm", "Pillow", "python-rtmidi"],
    extras_require={"dev": ["check-manifest"], "test": ["coverage"]},
    entry_points={
        "console_scripts": [
            "k2000=k2000.command_line:main",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/psobot/k2000/issues",
        "Source": "https://github.com/psobot/k2000/",
    },
)
