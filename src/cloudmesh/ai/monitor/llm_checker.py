import warnings
warnings.filterwarnings("ignore")

import requests
import json
import sys
import subprocess
import re
import os
import time

# ANSI Colors
class Colors:
    HEADER = '\033[95m'
    OK = '\033[92m'
    WARN = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

class LLMChecker:
    def __init__(self, host, port, key_path):
        self.host = host
        self.port = int(port)
        self.key_path = os.path.expanduser(key_path)
        self.api_key = self._load_api_key()
        self.summary_results = []
        self.metrics = {}

    def _load_api_key(self):
        try:
            with open(self.key_path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            self.log(f"API key not loaded from {self.key_path}: {e}", "WARN")
            return None

    def log(self, message, level="INFO"):
        colors = {
            "INFO": "",
            "OK": Colors.OK,
            "WARN": Colors.WARN,
            "FAIL": Colors.FAIL,
            "HEADER": Colors.HEADER
        }
        color = colors.get(level, "")
        print(f"{color}[{level}] {message}{Colors.ENDC}")

    @staticmethod
    def humanize_number(value):
        try:
            num = float(value)
            if num >= 1_000_000:
                return f"{num / 1_000_000:.2f}M"
            if num >= 1_000:
                return f"{num / 1_000:.2f}K"
            return f"{num:.2f}"
        except (ValueError, TypeError):
            return value

    def check_process(self):
        is_localhost = (self.host in ["127.0.0.1", "localhost"])
        self.log(f"Checking for vLLM process on {self.host}...")
        
        cmd = "ps aux | grep vllm | grep -v grep"
        try:
            if is_localhost:
                result = subprocess.check_output(cmd, shell=True, text=True)
            else:
                result = subprocess.check_output(f"ssh -q {self.host} '{cmd}'", shell=True, text=True)
            
            if result:
                lines = result.strip().split('\n')
                self.log("vLLM process found.", "OK")
                
                # Parse details
                details = {}
                flags = {
                    "model": r"--model\s+([^\s]+)",
                    "port": r"--port\s+([^\s]+)",
                }
                for key, pattern in flags.items():
                    match = re.search(pattern, lines[0])
                    if match: details[key] = match.group(1)
                
                self.summary_results.append(("vLLM Process", True, details.get('model', 'Unknown')))
                return True, details
        except subprocess.CalledProcessError:
            pass
        
        self.log(f"No vLLM process found on {self.host}.", "FAIL")
        self.summary_results.append(("vLLM Process", False, "Not found"))
        return False, {}

    def check_gpu_status(self):
        """Enhanced Diagnostic: Check GPU memory via nvidia-smi."""
        if self.host == "localhost" or self.host == "127.0.0.1":
            cmd = "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits"
        else:
            cmd = f"ssh -q {self.host} 'nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits'"
        
        try:
            output = subprocess.check_output(cmd, shell=True, text=True).strip()
            if output:
                # Take first GPU
                used, total = output.split('\n')[0].split(',')
                self.summary_results.append(("GPU Memory", True, f"{used}/{total} MiB"))
                return True
        except Exception:
            pass
        self.summary_results.append(("GPU Memory", False, "Could not fetch"))
        return False

    def check_tunnel(self):
        self.log(f"Checking for local tunnel on port {self.port}...")
        try:
            cmd = f"lsof -i :{self.port} -sTCP:LISTEN -t"
            result = subprocess.check_output(cmd, shell=True, text=True).strip()
            if result:
                pid = result.split('\n')[0]
                proc_name = subprocess.check_output(f"ps -p {pid} -o comm=", shell=True, text=True).strip()
                self.log(f"Local port {self.port} is active ({proc_name})", "OK")
                self.summary_results.append(("Local Tunnel", True, proc_name))
                return True
        except subprocess.CalledProcessError:
            pass
        self.log(f"No local process listening on port {self.port}.", "WARN")
        self.summary_results.append(("Local Tunnel", False, "Not listening"))
        return False

    def probe_server(self):
        base_url = f"http://localhost:{self.port}/v1"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        
        # 1. Model List & Latency
        start = time.time()
        try:
            resp = requests.get(f"{base_url}/models", headers=headers, timeout=5)
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                models = resp.json()
                model_id = models['data'][0]['id'] if 'data' in models and models['data'] else "Unknown"
                self.log(f"Server responding in {latency:.1f}ms. Model: {model_id}", "OK")
                self.summary_results.append(("Server API", True, f"{latency:.1f}ms"))
                return True, model_id
        except Exception as e:
            self.log(f"Connection failed: {e}", "FAIL")
        
        self.summary_results.append(("Server API", False, "Unreachable"))
        return False, None

    def probe_chat(self, model_id):
        base_url = f"http://localhost:{self.port}/v1"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": model_id, 
            "messages": [{"role": "user", "content": "Hi, please respond with a short sentence."}], 
            "max_tokens": 20,
            "stream": True
        }
        
        start_time = time.time()
        first_token_time = None
        token_count = 0
        
        try:
            resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=10, stream=True)
            if resp.status_code != 200:
                self.log(f"Chat probe failed with status {resp.status_code}", "FAIL")
                self.summary_results.append(("Chat Probe", False, f"HTTP {resp.status_code}"))
                return False

            for line in resp.iter_lines():
                if line:
                    line_text = line.decode('utf-8')
                    if line_text.startswith("data: "):
                        data_str = line_text[6:]
                        if data_str == "[DONE]":
                            break
                        
                        # First token received
                        if first_token_time is None:
                            first_token_time = time.time()
                        
                        try:
                            data_json = json.loads(data_str)
                            content = data_json['choices'][0]['delta'].get('content', '')
                            if content:
                                token_count += 1
                        except json.JSONDecodeError:
                            pass

            end_time = time.time()
            
            if first_token_time:
                ttft = (first_token_time - start_time) * 1000
                total_duration = end_time - start_time
                tps = token_count / total_duration if total_duration > 0 else 0
                
                self.log(f"Chat probe successful: TTFT={ttft:.1f}ms, TPS={tps:.2f} tok/s", "OK")
                self.summary_results.append(("Chat TTFT", True, f"{ttft:.1f}ms"))
                self.summary_results.append(("Chat TPS", True, f"{tps:.2f} tok/s"))
                return True
            else:
                self.log("Chat probe failed: No tokens received", "FAIL")
                self.summary_results.append(("Chat Probe", False, "No tokens"))
                return False

        except Exception as e:
            self.log(f"Chat probe failed: {e}", "FAIL")
            self.summary_results.append(("Chat Probe", False, "Error"))
            return False

    def fetch_diagnostics(self):
        base_url = f"http://localhost:{self.port}"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        
        # Health
        try:
            h_resp = requests.get(f"{base_url}/health", headers=headers, timeout=5)
            health = "✅ OK" if h_resp.status_code == 200 else f"❌ {h_resp.status_code}"
            self.summary_results.append(("Service Health", h_resp.status_code == 200, health))
        except:
            self.summary_results.append(("Service Health", False, "Error"))

        # Metrics
        try:
            m_resp = requests.get(f"{base_url}/metrics", headers=headers, timeout=5)
            if m_resp.status_code == 200:
                text = m_resp.text
                metrics_to_find = {
                    "KV Cache %": r"vllm[:_]kv_cache_usage_perc\{.*?\}\s+([\d.e+-]+)",
                    "Waiting Req": r"vllm[:_]num_requests_waiting\{.*?\}\s+([\d.e+-]+)",
                    "Running Req": r"vllm[:_]num_requests_running\{.*?\}\s+([\d.e+-]+)",
                    "Total Success": r"vllm[:_]request_success_total\{.*?finished_reason=\"stop\".*?\}\s+([\d.e+-]+)",
                    "Prompt Tokens": r"vllm[:_]prompt_tokens_total\{.*?\}\s+([\d.e+-]+)",
                    "Gen Tokens": r"vllm[:_]generation_tokens_total\{.*?\}\s+([\d.e+-]+)",
                }
                for label, pattern in metrics_to_find.items():
                    match = re.search(pattern, text)
                    if match:
                        val = match.group(1)
                        self.metrics[label] = val
                        self.summary_results.append((f"Metric: {label}", True, self.humanize_number(val)))
        except:
            pass

    def print_summary(self):
        print("\n" + Colors.BOLD + "="*60)
        print(f"{'LLM CONNECTIVITY SUMMARY':^60}")
        print("="*60 + Colors.ENDC)
        print(f"{'Check':<25} | {'Status':<12} | {'Detail':<20}")
        print("-" * 60)
        for check, status, detail in self.summary_results:
            status_str = f"{Colors.OK}✅ OK{Colors.ENDC}" if status else f"{Colors.FAIL}❌ FAIL{Colors.ENDC}"
            print(f"{check:<25} | {status_str:<22} | {detail:<20}")
        print("="*60 + "\n")

    def to_json(self):
        return json.dumps({
            "host": self.host,
            "port": self.port,
            "results": [{"check": r[0], "status": r[1], "detail": r[2]} for r in self.summary_results],
            "metrics": self.metrics
        }, indent=2)