from distutils.command.clean import clean
from distutils import log
from setuptools import setup
import os

# Get the long description from the README file
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
      name='viscs',
      version=__import__('viscs').__version__,
      description='File download, upload and preview handler for the VIS document management system web client from PDV GmbH, unofficial Linux implementation.',
      long_description=long_description,
      long_description_content_type='text/markdown',
      install_requires=[i.strip() for i in open('requirements.txt').readlines()],
      license=__import__('viscs').__license__,
      author='Georg Sieber',
      keywords='python3 PDV VIS VIS.Sax WebClient download upload',
      url=__import__('viscs').__website__,
      classifiers=[
            'Development Status :: 5 - Production/Stable',
            'Intended Audience :: End Users/Desktop',
            'Operating System :: MacOS :: MacOS X',
            'Operating System :: Microsoft :: Windows',
            'Operating System :: POSIX :: Linux',
            'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
            'Programming Language :: Python',
            'Programming Language :: Python :: 3',
      ],
      packages=['viscs'],
      #package_data={'viscs': ['lang/*.qm']},
      entry_points={
            'console_scripts': [
                  'viscs = viscs.viscs:main',
            ],
      },
      platforms=['all'],
      #install_requires=[],
      #test_suite='tests',
)
