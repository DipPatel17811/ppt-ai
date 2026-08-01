"""Shared OOXML helpers: namespaces, qualified names, ordered insertion."""

from __future__ import annotations

from typing import Dict, Optional

from lxml import etree

from pptx.oxml.ns import nsmap as _pptx_nsmap, qn as _pptx_qn

# Additional namespaces beyond what python-pptx registers.
EXTRA_NS: Dict[str, str] = {
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
    "p15": "http://schemas.microsoft.com/office/powerpoint/2012/main",
    "xml": "http://www.w3.org/XML/1998/namespace",
}

NS: Dict[str, str] = {**_pptx_nsmap(), **EXTRA_NS}


def qn(tag: str) -> str:
    """Qualify a ``prefix:local`` tag name with the full namespace URI."""
    return _pptx_qn(tag) if ":" in tag and tag.split(":", 1)[0] in _pptx_nsmap else _pptx_qn(tag)


def _ns_uri(prefix: str) -> str:
    return NS.get(prefix, "")


def qname(prefix: str, local: str) -> str:
    uri = _ns_uri(prefix)
    return f"{{{uri}}}{local}" if uri else local


def find_children(element, prefix: str, local: str):
    """Find direct children with the given (prefix, local) name."""
    uri = _ns_uri(prefix)
    return element.findall(f"{{{uri}}}{local}")


def insert_in_slide_order(slide_element, child) -> None:
    """Insert ``child`` as a direct child of the ``p:sld`` element keeping
    the required schema order: cSld, clrMapOvr, transition, timing, extLst.

    Ordering is enforced by insertion index; the caller passes elements in
    schema order so later inserts slot in before earlier-present siblings.
    """
    tag = etree.QName(child).localname
    order = ["transition", "timing", "extLst"]
    anchor = None
    for sibling in slide_element:
        if etree.QName(sibling).localname in order:
            anchor = sibling
            break
    if anchor is None:
        slide_element.append(child)
    elif tag in order:
        slide_element.insert(list(slide_element).index(anchor), child)
    else:
        slide_element.append(child)


def new_element(prefix: str, local: str, attrs: Optional[Dict[str, str]] = None) -> etree._Element:
    el = etree.Element(qname(prefix, local), nsmap=NS)
    if attrs:
        for k, v in attrs.items():
            el.set(k, v)
    return el
