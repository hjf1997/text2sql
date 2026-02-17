"""Setup configuration for text2sql package."""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
if requirements_file.exists():
    with open(requirements_file) as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]
else:
    requirements = []

setup(
    name="text2sql",
    version="1.0.0",
    author="AMEX Data Engineering Team",
    author_email="your-email@example.com",
    description="Production-ready Text-to-SQL agent with Azure OpenAI and BigQuery",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/text2sql",
    packages=find_packages(where=".", include=["src", "src.*"]),
    package_dir={"": "."},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Database",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "text2sql=src.cli:main",  # Can be implemented later
        ],
    },
    include_package_data=True,
    package_data={
        "src.config": ["*.yaml"],
    },
    zip_safe=False,
)
