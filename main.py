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
    except Exception as e:
        print(f"[DEBUG] Error parsing timestamp: {e}")
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def bytes_to_mb_string(bytes_val):
    """Convert bytes to string MB"""
    try:
        mb_val = round(int(bytes_val) / (1024 * 1024), 2)
        return f"{mb_val}MB"
    except:
        return "0MB"

def send_to_firebase(data):
    """Send parsed data to Firebase"""
    print(f"\n[DEBUG] ========== SENDING REQUEST TO FIREBASE ==========")
    print(f"[DEBUG] URL: {FIREBASE_URL}")
    print(f"[DEBUG] Data being sent: {json.dumps(data, indent=2)}")
    
    try:
        headers = {"Content-Type": "application/json"}
        print(f"[DEBUG] Making POST request...")
        response = requests.post(FIREBASE_URL, headers=headers, json=data)
        print(f"[DEBUG] Response Status Code: {response.status_code}")
        print(f"[DEBUG] Response Body: {response.text}")
        if response.status_code in [200, 201]:
            print(f"[DEBUG] ✓ SUCCESS - Data sent to Firebase!")
        else:
            print(f"[DEBUG] ✗ FAILED - Firebase returned error")
        print(f"[DEBUG] ================================================\n")
    except Exception as e:
        print(f"[DEBUG] ✗ EXCEPTION OCCURRED: {e}")
        print(f"[DEBUG] ================================================\n")

def parse_ftp_logs(line, session_data):
    """Parse FTP log lines and track session data"""
    
    retr_pattern = r'\[I (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] [^\s]+-\[(\w+)\] RETR .+ completed=(\d+) bytes=(\d+) seconds=([\d.]+)'
    close_pattern = r'\[I (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] [^\s]+-\[(\w+)\] FTP session closed'
    
    matched_any = False
    
    retr_match = re.search(retr_pattern, line)
    if retr_match:
        matched_any = True
        print(f"\n[MATCHES] *** FOUND RETR LINE ***")
        print(f"[MATCHES] Raw line: {line.strip()}")
        
        timestamp_str = f"[I {retr_match.group(1)}]"
        username = retr_match.group(2)
        status_raw = retr_match.group(3)   # 0 or 1
        bytes_val = retr_match.group(4)
        seconds = retr_match.group(5)
        
        print(f"[MATCHES] Extracted values:")
        print(f"[MATCHES]   - Timestamp: {timestamp_str} -> {parse_timestamp(timestamp_str)}")
        print(f"[MATCHES]   - Username: {username}")
        print(f"[MATCHES]   - Status (raw): {status_raw}")
        print(f"[MATCHES]   - Bytes: {bytes_val} -> {bytes_to_mb_string(bytes_val)}")
        print(f"[MATCHES]   - Seconds: {seconds}")
        
        session_data[username] = {
            'timestamp': parse_timestamp(timestamp_str),
            'username': username,
            'status': int(status_raw),
            'bytes': int(bytes_val),
            'data': bytes_to_mb_string(bytes_val),  # renamed from dataMB
            'elapsedTime': f"{seconds}s"
        }
        
        # SEND immediately on success
        send_to_firebase(session_data[username])
    
    close_match = re.search(close_pattern, line)
    if close_match:
        matched_any = True
        print(f"\n[MATCHES] *** FOUND SESSION CLOSE LINE ***")
        print(f"[MATCHES] Raw line: {line.strip()}")
        
        username = close_match.group(2)
        print(f"[MATCHES] Username: {username}")
        
        if username in session_data:
            print(f"[MATCHES] Found stored session data for {username}!")
            # Optional: send again on session close if needed
            # send_to_firebase(session_data[username])
            del session_data[username]
        else:
            print(f"[MATCHES] No transfer data found for {username} - skipping Firebase send\n")
    
    if not matched_any:
        print(f"[DOES NOT MATCH] {line.strip()}")

def run_server_with_monitoring():
    """Run the FTP server and monitor its output"""
    print("[DEBUG] Starting FTP server with monitoring...", flush=True)
    print(f"[DEBUG] Logging to Firebase: {FIREBASE_URL}", flush=True)
    print("[DEBUG] " + "-" * 60, flush=True)
    
    session_data = {}
    
    try:
        process = subprocess.Popen(
            ['python3.11', '-u', 'server.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=0
        )
        
        for line in iter(process.stdout.readline, ''):
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                parse_ftp_logs(line, session_data)
        
        process.wait()
        
    except KeyboardInterrupt:
        print("\n\n[DEBUG] Shutting down server...", flush=True)
        process.terminate()
        process.wait()
        sys.exit(0)
    except Exception as e:
        print(f"[DEBUG] Error running server: {e}", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    run_server_with_monitoring()
