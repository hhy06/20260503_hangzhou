import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import datetime
import re

def _is_ascii(s):
    return all(ord(c) < 128 for c in s)

class PDFTextWriter:
    """Helper to write paginated text to a PdfPages object using Matplotlib."""
    def __init__(self, pdf, on_save_page=None):
        self.pdf = pdf
        self.on_save_page = on_save_page
        self.fig = None
        self.ax = None
        self.y = 0
        self.page_count = 0

    def _start_page(self, title):
        if self.fig:
            self.pdf.savefig(self.fig)
            if self.on_save_page:
                self.on_save_page()
            plt.close(self.fig)
        
        self.fig = plt.figure(figsize=(8.5, 11))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_axis_off()
        self.page_count += 1
        
        display_title = title
        if self.page_count > 1:
            display_title += " (cont.)"
        
        self.y = 0.95
        self.ax.text(0.05, self.y, display_title, fontsize=12, weight='bold', 
                     verticalalignment='top', family='sans-serif')
        self.y -= 0.04

    def add_line(self, text, section_title, fontsize=7, color='black', weight='normal'):
        if not self.fig or self.y < 0.05:
            self._start_page(section_title)
        
        # Simple wrapping for long lines
        max_chars = 110
        lines = [text[i:i+max_chars] for i in range(0, len(text), max_chars)]
        
        for line in lines:
            if self.y < 0.05:
                self._start_page(section_title)
            
            self.ax.text(0.05, self.y, line, fontsize=fontsize, color=color, 
                         weight=weight, family='monospace', verticalalignment='top')
            self.y -= 0.016

    def finish(self):
        if self.fig:
            self.pdf.savefig(self.fig)
            if self.on_save_page:
                self.on_save_page()
            plt.close(self.fig)
            self.fig = None

