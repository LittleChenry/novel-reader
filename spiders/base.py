import re
from abc import ABC, abstractmethod


class BaseSpider(ABC):

    @staticmethod
    def clean_content(raw_text):
        text = re.sub(r'\u3000{2,}', '\n', raw_text)
        text = re.sub(r'\s*\n\s*', '\n', text)
        text = re.sub(r'\n{2,}', '\n', text)
        parts = text.split('\n')
        cleaned = [p.strip() for p in parts if p.strip()]
        return "\n".join("\u3000\u3000" + p for p in cleaned)

    @abstractmethod
    def fetch_novel_info(self, novel_id):
        pass

    @abstractmethod
    def fetch_chapter_list(self, novel_id):
        pass

    @abstractmethod
    def fetch_chapter_content(self, chapter_url):
        pass
