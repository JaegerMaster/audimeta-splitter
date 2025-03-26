from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="audimeta-splitter",
    version="1.0.6",
    author="JaegerMaster",
    author_email="jaegermaster@example.com",
    description="Split audiobooks using AudiMeta API and ffmpeg",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/JaegerMaster/audimeta-splitter",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Multimedia :: Sound/Audio :: Conversion",
    ],
    python_requires=">=3.6",
    install_requires=[
        "requests>=2.25.0",
        "mutagen>=1.45.0",
        "tabulate>=0.8.0"
    ],
    entry_points={
        'console_scripts': [
            'audimeta_splitter=audimeta_splitter.audio_splitter:main',
        ],
    },
)
