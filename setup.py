"""
Setup script for the pymotivaxmc2 package.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="pymotivaxmc2",
    version="0.3.0",
    author="Dima Zavin, Dmitri Romanovskij",
    author_email="dmitri.romanovski@gmail.com",
    description="A Python library for controlling eMotiva A/V receivers, tested with XMC-2",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/droman42/pymotivaxmc2",
    packages=find_packages(exclude=["tests", "*.tests", "*.tests.*", "venv", "env", ".env"]),
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Home Automation",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.7",
    install_requires=[
        "typing-extensions>=3.7.4",
        "setuptools>=65.5.1",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "pytest-asyncio>=0.17.0",
            "black>=21.0",
            "mypy>=0.9",
            "flake8>=3.9",
        ],
    },
    entry_points={
        "console_scripts": [
            "emotiva-cli=pymotivaxmc2.cli:main",
        ],
    },
) 