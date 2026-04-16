FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install base Python & OS dependencies
RUN apt-get update && apt-get install -y \
    python3.10 python3-pip python3.10-venv git curl awscli \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Upgrade pip
RUN python3.10 -m pip install --upgrade pip

# Create requirements mapping
COPY requirements.txt .

# Install Data Science & Scraping Packages
RUN pip3 install -r requirements.txt beautifulsoup4
RUN pip3 install spacy nltk

# Install Playwright Headless Browser
RUN python3.10 -m playwright install chromium
RUN python3.10 -m playwright install-deps chromium
# Download Pre-Configured ML Models directly into image
RUN python3.10 -m spacy download en_core_web_sm
RUN python3.10 -c "import nltk; nltk.download('vader_lexicon', download_dir='/usr/local/share/nltk_data', quiet=True)"

# Default entry
CMD ["/bin/bash"]
