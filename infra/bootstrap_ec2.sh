#!/usr/bin/env bash
set -euxo pipefail

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git \
  python3-pip \
  python3-venv

python3 -m venv /opt/income-api-venv
/opt/income-api-venv/bin/pip install --upgrade pip
/opt/income-api-venv/bin/pip install \
  boto3==1.34.131 \
  fastapi==0.111.0 \
  joblib==1.4.2 \
  scikit-learn==1.4.2 \
  uvicorn==0.29.0

install -d -o ubuntu -g ubuntu /home/ubuntu/app /home/ubuntu/models

cat >/etc/systemd/system/income-api.service <<'EOF'
[Unit]
Description=Income Model Inference Server
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/app
Environment="ARTIFACT_BUCKET=income-lab-950037471965-us-east-1"
Environment="AWS_DEFAULT_REGION=us-east-1"
ExecStart=/opt/income-api-venv/bin/python /home/ubuntu/app/src/serve.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable income-api
