import xml.etree.ElementTree as ET
from pprint import pprint
from copy import deepcopy

from tinycss2 import parse_one_component_value as component, 
import tinycss2.ast as tca
import pyvips
import easing_functions
import webcolor

supported = {tca.NumberToken: Number, tca.UrlToken: Url, tca.HashToken: Color,
             tca.DimensionToken: Number, tca.PercentageToken: Number,
             tca.FunctionBlock: Fun}

def parse(token, defs):
    return supported[type(token)].tokenize(token, defs) if token in supported else token

class Number:
    
    def __init__(self, value, unit):
        self.value, self.unit = value, unit
    
    @staticmethod
    def tokenize(token, defs):
        return Number(token.value, 
                      ('%' if token.type == 'percentage' 
                      else token.unit if token.type == 'dimension' else ''))
    
    def default(self):
        return Number(0, self.unit)
    
    def diff(self, other, weight):
        if self.unit != other.unit: raise ValueError('Different units!')
        return self(self.value*(1-weight)+other.value*weight, self.unit)
    
    def make(self):
        return tca.DimensionToken(0, 0, self.value, self.value, 
                                  f'{self.value}{self.unit}', self.unit)

class Color:
    
    def __init__(self, r, g, b):
        self.r, self.g, self.b = r, g, b
    
    @staticmethod
    def tokenize(token, defs):
        return Color(*webcolors.hex_to_rgb(token.value))
    
    def default(self):
        raise ValueError('Cannot animate from no color to color!')
    
    def diff(self, other, weight):
        return Color(self.r*(1-weight)+other.r*weight,
                     self.g*(1-weight)+other.g*weight,
                     self.b*(1-weight)+other.b*weight)
    
    def make(self):
        return tca.HashToken(0, 0, format(self.r, 'x').zfill(2) +
                                   format(self.g, 'x').zfill(2) +
                                   format(self.b, 'x').zfill(2), False)

class Url:
    
    def __init__(self, obj, node):
        self.obj, self.node = obj, node
    
    @staticmethod
    def tokenize(self, token, defs):
        return Url((obj := defs[token.value.lstrip('#')]), Node(obj))
    
    def default(self):
        if self.obj.tag in ('linearGradient', 'radialGradient'):
            raise ValueError('Cannot animate from no gradient to gradient')
        if self.obj.tag == 'filter':
            new = Url((obj := deepcopy(self.obj)), Node(obj))
            for element in new.obj.findall('feGaussianBlur'):
                element.attrib['stdDeviation'] = '0'
            return new
        raise ValueError(f'Cannot animate whatever this is')
    
    def diff(self, other, weight):
        if self.obj.tag in ('linearGradient', 'radialGradient'):
            return Url(self.obj, self.node.diff(other.node, weight))
        if self.obj.tag == 'filter':
            
            

class Fun:
    
    def __init__(self, token, defs):
        self.name = token.name
        self.args = [parse(x, defs) for x in token.arguments]

class Node:
    
    def __init__(self, node):
        self.name = node.attrib['id']
        self.attrib = {key: parse(el) for key, value in node.attrib.items()
                       if (el := tc2.parse_one_component_value(value)) 
                       in supported}
        self.attrib['transform'] = [parse(x) for x in 
            tc2.parse_component_value_list(node.get('transform', ''))]
        self.style = {rule.name: parse(rule) for rule in 
                      tinycss2.parse_declaration_list(node.get('style', ''))}
    
        
