import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import datetime
import re

def _is_ascii(s):
    return all(ord(c) < 128 for c in s)

def render_pdf(data, output_path):
    meta = data.get("meta", {})
    nodes = data.get("nodes", {})
    edges = data.get("edges", {})
    
    with PdfPages(output_path) as pdf:
        # Title Page
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
        plt.close()

        # Nodes with Storage or Production Charts
        for nid in sorted(nodes.keys()):
            ndata = nodes[nid]
            storage_chart = ndata.get("chart_storage")
            prod_chart = ndata.get("chart_production")
            
            if not storage_chart and not prod_chart:
                continue
            
            disp_name = ndata.get('display_name', nid)
            # Use ID if display name has non-ASCII (to avoid boxes in PDF)
            title_name = disp_name if _is_ascii(disp_name) else nid
                
            plt.figure(figsize=(10, 6))
            
            if storage_chart:
                times = [p[0] for p in storage_chart]
                levels = [p[1] for p in storage_chart]
                plt.step(times, levels, where='post', color='#06b6d4', linewidth=1.5, label='Inventory')
                plt.fill_between(times, levels, step='post', alpha=0.15, color='#06b6d4')
                plt.title(f"Node: {title_name} (Warehouse Storage)")
                plt.ylabel("Pallets")
            
            elif prod_chart:
                times = [p[0] for p in prod_chart]
                outputs = [p[1] for p in prod_chart]
                # Adjust bar width based on window size
                width = (times[1]-times[0] if len(times)>1 else 1.0) * 0.8
                plt.bar(times, outputs, width=width, color='#22c55e', align='edge', alpha=0.6)
                plt.title(f"Node: {title_name} (Production Rate)")
                plt.ylabel("Units per Window")
                
            plt.xlabel("Time")
            plt.grid(True, linestyle=':', alpha=0.5)
            plt.tight_layout()
            pdf.savefig()
            plt.close()

        # Edges with Traffic Charts
        for eid in sorted(edges.keys()):
            edata = edges[eid]
            traffic_chart = edata.get("chart_traffic")
            
            if not traffic_chart:
                continue
            
            disp_name = edata.get('display_name', eid)
            title_name = disp_name if _is_ascii(disp_name) else eid
                
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
            plt.close()
