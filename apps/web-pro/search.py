import urllib.request
import urllib.parse
from html.parser import HTMLParser

class DDGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self.current_tag = None
        self.current_result = {}
        self.in_result_body = False
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self.current_tag = tag
        if tag == 'a' and 'class' in attrs_dict and 'result-url' in attrs_dict['class']:
            self.current_result['url'] = attrs_dict.get('href', '')
        if tag == 'a' and 'class' in attrs_dict and 'result-snippet' in attrs_dict['class']:
            self.in_result_body = True
            
    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self.in_result_body:
            self.current_result['snippet'] = self.current_result.get('snippet', '') + ' ' + text
            
    def handle_endtag(self, tag):
        if tag == 'a' and self.in_result_body:
            self.in_result_body = False
            if 'url' in self.current_result and 'snippet' in self.current_result:
                self.results.append(self.current_result)
                self.current_result = {}

def search(query):
    data = urllib.parse.urlencode({'q': query}).encode('utf-8')
    req = urllib.request.Request('https://lite.duckduckgo.com/lite/', data=data, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            parser = DDGParser()
            parser.feed(html)
            for i, r in enumerate(parser.results[:5]):
                print(f"[{i+1}] {r.get('url', '')}\n    {r.get('snippet', '')}")
    except Exception as e:
        print(f"Error: {e}")

import sys
search(sys.argv[1])
