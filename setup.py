#!/usr/bin/env python3

"""
nuqql-matrixd setup file
"""

from setuptools import setup

VERSION = "0.2"
DESCRIPTION = "Matrix client network daemon using the Matrix Python SDK"
with open("README.md", 'r') as f:
    LONG_DESCRIPTION = f.read()
CLASSIFIERS = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
]

setup(
    name="nuqql-matrixd",
    version=VERSION,
    description=DESCRIPTION,
    license="MIT",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    author="hwipl",
    author_email="nuqql-matrixd@hwipl.net",
    url="https://github.com/hwipl/nuqql-matrixd",
    packages=["nuqql_matrixd"],
    entry_points={
        "console_scripts": ["nuqql-matrixd = nuqql_matrixd.matrixd:main"]
    },
    classifiers=CLASSIFIERS,
    python_requires='>=3.6',
    install_requires=["matrix_client"],
)
