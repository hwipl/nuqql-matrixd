#!/usr/bin/env python3

"""
nuqql-matrixd setup file
"""

import os
import re
import codecs

from setuptools import setup

# setup parameters
DESCRIPTION = "Matrix client network daemon using the Matrix Python SDK"
with open("README.md", 'r', encoding='UTF-8') as f:
    LONG_DESCRIPTION = f.read()
CLASSIFIERS = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
]


# setup helpers
def read(*parts):
    """
    Read encoded file
    """

    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, *parts), 'r') as enc_file:
        return enc_file.read()


def find_version(*file_paths):
    """
    Find version in encoded file
    """

    version_file = read(*file_paths)
    version_pattern = r"^VERSION = ['\"]([^'\"]*)['\"]"
    version_match = re.search(version_pattern, version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


# run setup
setup(
    name="nuqql-matrixd",
    version=find_version("nuqql_matrixd", "server.py"),
    description=DESCRIPTION,
    license="MIT",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    author="hwipl",
    author_email="nuqql-matrixd@hwipl.net",
    url="https://github.com/hwipl/nuqql-matrixd",
    packages=["nuqql_matrixd"],
    entry_points={
        "console_scripts": ["nuqql-matrixd = nuqql_matrixd.main:main"]
    },
    classifiers=CLASSIFIERS,
    python_requires='>=3.7',
    install_requires=["nuqql-based~=0.3.0", "matrix_client~=0.4.0"],
)
