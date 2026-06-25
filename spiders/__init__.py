from .alicesw import AliceSWSpider, alicesw_bp
from .biquge import BiqigeSpider, biquge_bp

SPIDER_REGISTRY = {}


def register_spider(site_pattern, spider_class):
    SPIDER_REGISTRY[site_pattern] = spider_class


def get_spider(site):
    for pattern, spider_class in SPIDER_REGISTRY.items():
        if pattern in site:
            return spider_class()
    raise ValueError(f"不支持的网站: {site}，目前支持: {list(SPIDER_REGISTRY.keys())}")


register_spider("alicesw.com", AliceSWSpider)
register_spider("alicesw", AliceSWSpider)
register_spider("biquge", BiqigeSpider)
register_spider("tobiquge.com", BiqigeSpider)


def register_blueprints(app):
    app.register_blueprint(alicesw_bp, url_prefix="/api/alicesw")
    app.register_blueprint(biquge_bp, url_prefix="/api/biquge")
