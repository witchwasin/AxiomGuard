"""
AxiomGuard — Deterministic Neuro-Symbolic Guardrails for Enterprise AI.

This setup.py exists for backward compatibility with older pip versions
and editable installs. The canonical metadata lives in pyproject.toml.
"""

from setuptools import setup, find_packages

setup(
    name="axiomguard",
    version="0.5.0",
    author="Witchwasin K. (Thai Novel)",
    author_email="witchwasin@gmail.com",
    description="Deterministic Neuro-Symbolic Guardrails for Enterprise AI.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/witchwasin/AxiomGuard",
    project_urls={
        "Bug Tracker": "https://github.com/witchwasin/AxiomGuard/issues",
        "Documentation": "https://github.com/witchwasin/AxiomGuard#readme",
        "Source": "https://github.com/witchwasin/AxiomGuard",
        "Changelog": "https://github.com/witchwasin/AxiomGuard/blob/main/CHANGELOG.md",
    },
    license="MIT",
    packages=find_packages(include=["axiomguard", "axiomguard.*"]),
    python_requires=">=3.9",
    install_requires=[
        "z3-solver>=4.12.0",
        "pydantic>=2.0",
        "pyyaml>=6.0",
    ],
    extras_require={
        "anthropic": ["anthropic>=0.39.0"],
        "openai": ["openai>=1.0.0"],
        "chroma": ["chromadb>=0.4.0"],
        "qdrant": ["qdrant-client>=1.7.0"],
        "all": [
            "anthropic>=0.39.0",
            "openai>=1.0.0",
            "chromadb>=0.4.0",
            "qdrant-client>=1.7.0",
        ],
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "ruff>=0.1.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Typing :: Typed",
    ],
    keywords=[
        "ai",
        "hallucination",
        "llm",
        "rag",
        "guardrails",
        "neuro-symbolic",
        "formal-verification",
        "z3",
        "smt-solver",
        "theorem-prover",
        "enterprise-ai",
    ],
)
