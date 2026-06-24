"""
BOM Flattening Script: Eliminate dual-nature SKU violations.

Rule 1 (17AT961261H, 17AT971201H, 17AT581204H, 17AX141200H):
  - Keep production BOM at producing workstations (still FG products)
  - Flatten into downstream products' inputs (remove from their input lists)
  - Add weighted raw inputs: new_qty = consumption_qty * viol_input_qty

Rule 2 (1101xxx intermediate SKUs):
  - Remove from producing workstations' BOM entirely
  - Flatten into downstream products' inputs
  - These SKUs should no longer appear anywhere in production
"""

import re
import ast
import copy
import sys
from pathlib import Path

TOPO_FILE = Path(__file__).parent / "scenario/srw_hangzhou1/plant_topology.py"

RULE1_SKUS = ['17AT961261H', '17AT971201H', '17AT581204H', '17AX141200H']
RULE2_SKUS = ['1101271', '1101237', '1101239', '1101251', '1101252', '1101253',
              '1101254', '1101260', '1101261', '1101263', '1101264', '1101265', '1101266']
ALL_VIOL_SKUS = RULE1_SKUS + RULE2_SKUS

# Workstations that produce violation SKUs (need removal for Rule2)
RULE2_PRODUCER_WORKSTATIONS = {
    'workstation_X07': ['1101251', '1101263', '1101271'],
    'workstation_X10': ['1101271'],
    'workstation_X15': ['1101237', '1101239', '1101252', '1101253',
                        '1101254', '1101260', '1101261', '1101264', '1101265', '1101266'],
}

# Workstations that consume violation SKUs (need BOM flattening)
CONSUMER_WORKSTATIONS = [
    'workstation_X18',   # consumes all 13 1101xxx
    'workstation_X11',   # consumes 17AT961261H, 17AT971201H
    'workstation_X13',   # consumes 17AT961261H, 17AT971201H
    'workstation_X14',   # consumes 17AT581204H (self-loop)
    'workstation_X02',   # consumes 17AX141200H (self-loop)
]


def extract_ws_block(content, ws_name):
    search_str = 'NODES["' + ws_name + '"]'
    idx = content.find(search_str)
    if idx == -1:
        return None
    brace_start = content.find('{', idx)
    brace_count = 1
    pos = brace_start + 1
    while brace_count > 0 and pos < len(content):
        if content[pos] == '{':
            brace_count += 1
        elif content[pos] == '}':
            brace_count -= 1
        pos += 1
    return content[idx:pos]


def extract_bom_text(content, ws_name):
    """Extract the raw BOM dict text from a workstation definition."""
    block = extract_ws_block(content, ws_name)
    if not block:
        return None, None, None

    bom_idx = block.find('"bom"')
    if bom_idx == -1:
        return None, None, None

    # Find the opening { of the bom dict
    dict_start = bom_idx + 5
    while dict_start < len(block) and block[dict_start] != '{':
        dict_start += 1

    brace_count = 1
    pos = dict_start + 1
    while brace_count > 0 and pos < len(block):
        if block[pos] == '{':
            brace_count += 1
        elif block[pos] == '}':
            brace_count -= 1
        pos += 1

    bom_text = block[dict_start:pos]
    bom_end_pos = pos  # position right after the closing }

    # Parse the bom dict
    try:
        bom_dict = ast.literal_eval(bom_text)
    except Exception:
        # For very large BOMs, parse using regex
        bom_dict = _parse_bom_regex(block, bom_idx)

    return bom_dict, bom_text, bom_end_pos


