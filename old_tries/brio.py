import xml.etree.ElementTree as ET
from pprint import pprint

import cairosvg
import tinycss2
import pyvips
from easing_functions import QuadEaseInOut

ET.register_namespace("", "http://www.w3.org/2000/svg")

def is_number(x):
    try: return float(x)
    except ValueError: return False

def attrs_to_node(attrs):
    return {key: value for key, el in attrs.items()
            if (value := is_number(el))}

def style_to_node(attrs):
    return {rule.name: rule.value[0].value
            for rule in tinycss2.parse_declaration_list(attrs)
            if isinstance(rule.value[0], tinycss2.ast.NumberToken)}

def transform_to_node(attrs):
    return {rules.name: [a.value for a in rules.arguments 
            if isinstance(a, tinycss2.ast.NumberToken)]
            for rules in tinycss2.parse_component_value_list(attrs)}

def nodes_of(filename):
    root = ET.parse(filename).getroot()
    nodes = {}
    for el in root.iter():
        if 'id' in el.attrib:
            a = attrs_to_node(el.attrib)
            if 'style' in el.attrib:
                b = style_to_node(el.attrib['style'])
            else: b = {}
            if 'transform' in el.attrib:
                c = transform_to_node(el.attrib['transform'])
            else: c = {}
            if 'matrix' not in c:
                c['matrix'] = [0, 0, 0, 0, 0, 0]
            if 'rotate' not in c:
                c['rotate'] = [0]
            if 'translate' not in c:
                c['translate'] = [0, 0]
            if a or b or c:
                nodes[el.attrib['id']] = (a, b, c)
    return nodes

def diff_nodes(before, after):
    diff = {}
    for key in before.keys() & after.keys():
        diff[key] = ({}, {}, {})
        for index, kind in enumerate(('xml', 'style', 'transform')):
            bef, aft = before[key][index], after[key][index]
            for prop in bef.keys() & aft.keys():
                if bef[prop] != aft[prop]:
                    diff[key][index][prop] = (bef[prop], aft[prop])
    return diff

def interpolate_values(before, after, value):
    value = QuadEaseInOut(start=0, end=1, duration=1)(value)
    return before*value + after*(1-value)

def interpolate_list(before, after, value):
    return [interpolate_values(b, a, value) for b, a in zip(before, after)]

def interpolate_svg(before, diff, interp):
    before = (tree := ET.parse(before)).getroot()
    for el in before.iter():
        if 'id' in el.attrib and el.attrib['id'] in diff:
            id = el.attrib['id']
            for key, value in diff[id][0].items():
                el.attrib[key] = str(interpolate_values(*value, interp))
            
            rules = tinycss2.parse_declaration_list(el.attrib.get('style', ''))
            for key, value in diff[id][1].items():
                for rule in rules:
                    if rule.name != key: continue
                    v = interpolate_values(*value, interp)
                    rule.value = [tinycss2.ast.NumberToken(0, 0, 0, v, repr(v))]
            el.attrib['style'] = tinycss2.serialize(rules)
            
            rules = tinycss2.parse_component_value_list(el.attrib.get('transform', ''))
            for key, value in diff[id][2].items():
                v = interpolate_list(*value, interp)
                v = [tinycss2.ast.NumberToken(0, 0, 0, k, repr(k)) for k in v]
                for rule in rules:
                    if rule.name != key: continue
                    rule.arguments = v
                    break
                else:
                    rules.append(tinycss2.ast.FunctionBlock(0, 0, key, v))
            el.attrib['transform'] = tinycss2.serialize(rules).replace('/**/', ',')
    tree.write(f'out/.svg/{round(interp*100):03}.svg')
    #in = open(f'out/.svg/{round(interp*100):03}.svg', 'r').read().replace('ns0:', '').replace('ns2:', '')
    #open(f'out/.svg/{round(interp*100):03}.svg', 'w').write(in)
    pyvips.Image.new_from_file(f'out/.svg/{round(interp*100):03}.svg').write_to_file(f'out/{round(interp*100):03}.png')
    

before, after = nodes_of('drawing.svg'), nodes_of('drawingb.svg')
pprint(after)
diff = diff_nodes(before, after)
pprint(diff)
for i in range(100):
    print((i/100))
    interpolate_svg('drawingb.svg', diff, i/100)
