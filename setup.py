# Always prefer setuptools over distutils
from setuptools import setup, find_packages
from os import path
import k2000

# io.open is needed for projects that support Python 2.7
# It ensures open() defaults to text mode with universal newlines,
# and accepts an argument to specify the text encoding
# Python 3 only projects can skip this import
from io import open

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()


def find_meta(meta):
    attr = getattr(k2000, "__{meta}__".format(meta=meta), None)
    if not attr:
        raise RuntimeError("Unable to find __{meta}__ string.".format(meta=meta))
    return attr


setup(
    name="k2000",
    version=find_meta("version"),
    description=find_meta("description"),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/psobot/k2000",
    author=find_meta("author"),
    author_email=find_meta("email"),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    keywords="kurzweil midi synthesizer k2000 k2vx k2500 k2600 sysex",
    packages=find_packages(exclude=["contrib", "docs", "tests"]),
    install_requires=["Pillow", "python-rtmidi", "numpy"],
    extras_require={"dev": ["check-manifest"], "test": ["coverage"]},
    entry_points={
        # "console_scripts": [
        #     "k2000=k2000.command_line:main",
        # ],
    },
    project_urls={
        "Bug Reports": find_meta("new_issue_url"),
        "Source": find_meta("url"),
    },
)
