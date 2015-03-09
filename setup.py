import os
from distutils.core import setup

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
CHANGES = open(os.path.join(here, 'CHANGES.rst')).read()
LICENSE = open(os.path.join(here, 'LICENSE')).read()

setup(
    name='saferedisqueue',
    version='4.0b0',
    description='A small wrapper around Redis that provides access to a FIFO queue.',
    long_description=README + '\n\n' + CHANGES,
    license=LICENSE,
    author="Fabian Neumann, ferret go GmbH",
    author_email="neumann@ferret-go.com",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Topic :: Internet",
    ],
    keywords='Redis, key-value store, queue, queueing, Storm',
    url='https://github.com/hellp/saferedisqueue',
    py_modules=['saferedisqueue'],
    install_requires=[
        'redis >= 2.7.6, < 2.11',
    ],
    zip_safe=False,
)
