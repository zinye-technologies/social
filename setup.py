from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in social/__init__.py
from social import __version__ as version

setup(
	name="social",
	version=version,
	description="Social Media App",
	author="Developer",
	author_email="developer@example.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)