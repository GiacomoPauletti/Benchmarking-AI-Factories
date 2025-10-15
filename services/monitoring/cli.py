# services/monitoring/cli.py
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Optional

from .main import MonitoringService

svc = MonitoringService()

def cmd_session_create(args):
    cfg = {
        "run_id": args.run_id,
        "scrape_interval": args.scrape_interval,
        "retention_hours": args.retention,
        "prometheus_port": args.port,
        "prom_host": args.prom_host,
    }
    out = svc.create_session(cfg)
    print(out)

def cmd_start(args):
    out = svc.start(args.session, partition=args.partition, time_limit=args.time_limit)
    print(out)

def cmd_status(args):
    out = svc.status(args.session)
    print(out)

def cmd_collect(args):
    window = (args.from_iso, args.to_iso)
    out = svc.collect(args.session, window, args.out, run_id=args.run_id)
    print(out)

def cmd_stop(args):
    ok = svc.stop(args.session)
    print({"stopped": ok})

def cmd_delete(args):
    ok = svc.delete(args.session)
    print({"deleted": ok})

def cmd_client_connect(args):
    req = {
        "session_id": args.session,
        "client_id": args.client_id,
        "node": args.node,
        "exporters": {
            "node": args.node_exporter,
            "dcgm": args.dcgm_exporter,
        },
        "preferences": {
            "enable_node": args.enable_node,
            "enable_dcgm": args.enable_dcgm,
        }
    }
    out = svc.register_client(req)
    print(out)

def cmd_service_register(args):
    svc_req = {
        "session_id": args.session,
        "client_id": args.client_id,
        "name": args.name,
        "endpoint": args.endpoint,
        "labels": {},
    }
    out = svc.register_service(svc_req)
    print(out)

def build_parser():
    p = argparse.ArgumentParser("monitoring")
    sp = p.add_subparsers(dest="cmd")

    # session create
    s_create = sp.add_parser("session-create")
    s_create.add_argument("--run-id", default=None)
    s_create.add_argument("--scrape-interval", default="1s")
    s_create.add_argument("--retention", type=int, default=6)
    s_create.add_argument("--port", type=int, default=9090)
    s_create.add_argument("--prom-host", default="localhost",
                          help="Host where Prometheus will be reachable (e.g., login node or fixed host)")
    s_create.set_defaults(func=cmd_session_create)

    # start
    s_start = sp.add_parser("start")
    s_start.add_argument("--session", required=True)
    s_start.add_argument("--partition", default=None, help="Slurm partition (e.g., login)")
    s_start.add_argument("--time-limit", default="04:00:00")
    s_start.set_defaults(func=cmd_start)

    # status
    s_status = sp.add_parser("status")
    s_status.add_argument("--session", required=True)
    s_status.set_defaults(func=cmd_status)

    # collect
    s_collect = sp.add_parser("collect")
    s_collect.add_argument("--session", required=True)
    s_collect.add_argument("--from-iso", required=True)
    s_collect.add_argument("--to-iso", required=True)
    s_collect.add_argument("--out", default="results/metrics")
    s_collect.add_argument("--run-id", default="run")
    s_collect.set_defaults(func=cmd_collect)

    # stop
    s_stop = sp.add_parser("stop")
    s_stop.add_argument("--session", required=True)
    s_stop.set_defaults(func=cmd_stop)

    # delete
    s_del = sp.add_parser("delete")
    s_del.add_argument("--session", required=True)
    s_del.set_defaults(func=cmd_delete)

    # client connect
    s_cc = sp.add_parser("client-connect")
    s_cc.add_argument("--session", required=True)
    s_cc.add_argument("--client-id", required=True)
    s_cc.add_argument("--node", required=True)
    s_cc.add_argument("--node-exporter", default=None)
    s_cc.add_argument("--dcgm-exporter", default=None)
    s_cc.add_argument("--enable-node", action="store_true", default=True)
    s_cc.add_argument("--enable-dcgm", action="store_true", default=True)
    s_cc.set_defaults(func=cmd_client_connect)

    # service register
    s_sr = sp.add_parser("service-register")
    s_sr.add_argument("--session", required=True)
    s_sr.add_argument("--client-id", required=True)
    s_sr.add_argument("--name", required=True)
    s_sr.add_argument("--endpoint", required=True, help="HTTP URI to /metrics as seen by Prometheus")
    s_sr.set_defaults(func=cmd_service_register)

    return p

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
