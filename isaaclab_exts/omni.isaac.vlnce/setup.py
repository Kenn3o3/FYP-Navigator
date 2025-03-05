"""Installation script for the 'omni.isaac.leggedloco' python package."""


from setuptools import setup

# Minimum dependencies required prior to installation
INSTALL_REQUIRES = [
    # generic
    "numpy",
    "scipy>=1.7.1",
    "torch>=2.2.0",
]

# Installation operation
setup(
    name="omni-isaac-vlnce",
    version="0.0.1",
    keywords=["robotics", "navigation"],
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=INSTALL_REQUIRES,
    packages=["omni.isaac.vlnce"],
    classifiers=["Natural Language :: English", "Programming Language :: Python :: 3.10"],
    zip_safe=False,
)

# EOF
