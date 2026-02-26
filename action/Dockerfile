# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12
FROM public.ecr.aws/lambda/python:${PYTHON_VERSION}

# Optional system packages (glob trick: file[t] matches file if exists, no-op otherwise)
COPY system-requirements.tx[t] /tmp/
RUN if [ -f /tmp/system-requirements.txt ]; then \
      dnf install -y $(cat /tmp/system-requirements.txt) && dnf clean all; \
    fi

# Optional system config script
COPY system-config.s[h] /tmp/
RUN if [ -f /tmp/system-config.sh ]; then \
      chmod +x /tmp/system-config.sh && /tmp/system-config.sh; \
    fi

# Install Python dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN --mount=type=secret,id=github_token \
    if [ -f /run/secrets/github_token ]; then \
      export GIT_TOKEN=$(cat /run/secrets/github_token) && \
      git config --global url."https://${GIT_TOKEN}@github.com/".insteadOf "https://github.com/" ; \
    fi && \
    pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy entire source directory (user's directory = their container)
COPY . ${LAMBDA_TASK_ROOT}/

CMD ["main.handler"]
