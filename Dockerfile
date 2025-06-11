FROM python:3.9.23-slim

RUN apt-get update && apt-get install -y git wget

# we have to figure out our architecture, as GH will not provide
# a docker image: https://github.com/cli/cli/issues/2027
RUN export ARCH=$(uname -m); if [ $ARCH = "aarch64" ]; then ARCH="arm64"; fi; wget https://github.com/cli/cli/releases/download/v2.74.1/gh_2.74.1_linux_${ARCH}.deb
RUN dpkg -i gh_2.74.1_linux_*.deb && rm gh_2.74.1_linux_*.deb

RUN pip install requests

WORKDIR /code
CMD ["python3", "main.py"]
