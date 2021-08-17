import json
import logging 

import requests
import nbformat
from nbconvert.preprocessors import ExecutePreprocessor, CellExecutionError
from nbconvert import HTMLExporter

# from preprocessors import ImageReplacement, RemoveCustomCSS
# from post_processors import remove_box_shadow, insert_target_blank

import re

log = logging.getLogger(__name__)

# preprocess
class Processor(object):
    """Base cell transformer - applies `process_cell` to each cell"""

    def __init__(self, nb):
        self.nb = nb

    def process_cell(self, cell):
        raise NotImplemented

    def finish(self):
        """Optional function to be called after iterations are complete"""
        pass


class RemoveCustomCSS(Processor):
    """Remove the cell that loads custom css if it's present"""

    def __init__(self, nb):
        super(RemoveCustomCSS, self).__init__(nb)
        self.search_text = 'from IPython.core.display import HTML'
        self.found = False
        self.cell_num = 0

    def process_cell(self, cell):
        if not self.found:
            if self.search_text in cell['source']:
                log.debug("Found Custom CSS Cell @ cells[{}]".format(self.cell_num))
                self.found = True
                return
            self.cell_num += 1

    def finish(self):
        """Remove custom css cell if found"""
        if self.found:
            del self.nb['cells'][self.cell_num]
            log.debug("Removed cell #: {} [custom css]".format(self.cell_num))


class ImageReplacement(Processor):
    """Replaces img src attribute with absolute path"""

    def __init__(self, nb, images_url):
        super(ImageReplacement, self).__init__(nb)
        self.images_url = images_url

    def process_cell(self, cell):
        matches = re.findall(r'<img.+src=\"(.+?)\"', cell['source'])
        for m in matches:
            tail = m.split('/')[-1]
            cell['source'] = cell['source'].replace(m, '{}{}'.format(self.images_url, tail))

#post process
def remove_box_shadow(raw_html):
    """Removes box shadow around document by replacing defining class name"""
    container = "#notebook-container"
    log.debug("Found #notebook-container class: {}".format(raw_html.find(container)))

    return raw_html.replace(container, "#doesnotexisthere")


def insert_target_blank(raw_html):
    """Adds 'target=_blank' attribute to all `<a href=...>` links """
    return re.sub('(<a .+?>)', _match_fn, raw_html.encode('utf-8'))


def _match_fn(matchobj):
    """Return original <a href...> with `target='_blank'` inserted"""
    s = matchobj.group(0)
    return '{} target="_blank" {}'.format(s[:2], s[3:])


def fetch_notebook(url):
    """Fetches the notbook from URL"""

    log.info("Fetching URL: {}".format(url))
    resp = requests.get(url)
    return resp


def json_to_nb_format(nb_str):
    """Converts Notebook JSON to python object"""
    nb = nbformat.reads(nb_str, as_version=4)
    return nb


def convert_to_html(nb):
    """Converts notebook dict to HTML with included CSS"""
    exporter = HTMLExporter()
    body, resources = exporter.from_notebook_node(nb)

    return body, resources


def filter_start_end(nb, start_tag=None, end_tag=None):
    """Filter out everything outside of `start_tag` and `end_tag`"""

    # Just return if nothing to filter
    if start_tag is None and end_tag is None:
        return nb

    start_cell_num = 0
    num_cells = end_cell_num = len(nb['cells'])
    for cell_num, cell in enumerate(nb['cells']):
        # Find first occurrence of start_tag
        if start_tag and start_tag in cell['source'] and start_cell_num == 0:
            start_cell_num = cell_num
        # Find first occurrence of end_tag
        if end_tag and end_tag in cell['source'] and end_cell_num == num_cells:
            end_cell_num = cell_num

    if start_tag and start_cell_num == 0:
        log.warning("No cell with start content: {} found".format(start_tag))
    if end_tag and end_cell_num == num_cells:
        log.warning("No cell with start content: {} found".format(end_tag))

    nb['cells'] = nb['cells'][start_cell_num:end_cell_num]
    
    return nb


def preprocess(nb, processors):
    """Applies preprocessor to each cell"""
    gen = (cell for cell in nb['cells'])

    # Run processor on each cell
    for cell in gen:
        for t in processors:
            t.process_cell(cell)
    
    # Run finish on each processor
    for t in processors:
        t.finish()


def postprocess(raw_html):
    """Post-processes raw html"""
    html = remove_box_shadow(raw_html)
    html = insert_target_blank(html)
    return html


def process_nb(url, images_url=None, start=None, end=None):
    """Main method to fetch, process, and return HTML for ipython notebook"""

    # Retrieve nb from URL, conver to python fmt, and filter appropriately
    response = fetch_notebook(url)
    nb = json_to_nb_format(response.text)
    nb = filter_start_end(nb, start, end)

    # Setup pre-processors
    transforms = [RemoveCustomCSS(nb)]
    if images_url:
        transforms.append(ImageReplacement(nb, images_url))

    # Run transformation pipeline
    preprocess(nb, transforms)
    html, resources = convert_to_html(nb)
    html = postprocess(html)

    return html