def _parse_bom_regex(block, bom_idx):
    """Fallback regex-based BOM parser for very large dicts."""
    # Find opening { after "bom":
    dict_start = bom_idx + 5
    while dict_start < len(block) and block[dict_start] != '{':
        dict_start += 1

    brace_count = 1
    pos = dict_start + 1
    while brace_count > 0 and pos < len(block):
        if block[pos] == '{':
            brace_count += 1
        elif block[pos] == '}':
            brace_count -= 1
        pos += 1

    bom_text = block[dict_start:pos]

    bom_dict = {}
    # Find each product entry: 'product_sku': {'inputs': {input_dict}, 'speed': ..., 'lead_time': ...}
    prod_pattern = r"'(\w+)':\s*\{\s*'inputs':\s*\{"
    for prod_match in re.finditer(prod_pattern, bom_text):
        product_sku = prod_match.group(1)
        inputs_start = prod_match.end()

        # Find the closing } of inputs dict
        brace_count2 = 1
        ipos = inputs_start
        while brace_count2 > 0 and ipos < len(bom_text):
            if bom_text[ipos] == '{':
                brace_count2 += 1
            elif bom_text[ipos] == '}':
                brace_count2 -= 1
            ipos += 1
        inputs_text = bom_text[inputs_start - 1:ipos]

        # Parse inputs
        inputs = {}
        for inp_match in re.finditer(r"'(\w+)':\s*([0-9.eE+-]+)", inputs_text):
            inputs[inp_match.group(1)] = float(inp_match.group(2))

        # Find speed and lead_time after inputs dict
        remaining = bom_text[ipos:]
        speed_match = re.search(r"'speed':\s*([0-9.eE+-]+)", remaining[:100])
        lead_match = re.search(r"'lead_time':\s*([0-9.eE+-]+)", remaining[:100])

        bom_dict[product_sku] = {
            'inputs': inputs,
            'speed': float(speed_match.group(1)) if speed_match else 0,
            'lead_time': float(lead_match.group(1)) if lead_match else 0,
        }

    return bom_dict


def format_bom_dict(bom_dict):
    """Format a BOM dict as Python code string."""
    lines = []
    lines.append('{')
    for sku in sorted(bom_dict.keys()):
        entry = bom_dict[sku]
        inputs_str = ', '.join(
            f"'{k}': {v}" for k, v in sorted(entry['inputs'].items())
        )
        lines.append(f"    '{sku}: {{'inputs': {{{inputs_str}}}, 'speed': {entry['speed']}, 'lead_time': {entry['lead_time']}}},")
    lines.append('}')
    return '\n'.join(lines)


def flatten_bom(product_inputs, viol_sku, viol_inputs, consumption_qty):
    """
    Flatten a violation SKU's inputs into a product's BOM.

    product_inputs: dict of the product's current inputs {input_sku: qty}
    viol_sku: the violation SKU being flattened
    viol_inputs: the violation SKU's BOM inputs {input_sku: qty_per_unit}
    consumption_qty: how much of viol_sku this product consumes per unit

    Returns: modified product_inputs dict (viol_sku removed, viol inputs added/merged)
    """
    new_inputs = copy.deepcopy(product_inputs)

    # Remove the violation SKU from inputs
    if viol_sku in new_inputs:
        del new_inputs[viol_sku]

    # Add/merge violation SKU's inputs, weighted by consumption quantity
    for inp_sku, inp_qty_per in viol_inputs.items():
        flat_qty = consumption_qty * inp_qty_per
        if inp_sku in new_inputs:
            new_inputs[inp_sku] += flat_qty
        else:
            new_inputs[inp_sku] = flat_qty

    return new_inputs


