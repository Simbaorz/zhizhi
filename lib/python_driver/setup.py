# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name='PyMySQL',
    version='1.0.3',
    description = "Pure Python Goldendb Driver",
    author=[],
    packages=find_packages(),
    readme = "README.md",
    classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.6",
    "Programming Language :: Python :: 3.7",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: Implementation :: CPython",
    "Programming Language :: Python :: Implementation :: PyPy",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Topic :: Database",
    ],
    extras_require={
        'interactive':["cryptography","PyNaCl>=1.4.0"]
    }
)