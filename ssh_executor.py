import paramiko
from rich import print
import os

class SSHExecutor:
    def __init__(self, host, username, password=None, key_filename=None, backup_username=None):
        self.host = host
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self.backup_username = backup_username
        self.client = None

    def connect(self):
        try:
            print("[yellow]Connecting to server...[/yellow]")

            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                self.client.connect(
                    hostname=self.host,
                    username=self.username,
                    password=self.password,
                    timeout=10
                )
            except paramiko.ssh_exception.AuthenticationException:
                if self.key_filename and self.backup_username:
                    print("[yellow]Password authentication failed. Falling back to public key...[/yellow]")
                    self.client.connect(
                        hostname=self.host,
                        username=self.backup_username,
                        key_filename=self.key_filename,
                        timeout=10
                    )
                else:
                    raise

            print("[green]Connected successfully![/green]")

        except Exception as e:
            print(f"[red]Connection failed: {e}[/red]")
            self.client = None
            raise

    def run_command(self, command):
        if not self.client:
            raise Exception("SSH not connected")

        print(f"[blue]Running:[/blue] {command}")

        # Use get_pty=True so sudo reads from the terminal device (/dev/tty)
        # instead of standard input, preserving pipelines.
        stdin, stdout, stderr = self.client.exec_command(command, get_pty=True)
        
        if self.password:
            try:
                # Feed the password to the PTY for sudo to consume
                stdin.write(self.password + "\n")
                stdin.flush()
            except OSError:
                # Channel might already be closed if command finished instantly
                pass

        exit_code = stdout.channel.recv_exit_status()

        # When get_pty=True is used, stderr is usually combined with stdout.
        output = stdout.read().decode()
        error = stderr.read().decode()

        # Clean up sudo password prompt from output if present
        if self.password:
            # Common sudo prompts
            output = output.replace(f"[sudo] password for {self.username}: ", "")
            output = output.replace("[sudo] password for ", "")
            
            # The password itself might be echoed back by the PTY
            output = output.replace(self.password + "\r\n", "")

        return {
            "output": output.strip(),
            "error": error.strip(),
            "exit_code": exit_code,
        }

    def close(self):
        if self.client:
            self.client.close()
            print("[yellow]Connection closed[/yellow]")