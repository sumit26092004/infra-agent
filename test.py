from ssh_executor import SSHExecutor

import os
ssh = SSHExecutor(
    host="34.244.170.74",
    username=os.getenv("SSH_USERNAME", "your_ec2_user"),
    password=os.getenv("SSH_PASSWORD", "your_ec2_password"),
)

ssh.connect()

if not ssh.client:
    raise SystemExit("SSH connection failed")

# Install nginx (Ubuntu/Debian)
install_result = ssh.run_command(
    "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && "
    "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx"
)
print("=== Install stdout ===")
print(install_result["output"])
print("=== Install stderr ===")
print(install_result["error"])

if install_result["exit_code"] != 0:
    print("Install failed!")
    ssh.close()
    raise SystemExit(1)

# Enable and start nginx
start_result = ssh.run_command("sudo systemctl enable --now nginx")
print("=== Start stdout ===")
print(start_result["output"])
print("=== Start stderr ===")
print(start_result["error"])

if start_result["exit_code"] != 0:
    print("Failed to start nginx!")
    ssh.close()
    raise SystemExit(1)

# Check nginx status
status_result = ssh.run_command("sudo systemctl status nginx --no-pager")
print("=== Status stdout ===")
print(status_result["output"])
print("=== Status stderr ===")
print(status_result["error"])

# Quick active check
active_result = ssh.run_command("systemctl is-active nginx")
print("=== Nginx active? ===")
print(active_result["output"].strip())

ssh.close()
