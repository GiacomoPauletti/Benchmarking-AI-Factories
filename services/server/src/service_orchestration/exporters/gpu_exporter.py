import http.server
import socketserver
import subprocess
import sys
import logging
import csv
import io

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("gpu_exporter")

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18001

class GPUExporterHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            try:
                metrics = self.collect_metrics()
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; version=0.0.4')
                self.end_headers()
                self.wfile.write(metrics.encode('utf-8'))
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def collect_metrics(self):
        # Run nvidia-smi to get metrics in CSV format
        # index, uuid, utilization.gpu, memory.used, memory.total, temperature.gpu, power.draw
        cmd = [
            "nvidia-smi", 
            "--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw", 
            "--format=csv,noheader,nounits"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"nvidia-smi failed: {e}")
            return "# HELP aif_gpu_up Status of GPU exporter (1=up, 0=down)\n# TYPE aif_gpu_up gauge\naif_gpu_up 0\n"
        except FileNotFoundError:
             logger.error("nvidia-smi not found")
             return "# HELP aif_gpu_up Status of GPU exporter (1=up, 0=down)\n# TYPE aif_gpu_up gauge\naif_gpu_up 0\n"

        lines = []
        lines.append("# HELP aif_gpu_up Status of GPU exporter (1=up, 0=down)")
        lines.append("# TYPE aif_gpu_up gauge")
        lines.append("aif_gpu_up 1")
        
        lines.append("# HELP aif_gpu_utilization_percent GPU utilization in percent")
        lines.append("# TYPE aif_gpu_utilization_percent gauge")
        
        lines.append("# HELP aif_gpu_memory_used_bytes GPU memory used in bytes")
        lines.append("# TYPE aif_gpu_memory_used_bytes gauge")
        
        lines.append("# HELP aif_gpu_memory_total_bytes Total GPU memory in bytes")
        lines.append("# TYPE aif_gpu_memory_total_bytes gauge")
        
        lines.append("# HELP aif_gpu_temperature_celsius GPU temperature in Celsius")
        lines.append("# TYPE aif_gpu_temperature_celsius gauge")
        
        lines.append("# HELP aif_gpu_power_watts GPU power draw in Watts")
        lines.append("# TYPE aif_gpu_power_watts gauge")

        reader = csv.reader(io.StringIO(output))
        for row in reader:
            if len(row) < 7:
                continue
            
            # Parse values
            try:
                index = row[0].strip()
                uuid = row[1].strip()
                util_gpu = float(row[2].strip())
                mem_used_mb = float(row[3].strip())
                mem_total_mb = float(row[4].strip())
                temp_c = float(row[5].strip())
                power_w = float(row[6].strip())
                
                # Convert MB to Bytes
                mem_used_bytes = mem_used_mb * 1024 * 1024
                mem_total_bytes = mem_total_mb * 1024 * 1024
                
                labels = f'gpu_index="{index}",gpu_uuid="{uuid}"'
                
                lines.append(f'aif_gpu_utilization_percent{{{labels}}} {util_gpu}')
                lines.append(f'aif_gpu_memory_used_bytes{{{labels}}} {mem_used_bytes}')
                lines.append(f'aif_gpu_memory_total_bytes{{{labels}}} {mem_total_bytes}')
                lines.append(f'aif_gpu_temperature_celsius{{{labels}}} {temp_c}')
                lines.append(f'aif_gpu_power_watts{{{labels}}} {power_w}')
                
            except ValueError as e:
                logger.warning(f"Failed to parse row {row}: {e}")
                continue

        return "\n".join(lines) + "\n"

if __name__ == "__main__":
    logger.info(f"Starting GPU exporter on port {PORT}")
    with socketserver.TCPServer(("", PORT), GPUExporterHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()