def main():
    content = TOPO_FILE.read_text()
    print(f"Read {TOPO_FILE}: {len(content)} chars")

    # Step 1: Get violation SKU BOMs (from their producing workstations)
    viol_boms = {}  # viol_sku -> {'inputs': {...}, 'speed': ..., 'lead_time': ...}

    # For 1101271: get from X07 (confirmed identical at X07 and X10)
    # For 1101xxx at X15: get from X15
    # For 17AT: get from X01
    # For self-loop: get from X14/X02
    producer_ws_for_viol = {
        '1101271': 'workstation_X07',
        '1101251': 'workstation_X07',
        '1101263': 'workstation_X07',
        '1101237': 'workstation_X15',
        '1101239': 'workstation_X15',
        '1101252': 'workstation_X15',
        '1101253': 'workstation_X15',
        '1101254': 'workstation_X15',
        '1101260': 'workstation_X15',
        '1101261': 'workstation_X15',
        '1101264': 'workstation_X15',
        '1101265': 'workstation_X15',
        '1101266': 'workstation_X15',
        '17AT961261H': 'workstation_X01',
        '17AT971201H': 'workstation_X01',
        '17AT581204H': 'workstation_X14',
        '17AX141200H': 'workstation_X02',
    }

    for viol_sku, ws_name in producer_ws_for_viol.items():
        bom_dict, _, _ = extract_bom_text(content, ws_name)
        if bom_dict and viol_sku in bom_dict:
            viol_boms[viol_sku] = bom_dict[viol_sku]
            print(f"  {viol_sku} BOM from {ws_name}: {len(bom_dict[viol_sku]['inputs'])} inputs")
        else:
            print(f"  ERROR: {viol_sku} BOM not found at {ws_name}!")
            sys.exit(1)

    # Step 2: Flatten consumer workstations' BOMs
    modified_boms = {}  # ws_name -> new bom_dict

    for ws_name in CONSUMER_WORKSTATIONS:
        bom_dict, bom_text, bom_end_pos = extract_bom_text(content, ws_name)
        if bom_dict is None:
            print(f"  ERROR: Could not parse BOM for {ws_name}")
            sys.exit(1)

        print(f"\nProcessing {ws_name}: {len(bom_dict)} products")

        new_bom = copy.deepcopy(bom_dict)
        changes = 0

        for product_sku, product_data in new_bom.items():
            product_inputs = product_data['inputs']

            for viol_sku in ALL_VIOL_SKUS:
                if viol_sku in product_inputs:
                    consumption_qty = product_inputs[viol_sku]
                    viol_inputs = viol_boms[viol_sku]['inputs']

                    # Flatten
                    new_inputs = flatten_bom(product_inputs, viol_sku, viol_inputs, consumption_qty)
                    product_data['inputs'] = new_inputs
                    product_inputs = new_inputs  # update for next violation

                    changes += 1
                    print(f"    {product_sku}: flattened {viol_sku} (qty={consumption_qty}), "
                          f"inputs: {len(product_data['inputs'])}")

        if changes > 0:
            modified_boms[ws_name] = new_bom
            print(f"  {ws_name}: {changes} products modified")

    # Step 3: Remove Rule2 SKUs from producer workstations' BOMs
    for ws_name, skus_to_remove in RULE2_PRODUCER_WORKSTATIONS.items():
        bom_dict, bom_text, bom_end_pos = extract_bom_text(content, ws_name)
        if bom_dict is None:
            print(f"  ERROR: Could not parse BOM for {ws_name}")
            sys.exit(1)

        new_bom = copy.deepcopy(bom_dict)
        for sku in skus_to_remove:
            if sku in new_bom:
                del new_bom[sku]
                print(f"  {ws_name}: removed {sku} from BOM")

        modified_boms[ws_name] = new_bom

    # Step 4: Apply modifications to plant_topology.py
    # We need to replace the BOM text in each affected workstation definition

    for ws_name, new_bom in modified_boms.items():
        block = extract_ws_block(content, ws_name)
        if not block:
            print(f"  ERROR: {ws_name} block not found!")
            sys.exit(1)

        # Find the old bom text and its position within the block
        bom_idx = block.find('"bom"')
        dict_start = bom_idx + 5
        while dict_start < len(block) and block[dict_start] != '{':
            dict_start += 1

        brace_count = 1
        pos = dict_start + 1
        while brace_count > 0 and pos < len(block):
            if block[pos] == '{':
                brace_count += 1
            elif block[pos] == '}':
                brace_count -= 1
            pos += 1

        old_bom_text = block[dict_start:pos]

        # Generate new bom text
        new_bom_text = _format_bom_python(new_bom)

        # Replace in content
        # Find the block in content and replace the bom section
        ws_start = content.find('NODES["' + ws_name + '"]')
        ws_block_start = ws_start
        brace_start = content.find('{', ws_start)
        brace_count2 = 1
        ws_pos = brace_start + 1
        while brace_count2 > 0 and ws_pos < len(content):
            if content[ws_pos] == '{':
                brace_count2 += 1
            elif content[ws_pos] == '}':
                brace_count2 -= 1
            ws_pos += 1

        # Find bom dict position within the full content
        bom_idx_global = content.find('"bom"', ws_start, ws_pos)
        dict_start_global = bom_idx_global + 5
        while dict_start_global < len(content) and content[dict_start_global] != '{':
            dict_start_global += 1

        brace_count3 = 1
        bom_pos_global = dict_start_global + 1
        while brace_count3 > 0 and bom_pos_global < len(content):
            if content[bom_pos_global] == '{':
                brace_count3 += 1
            elif content[bom_pos_global] == '}':
                brace_count3 -= 1
            bom_pos_global += 1

        old_global_bom = content[dict_start_global:bom_pos_global]

        content = content[:dict_start_global] + new_bom_text + content[bom_pos_global:]

        print(f"  Applied: {ws_name} BOM updated in plant_topology.py")

    # Step 5: Write modified content
    TOPO_FILE.write_text(content)
    print(f"\nWrote {TOPO_FILE}: {len(content)} chars")

    # Step 6: Verify no more violations
    print("\n" + "=" * 80)
    print("Verification: checking for remaining dual-nature violations...")
    print("=" * 80)

    # Re-parse the modified file
    content2 = TOPO_FILE.read_text()

    # Build sku_producers from all workstations
    all_produced = set()
    all_consumed_as_input = set()

    for match in re.finditer(r'NODES\["(workstation_\w+)"\]\s*=\s*\{', content2):
        ws_name = match.group(1)
        ws_start = match.start()
        brace_count = 0
        pos = ws_start
        while pos < len(content2):
            if content2[pos] == '{':
                brace_count += 1
            elif content2[pos] == '}':
                brace_count -= 1
                if brace_count == 0:
                    break
            pos += 1
        ws_block = content2[ws_start:pos + 1]

        bom_keys = re.findall(r"'([A-Za-z0-9_]+)':\s*\{'inputs':\s*\{", ws_block)
        for sku in bom_keys:
            all_produced.add(sku)

        for prod_match in re.finditer(r"'(\w+)':\s*\{'inputs':\s*\{([^}]+)\}", ws_block):
            input_skus = re.findall(r"'([A-Za-z0-9_]+)':", prod_match.group(2))
            for inp_sku in input_skus:
                all_consumed_as_input.add(inp_sku)

    remaining_violations = all_produced & all_consumed_as_input
    # Exclude WIP SKUs that drain to wip_storage (these are expected)
    # We need to check drain type

    output_drains = {}
    for match in re.finditer(r'"from_node":\s*"(\w+)",\s*"to_node":\s*"(\w+)"', content2):
        f, t = match.group(1), match.group(2)
        if f.startswith('output_'):
            output_drains[f] = t

    sku_producers2 = {}
    sku_drain2 = {}
    for match2 in re.finditer(r'NODES\["(workstation_\w+)"\]\s*=\s*\{', content2):
        ws_name2 = match2.group(1)
        ws_start2 = match2.start()
        brace_count = 0
        pos = ws_start2
        while pos < len(content2):
            if content2[pos] == '{':
                brace_count += 1
            elif content2[pos] == '}':
                brace_count -= 1
                if brace_count == 0:
                    break
            pos += 1
        ws_block2 = content2[ws_start2:pos + 1]

        bom_keys2 = re.findall(r"'([A-Za-z0-9_]+)':\s*\{'inputs':\s*\{", ws_block2)
        drain = output_drains.get('output_' + ws_name2.replace('workstation_', ''), 'UNKNOWN')

        for sku in bom_keys2:
            sku_producers2.setdefault(sku, []).append(ws_name2)
            sku_drain2.setdefault(sku, set()).add(drain)

    fg_violations = []
    for sku in remaining_violations:
        drains = sku_drain2.get(sku, set())
        if 'fg_storage' in drains:
            fg_violations.append(sku)

    print(f"Remaining FG→FG dual-nature violations: {len(fg_violations)}")
    if fg_violations:
        for sku in sorted(fg_violations):
            print(f"  {sku}: producers={sku_producers2.get(sku, [])}, drains={sku_drain2.get(sku, set())}")
    else:
        print("  All violations eliminated! ✓")

    # Check Rule2 SKUs no longer exist
    rule2_remaining = [sku for sku in RULE2_SKUS if sku in all_produced]
    if rule2_remaining:
        print(f"  WARNING: Rule2 SKUs still in production: {rule2_remaining}")
    else:
        print("  All Rule2 SKUs removed from production ✓")


def _format_bom_python(bom_dict):
    """Format a BOM dict as a Python dict literal string."""
    entries = []
    for sku in sorted(bom_dict.keys()):
        entry = bom_dict[sku]
        input_items = []
        for inp_sku in sorted(entry['inputs'].keys()):
            qty = entry['inputs'][inp_sku]
            # Format quantity: use compact representation
            if qty == int(qty):
                qty_str = str(int(qty))
            elif qty < 0.001:
                qty_str = repr(qty)
            else:
                qty_str = repr(qty)
            input_items.append(f"'{inp_sku}': {qty_str}")

        inputs_str = ', '.join(input_items)
        speed = entry.get('speed', 0)
        lead_time = entry.get('lead_time', 0)
        entries.append(f"'{sku}': {{'inputs': {{{inputs_str}}}, 'speed': {speed}, 'lead_time': {lead_time}}}")

    return '{' + ', '.join(entries) + '}'


if __name__ == '__main__':
    main()
