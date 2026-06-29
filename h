[33mcommit 902e303cce65a438f000eb5685d783f4e0718a8c[m[33m ([m[1;36mHEAD[m[33m -> [m[1;32mpsp[m[33m)[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Mon Jun 29 10:44:16 2026 +0800

    initiate psp scenario - modified data, aiming for better production schedule planning.

[33mcommit cae9d9be40a1941dd92c4e17aa24437ce0a4d56f[m[33m ([m[1;31morigin/psp[m[33m)[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Mon Jun 29 09:12:26 2026 +0800

    new psp branch, desperately focusing on production
     schedule plans.

[33mcommit 2eb7402ebffa20b2fc44e90e9b1755f899c0d988[m[33m ([m[1;32mfirst_delivery[m[33m)[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Fri Jun 26 19:42:28 2026 +0800

    its a mess now

[33mcommit 3f62deb375d4cf575305b79a121d439f13581c5f[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Fri Jun 26 18:28:12 2026 +0800

    use new excess_management style; modify sku-bomspeed data

[33mcommit 868b08517a5baaef0e4ee09d26262d4427c34e1b[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Wed Jun 24 19:16:57 2026 +0800

    flatten some boms;

[33mcommit 4d486e335e4ee231e89bece102da5d1e913f09b8[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Wed Jun 24 17:18:29 2026 +0800

    new branch; focus on srw_real_weightedSafestock scenario for a first delivery.

[33mcommit fcf0af94284e4409b7d4e765247a604e34cf9187[m[33m ([m[1;31morigin/first_delivery[m[33m, [m[1;31morigin/core_restart[m[33m, [m[1;32mcore_restart[m[33m)[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Mon Jun 22 09:19:28 2026 +0800

    modified report related code.

[33mcommit 8658f35a4959e14959710bc8e629ec99b7725290[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Thu Jun 18 17:30:28 2026 +0800

    modified stock gen logic.

[33mcommit dec2b82cbc4bdcef793d129c3597d9a2e449cb31[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Thu Jun 18 11:45:43 2026 +0800

    a not successful rw_hangzhou1, r for real hangzhou sku/lines/bom.

[33mcommit ee14f1fa3b82a2df5caab1002e6f38ceec10d890[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Thu Jun 18 08:57:39 2026 +0800

    add rw_hangzhou1 and new batch of xlsx files

[33mcommit cd829368f2dac5610b694c065c80f052a2ce9792[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Mon Jun 8 12:05:49 2026 +0800

    modified veg/other wip flow.

[33mcommit 2a8a4896b3164e365ed8a3433dc1f4489dbd7b9a[m
Merge: 3fa7f9f 78419a2
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Fri Jun 5 16:36:29 2026 +0800

    Merge branch 'core_restart' of github.com:hhy06/20260503_hangzhou into core_restart
    
    I did some tests tweaking in krank_win10 and that was pushed; here i modified veg output. I could use rebase as well, but chose merge.

[33mcommit 3fa7f9fed1c505723b30cb3f4a273babb443be1a[m
Author: Harry Huang (Krankenstein) <haoyanghuang@qq.com>
Date:   Fri Jun 5 16:36:01 2026 +0800

    Fix a veg output bug. Before veg produce N, and main_1 and main_2 all demand N, making main_2 startve. Now veg split it in half. Still cause some problems with downstream.

[33mcommit 78419a23c35755520491587143b3d98388ec0fcc[m
Author: Harry Huang (krank_win10) <haoyanghuang@qq.com>
Date:   Fri Jun 5 16:14:15 2026 +0800

    tweak tests according to vulture suggestions.

[33mcommit f6fe4018aa1ac1df9186d71740b5b873eebd0ce6[m
Author: Harry Huang (krank_win10) <haoyanghuang@qq.com>
Date:   Fri Jun 5 14:57:27 2026 +0800

    fix tests due to weigh_ss_man change and log being moved from man to node/edge.

[33mcommit 88b91052be715636f20a4b953d64398aa32e9d3b[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Fri Jun 5 14:20:55 2026 +0800

    remove global shift data, use node-wise shift length/start_time. Extensive change on weight_safe_stock_man.

[33mcommit 663ff6fad103fc2060a5d3571a225ea9ac18e756[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Fri Jun 5 13:00:55 2026 +0800

    fix demand.xlsx to make time increasing. add warning in xlsx_loader.

[33mcommit 998c4fad2c797666e1649b2db3f0397e2b95a775[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Fri Jun 5 12:50:34 2026 +0800

    remove (mistakenly) hardcoded demand data from demand.py

[33mcommit f75187827f7e9955694c00631fda228dcf0439c2[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Fri Jun 5 11:13:41 2026 +0800

    1. Management log removed (4 files)
    - static_order.py, safe_stock_management.py, trace_management.py, weigh_safe_stock_management.py
    - Removed all self.log.append(...) from _execute_decision and self.log: list[dict] = [] from __init__
    2. ProductionNode.add_production_order() — now logs production_job_added with subject: self.node_name
    3. WarehouseNode — fixed capacity_warning to use self.node_name instead of self.display_name; added subject to debited, received, capacity_warning
    4. Edge — added subject: self.edge_name to transport_order_added, transport_order_skipped, transport_started, transport_completed
    5. output.py
    - No _type on any record
    - init_state → {"type": "set_init", "subject": name, ...}
    - Collects node/edge logs as-is (no modification)
    - Removed management log collection entirely
    6. jsonl_count.py — reads subject with fallback to node; output CSV renamed to subject_type_counts.csv
    Every record in sim.jsonl now has subject = the responsible node/edge ID, with no display-name leakage.

[33mcommit 232b6ee1da234a45b2b24cff6b2ba98a53cb0175[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Fri Jun 5 10:32:01 2026 +0800

    jsonl_count accepts file path; add it to gow.

[33mcommit 064ce3827fcbcd9927fcefa0b749ac756f509adc[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Fri Jun 5 10:25:56 2026 +0800

    modify events in sim.jsonl so production orders have nodes or edges.

[33mcommit de78af8758d3a9c61e57dd0ed6bdbd1211649b02[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Fri Jun 5 09:00:34 2026 +0800

    Modify simulation event, add stock after each mvoement/change.

[33mcommit 431cf36ead4e3156b6211790d847884ffcccfed5[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri Jun 5 00:09:15 2026 +0800

    add sseta, pdf, progress, diagram, details.

[33mcommit 78b3ead1850adb104d0fcd323851fc0945c52bc5[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Thu Jun 4 18:36:23 2026 +0800

    add sseta, a pdf report generator.

[33mcommit 9e69bf202e7a743e630c4d8eed98328e6d98aa39[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Thu Jun 4 18:06:09 2026 +0800

    fix seta warehouse diagram using raw qty; now should be in pallets.

[33mcommit 8216267af4f584330f9a8f71b2b7331395b3454a[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Thu Jun 4 17:58:33 2026 +0800

    fix upstrea-prod_node-downstream display in mermaid diagram.

[33mcommit 50bb9fb901e6848bbff565b2d4289ec61ab9b1da[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Thu Jun 4 17:28:45 2026 +0800

      Key Improvements
    
      1. Data Processing Optimization (processor.py)
       - Memory Efficiency: Changed sim.jsonl loading to be iterative (line-by-line), preventing OOM errors on large trace files.
       - Speed: Optimized event grouping and chart computation. Previously, the processor performed O(N_{nodes} × Nₑᵥₑₙₜₛ) iterations; it now groups
         events by node once (O(Nₑᵥₑₙₜₛ)), drastically speeding up the "Processing" phase.
       - Chart Downsampling: Storage charts, which previously recorded every single pallet change, are now downsampled to a maximum of 1,000 points. This
         maintains visual fidelity while reducing JSON size by up to 99% for high-frequency nodes.
       - Compact Dicts: Merged event dictionaries now omit keys with None values, further shrinking the embedded JSON.
    
      2. Report Rendering Optimization (renderer.py)
       - Streaming JSON: Replaced json.dumps() with json.dump(), streaming data directly to the file. This avoids allocating massive strings in memory
         (e.g., for a 1GB report), which was a primary bottleneck.
       - Frontend Logic Offloading: Ported the event display string generation from Python to JavaScript (buildEventDisplay). By generating these strings
         on-the-fly in the browser, I eliminated thousands of redundant "display" strings from the JSON, saving hundreds of megabytes in large reports.
       - Shared Object Handling: Optimized the field-stripping process to handle shared event objects efficiently, avoiding redundant work and ensuring
         data integrity.
    
      Results
      In a test with a 180MB trace file (~745k events), the optimized generator produced a 220MB self-contained report in approximately 50 seconds.

[33mcommit 4f030e0bd8aeaf74dc06f6b16fae41ce1f9313d6[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Thu Jun 4 16:13:04 2026 +0800

    removed float=999 as default expect_time for static orders.

[33mcommit 3089e63c5b431951bcaaedcb83076d0872821b59[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Thu Jun 4 11:03:42 2026 +0800

    mod source/sink related transport to 24pallet/5min to simulate vehicle. fix seta config loading for sku

[33mcommit 36e845138d7fc9bf3b2774073cb514f209e3a3d4[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Thu Jun 4 10:10:46 2026 +0800

    Renamed: pallets_for_quantity(sku, qty) ->      rounded_up_full_pallets_qty(sku, qty)
    quantity_for_pallets(sku, pallets) ->   quantity_of_full_pallets(sku, pallets)
    And some related bugs. But gow and go1t run until seta throws a bug concerning powder1 not in sku_registry

[33mcommit 9ee7108adadba8db4dc2830f4cedc858252c0e66[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Wed Jun 3 21:27:08 2026 +0800

    furthur remove conversion_factor residue

[33mcommit 1d561acad0c1ff8797e054c7ed2cd18cee22504b[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Wed Jun 3 20:48:27 2026 +0800

    removed conversion_factors etc and use sku.pallet_num(qty) instead

[33mcommit b562073de43d123750364aca618cc84edbdbd0b8[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Wed Jun 3 17:47:21 2026 +0800

    modified lineside node tracking method, not using name string; added 55 new tests on management

[33mcommit c5f42e6a94ed0c21fe84ae78c91da34b2b3f46fb[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Wed Jun 3 16:11:49 2026 +0800

    :
    base.py: Moved nodes, edges, _edge_map, _production_nodes, _lineside_suppliers init and find_edge() into the base __init__. Replaced the stub gather_info() with the full snapshot logic (the same 8 lines that were duplicated 3×).
    Removed from 4 subclasses (safe_stock, trace, weigh_safe_stock, static_order):
    self.nodes = dict(nodes) / self.edges = list(edges) — now in base
    _edge_map construction loop — now in base
    _production_nodes detection loop — now in base
    _lineside_suppliers construction loop — now in base
    find_edge() override — now in base (_edge_map dict lookup)
    gather_info() override — now in base (identical 8-line snapshot)
    Unused imports (WarehouseNode, NodeRole) removed

[33mcommit edb94e9736711373aa656925c7efb229cbcda6a8[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Wed Jun 3 11:36:34 2026 +0800

    removed obsolete snapshots and verbose line-by-line process log output from main.(jsonl output untouched.)

[33mcommit a381fca61d63c5956e582f28b6ee4f3569d9ffa6[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Wed Jun 3 09:22:54 2026 +0800

    add clear_run script to purge run_* folders of all scenarios.

[33mcommit 630237d3d835bf8202fb31f5190f8608a1763e01[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Wed Jun 3 09:13:09 2026 +0800

    output wall clock time after simulation run

[33mcommit fd45704d877cde7a67cae4e143fedd7894003bc2[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Wed Jun 3 00:45:05 2026 +0800

    add percentage in text report

[33mcommit 5164c9019a0f5470e634a09c086d31d98b864465[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Wed Jun 3 00:43:11 2026 +0800

    text report add start/total comparison, in #orders and #qty, for edge/prod.

[33mcommit 70f24349a622a11a8bb52ca1f4a005442ed312b8[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Wed Jun 3 00:31:36 2026 +0800

    add report text.

[33mcommit 40db1b4a1c5d72dcdabf28dc36c0c184ed987506[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue Jun 2 18:32:39 2026 +0800

    modify output file encoding to display unicode correctly

[33mcommit 8c8a2021e661281fa917214fde6293c83ff9d6c6[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue Jun 2 18:22:12 2026 +0800

    add report functionality after sim.

[33mcommit 967b978501f73839720ce8826b4c357072350740[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue Jun 2 18:09:48 2026 +0800

    fix a silent return when debit whole is not successful, for an edge executing a transport order.

[33mcommit e565286c2a45ed46a8504be00792a3fc8f5dd369[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue Jun 2 17:53:23 2026 +0800

    tweak go scripts.

[33mcommit 9dfe84ec5454ac916b2fc9aedc082a3c91f12b6c[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue Jun 2 17:37:52 2026 +0800

    fix edge name display: use str(edge) instead of edge.name (Component.name is a method, not property)

[33mcommit eae359291f5bce57bc744fd1acb440ebfb4e117f[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue Jun 2 17:26:26 2026 +0800

    add demand fulfillment report after simulation
    
    Aggregate demand orders by SKU and compare with sink received.
    Print ordered vs received quantities with pass/fail per SKU.

[33mcommit bbf1e6f7fe804eb06a9eddcc66242dddcc96f523[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue Jun 2 17:17:58 2026 +0800

    ignore run output directories

[33mcommit cc4ad74436d6807c267f38bc99011909ddfc09a3[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue Jun 2 17:17:53 2026 +0800

    remove accidental run output

[33mcommit ed05c18727dd248a6cdf1f68f0a8c518a44d1a3b[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue Jun 2 17:17:49 2026 +0800

    convert hardcoded data to xlsx, unify SKU model across scenarios
    
    - Add safe_stock.xlsx and init_stock.xlsx to data/ (canonical business data)
    - Add src/_xlsx_loaders.py with per-type loading functions (load_skus_and_bom, load_demand, load_safe_stock, load_init_stock)
    - Convert t_hangzhou1, ss_hangzhou0b, w_hangzhou1 to SKU object model (from dict[str,str])
    - Derive SAUCE_INGREDIENTS/POWDER_INGREDIENTS/VEG_INGREDIENTS from SKU.bom
    - Remove hardcoded speed from plant_topology.py BOM entries (use sku.bom_speed)
    - Add xlsx loading with fallback to all demand/safe_stock/init_stock modules
    - Update test to accept speed from either BOM entry or SKU registry

[33mcommit 8cdd84f091267324de2105ccbd010465fab98388[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Tue Jun 2 16:58:10 2026 +0800

    fix _pallet_qty: use PALLET_SIZE from xlsx instead of hardcoded 100

[33mcommit 675f36a0b2b52c8a6abe1fb416ec01cc90f36e25[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Tue Jun 2 16:28:47 2026 +0800

    remove speed from nodes config. Use speed from sku.xlsx. This is for t_hangzhou1mini

[33mcommit a5c69df323df49888efac691a2737df56ada3110[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Tue Jun 2 14:36:03 2026 +0800

    Fix the 2^n-1 mystery. Run the simulation once to the configured duration.  The original code called ``env.run(next_t)``, which interprets the argument as a *duration* (not a *till* time), causing simulated time to overshoot ``SIM_DURATION`` by a growing geometric progression (2^n−1). Using ``env.run(till=...)`` fixes the semantics so the simulation stops exactly at the configured duration.

[33mcommit a036af468de9b269256712c2b3513909d48cf282[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Tue Jun 2 14:05:51 2026 +0800

    add demand.xlsx.

[33mcommit 35e59715f00b79a99499ebc8865e338eb89d1cb6[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Tue Jun 2 12:04:44 2026 +0800

    add xlsx support for sku and bom

[33mcommit 41cb8fd841f524f6a685dad3515ec2476061ff14[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri May 29 14:56:15 2026 +0800

    specify .gitignore to exclude jsonl

[33mcommit e825f0782069c70927e4f2abb8268a4e953c2a1d[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Fri May 29 18:28:58 2026 +0800

    Emit implicit production edges (upstream -> workstation -> downstream)

[33mcommit dda7cde13fffcc89b7b66da01956deb2ffe59145[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri May 29 14:21:28 2026 +0800

    modfied go_ series scripts to automate seta generation.

[33mcommit 10dc06bf547613bebbf18ba26c0518001b142280[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri May 29 13:57:19 2026 +0800

    add w_hangzhou1 with weigh_safe_stock management.

[33mcommit ad4f4871e9ae46c1f599a6405dec251adc3e16cf[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Fri May 29 11:22:35 2026 +0800

    add topology visualizer

[33mcommit dcfd15b218a19bf5d5fb37b3ac75f28d8fe1fa58[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri May 29 11:06:34 2026 +0800

    mod plant topology for hangzhou1: small batch instead of by pallet

[33mcommit cefee767ef61c7591d1518b86c77b3e42c3ebd02[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Thu May 28 15:48:30 2026 +0800

    tweaked hangzhou1, add more demand.

[33mcommit e3eda752aa913fa38de983e41f46dde1b507845b[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Thu May 28 15:12:05 2026 +0800

    fixed warehouse node diagram. Now the graphs are working.

[33mcommit 614ea047d18dda2f26de23fd443d851d2b2cba2e[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Thu May 28 14:00:55 2026 +0800

    add storage node exceed_capacity flag, and only when this toggles will there be a warning, not every 10 minutes.

[33mcommit e537156364992eb1b97f3aeadeff7d3ead2ea318[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Thu May 28 11:42:15 2026 +0800

    explicitly say source=期初库存

[33mcommit e7fed13324c6125092487772b0af4280701e020d[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Thu May 28 10:46:09 2026 +0800

    modified report html to chinese

[33mcommit e2aebb516d329e17255a3ef19e9941b8f0984d6c[m
Author: Harry Huang <haoyanghuang@qq.com>
Date:   Thu May 28 10:19:27 2026 +0800

    fixed seta report edge encoding/no-display problem

[33mcommit eaa0be735ab8fe2c51f3b22648ac9716e4b6d9c3[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Wed May 27 00:53:37 2026 +0800

    report.

[33mcommit 762fe01d7f6d2bc8100498b080acd65d3284a4b3[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 26 15:51:27 2026 +0800

    The problem: run_scenario() unconditionally imported and printed config_static_jobs.TRANSPORT_ORDERS and PRODUCTION_JOBS, even for trace-managed scenarios where those static orders are never used. This made the setup print misleading — orders for SKU1-10 appeared to be scheduled when only SKU_1 was actually being ordered.
    The fix: main.py now reads the management type before the setup print section (mgmt_type = config.MANAGEMENT.get(type)) and only prints static transport/production orders when mgmt_type == static_order. For trace or safe_stock management, static orders are skipped entirely.

[33mcommit e4e36cf887ac625c956fdb7cb45b87e59781dd61[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 26 14:49:26 2026 +0800

    systematically add order_id and record event list. use ds4.

[33mcommit 567e10f0195c6879afdb555bd6c8d583ffb309e8[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sun May 24 22:58:03 2026 +0800

    modfiy config generation

[33mcommit 9d727b6a1e7f31d48e6a6d1d0d89a05205bc7de5[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sun May 24 09:07:52 2026 +0800

    Clean. No scenario folder file hardcodes its own name anywhere. The changes:
    File    Before  After
    ss_hangzhou0b/scenario_builder.py       scenario_name="scenario.ss_hangzhou0b"  scenario_name=__name__.rsplit(".", 1)[0]
    t_hangzhou1/scenario_builder.py scenario_name="scenario.t_hangzhou1"    same pattern
    example/scenario_builder.py     scenario_name="scenario.example"        same pattern
    example/config.py       from scenario.example.sku import ...    from .sku import ...
    example/bom.py  from scenario.example.sku import N      from .sku import N
    example/plant_topology.py       from scenario.example.bom import FG_BOM from .bom import FG_BOM
    ss_hangzhou0b/config.py docstring from scenario.ss_hangzhou0b import config     from . import config
    t_hangzhou1/config.py   same    same
    ss_hangzhou0b/dump_scenario.py  usage scenario.ss_hangzhou0b.dump_scenario      scenario.<scenario_name>.dump_scenario
    t_hangzhou1/dump_scenario.py    same    same
    
    Now you can cp -r scenario/ss_hangzhou0b scenario/your_new_scenario, update only the MANAGEMENT type in config.py, and register it in test_scenario_configs.py — nothing else needs to change.

[33mcommit a18c5ff31cff4190bc13a4aa8e7280abd19cc99d[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sun May 24 09:05:31 2026 +0800

    rename scenes: ss_hangzhou0b, and new t_hangzhou1

[33mcommit 2d2736698727d47225043164c0b88d8f7f532fdd[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sun May 24 08:43:55 2026 +0800

    commentator allow using filesystem-style paths (e.g. "scenario/hangzhou0b/")

[33mcommit d60691b3e7f936980ffb0458269bc2545f1f082e[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 23 20:39:53 2026 +0800

    when edge/node is none, throw exception than making a log entry.

[33mcommit 0038597a7fb193975146f1bb85008d0788edd56b[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 23 20:33:57 2026 +0800

    fix management type related settings.

[33mcommit 16b5bee122b612f4c2ead7879a20c2f8739eb539[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 23 17:49:15 2026 +0800

    batch fix 9

[33mcommit 4e4b50e3538375404a23d3dcf37a3fcbedf5b2b2[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 23 14:04:06 2026 +0800

    add trace style management. Given demand, trace all upstream actions needed, and issue orders

[33mcommit 28c7a10d3c8ce70fe2161046aaad3c56c3b1f799[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 23 10:19:01 2026 +0800

    1. src/management/base.py — Refactored base Management class with gather_info() → make_decisions(time, info) → _execute_decision() cycle, Snapshot/Decision dataclasses

[33mcommit c24b995e71a7329b3331e2943e5dae36a606c87e[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 23 09:39:48 2026 +0800

    modify edge properties

[33mcommit d5c69b2c9d66e14d04a195724a64cd278623fa84[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 23 01:45:21 2026 +0800

    switch to dynamic man

[33mcommit 465af21045d8088c0f30515cab956a71957a33df[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 23 01:28:59 2026 +0800

    rm hangzhou0. only keep 0b. mod edge speed.

[33mcommit a237af99651f284193469ebf8d9a66ee8149f510[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 23 00:10:52 2026 +0800

    modify main.py; move scene init related logic to scenario. src/ has new builder.py

[33mcommit 4f13f3507ec95814a2119d3962872c306e4c9403[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri May 22 21:59:59 2026 +0800

    restructure edge str name

[33mcommit 6a488a28c4c49583ccb3b9cef49aa56347500798[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri May 22 21:56:14 2026 +0800

    restructured scenario folder into scenario/xxx

[33mcommit 3aa65fd90e37a182ae3a42b931728cf0e2b4c275[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri May 22 21:33:46 2026 +0800

    add config dump_config method.
    
     Both scenario_hangzhou0 and scenario_hangzhou0b now have:
    config.dump_config() — prints a structured summary: SKU counts (with category breakdown), BOM stats, topology (node types + counts), static jobs, safe stock, and management config.
    dump_scenario.py — a thin entry point that calls config.dump_config(). Runnable either way:
    python scenario_hangzhou0b/dump_scenario.py
    python -m scenario_hangzhou0b.dump_scenario

[33mcommit 5ce02792e27a8e267b35c89bb02f79a8eda8f618[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri May 22 13:47:11 2026 +0800

    modified edge print format. now print as Edge(from_node->to_node)

[33mcommit 211ab324cfb1721a107d6f7a271a078ba731f031[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Wed May 20 15:30:44 2026 +0800

    add scenario_example; restructured config

[33mcommit e7251a366a4371f31696e4f7d56af64c3c9c5503[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Wed May 20 10:45:57 2026 +0800

    safe-stock management: multi-echelon pull chain + rename edge params
    
    - SafeStockManagement new management class with rules-based pull chain
    - Configurable safe_stock entries: produce_at, replenish_from, push_to modes
    - push_to mechanism clears production output buffers (push, not pull)
    - BOM-adjusted lineside safe stock levels (1000 items, covers max batch)
    - Full safe_stock.py config: raw material, lineside, WIP, FG, demand orders
    - generate_stock.py / generate_demand.py helper scripts

[33mcommit 5cc78cd736439c485fa1b4b22c5ee8ab4b6a4520[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Wed May 20 09:02:08 2026 +0800

    new management subclass: man with safe stock

[33mcommit 08ca49a4f8e76b582ab9694ea987bb74d387bc7b[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 19 23:53:36 2026 +0800

    restructured; add scr/infra and scr/management

[33mcommit 648323858456dc46f4cb553791d5bb0217f479c4[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 19 23:44:01 2026 +0800

    reimplement static order management

[33mcommit a31b6161683b1f13a6b604996eef6c37d55e453b[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 19 23:20:23 2026 +0800

    modify edge mechanism: debit entire quantity at first, keep it in temp storck, and send out to end-node repeatedly

[33mcommit b289d11da2c2f3d17a5c6835de6209b4602bb286[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 19 21:46:48 2026 +0800

    mod main.py default scenario

[33mcommit dd571959135cb3151f4e1a58e3397abe9a9c922d[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 19 21:44:46 2026 +0800

    tweaked production nodes

[33mcommit ea3dd455a2a1035df3390bf120c36e14f5b086b0[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 19 21:31:29 2026 +0800

    refactor storage node behavior

[33mcommit ec5679e63d4afcfd1c5484e31e59068effa92c51[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 16 10:10:52 2026 +0800

    Final version for static decisions. Modified the management decision interface.

[33mcommit 1e2e40807bbf7191c5e3eb13b1e52308ed031ad2[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sat May 16 09:52:44 2026 +0800

    Modify management interface to mock real time decisions.
    
    src/management.py — Core change
    JobManager is now a sim.Component subclass with a process() generator loop
    Added DECISION_INTERVAL = 10 — the agent wakes every 10 minutes
    Constructor now takes nodes: Mapping[str, object] (node name → node map) to issue orders directly
    process() loop: on each wake it calls _issue_pending_jobs(), then yield self.hold(DECISION_INTERVAL)
    Job issuance events go to self.log (same pattern as WarehouseNode / ProductionNode)
    The _issue_pending_jobs() method encapsulates the same logic as the old issue_pending_jobs()
    main.py — Removed manual polling
    Removed process_events() function — job issuance is now handled automatically by the component's process() loop during env.run()
    Updated process_all_logs() to accept an optional job_manager parameter and iterate its log
    Added job_issued event printing to process_all_logs()
    run_scenario(): creates JobManager(jobs, nodes, env) (nodes now passed), removed explicit process_events() calls
    src/__init__.py
    Exports DECISION_INTERVAL
    tests/test_unit_management.py
    Tests now work through the component's wake cycle: create JobManager with nodes, call env.run(t), inspect mgr.log
    Added sink fixture for destination nodes
    Added sim.yieldless(False) to test env fixtures
    Added 2 new tests: test_wake_cycle_respects_interval and test_initial_wake_at_time_zero
    Behavior preserved
    Static jobs from config_static_jobs.py still work — loaded as before, just issued by the component's wake cycle
    All 120 relevant tests pass (60 pre-existing failures are unrelated ModuleNotFoundError for obsolete scenarios)
    scenario_hangzhou0 simulation runs end-to-end correctly

[33mcommit 1dda0d0ad4b6d1221d6be9c9c26919ec5c923af6[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri May 15 09:14:24 2026 +0800

    clean up opencode session mds

[33mcommit 3ca5c50c1e8438686fc2a87242595e478a84a2a7[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Fri May 15 09:13:42 2026 +0800

    clean up old scenarios

[33mcommit 69b8aa2e11144de0f92d22f6ae6983a82fd2f0e4[m[33m ([m[1;31morigin/master[m[33m, [m[1;31morigin/HEAD[m[33m, [m[1;32mmaster[m[33m)[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Thu May 14 18:39:49 2026 +0800

    Summary of the bug and fix:
    Root cause: In warehouse_node.py:_dispatch_for_destination(), avail_pallets was computed via pallets_for_quantity() which uses math.ceil(units / pallet_size). This inflates actual available units — e.g., 20 units with pallet_size=50 gives ceil(20/50)=1 pallet → 50 units dispatch, but only 20 exist. This caused inventory[sku] -= actual to go negative.
    Fix: Replaced with floor division (avail // conversion_factors[sku]), so only fully-fillable pallets are eligible for dispatch. If you have 20 units on a 50-unit pallet, avail_pallets=0 → no over-dispatch.
    Why floor is correct here but ceil is correct elsewhere:
    - pallets_for_quantity(20) = 1 pallet is valid for capacity tracking (it occupies 1 pallet position)
    - But for dispatch, you can only ship what you physically have — shipping quantity_for_pallets(1) = 50 units when you only have 20 is impossible

[33mcommit 980a3da262df58978d719e7de67c8ee91a5507d6[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Thu May 14 17:26:10 2026 +0800

    Modified the pytest system to include scenarios rather than only /src components.
    
    Here's what tests/test_scenario_configs.py validates for every scenario:
    | Test group | What it checks |
    |---|---|
    | ModuleStructure | Config/jobs modules importable, required attrs present, not empty |
    | SkuPalletAlignment | SKUS keys = PALLET_SIZE keys, values positive |
    | NodeStructure | All nodes have valid type, production nodes have BOM + conversion_factors, warehouses have max_pallets |
    | EdgeReferences | All from_node/to_node exist in NODES, transfer_mode is TransferMode enum |
    | BomSkuReferences | BOM output SKUs, input SKUs, and conversion_factors keys all exist in SKUS |
    | JobReferences | Transport/production job nodes and SKUs all resolve correctly |
    To add a new scenario in the future, just add its folder name to the SCENARIOS list and all 20 tests run against it automatically.

[33mcommit ac49097c2f70988d76be87c161779bb26031a2fe[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Thu May 14 17:00:31 2026 +0800

    i18n with hangzhou proj chinese sku names / node names

[33mcommit 3a016a4099b3ea23b7a5c7d1c4c6405b4f2e75d2[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Thu May 14 11:37:59 2026 +0800

     Scenario scenario_hangzhou0/ is ready. Here's what it does:
    source (供应商)
      → raw_material_wh (调理原料库)
        → seasoning_lineside (公用线边仓)
          → sauce_workshop (酱包) --wip_s→ semi_finished_wh (半成品库)
          → powder_workshop (粉包) --wip_p→ semi_finished_wh
        → semi_finished_wh
          → warehouse_1 (一库) → line_side_1 → noodle_ws_1 (一制面) → finished_wh
          → warehouse_2 (二库) → line_side_2 → noodle_ws_2 (二制面) → finished_wh
        → finished_wh (成品库) → sink (发货)
    Timeline:
    t       Event
    0       source→raw_wh: 500 raw → seasoning_lineside: 300 raw
    0       sauce/powder workshops start (consume 100 raw each)
    10      100 wip_s → semi_finished_wh, 50 of which → warehouse_1 → line_side_1
    10      100 wip_p → semi_finished_wh, 50 of which → warehouse_2 → line_side_2
    50      noodle_ws_1 draws 40 wip_s from line_side_1 → produces 40 fg
    50      noodle_ws_2 draws 40 wip_p from line_side_2 → produces 40 fg
    58      80 fg → finished_wh → sink
    Final state:
    - 4/4 production jobs completed ✅
    - sink received: 80 fg ✅
    - Remaining stock in intermediate warehouses (not oversold)
    Run with python main.py scenario_hangzhou0.

[33mcommit d29c30c5636c23888a05de6daa6b0867c9cad8c9[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Thu May 14 11:26:32 2026 +0800

     Here's the scenario_spws/ scenario:
    Architecture note: I added a raw_wh node between source and productionlien — the ProductionNode draws materials from an upstream warehouse's inventory (self.upstream_node.inventory), and Source (role=SOURCE) doesn't have an inventory dict. So the actual flow is:
    source  →  raw_wh  →  productionlien  →  warehouse  →  sink
                        ↑ upstream              ↓ downstream
    What ran:
    Job     Time
    source → raw_wh t=0
    productionlien sku_a    t=0→100
    productionlien sku_b    t=100→150
    warehouse → sink        t=0
    Results:
    - raw_wh final: 500 raw (1000 supplied − 300 for sku_a − 200 for sku_b)
    - warehouse final: 0 (all shipped)
    - sink received: 100 sku_a + 100 sku_b ✅
    Run it again with python main.py scenario_spws to see the full log. The production line runs sku_a first (job_id ordering), then sku_b sequentially — both orders placed at t=0, line is single-threaded.

[33mcommit 765c1d90b4cf41623820a4096df190a35fac5a2a[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 12 17:33:54 2026 +0800

    Summary of Changes
    New file: src/production_node.py
    - ProductionOrder dataclass — job_id, output_sku, quantity, start_time, node_name
    - ProductionNode(sim.Component) — separate class (not extending WarehouseNode)
    - Takes materials directly from upstream warehouse inventory (instant, no transport)
    - Pushes finished goods to downstream warehouse via receive(); if returns False → product lost (no retry)
    - start_time gating + job_id tiebreaker for queue ordering
    - Batch output in global_time_step increments: full batches at speed × time_step, final partial batch pro-rata
    - Logs: materials_consumed, production_started, production_output, production_output_lost, production_completed, production_failed
    Modified: src/__init__.py
    - Exports ProductionNode, ProductionOrder
    Modified: main.py
    - build_nodes() — two-pass: warehouse-class nodes first, production nodes second
    - SimulationResult — hasattr guards for hybrid node types
    - process_all_logs() — prints all production event types
    - run_scenario() — loads PRODUCTION_JOBS, prints production setup, final report for production nodes
    New: scenario_production/ — config demonstrating Source → RawMaterialWH → ProductionLine → ProductWH → Sink
    New: tests/test_unit_production.py — 21 unit tests covering:
    - Material checks (sufficient/insufficient) — 5 tests
    - Material consumption (quantities, key removal, stacking) — 3 tests
    - Queue ordering (sort by start_time → job_id) — 2 tests
    - Output to downstream (success/lost) — 2 tests
    - Full job execution (failure, timing, BOM match, sequential jobs) — 6 tests
    - Plus test_job_not_started_before_start_time and test_job_starts_at_start_time

[33mcommit 3d62cc8f341577a860f40c02b12ebc3ea73c642f[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 12 14:27:10 2026 +0800

    New test files
    tests/
    ├── __init__.py
    ├── conftest.py              # Fixtures + invariant helpers
    ├── test_unit_edge.py        # Tier 1 — 14 tests
    ├── test_unit_warehouse.py   # Tier 1 — 17 tests
    ├── test_unit_management.py  # Tier 1 — 6 tests
    ├── test_scenarios.py        # Tier 2 — 6 tests
    └── test_invariants.py       # Tier 3 — 6 tests
    52 tests, all passing in 0.68s.
    What each tier catches
    Tier    What it catches Example
    Unit (37 tests) Math errors, edge cases pallets_for_quantity(1) should be ceil(1/10)=1, not 0
    Scenario (6 tests)      Regressions in specific configs Final WH inventory changes from {SKU_X: 50} to something else
    Invariant (6 tests)     Cross-cutting logic bugs        Conservation fails = goods lost/created; capacity exceeded = can_accept logic broken
    How to use
    pytest tests/
    pytest tests/test_scenarios.py -v
    pytest tests/test_invariants.py -v
    python main.py test_scenario2
    Adding new tests
    To add a test for a new scenario:
    1. Create new_scenario/config.py and new_scenario/config_static_jobs.py (same pattern as existing)
    2. Add a session fixture in tests/conftest.py:
          @pytest.fixture(scope="session")
       def new_result() -> SimulationResult:
           return run_scenario("new_scenario")
       3. Add assertions in tests/test_scenarios.py using the fixture
    4. Invariant tests in tests/test_invariants.py automatically cover the new scenario via conservation/capacity/no-negative-inventory checks

[33mcommit 22e20fa73b156942230741d6f484d1c1bb84c674[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 12 11:17:22 2026 +0800

    test_scenario2 fixed.

[33mcommit 2d922e0a880ebfe8e6633468ad8024a695b0cbd8[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 12 10:48:41 2026 +0800

    buggy 2test

[33mcommit 36d0c0d195129283d95135d5700a603392b87670[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Tue May 12 10:08:35 2026 +0800

    2

[33mcommit 83e077a447c043b94afbf226ef109404e01ec090[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Wed May 6 10:01:24 2026 +0800

    20260506.start

[33mcommit d13040804ea19efb37d30b4c746fdd5ea8a5e72a[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sun May 3 17:18:49 2026 +0800

    Done. Changes made:
    1. Jobs now specify from_node -> to_node (e.g. Source -> Sink) instead of just a target node. The destination propagates through the chain.
    2. Files:
       - src/config.py — SKUS, PALLET_SIZE, NODES, EDGES, SIM_DURATION
       - src/edge.py — Edge, TransferMode
       - src/warehouse_node.py — WarehouseNode, SourceNode, SinkNode, OutboundOrder, InboundShipment
       - src/management.py — Job (with from_node/to_node), JobManager, JOBS
       - main.py — builds from config, runs with sorted/deduplicated logging
    3. Routing: When destination is Sink but the only edge goes to WarehouseB, items are forwarded through. Intermediate nodes auto-create outbound orders for shipments whose destination is beyond the current node.
    4. Output format:
      [t=0.0] JOB ISSUED: Source -> Sink:
        -> Order: SKU_A x500 (priority=1)
      [t=0.0] Source: dispatched -> Sink -> SKU_Ax500, ...
      [t=0.0] WarehouseA: received SKU_A x500 from Source
      [t=0.0] WarehouseB: dispatched -> Sink -> SKU_Ax100
      [t=0.0] Sink: received SKU_A x100 from WarehouseB
    Final Sink totals: SKU_A=1000, SKU_B=300, SKU_C=1500 (matches job quantities).

[33mcommit f88db4bbfbc8e4584652008f1622b1849448a900[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sun May 3 17:02:57 2026 +0800

    All coding complete. Final structure:
    src/
      __init__.py           # exports
      config.py             # SKUs, PALLET_SIZE, NODES, EDGES, SIM_DURATION
      edge.py               # Edge, TransferMode
      management.py         # Job, JobManager, JOBS list
      warehouse_node.py     # WarehouseNode, SourceNode, SinkNode, OutboundOrder, InboundShipment
    main.py                 # builds from config, runs simulation
    - config.py: Defines SKUS, PALLET_SIZE dict (e.g. pallet_size["SKU_A"] = 50), NODES dict (with type: source/warehouse/sink), EDGES list (with per-edge transfer mode/time/batch), and SIM_DURATION
    - management.py: JOBS list of timed job orders, JobManager.issue_pending_jobs() fires jobs at the right simulation time
    - SourceNode: infinite supply, auto-forwards dispatched items to downstream edges
    - SinkNode: unlimited capacity, tracks total received per SKU
    - WarehouseNode: receives, auto-creates outbound orders, dispatches by priority with pallet limits, forwards to downstream edges
    Output shows: time, job issuance, orders queued, dispatches, receives, and periodic state snapshots.
    x

[33mcommit ff0cb708319281260b88bfc060b1064ab51af154[m
Author: hhy06 <haoyangh@gmail.com>
Date:   Sun May 3 16:17:23 2026 +0800

    实现完成。项目结构：
    src/
      __init__.py
      edge.py          # Edge 类 (传送边)
      warehouse_node.py # WarehouseNode 类 (仓储节点)
    main.py            # 示例
    WarehouseNode 核心功能：
    - max_pallets - 最大托盘容量
    - inventory[SKU] = quantity - 按 SKU 记录物品数量
    - conversion_factors[SKU] = items_per_pallet - 每个 SKU 独立的换算系数
    - pallets_for_quantity() - 数量转托盘数 (上取整)
    - output_queue - 发货队列，按 priority 排序
    - compute_dispatch_plan() - 按优先级计算发货计划，优先发高优先级 SKU
    - dispatch_step() - 每个 dispatch_interval 执行一次，发最多 dispatch_max_pallets 个托盘
    Edge 核心功能：
    - TransferMode.PER_PALLET - 每托盘耗时 transfer_time
    - TransferMode.BATCH - 每批次耗时 transfer_time，每批 batch_size 个托盘
    运行 python main.py 可查看示例输出。下一步可实现生产类型节点。
