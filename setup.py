from distutils.core import setup

# Keeping it quite minimal here...
setup(
    name='saferedisqueue',
    version='0.2.1',
    description='A small wrapper around Redis that provides access to a FIFO queue.',
    author="Ferret Go GmbH, Fabian Neumann",
    author_email="neumann@ferret-go.com",
    py_modules=['saferedisqueue'],
    install_requires=[
        'redis < 2.5',
    ],
)
