#!/usr/bin/env python3.11
import subprocess
import re
import requests
import json
from datetime import datetime
import sys

# Firebase configuration
FIREBASE_URL = "https://test-c7bf3-default-rtdb.firebaseio.com/record.json"

def parse_timestamp(timestamp_str):
    """Convert log timestamp to ISO 8601 format"""
    try:
        dt = datetime.strptime(timestamp_str, "[I %Y-%m-%d %H:%M:%S]")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def bytes_to_mb_string(bytes_val):
    """Convert bytes to string MB"""
    try:
        mb_val = round(int(bytes_val) / (1024 * 1024), 2)
        return f"{mb_val}MB"
    except Exception:
        return "0MB"

def send_to_firebase(data):
    """Send parsed data to Firebase"""
    try:
        headers = {"Content-Type": "application/json"}
        requests.post(FIREBASE_URL, headers=headers, json=data)
    except Exception:
        pass

def parse_ftp_logs(line, session_data):
    """Parse FTP log lines and track session data"""
    
    retr_pattern = (
        r'\[I (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] '
        r'[^\s]+-\[(\w+)\] RETR .+ completed=(\d+) bytes=(\d+) seconds=([\d.]+)'
    )
    close_pattern = (
        r'\[I (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] '
        r'[^\s]+-\[(\w+)\] FTP session closed'
    )
    
    retr_match = re.search(retr_pattern, line)
    if retr_match:
        timestamp_str = f"[I {retr_match.group(1)}]"
        username = retr_match.group(2)
        status_raw = retr_match.group(3)
        bytes_val = retr_match.group(4)
        seconds = retr_match.group(5)
        
        session_data[username] = {
            "timestamp": parse_timestamp(timestamp_str),
            "username": username,
            "status": int(status_raw),
            "bytes": int(bytes_val),
            "data": bytes_to_mb_string(bytes_val),
            "elapsedTime": f"{seconds}s"
        }
        
        send_to_firebase(session_data[username])
        return
    
    close_match = re.search(close_pattern, line)
    if close_match:
        username = close_match.group(2)
        if username in session_data:
            del session_data[username]

def run_server_with_monitoring():
    """Run the FTP server and monitor its output"""
    
    session_data = {}
    
    try:
        process = subprocess.Popen(
            ["python3.11", "-u", "server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=0
        )
        
        for line in iter(process.stdout.readline, ""):
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                parse_ftp_logs(line, session_data)
        
        process.wait()
        
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        sys.exit(0)
    except Exception:
        sys.exit(1)

if __name__ == "__main__":
    run_server_with_monitoring()
