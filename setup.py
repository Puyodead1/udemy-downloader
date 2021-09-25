from setuptools import setup, Command, find_packages

exec(compile(open('udemy_downloader/version.py').read(), 'udemy_downloader/version.py', 'exec'))

packages = find_packages()

setup(
    name="udemy-downloader",
    version="1.2.2",
    author="Puyodead1",
    author_email="puyodead@protonmail.com",
    description="Utility script to download DRM encrypted lectures from Udemy",
    url="https://github.com/Puyodead1/udemy-downloader",
    project_urls={
        "Bug Tracker": "https://github.com/Puyodead1/udemy-downloader/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Natural Language :: English",
        "Topic :: Multimedia",
        "Topic :: Utilities"
    ],
    install_requires=["mpegdash", "sanitize_filename", "tqdm", "requests", "python-dotenv", "protobuf", "webvtt-py", "pysrt", "m3u8", "colorama", "yt-dlp", "bitstring", "unidecode", "six"],
    packages=packages,
    python_requires=">=3.6",
    entry_points={
        'console_scripts': ["udemy-downloader = udemy_downloader:UdemyDownloader"]
    }
)