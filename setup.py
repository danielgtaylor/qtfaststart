try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import qtfaststart

with open('README.txt') as readme:
    long_description = readme.read()

setup_params = dict(
    name='qtfaststart',
    version=qtfaststart.VERSION,
    description='Quicktime atom positioning in Python for fast streaming.',
    long_description=long_description,
    author='Daniel G. Taylor',
    author_email='dan@programmer-art.org',
    url='https://github.com/gtaylor/qtfaststart',
    license='MIT License',
    platforms=["any"],
    provides=['qtfaststart'],
    packages=[
        'qtfaststart',
    ],
    scripts=['bin/qtfaststart'],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Multimedia :: Video :: Conversion',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)

if __name__ == '__main__':
    setup(**setup_params)