def render_pdf(data, output_path):
    meta = data.get("meta", {})
    nodes = data.get("nodes", {})
    edges = data.get("edges", {})
    orders = data.get("orders", {})

    total_pages = [0]
    def on_save_page():
        total_pages[0] += 1
        print(f"\r  Generating page {total_pages[0]}...", end="", flush=True)
    
    with PdfPages(output_path) as pdf:
        # 1. Title Page
        plt.figure(figsize=(8.5, 11))
        plt.clf()
        plt.text(0.5, 0.9, "SETA Static Report", fontsize=24, ha='center', weight='bold')
        plt.text(0.5, 0.85, f"Scenario: {meta.get('scenario', 'Unknown')}", fontsize=16, ha='center')
        
        info_text = [
            f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Simulation Duration: {meta.get('sim_duration', 0)}",
            f"Nodes: {meta.get('num_nodes', 0)}",
            f"Edges: {meta.get('num_edges', 0)}",
            f"Total Orders: {meta.get('order_count', 0)}",
            f"Total Events: {meta.get('event_count', 0)}",
        ]
        plt.text(0.1, 0.7, "\n".join(info_text), fontsize=12, family='monospace', verticalalignment='top')
        plt.axis('off')
        pdf.savefig()
        on_save_page()
        plt.close()

        # 2. Process Nodes
        for nid in sorted(nodes.keys()):
            ndata = nodes[nid]
            disp_name = ndata.get('display_name', nid)
            title_name = disp_name if _is_ascii(disp_name) else nid
            
            # --- Chart Page ---
            storage_chart = ndata.get("chart_storage")
            prod_chart = ndata.get("chart_production")
            
            if storage_chart or prod_chart:
                plt.figure(figsize=(10, 6))
                if storage_chart:
                    times = [p[0] for p in storage_chart]
                    levels = [p[1] for p in storage_chart]
                    plt.step(times, levels, where='post', color='#06b6d4', linewidth=1.5)
                    plt.fill_between(times, levels, step='post', alpha=0.15, color='#06b6d4')
                    plt.title(f"Node: {title_name} (Warehouse Storage)")
                    plt.ylabel("Pallets")
                elif prod_chart:
                    times = [p[0] for p in prod_chart]
                    outputs = [p[1] for p in prod_chart]
                    width = (times[1]-times[0] if len(times)>1 else 1.0) * 0.8
                    plt.bar(times, outputs, width=width, color='#22c55e', align='edge', alpha=0.6)
                    plt.title(f"Node: {title_name} (Production Rate)")
                    plt.ylabel("Units")
                plt.xlabel("Time")
                plt.grid(True, linestyle=':', alpha=0.5)
                plt.tight_layout()
                pdf.savefig()
                on_save_page()
                plt.close()

            # --- Details & Events Pages ---
            writer = PDFTextWriter(pdf, on_save_page=on_save_page)
            section_title = f"Node Details: {title_name}"
            
            # Metadata
            writer.add_line(f"ID: {nid}", section_title)
            writer.add_line(f"Type: {ndata.get('type', 'unknown')}", section_title)
            
            # Initial Inventory
            inv = ndata.get("init_inventory", {})
            if inv:
                writer.add_line("", section_title)
                writer.add_line("INITIAL INVENTORY:", section_title, weight='bold')
                for sku, qty in sorted(inv.items()):
                    writer.add_line(f"  {sku}: {qty}", section_title)

            # Jobs
            job_ids = ndata.get("jobs", [])
            if job_ids:
                writer.add_line("", section_title)
                writer.add_line("JOBS:", section_title, weight='bold')
                for oid in job_ids:
                    order = orders.get(oid)
                    if order:
                        summary = order.get("display_summary", f"#{oid} {order.get('sku')} x{order.get('quantity')}")
                        # Filter non-ascii from summary for safety
                        clean_summary = "".join([c if ord(c) < 128 else "?" for c in summary])
                        writer.add_line(f"  {clean_summary}", section_title)

            # Events
            events = ndata.get("events", [])
            if events:
                writer.add_line("", section_title)
                writer.add_line("EVENTS:", section_title, weight='bold')
                for ev in events:
                    t = ev.get("time", 0.0)
                    et = ev.get("end_time")
                    time_str = f"t={t}" if et is None else f"t={t}->{et}"
                    disp = ev.get("display", ev.get("type", "unknown"))
                    # Filter non-ascii
                    clean_disp = "".join([c if ord(c) < 128 else "?" for c in disp])
                    writer.add_line(f"  [{time_str}] {clean_disp}", section_title)
            
            writer.finish()

        # 3. Process Edges
        for eid in sorted(edges.keys()):
            edata = edges[eid]
            disp_name = edata.get('display_name', eid)
            title_name = disp_name if _is_ascii(disp_name) else eid
            
            # --- Chart Page ---
            traffic_chart = edata.get("chart_traffic")
            if traffic_chart:
                plt.figure(figsize=(10, 6))
                times = [p[0] for p in traffic_chart]
                vols = [p[1] for p in traffic_chart]
                width = (times[1]-times[0] if len(times)>1 else 1.0) * 0.8
                plt.bar(times, vols, width=width, color='#a855f7', align='edge', alpha=0.6)
                plt.title(f"Edge: {title_name} (Traffic Rate)")
                plt.xlabel("Time")
                plt.ylabel("Transport Starts")
                plt.grid(True, linestyle=':', alpha=0.5)
                plt.tight_layout()
                pdf.savefig()
                on_save_page()
                plt.close()

            # --- Details & Events Pages ---
            writer = PDFTextWriter(pdf, on_save_page=on_save_page)
            section_title = f"Edge Details: {title_name}"
            
            writer.add_line(f"ID: {eid}", section_title)
            writer.add_line(f"From: {edata.get('from')} -> To: {edata.get('to')}", section_title)

            # Jobs
            job_ids = edata.get("jobs", [])
            if job_ids:
                writer.add_line("", section_title)
                writer.add_line("JOBS:", section_title, weight='bold')
                for oid in job_ids:
                    order = orders.get(oid)
                    if order:
                        summary = order.get("display_summary", f"#{oid} {order.get('sku')} x{order.get('quantity')}")
                        clean_summary = "".join([c if ord(c) < 128 else "?" for c in summary])
                        writer.add_line(f"  {clean_summary}", section_title)

            # Events
            events = edata.get("events", [])
            if events:
                writer.add_line("", section_title)
                writer.add_line("EVENTS:", section_title, weight='bold')
                for ev in events:
                    t = ev.get("time", 0.0)
                    et = ev.get("end_time")
                    time_str = f"t={t}" if et is None else f"t={t}->{et}"
                    disp = ev.get("display", ev.get("type", "unknown"))
                    clean_disp = "".join([c if ord(c) < 128 else "?" for c in disp])
                    writer.add_line(f"  [{time_str}] {clean_disp}", section_title)
            
            writer.finish()
    print() # New line after the progress output
