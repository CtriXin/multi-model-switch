import urllib.request
import urllib.parse
from html.parser import HTMLParser

class DDGHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self.current_result = {}
        self.in_result = False
        self.in_title = False
        self.in_snippet = False
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if tag == 'a' and 'class' in attrs_dict and 'result__url' in attrs_dict['class']:
            self.current_result['url'] = attrs_dict.get('href', '')
            
        if tag == 'h2' and 'class' in attrs_dict and 'result__title' in attrs_dict['class']:
            self.in_title = True
            
        if tag == 'a' and 'class' in attrs_dict and 'result__snippet' in attrs_dict['class']:
            self.in_snippet = True
            
    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
            
        if self.in_title:
            self.current_result['title'] = self.current_result.get('title', '') + ' ' + text
            
        if self.in_snippet:
            self.current_result['snippet'] = self.current_result.get('snippet', '') + ' ' + text
            
    def handle_endtag(self, tag):
        if tag == 'h2' and self.in_title:
            self.in_title = False
            
        if tag == 'a' and self.in_snippet:
            self.in_snippet = False
            if 'url' in self.current_result:
                self.results.append(self.current_result)
                self.current_result = {}

def search(query):
    data = urllib.parse.urlencode({'q': query})
    url = f"https://html.duckduckgo.com/html/?{data}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            parser = DDGHTMLParser()
            parser.feed(html)
            for i, r in enumerate(parser.results[:5]):
                print(f"[{i+1}] {r.get('title', '')}\n    URL: {r.get('url', '')}\n    {r.get('snippet', '')}\n")
    except Exception as e:
        print(f"Error: {e}")

import sys
search(sys.argv[1])
